import typing
import numpy as np
import json
import os
import re
from datetime import datetime, timedelta
from pkg.core import app
from collections import Counter
from plugins.Waifu.cells.text_analyzer import TextAnalyzer
from plugins.Waifu.cells.generator import Generator
from pkg.plugin.context import APIHost
from pkg.provider import entities as llm_entities
from plugins.Waifu.cells.config import ConfigManager


class Memory:

    ap: app.Application
    bot_account_id: int
    def __init__(self, ap: app.Application, launcher_id: str, launcher_type: str):
        self.ap = ap
        self.short_term_memory: typing.List[llm_entities.Message] = []
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

    async def load_config(self, character: str, launcher_id: str, launcher_type: str):
        waifu_config = ConfigManager(f"data/plugins/Waifu/config/waifu", "plugins/Waifu/templates/waifu", launcher_id)
        await waifu_config.load_config(completion=True)

        self.conversation_analysis_flag = waifu_config.data.get("conversation_analysis", True)
        self._thinking_mode_flag = waifu_config.data.get("thinking_mode", True)
        self._short_term_memory_size = waifu_config.data["short_term_memory_size"]
        self._memory_batch_size = waifu_config.data["memory_batch_size"]
        self._retrieve_top_n = waifu_config.data["retrieve_top_n"]
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

        # 提取前top_n个高频词
        for word, freq in term_freq_counter.most_common(top_n):
            tags.append(word)

        # 加入i18n标签
        tags.extend(i18n_list)

        # 若为提取记忆，则将结构返回的related也加入tags
        if len(conversations) <= 1:
            tags.extend(related_list)

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

    async def _tag_and_add_conversations(self):
        if self.short_term_memory:
            summary, tags = await self._tag_conversations(self.short_term_memory[: self._memory_batch_size], True)
            tags.extend(self._generate_time_tags()) # 增加当天时间标签并去重
            tags = list(set(tags))
            if len(self.short_term_memory) > self._memory_batch_size:
                self.short_term_memory = self.short_term_memory[self._memory_batch_size :]
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
        except Exception as e:
            self.ap.logger.error(f"Error saving conversations to file '{self._conversations_file}': {e}")

    def _add_long_term_memory(self, summary: str, tags: typing.List[str]):
        formatted_tags = ", ".join(tags)
        self.ap.logger.info(f"New memories: \nSummary: {summary}\nTags: {formatted_tags}")
        self._long_term_memory.append((summary, tags))
        for tag in tags:
            if tag not in self._tags_index:
                self._tags_index[tag] = len(self._tags_index)

    def _get_tag_vector(self, tags: typing.List[str]) -> np.ndarray:
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

    def _retrieve_related_memories(self, input_tags: typing.List[str]) -> typing.List[str]:
        input_vector = self._get_tag_vector(input_tags)
        similarities = []

        for summary, tags in self._long_term_memory:
            summary_vector = self._get_tag_vector(tags)
            similarity = self._cosine_similarity(input_vector, summary_vector)
            similarities.append((similarity, summary))
            # self.ap.logger.info(f"Similarity: {similarity}, Tags: {tags}")

        similarities.sort(reverse=True, key=lambda x: x[0])
        return [summary for _, summary in similarities[: self._retrieve_top_n]]

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
        return self._retrieve_related_memories(tags)

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
        try:
            with open(self._long_term_memory_file, "w", encoding="utf-8") as file:
                json.dump({"long_term": [{"summary": summary, "tags": tags} for summary, tags in self._long_term_memory], "tags_index": self._tags_index}, file, ensure_ascii=False, indent=4)
        except Exception as e:
            self.ap.logger.error(f"Error saving memory to file '{self._long_term_memory_file}': {e}")

    def _save_short_term_memory_to_file(self):
        try:
            with open(self._short_term_memory_file, "w", encoding="utf-8") as file:
                json.dump([{"role": conv.role, "content": conv.content} for conv in self.short_term_memory], file, ensure_ascii=False, indent=4)
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
