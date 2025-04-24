import typing
import numpy as np
import json
import os
import re
import math
from datetime import datetime, timedelta
from pkg.core import app
from collections import Counter
from plugins.Waifu.cells.text_analyzer import TextAnalyzer
from plugins.Waifu.cells.generator import Generator
from pkg.plugin.context import APIHost
from pkg.provider import entities as llm_entities
from plugins.Waifu.cells.config import ConfigManager


## 多级召回记忆系统
# L0 短期记忆 完整对话 滑动窗口 无指向要求
# L1 会话记忆 0-3天 分钟级时间敏感 低指向
# L2 近期记忆 0-7天 小时级衰减 中低指向
# L3 长期记忆 0-30天 天级衰减 中指向
# L4 归档记忆 30天以上 天级衰减 高指向

class Memory:

    ap: app.Application
    def __init__(self, ap: app.Application, launcher_id: str, launcher_type: str):
        self.ap = ap
        self.short_term_memory: typing.List[llm_entities.Message] = []
        self.bot_account_id = 0
        self.analyze_max_conversations = 9
        self.narrate_max_conversations = 8
        self.value_game_max_conversations = 5
        self.response_min_conversations = 5
        self.response_rate = 0.7
        self.max_thinking_words = 30
        self.max_narrat_words = 30
        self.repeat_trigger = 0
        self.user_name = "user"
        self.assistant_name = "assistant"
        self.conversation_analysis_flag = True
        self._text_analyzer = TextAnalyzer(ap)
        self._launcher_id = launcher_id
        self._launcher_type = launcher_type
        self._generator = Generator(ap)
        self._long_term_memory: typing.List[typing.Tuple[str, typing.List[str]]] = []
        self._tags_index = {}
        self._short_term_memory_size = 100
        self._memory_batch_size = 50
        self._retrieve_top_n = 5
        self._summary_max_tags = 50
        self._long_term_memory_file = f"data/plugins/Waifu/data/memories_{launcher_id}.json"
        self._conversations_file = f"data/plugins/Waifu/data/conversations_{launcher_id}.log"
        self._short_term_memory_file = f"data/plugins/Waifu/data/short_term_memory_{launcher_id}.json"
        self._summarization_mode = False
        self._status_file = ""
        self._thinking_mode_flag = True
        self._already_repeat = set()
        self._load_long_term_memory_from_file()
        self._load_short_term_memory_from_file()
        self._has_preset = True
        self._memories_session = []
        self._memories_session_capacity = 0
        self._memories_recall_once = 5
        self._memory_weight_max = 1.0
        self._memory_decay_rate = 0.95
        self._memory_boost_rate = 0.15
        self._memory_base_growth = 0.2
        self._backoff_timestamp = 1745069038
        # debug info
        self._last_recall_memories = []
        self._last_l1_recall_memories = []
        self._last_l2_recall_memories = []
        self._last_l3_recall_memories = []
        self._last_l4_recall_memories = []

    async def load_config(self, character: str, launcher_id: str, launcher_type: str):
        waifu_config = ConfigManager(f"data/plugins/Waifu/config/waifu", "plugins/Waifu/templates/waifu", launcher_id)
        await waifu_config.load_config(completion=True)

        self.conversation_analysis_flag = waifu_config.data.get("conversation_analysis", True)
        self._thinking_mode_flag = waifu_config.data.get("thinking_mode", True)
        self._short_term_memory_size = waifu_config.data["short_term_memory_size"]
        self._memory_batch_size = waifu_config.data["memory_batch_size"]
        self._retrieve_top_n = waifu_config.data["retrieve_top_n"]
        self._memories_recall_once = waifu_config.data["recall_once"]
        self._memories_session_capacity = waifu_config.data["session_memories_size"]
        self._summary_max_tags = waifu_config.data["summary_max_tags"]
        self._summarization_mode = waifu_config.data.get("summarization_mode", False)

        self.analyze_max_conversations = waifu_config.data.get("analyze_max_conversations", 9)
        self.narrate_max_conversations = waifu_config.data.get("narrat_max_conversations", 8)
        self.value_game_max_conversations = waifu_config.data.get("value_game_max_conversations", 5)
        self.response_min_conversations = waifu_config.data.get("response_min_conversations", 1)
        if self.response_min_conversations < 1:
            self.response_min_conversations = 1 # 最小值为1
        self.response_rate = waifu_config.data.get("response_rate", 0.7)
        self.max_thinking_words = waifu_config.data.get("max_thinking_words", 30)
        self.max_narrat_words = waifu_config.data.get("max_narrat_words", 30)
        self.repeat_trigger = waifu_config.data.get("repeat_trigger", 0)

        if character != "off":
            self._has_preset = True
            self._status_file = f"data/plugins/Waifu/data/{character}_{launcher_id}.json"
            character_config = ConfigManager(f"data/plugins/Waifu/cards/{character}", f"plugins/Waifu/templates/default_{launcher_type}")
            await character_config.load_config(completion=False)
            self.user_name = character_config.data.get("user_name", "用户")
            self.assistant_name = character_config.data.get("assistant_name", "助手")
        else:
            self._has_preset = False

    async def _tag_conversations(self, conversations: typing.List[llm_entities.Message], summary_flag: bool) -> typing.Tuple[str, typing.List[str]]:
        # 生成Tags：
        # 1、短期记忆转换长期记忆时：进行记忆总结
        # 2、对话提取记忆时：直接拼凑末尾对话
        if summary_flag:
            memory = await self._generate_summary(conversations)
        else:
            memory = self.get_last_content(conversations, 10)

        # 使用TexSmart HTTP API生成词频统计并获取i18n信息和related信息
        term_freq_counter, i18n_list, related_list = await self._text_analyzer.term_freq(memory)

        # 从词频统计中提取前N个高频词及其i18n标签作为标签
        top_n = self._summary_max_tags - len(i18n_list)
        tags = []

        # # 提取前top_n个高频词
        for word, freq in term_freq_counter.most_common(top_n):
            tags.append(word)

        # 加入i18n标签
        tags.extend(i18n_list)

        # 污染太严重，导致召回准确率不高
        # 若为提取记忆，则将结构返回的related也加入tags
        # if len(conversations) <= 1:
        #     tags.extend(related_list)

        return memory, tags

    async def _generate_summary(self, conversations: typing.List[llm_entities.Message]) -> str:
        user_prompt_summary = ""
        if self._launcher_type == "person":
            _, conversations_str = self.get_conversations_str_for_person(conversations)
            user_prompt_summary = f"""总结以下对话中的最重要细节和事件: "{conversations_str}"。将总结限制在200字以内。总结应使用中文书写，并以过去式书写。你的回答应仅包含总结。"""
        else:
            conversations_str = self.get_conversations_str_for_group(conversations)
            user_prompt_summary = f"""总结以下对话中的最重要细节和事件: "{conversations_str}"。将总结限制在200字以内。总结应使用中文书写，其中@{self.bot_account_id}为对你说的话，或对你的动作，并以过去式书写。你的回答应仅包含总结。"""

        return await self._generator.return_string(user_prompt_summary)

    def current_time_str(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def get_time_form_str(self, time_str: str) -> datetime:
        return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")

    async def _tag_and_add_conversations(self):
        if self.short_term_memory:
            summary, tags = await self._tag_conversations(self.short_term_memory[: self._memory_batch_size], True)
            tags.extend(self._generate_time_tags()) # 增加当天时间标签并去重
            tags = list(set(tags))
            if len(self.short_term_memory) > self._memory_batch_size:
                self.short_term_memory = self.short_term_memory[self._memory_batch_size :]
            tags.append("DATETIME: " + self.current_time_str())
            self._add_long_term_memory(summary, tags)
            self._save_long_term_memory_to_file()
            self._save_short_term_memory_to_file()

    def _generate_time_tags(self) -> typing.List[str]:
        now = datetime.now()

        period = "上午"
        if now.hour >= 12:
            period = "下午"

        year_tag = f"{now.year}年"
        month_tag = f"{now.month}月"
        day_tag = f"{now.day}日"
        period_tag = period

        return [year_tag, month_tag, day_tag, period_tag]

    def _extract_time_and_add_tags(self, message: typing.Union[str, object]) -> typing.List[str]:
        """
            提取 message_content 中的时间戳，并添加相应的时间标签。

            已匹配过的关键词不能再次匹配，字数多的关键词优先。
            匹配后从句子中删除已匹配的文字。
            """
        ct = str(message.get_content_platform_message_chain())
        time_pattern = r"\[(\d{2}年\d{2}月\d{2}日(?:上午|下午)?\d{2}时\d{2}分)\]"
        matches = re.findall(time_pattern, ct)

        if not matches:
            return []

        now = self._parse_chinese_time(matches[0])
        time_tags = []

        # 处理日期关键词
        relative_days = {"大后天": 3, "后天": 2, "明天": 1, "今天": 0,
                            "昨天": -1, "前天": -2, "大前天": -3}
        for day_str, offset in sorted(relative_days.items(), key=lambda x: -len(x[0])):
            if day_str in ct:
                target_date = now + timedelta(days=offset)
                time_tags += [f"{target_date.year}年", f"{target_date.month}月", f"{target_date.day}日"]
                ct = ct.replace(day_str, "", 1)

        # 处理本周、上周、下周和扩展周期
        week_prefixes = {"上上": -14, "上": -7, "": 0, "这": 0, "本": 0, "下": 7, "下下": 14}
        weekdays = {"周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5, "周日": 6}
        for prefix, week_offset in sorted(week_prefixes.items(), key=lambda x: -len(x[0])):
            for weekday_str, weekday_offset in weekdays.items():
                week_str = f"{prefix}{weekday_str}"
                if week_str in ct:
                    start_of_week = now - timedelta(days=now.weekday())
                    target_date = start_of_week + timedelta(days=week_offset + weekday_offset)
                    time_tags += [f"{target_date.year}年", f"{target_date.month}月", f"{target_date.day}日"]
                    ct = ct.replace(week_str, "", 1)

        # 完整周添加 (e.g., 下周 = 添加下周一至下周日)
        for prefix, week_offset in sorted(week_prefixes.items(), key=lambda x: -len(x[0])):
            week_str = f"{prefix}周"
            if week_str in ct and prefix: # 跳过仅“周”字避免误触
                start_of_week = now - timedelta(days=now.weekday())
                target_week_start = start_of_week + timedelta(days=week_offset)
                for weekday_offset in range(7):
                    target_date = target_week_start + timedelta(days=weekday_offset)
                    time_tags += [f"{target_date.year}年", f"{target_date.month}月", f"{target_date.day}日"]
                ct = ct.replace(week_str, "", 1)

        # 处理本月、上一个月、下一个月
        month_keywords = {"本月": 0, "上月": -1, "下月": 1, "上个月": -1, "下个月": 1}
        for month_str, offset in sorted(month_keywords.items(), key=lambda x: -len(x[0])):
            if month_str in ct:
                target_month = now.replace(day=1) + timedelta(days=30 * offset)
                time_tags += [f"{target_month.year}年", f"{target_month.month}月"]
                ct = ct.replace(month_str, "", 1)

        # 处理今年、明年、后年、前年
        year_keywords = {"今年": 0, "明年": 1, "后年": 2, "前年": -2}
        for year_str, offset in sorted(year_keywords.items(), key=lambda x: -len(x[0])):
            if year_str in ct:
                target_year = now.replace(year=now.year + offset, month=1, day=1)
                time_tags = [f"{target_year.year}年"]
                ct = ct.replace(year_str, "", 1)

        # 处理时段关键词
        time_period_keywords = {"上午": ["早上", "清晨", "上午"], "下午": ["晚上", "傍晚", "下午"]}
        for tag, keywords in time_period_keywords.items():
            for keyword in sorted(keywords, key=lambda x: -len(x)):
                if keyword in ct:
                    time_tags += [tag]
                    ct = ct.replace(keyword, "", 1)

        return time_tags

    def _parse_chinese_time(self, time_str) -> datetime:
        # 判断是否为下午
        is_afternoon = "下午" in time_str

        # 移除汉字 "年"、"月"、"日"、"上午"、"下午"、"时"、"分"
        pattern = r"[年月日时分上下午]"
        time_cleaned = re.sub(pattern, "", time_str)
        time_cleaned = f"20{time_cleaned}"  # 补全年份

        # 转换为 datetime 对象
        dt = datetime.strptime(time_cleaned, "%Y%m%d%H%M")

        # 如果是下午且小时小于12，需加12小时
        if is_afternoon and dt.hour < 12:
            dt = dt.replace(hour=dt.hour + 12)

        return dt

    def _save_conversations_to_file(self, conversations: typing.List[llm_entities.Message]):
        try:
            with open(self._conversations_file, "a", encoding="utf-8") as file:
                for conv in conversations:
                    file.write(conv.readable_str() + "\n")
                file.flush()
        except Exception as e:
            self.ap.logger.error(f"Error saving conversations to file '{self._conversations_file}': {e}")

    def _add_long_term_memory(self, summary: str, tags: typing.List[str]):
        formatted_tags = ", ".join(tags)
        self.ap.logger.info(f"New memories: \nSummary: {summary}\nTags: {formatted_tags}")
        self._long_term_memory.append((summary, tags))
        for tag in tags:
            if tag not in self._tags_index:
                self._tags_index[tag] = len(self._tags_index)

    def _extract_time_tag(self, tags: typing.List[str]) -> tuple[int, str]:
        for i in range(len(tags)):
            if tags[i].startswith("DATETIME: "):
                time_tags = tags[i].replace("DATETIME: ", "")
                return (i, time_tags)
        return (-1,"")

    def _extract_priority_tags(self, tags: typing.List[str]) -> tuple[int, str]:
        for i in range(len(tags)):
            if tags[i].startswith("PRIORITY: "):
                priority_tags = tags[i].replace("PRIORITY: ", "")
                return (i, priority_tags)
        return (-1,"")

    def _get_real_tags(self, tags: typing.List[str]) -> typing.List[str]:
        tags = tags.copy()
        (time_index,_) = self._extract_time_tag(tags)
        if time_index != -1:
            tags.pop(time_index)
        (priority_index,_) = self._extract_priority_tags(tags)
        if priority_index != -1:
            tags.pop(priority_index)
        return tags

    def _get_tag_vector(self, tags: typing.List[str]) -> np.ndarray:
        tags = self._get_real_tags(tags)

        vector = np.zeros(len(self._tags_index))
        for tag in tags:
            if tag in self._tags_index:
                vector[self._tags_index[tag]] = 1
        return vector

    def _cosine_similarity(self, vector_a: np.ndarray, vector_b: np.ndarray) -> float:
        dot_product = np.dot(vector_a, vector_b)
        norm_a = np.linalg.norm(vector_a)
        norm_b = np.linalg.norm(vector_b)
        return 0.0 if norm_a == 0 or norm_b == 0 else dot_product / (norm_a * norm_b)

    def _get_event_seq_of_memory(self, memory: str) -> int:
        for i in range(len(self._long_term_memory)):
            if self._long_term_memory[i][0] == memory:
                return i
        return len(self._long_term_memory)

    def get_last_recall_memories(self) -> str:
        memories = []
        for summary,weight in self._last_recall_memories:
            memories.append(f"权重：{weight:.2f} 记忆：{summary}")
        return "\n\n".join(memories)

    def get_last_l1_recall_memories(self) -> str:
        memories = []
        for weight, similarity, summary in self._last_l1_recall_memories:
            memories.append(f"L1权重：{weight:.2f} 相似度：{similarity:.2f} 记忆：{summary}")
        msg = "\n\n".join(memories)
        self.ap.logger.info(f"召回L1记忆：\n\n{msg}")
        return "已打印"

    def get_last_l2_recall_memories(self) -> str:
        memories = []
        for weight,jaccard, similarity, summary in self._last_l2_recall_memories:
            memories.append(f"L2权重：{weight:.2f} Jaccard: {jaccard:.2f} 相似度：{similarity:.2f} 记忆：{summary}")
        msg = "\n\n".join(memories)
        self.ap.logger.info(f"召回L2记忆：\n\n{msg}")
        return "已打印"

    def get_last_l3_recall_memories(self) -> str:
        memories = []
        for weight, jaccard, similarity, summary in self._last_l3_recall_memories:
            memories.append(f"L3权重：{weight:.2f} Jaccard: {jaccard:.2f} 相似度：{similarity:.2f} 记忆：{summary}")
        msg = "\n\n".join(memories)
        self.ap.logger.info(f"召回L3记忆：\n\n{msg}")
        return "已打印"

    def get_last_l4_recall_memories(self) -> str:
        memories = []
        for weight, similarity, summary in self._last_l4_recall_memories:
            memories.append(f"L4权重：{weight:.2f} 相似度：{similarity:.2f} 记忆：{summary}")
        msg = "\n\n".join(memories)
        self.ap.logger.info(f"召回L4记忆：\n\n{msg}")
        return "已打印"

    def _detect_query_type(self, tags: typing.List[str]) -> str:
        """查询类型检测"""
        time_indicators = {'今天','昨天','上午','下午','傍晚','晚上','早上','清晨','凌晨'}
        scene_markers = {'当时','那时'}
        just_right_now_indicators = {'之前','以前','刚刚'}

        if any(m in tags for m in scene_markers):
            return 'high_scene'
        elif any(t in tags for t in time_indicators):
            return 'low_time'
        elif any(j in tags for j in just_right_now_indicators):
            return 'low_general'
        else:
            return 'general'

    def _retrieve_related_l1_memories(self, input_tags: typing.List[str]) -> typing.List[tuple[float, typing.List[str]]]:
        self.ap.logger.info(f"开始L1记忆召回 Tags: {', '.join(input_tags)}")
        current_time = datetime.now()
        input_vector = self._get_tag_vector(input_tags)
        l1_memories = []
        self._last_l1_recall_memories = []

        # L1配置（0-3天）
        DECAY_RATE_PER_MIN = 0.0005
        SIMILARITY_THRESHOLD = 0.22
        MAX_DAYS = 3
        TIME_WEIGHT_POWER = 1.3

        for summary, tags in self._long_term_memory:
            # 提取元标签
            (_,time_tags) = self._extract_time_tag(tags)
            summary_time = datetime.fromtimestamp(self._backoff_timestamp)
            if time_tags != "":
                summary_time = self.get_time_form_str(time_tags)
            else:
                time_tags = summary_time.strftime("%Y-%m-%d %H:%M:%S")

            # 严格时间过滤
            delta_days = (current_time - summary_time).days
            if delta_days > MAX_DAYS:
                continue

            # 时间敏感度检测
            query_type = self._detect_query_type(input_tags)
            time_boost = 1.6 if 'time' in query_type else 1.0

            # 计算权重
            delta_min = (current_time - summary_time).total_seconds() / 60
            time_weight = math.exp(-DECAY_RATE_PER_MIN * delta_min) ** TIME_WEIGHT_POWER
            similarity = self._cosine_similarity(input_vector, self._get_tag_vector(tags))
            weight = similarity * time_weight * time_boost

            self._last_l1_recall_memories.append((weight, similarity, summary[:40]))

            # 动态准入
            dynamic_th = SIMILARITY_THRESHOLD * (0.8 if 'time' in query_type else 1.2)
            if weight > dynamic_th:
                l1_memories.append((weight, summary))

        l1_memories.sort(reverse=True, key=lambda x: x[0])
        return l1_memories[: self._memories_recall_once]

    def _retrieve_related_l2_memories(self, input_tags: typing.List[str]) -> typing.List[tuple[float, str]]:
        self.ap.logger.info(f"开始L2记忆召回 Tags: {', '.join(input_tags)}")
        current_time = datetime.now()
        input_vector = self._get_tag_vector(input_tags)
        l2_memories = []

        # L2配置（3-7天）
        TIME_DECAY_RATE = 0.0001  # 小时级衰减
        SIMILARITY_THRESHOLD = 0.12
        MIN_DAYS, MAX_DAYS = 2.4, 7
        TOPIC_WEIGHT = 0.5

        for summary, tags in self._long_term_memory:
            # 提取元标签
            (_,time_tags) = self._extract_time_tag(tags)
            summary_time = datetime.fromtimestamp(self._backoff_timestamp)
            if time_tags != "":
                summary_time = self.get_time_form_str(time_tags)
            else:
                time_tags = summary_time.strftime("%Y-%m-%d %H:%M:%S")

            delta_days = (current_time - summary_time).days
            if not (MIN_DAYS <= delta_days <= MAX_DAYS):
                continue

            # 主题关联计算
            real_tags = self._get_real_tags(tags)
            input_set = set(input_tags)
            mem_tags = set(real_tags)
            intersection = input_set & mem_tags
            union = input_set | mem_tags
            jaccard = len(intersection)/len(union) if union else 0

            # 权重计算
            delta_hours = (current_time - summary_time).total_seconds() / 3600
            time_weight = math.exp(-TIME_DECAY_RATE * delta_hours)
            similarity = self._cosine_similarity(input_vector, self._get_tag_vector(tags))

            weight = similarity * time_weight * (0.5 + TOPIC_WEIGHT * jaccard)

            self._last_l2_recall_memories.append((weight,jaccard, similarity, summary[:40]))

            # 分级准入
            if weight >= SIMILARITY_THRESHOLD or (jaccard >= 0.02 and similarity >= 0.12):
                l2_memories.append((weight, summary))

        l2_memories.sort(reverse=True, key=lambda x: x[0])
        return l2_memories[: self._memories_recall_once]

    def _retrieve_related_l3_memories(self, input_tags: typing.List[str]) -> typing.List[tuple[float, str]]:
        self.ap.logger.info(f"开始L3记忆召回 Tags: {', '.join(input_tags)}")
        current_time = datetime.now()
        input_vector = self._get_tag_vector(input_tags)
        l3_memories = []

        # L3配置（7-30天）
        DECAY_RATE = 0.00015  # 天级衰减
        SIMILARITY_THRESHOLD = 0.15
        MIN_DAYS, MAX_DAYS = 5.6, 30
        JACCARD_FLOOR = 0.03  # 最低标签匹配

        for summary, tags in self._long_term_memory:
            # 提取元标签
            (_,time_tags) = self._extract_time_tag(tags)
            summary_time = datetime.fromtimestamp(self._backoff_timestamp)
            if time_tags != "":
                summary_time = self.get_time_form_str(time_tags)
            else:
                time_tags = summary_time.strftime("%Y-%m-%d %H:%M:%S")

            delta_days = (current_time - summary_time).days
            if not (MIN_DAYS <= delta_days <= MAX_DAYS):
                continue

            # 混合匹配计算
            mem_tags = set(self._get_real_tags(tags))
            input_set = set(input_tags)
            jaccard = len(input_set & mem_tags) / len(input_set | mem_tags) if input_set else 0

            similarity = self._cosine_similarity(input_vector, self._get_tag_vector(tags))
            time_weight = math.exp(-DECAY_RATE * delta_days)
            weight = (similarity * 0.7 + jaccard * 0.3) * time_weight

            self._last_l3_recall_memories.append((weight, jaccard, similarity, summary[:40]))

            # 准入规则
            if weight >= SIMILARITY_THRESHOLD and jaccard >= JACCARD_FLOOR:
                l3_memories.append((weight, summary))

        l3_memories.sort(reverse=True, key=lambda x: x[0])
        return l3_memories[: self._memories_recall_once]

    def _retrieve_related_l4_memories(self, input_tags: typing.List[str]) -> typing.List[tuple[float, str]]:
        self.ap.logger.info(f"开始L4记忆召回 Tags: {', '.join(input_tags)}")
        current_time = datetime.now()
        input_vector = self._get_tag_vector(input_tags)
        l4_memories = []

        # L4配置（30天+）
        DECAY_RATE = 0.00002  # 超低衰减率
        EMERGENCY_THRESHOLD = 0.4
        SIMILARITY_THRESHOLD = 0.12
        MIN_DAYS = 24

        for summary, tags in self._long_term_memory:
            # 提取元标签
            (_,time_tags) = self._extract_time_tag(tags)
            summary_time = datetime.fromtimestamp(self._backoff_timestamp)
            if time_tags != "":
                summary_time = self.get_time_form_str(time_tags)
            else:
                time_tags = summary_time.strftime("%Y-%m-%d %H:%M:%S")

            delta_days = (current_time - summary_time).days
            if delta_days < MIN_DAYS:
                continue

            # 纯语义匹配
            similarity = self._cosine_similarity(input_vector, self._get_tag_vector(tags))
            time_weight = math.exp(-DECAY_RATE * delta_days)
            weight = similarity * time_weight

            self._last_l4_recall_memories.append((weight, similarity, summary[:40]))

            # 紧急通道 + 正常准入
            if weight >= SIMILARITY_THRESHOLD or similarity >= EMERGENCY_THRESHOLD:
                l4_memories.append((weight, summary))

        l4_memories.sort(reverse=True, key=lambda x: x[0])
        return l4_memories[: self._memories_recall_once]


    def _update_memories_session(self, new_memories: list):
        """更新记忆池"""
        good_memory_weight = 0.3
        mid_memory_weight = 0.2

        # 步骤1：衰减旧记忆权重
        for mem, old_score in self._memories_session:
            # 根据记忆质量调整衰减率
            decay_rate = 0.85
            if old_score > 0.4:
                decay_rate = 0.9
            new_score = old_score * decay_rate

        # 步骤2：计算动态增量
        updated = {}
        for mem, old_score in self._memories_session:
            if mem in [k for k in new_memories]:
                similarity = new_memories[mem]
                # 计算剩余增长空间
                headroom = self._memory_weight_max - old_score
                # 动态增长率 = 基础因子 × 剩余空间的平方占比
                base_growth = self._memory_base_growth * (1 + similarity * 0.5)
                growth_rate = base_growth * (headroom ** 1.5 / self._memory_weight_max)
                new_score = old_score + growth_rate
                updated[mem] = min(new_score,1.0)

        # 步骤3：合并新记忆
        for mem,weight in new_memories:
            if mem in updated:
                continue
            quality_factor = 0.8
            if weight > good_memory_weight:
                quality_factor = 1.8
            elif weight > mid_memory_weight:
                quality_factor = 1.4

            init_score = min(weight * quality_factor, self._memory_weight_max)  # 设置上限
            updated[mem] = init_score

        # 步骤4：排序保留TopN
        sorted_mem = sorted(updated.items(), key=lambda x: -x[1])
        sorted_mem = sorted_mem[:self._memories_session_capacity]
        # 在排序后添加淘汰逻辑
        sorted_mem = [
            (mem, score) for mem, score in sorted_mem
            if score > 0.15
        ]
        self._memories_session = sorted_mem.copy()

        # 调试日志
        self.ap.logger.info(f"记忆池更新完成，当前内容：{self._memories_session}")

    def get_latest_memory(self) -> str:
        """获取最新记忆"""
        if len(self._long_term_memory) > 0:
            latest = self._long_term_memory[-1][0]
            return latest
        return ""

    def _get_memories_session(self) -> typing.List[str]:
        """获取当前记忆池"""
        memories = [mem for mem, _ in self._memories_session]
        if len(self._long_term_memory) > 0:
            latest = self.get_latest_memory()
            for i in range(len(memories)):
                if memories[i] == latest:
                    memories[i] = f"最近的记忆： {latest}"
                    break
        return memories

    def get_memories_session(self) -> str:
        """获取当前记忆池"""
        memories = []
        for mem, score in self._memories_session:
            memories.append(f"记忆：{mem} 权重：{score:.2f}")
        return "\n\n".join(memories)

    def _retrieve_related_memories(self, input_tags: typing.List[str]) -> typing.List[str]:
        self.ap.logger.info(f"开始多级记忆召回 Tags: {', '.join(input_tags)}")

        # 获取各层记忆结果（带权重）
        l1_results =[]
        l2_results = []
        l3_results = []
        l4_results = []

        recall_threshold = self._memories_recall_once * 1.2
        current_recall_count = 0

        l1_results = self._retrieve_related_l1_memories(input_tags)
        current_recall_count += len(l1_results)

        if current_recall_count < recall_threshold:
            l2_results = self._retrieve_related_l2_memories(input_tags)
            current_recall_count += len(l2_results)

        if current_recall_count < recall_threshold:
            l3_results = self._retrieve_related_l3_memories(input_tags)
            current_recall_count += len(l3_results)

        if current_recall_count < recall_threshold:
            l4_results = self._retrieve_related_l4_memories(input_tags)
            current_recall_count += len(l4_results)

        # 构建带权记忆池
        weighted_memories = []

        # 处理L4记忆
        for weight, summary in l4_results:
            final_weight = weight
            weighted_memories.append((final_weight , summary))

        # 处理L3记忆
        for weight, summary in l3_results:
            final_weight = weight
            weighted_memories.append((final_weight , summary))

        # 处理L2记忆
        for weight, summary in l2_results:
            final_weight = weight
            weighted_memories.append((final_weight, summary))

        # 处理L1记忆
        for weight, summary in l1_results:
            final_weight = weight
            weighted_memories.append((final_weight, summary))

        # 记忆去重（保留最高权重）
        memory_dict = {}
        for weight, mem in weighted_memories:
            if mem not in memory_dict or weight > memory_dict[mem]:
                memory_dict[mem] = weight

        # 按最终权重排序
        sorted_memories = sorted(memory_dict.items(), key=lambda x: x[1], reverse=True)
        self.ap.logger.info(f"加权合并完成，共召回{len(sorted_memories)}条记忆")

        # 截取前N个结果
        self._last_recall_memories = sorted_memories[:self._memories_recall_once]
        result = [mem for mem, _ in sorted_memories[:self._memories_recall_once]]
        for mem in result:
            self.ap.logger.info(f"召回记忆: {mem}")
        self.ap.logger.info(f"召回并选择了{len(result)}条记忆")

        # 更新记忆池
        self._update_memories_session(sorted_memories[:self._memories_recall_once])
        memories = self._get_memories_session()
        return memories[: self._retrieve_top_n]

    async def save_memory(self, role: str, content: str):
        time = self._generator.get_chinese_current_time()
        conversation = llm_entities.Message(role=role, content=f"[{time}]{content}")
        self.short_term_memory.append(conversation)
        self._save_short_term_memory_to_file()
        self._save_conversations_to_file([conversation])

        if len(self.short_term_memory) >= self._short_term_memory_size:
            if self._summarization_mode:
                await self._tag_and_add_conversations()
            else:
                self.short_term_memory = self.short_term_memory[-self._short_term_memory_size :]

    async def remove_last_memory(self) -> str:
        if self.short_term_memory:
            last_conversation = self.short_term_memory.pop().get_content_platform_message_chain()
            self._save_short_term_memory_to_file()
            return last_conversation

    async def load_memory(self, conversations: typing.List[llm_entities.Message]) -> typing.List[str]:
        if not self._long_term_memory:
            return []
        _, tags = await self._tag_conversations(conversations, False)
        for message in conversations:
            tags.extend(self._extract_time_and_add_tags(message))  # 增加时间相关标签并去重
        tags = list(set(tags))
        formatted_tags = ", ".join(tags)
        self.ap.logger.info(f"记忆加载中 Tags: {formatted_tags}")
        memories = self._retrieve_related_memories(tags)
        return memories

    def get_all_memories(self) -> str:
        memories_str = [conv.readable_str() for conv in self.short_term_memory]
        for summary, tags in self._long_term_memory:
            memory_str = f"Summary: {summary}\nTags: {', '.join(tags)}"
            memories_str.append(memory_str)
        return "\n\n".join(memories_str)

    def delete_local_files(self):
        files_to_delete = [
            self._long_term_memory_file,
            self._conversations_file,
            self._short_term_memory_file,
            self._status_file,
            f"data/plugins/Waifu/data/life_{self._launcher_id}.json",
        ]

        for file in files_to_delete:
            if os.path.exists(file):
                os.remove(file)
                self.ap.logger.info(f"Deleted {file}")
            else:
                self.ap.logger.info(f"File {file} does not exist")

        self.short_term_memory.clear()
        self._long_term_memory.clear()
        self.ap.logger.info("Cleared short-term and long-term memories")

    def _save_long_term_memory_to_file(self):
        tmpFile = "{}.tmp".format(self._long_term_memory_file)
        try:
            with open(tmpFile, "w", encoding="utf-8") as file:
                json.dump({"long_term": [{"summary": summary, "tags": tags} for summary, tags in self._long_term_memory], "tags_index": self._tags_index}, file, ensure_ascii=False, indent=4)
                file.flush()
                os.replace(tmpFile, self._long_term_memory_file)
        except Exception as e:
            self.ap.logger.error(f"Error saving memory to file '{self._long_term_memory_file}': {e}")

    def _save_short_term_memory_to_file(self):
        tmpFile = "{}.tmp".format(self._short_term_memory_file)
        try:
            with open(tmpFile, "w", encoding="utf-8") as file:
                json.dump([{"role": conv.role, "content": conv.content} for conv in self.short_term_memory], file, ensure_ascii=False, indent=4)
                file.flush()
                os.replace(tmpFile, self._short_term_memory_file)
        except Exception as e:
            self.ap.logger.error(f"Error saving memory to file '{self._short_term_memory_file}': {e}")

    def _load_long_term_memory_from_file(self):
        try:
            with open(self._long_term_memory_file, "r", encoding="utf-8") as file:
                file_content = file.read()
                if not file_content.strip():
                    self.ap.logger.warning(f"Memory file '{self._long_term_memory_file}' is empty. Starting with empty memory.")
                    return

                data = json.loads(file_content)
                self._long_term_memory = [(item["summary"], item["tags"]) for item in data["long_term"]]
                self._tags_index = data["tags_index"]
        except FileNotFoundError:
            self.ap.logger.warning(f"Memory file '{self._long_term_memory_file}' not found. Starting with empty memory.")
        except json.JSONDecodeError as e:
            self.ap.logger.error(f"Error decoding JSON from memory file '{self._long_term_memory_file}': {e}. Starting with empty memory.")
        except Exception as e:
            self.ap.logger.error(f"Unexpected error loading memory file '{self._long_term_memory_file}': {e}")

    def _load_short_term_memory_from_file(self):
        try:
            with open(self._short_term_memory_file, "r", encoding="utf-8") as file:
                file_content = file.read()
                if not file_content.strip():
                    self.ap.logger.warning(f"Cache file '{self._short_term_memory_file}' is empty. Starting with empty memory.")
                    return
                data = json.loads(file_content)
                self.short_term_memory = [llm_entities.Message(role=item["role"], content=item["content"]) for item in data]
        except FileNotFoundError:
            self.ap.logger.warning(f"Cache file '{self._short_term_memory_file}' not found. Starting with empty memory.")
        except json.JSONDecodeError as e:
            self.ap.logger.error(f"Error decoding JSON from memory file '{self._short_term_memory_file}': {e}. Starting with empty memory.")
        except Exception as e:
            self.ap.logger.error(f"Unexpected error loading memory file '{self._short_term_memory_file}': {e}")

    def get_conversations_str_for_person(self, conversations: typing.List[llm_entities.Message]) -> typing.Tuple[typing.List[str], str]:
        speakers = []
        conversations_str = ""
        listener = self.assistant_name
        date_time_pattern = re.compile(r"\[\d{2}年\d{2}月\d{2}日(上午|下午)?\d{2}时\d{2}分\]")

        for message in conversations:
            role = self.to_custom_names(message.role)
            content = str(message.get_content_platform_message_chain())

            # 提取并移除日期时间信息
            date_time_match = date_time_pattern.search(content)
            if date_time_match:
                date_time_str = date_time_match.group(0)
                content = content.replace(date_time_str, "").strip()
            else:
                date_time_str = ""

            if role == "narrator":
                conversations_str += f"{self.to_custom_names(content)}"
            else:
                if speakers:
                    if role != speakers[-1]:
                        listener = speakers[-1]
                elif role == self.assistant_name:
                    listener = self.user_name
                conversations_str += f"{date_time_str}{role}对{listener}说：“{content}”。"
                if role in speakers:
                    speakers.remove(role)
                speakers.append(role)
        return speakers, conversations_str

    def get_conversations_str_for_group(self, conversations: typing.List[llm_entities.Message]) -> str:
        conversations_str = ""
        date_time_pattern = re.compile(r"\[\d{2}年\d{2}月\d{2}日(上午|下午)?\d{2}时\d{2}分\]")

        for message in conversations:
            role = message.role
            if role == "assistant":
                role = "你"

            content = str(message.get_content_platform_message_chain())
            date_time_match = date_time_pattern.search(content)

            if date_time_match:
                date_time_str = date_time_match.group(0)
                content = content.replace(date_time_str, "").strip()
            else:
                date_time_str = ""

            conversations_str += f"{date_time_str}{role}说：“{content}”。"

        return conversations_str

    def get_unreplied_msg(self, unreplied_count: int) -> typing.Tuple[int, typing.List[llm_entities.Message]]:
        count = 0  # 未回复的数量 + 穿插的自己发言的数量 用以正确区分 replied 及 unreplied 分界线
        messages = []
        for message in reversed(self.short_term_memory):
            count += 1
            if message.role != "assistant":
                messages.insert(0, message)
                if len(messages) >= unreplied_count:
                    return count, messages
        return count, messages

    def get_last_speaker(self, conversations: typing.List[llm_entities.Message]) -> str:
        for message in reversed(conversations):
            if message.role not in {"narrator", "assistant"}:
                return self.to_custom_names(message.role)
        return ""

    def get_last_role(self, conversations: typing.List[llm_entities.Message]) -> str:
        return self.to_custom_names(conversations[-1].role) if conversations else ""

    def get_last_content(self, conversations: typing.List[llm_entities.Message], n: int = 1) -> str:
        if not conversations:
            return ""

        last_messages = conversations[-n:] if n <= len(conversations) else conversations
        combined_content = ""
        for message in last_messages:
            combined_content += self._generator.get_content_str_without_timestamp(message) + " "

        return combined_content.strip()

    def get_normalize_short_term_memory(self) -> typing.List[llm_entities.Message]:
        """
        将非默认角色改为user、合并user发言、保证user在assistant前
        """
        support_list = ["assistant", "user", "system", "tool", "command", "plugin"]
        normalized = []
        user_buffer = ""
        found_user = False

        for message in self.short_term_memory:
            role = message.role
            content = self._generator.get_content_str_without_timestamp(message)

            if role not in support_list:
                role = "user"  # 非思维链模式不支援特殊role

            if role == "user":
                found_user = True
                if not user_buffer:
                    user_buffer = content
                else:
                    user_buffer += " " + content
            elif found_user:
                if user_buffer:
                    normalized.append(llm_entities.Message(role="user", content=user_buffer.strip()))
                    user_buffer = ""
                normalized.append(llm_entities.Message(role=role, content=content))

        if user_buffer:
            normalized.append(llm_entities.Message(role="user", content=user_buffer.strip()))

        return normalized

    def get_repeat_msg(self) -> str:
        """
        检查短期记忆范围内的重复发言，若assistant没有复读过，则进行复读。
        """
        if self.repeat_trigger < 1: # 未开启复读功能
            return ""

        conversations = self.short_term_memory
        content_counter = Counter()
        potential_repeats = []

        for message in conversations:
            message_content = self._generator.get_content_str_without_timestamp(message)
            if message.role == "assistant":
                self._already_repeat.add(message_content)
            content_counter[message_content] += 1
            if content_counter[message_content] > self.repeat_trigger:
                # 更新复读条目的顺序，用于判断最新的复读
                if message_content in potential_repeats:
                    potential_repeats.remove(message_content)
                potential_repeats.append(message_content)
        repeat_messages = [msg for msg in potential_repeats if msg not in self._already_repeat]
        self._already_repeat.update(repeat_messages)  # 若有多条重复，只会跟读最新一种，其他则舍弃

        if repeat_messages:
            return repeat_messages[-1]
        else:
            return ""

    def to_custom_names(self, text: str) -> str:
        if not self._has_preset:
            return text
        text = re.sub(r"user", self.user_name, text, flags=re.IGNORECASE)
        text = re.sub(r"用户", self.user_name, text, flags=re.IGNORECASE)
        text = re.sub(r"assistant", self.assistant_name, text, flags=re.IGNORECASE)
        text = re.sub(r"助理", self.assistant_name, text, flags=re.IGNORECASE)
        return text

    def to_generic_names(self, text: str) -> str:
        if not self._has_preset:
            return text
        text = re.sub(self.user_name, "user", text, flags=re.IGNORECASE)
        text = re.sub(r"用户", "user", text, flags=re.IGNORECASE)
        text = re.sub(self.assistant_name, "assistant", text, flags=re.IGNORECASE)
        text = re.sub(r"助理", "assistant", text, flags=re.IGNORECASE)
        return text

    def set_jail_break(self, type: str, user_name: str):
        self._generator.set_jail_break(type, user_name)

