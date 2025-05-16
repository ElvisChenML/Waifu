import typing
import numpy as np
import json
import os
import re
import math
from datetime import datetime, timedelta
from pkg.core import app
from collections import Counter,defaultdict
from plugins.Waifu.cells.text_analyzer import TextAnalyzer
from plugins.Waifu.cells.generator import Generator
from pkg.plugin.context import APIHost
from pkg.provider import entities as llm_entities
from plugins.Waifu.cells.config import ConfigManager
from plugins.Waifu.organs.memory_item import MemoryItem
from plugins.Waifu.organs.lru_cache import LRUCache
from plugins.Waifu.organs.memory_graph import MemoryGraph


class Memory:

    ap: app.Application
    _short_term_memory: typing.List[llm_entities.Message]
    bot_account_id: int
    analyze_max_conversations: int
    narrate_max_conversations: int
    value_game_max_conversations: int
    response_min_conversations: int
    response_rate: float
    max_thinking_words: int
    max_narrat_words: int
    repeat_trigger: int
    user_name: str
    assistant_name: str
    conversation_analysis_flag: bool
    _text_analyzer: TextAnalyzer
    _launcher_id: str
    _launcher_type: str
    _generator: Generator
    _long_term_memory: typing.List[typing.Tuple[str, typing.List[str]]]
    _tags_index: dict
    _short_term_memory_size: int
    _retrieve_top_n: int
    _summary_max_tags: int
    _long_term_memory_file: str
    _conversations_file: str
    _short_term_memory_file: str
    _summarization_mode: bool
    _status_file: str
    _thinking_mode_flag: bool
    _already_repeat: set
    _meta_tag_count: int
    _has_preset: bool
    _memories_session: typing.List[typing.Tuple[str,float,datetime]]
    _memories_session_capacity: int
    _memories_recall_once: int
    _memory_weight_max: float
    _memory_decay_rate: float
    _memory_boost_rate: float
    _memory_base_growth: float
    _backoff_timestamp: int
    _state_trace_div: str
    _tags_div: str
    _split_word_cache: LRUCache
    _tag_boost: float
    _memory_graph: MemoryGraph
    _l0_threshold: float
    _l1_base: float
    _l1_threshold_floor: float
    _l1_hour_reduction_rate: float
    _l2_threshold: float
    _l2_jaccard: float
    _l2_similarity: float
    _l3_threshold: float
    _l3_jaccard_floor: float
    _l4_threshold: float
    _l4_emergency: float
    _l5_threshold: float
    _recall_keywords: typing.List
    _last_recall_memories: typing.List
    _last_l0_recall_memories: typing.List
    _last_l1_recall_memories: typing.List
    _last_l2_recall_memories: typing.List
    _last_l3_recall_memories: typing.List
    _last_l4_recall_memories: typing.List
    _last_l5_recall_memories: typing.List


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
        self._short_term_memory_size = 1500
        self._retrieve_top_n = 5
        self._summary_max_tags = 30
        self._long_term_memory_file = f"data/plugins/Waifu/data/memories_{launcher_id}.json"
        self._conversations_file = f"data/plugins/Waifu/data/conversations_{launcher_id}.log"
        self._short_term_memory_file = f"data/plugins/Waifu/data/short_term_memory_{launcher_id}.json"
        self._summarization_mode = False
        self._status_file = ""
        self._thinking_mode_flag = True
        self._already_repeat = set()
        self._meta_tag_count = 5 # year month day period datetime_mark
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
        self._state_trace_div = "状态追踪："
        self._tags_div = "关键概念："
        self._split_word_cache = LRUCache(100000)
        self._tag_boost = 0.2
        self._memory_graph = MemoryGraph(ap)
        self._l0_threshold = 0.0
        self._l1_base = 0.0
        self._l1_threshold_floor = 0.0
        self._l1_hour_reduction_rate = 0.0
        self._l2_threshold = 0.0
        self._l2_jaccard = 0.0
        self._l2_similarity = 0.0
        self._l3_threshold = 0.0
        self._l3_jaccard_floor = 0.0
        self._l4_threshold = 0.0
        self._l4_emergency = 0.0
        self._l5_threshold = 0.0
        # debug info
        self._recall_keywords = []
        self._last_recall_memories = []
        self._last_l0_recall_memories = []
        self._last_l1_recall_memories = []
        self._last_l2_recall_memories = []
        self._last_l3_recall_memories = []
        self._last_l4_recall_memories = []
        self._last_l5_recall_memories = []

    async def load_config(self, character: str, launcher_id: str, launcher_type: str):
        waifu_config = ConfigManager(f"data/plugins/Waifu/config/waifu", "plugins/Waifu/templates/waifu", launcher_id)
        await waifu_config.load_config(completion=True)

        self.conversation_analysis_flag = waifu_config.data.get("conversation_analysis", True)
        self._thinking_mode_flag = waifu_config.data.get("thinking_mode", True)
        self._short_term_memory_size = waifu_config.data["short_term_memory_size"]
        self._short_term_memory_size = max(self._short_term_memory_size, 2000)
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

        self._adjust_long_term_memory_tags()
        self._build_memory_graph()
        self._adjust_memory_thresholds()

    async def _tag_conversations(self, conversations: typing.List[llm_entities.Message], summary_flag: bool) -> typing.Tuple[str, typing.List[str]]:
        # 生成Tags：
        # 1、短期记忆转换长期记忆时：进行记忆总结
        # 2、对话提取记忆时：直接拼凑末尾对话
        if summary_flag:
            (memory,tags) = await self._generate_summary(conversations)
            return (memory,tags)

        memory = self.get_last_content(conversations,10)
        tags = await self._generate_tags(memory)
        return (memory, tags)

    def _remove_prefix_suffix_from_tag(self,tag:str) ->str:
        t = tag.replace("\"","").replace("\"","").replace("[","").replace("]","").replace("\n","")
        # Strip all invisible characters from beginning and end
        t = t.strip()
        while t.startswith("\\"):
            t = t[1:]
        while t.endswith("\\"):
            t = t[:-1]
        t = t.replace("DATETIME: ","DATETIME:")
        return t

    def _get_tags_from_str_array(self,tag_word:str) ->typing.List[str]:
        tag_words = tag_word.removeprefix("[").removesuffix("]").split(",")
        result = []
        for tag in tag_words:
            t = self._remove_prefix_suffix_from_tag(tag)
            if t == "":
                continue
            if t.count(":") == 0 and t.isalnum():
                t = t.lower()
            result.append(t)
        return result

    async def _generate_tags(self,conversation:str) -> typing.List[str]:
        conversation = conversation.replace("{","").replace("}","")
        tags = self._split_word_cache.get(conversation)
        if tags != None:
            return tags
        user_prompt_tags = f"""
提取文字中的关键概念："{conversation}"
1. 关键概念可以是名词，动词，或者特定人物
2. 输出只包含数组结果
"""
        output = await self._generator.return_string_without_jail_break(user_prompt_tags)
        self.ap.logger.info(f"词语： {conversation} 分词： {output}")
        tags = self._get_tags_from_str_array(output)
        self._split_word_cache.put(conversation,tags)
        return tags

    async def _generate_summary(self, conversations: typing.List[llm_entities.Message]) -> tuple[str,typing.List[str]]:
        user_prompt_summary = ""
        if self._launcher_type == "person":
            last = ""
            if len(self._long_term_memory) != 0:
                last = f"""背景信息(不可直接复述):"{self.get_latest_memory()}"\n\n"""
            _, conversations_str = self.get_conversations_str_for_person(conversations)
            prompt_rule=f"""
基于先前提供的背景总结（仅用于上下文参考）和最新对话内容，生成独立的新总结：

背景总结："{last}"

当前对话:"{conversations_str}"

你的回答应仅包含总结。

将总结限制在200字以内。总结应使用中文书写，并以过去式书写。

你需要在总结的末尾包含状态追踪和重要事务以及关键概念，规范如下：

{self._state_trace_div}
    互动状态：
        {self.user_name}正在进行的 持续动作
        {self.assistant_name}正在进行的 持续动作
    空间位置：
        {self.user_name}的 位置
        {self.assistant_name}的 位置
    事件结束时的动作姿态：
        {self.user_name}的 动作姿态
        {self.assistant_name}的 动作姿态
    关联物品:
        {self.user_name}的 关联物品
        {self.assistant_name}的 关联物品
    对象指代:
        当前对话中的 某个对象 实际指的是 另一对象
        如果没有指代则留空
        不得重复背景总结的信息，除非当前对话中有提及

重要事务规则：
    1. 包含对话中提出的某规则的具体条款
    2. 包含对话中提出的某操作的具体步骤
    3. 包含对话中提出的某方法的具体条件
    4. 包含对话中提出的某个概念的具体定义
    5. 如果在当前对话中以上的信息都没有则留空
    6. 不得重复背景总结的信息，除非当前对话中有提及
    7. 尽可能使用原始词汇
    8. 使用列表形式输出到以下位置：

    重要事务：

关键概念规则：
    1. 至多为{self._summary_max_tags}个
    2. 按重要性排序
    3. 尽可能使用对话原始词汇
    4. 可以是名词，动词，或者特定人物
    5. 使用数组的形式输出到以下位置：

    {self._tags_div}
            """
            user_prompt_summary = prompt_rule
        else:
            conversations_str = self.get_conversations_str_for_group(conversations)
            prompt_rule = f"""
基于最新对话内容，生成独立的新总结：

当前对话:"{conversations_str}"

将总结限制在200字以内。总结应使用中文书写，以{self.bot_account_id}为视角，并以过去式书写。

你的回答应仅包含总结。

你需要在总结的末尾包含核心关键词，规范如下：

关键概念规则：
1. 至多为{self._summary_max_tags}个
2. 按重要性排序
3. 尽可能使用对话原始词汇
4. 可以是名词，动词，或者特定人物
5. 使用数组的形式输出到以下位置：

{self._tags_div}
"""
            user_prompt_summary = prompt_rule

        output = await self._generator.return_string_without_jail_break(user_prompt_summary)
        self.ap.logger.info(f"总结完成：{output}")
        parts = output.split(self._tags_div)
        summary = parts[0] # 总结部分
        keywords = parts[-1].removeprefix("\n") # 关键词部分
        tags = self._get_tags_from_str_array(keywords)
        if len(tags) > self._summary_max_tags:
            tags = tags[:self._summary_max_tags]
        return (summary,tags)

    def current_time_str(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def get_time_form_str(self, time_str: str) -> datetime:
        return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")

    async def _tag_and_add_conversations(self):
        if self.short_term_memory:
            summary, tags = await self._tag_conversations(self.short_term_memory, True)
            tags.extend(self._generate_time_tags()) # 增加当天时间标签并去重
            tags = list(set(tags))

            # 保留最后1/10
            limit = self._short_term_memory_size / 10
            self._drop_short_term_memory(int(limit))

            # 加入元标签
            tags.append("DATETIME:" + self.current_time_str())

            # 填充到指定数量
            tag_cnt = self._meta_tag_count + self._summary_max_tags
            need_padding = tag_cnt - len(tags)
            if need_padding > 0:
                for i in range(need_padding):
                    tags.append(f"PADDING:{i}")

            # 保存记忆
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
        self._memory_graph.add_memory(MemoryItem(summary, tags))
        for tag in tags:
            if tag not in self._tags_index:
                if tag.count(":") == 0:
                    self._tags_index[tag] = len(self._tags_index)

    def _extract_time_tag(self, tags: typing.List[str]) -> tuple[int, str]:
        for i in range(len(tags)):
            if tags[i].startswith("DATETIME:"):
                time_tags = tags[i].replace("DATETIME:", "")
                return (i, time_tags)
        return (-1,"")

    def _extract_priority_tags(self, tags: typing.List[str]) -> tuple[int, str]:
        for i in range(len(tags)):
            if tags[i].startswith("PRIORITY:"):
                priority_tags = tags[i].replace("PRIORITY:", "")
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

    def get_last_recall_memories(self) -> str:
        memories = []
        for summary,weight in self._last_recall_memories:
            memories.append(f"权重：{weight:.2f} 记忆：{summary}")
        msg = "\n\n".join(memories)
        keywords = ",".join(self._recall_keywords)
        return f"关键词：{keywords}\n\n{msg}"

    def get_last_l0_recall_memories(self) -> str:
        memories = []
        for weight, similarity, summary,tags in self._last_l0_recall_memories:
            tags_str = ",".join(tags)
            memories.append(f"L0权重：{weight:.2f} 相似度：{similarity:.2f} 记忆：{summary} 标签:[{tags_str}]")
        msg = "\n\n".join(memories)
        self.ap.logger.info(f"召回L0记忆：\n\n{msg}")
        return "已打印"

    def get_last_l1_recall_memories(self) -> str:
        memories = []
        for weight, similarity, summary,tags in self._last_l1_recall_memories:
            tags_str = ",".join(tags)
            memories.append(f"L1权重：{weight:.2f} 相似度：{similarity:.2f} 记忆：{summary} 标签:[{tags_str}]")
        msg = "\n\n".join(memories)
        self.ap.logger.info(f"召回L1记忆：\n\n{msg}")
        return "已打印"

    def get_last_l2_recall_memories(self) -> str:
        memories = []
        for weight,jaccard, similarity, summary,tags in self._last_l2_recall_memories:
            tags_str = ",".join(tags)
            memories.append(f"L2权重：{weight:.2f} Jaccard: {jaccard:.2f} 相似度：{similarity:.2f} 记忆：{summary} 标签:[{tags_str}]")
        msg = "\n\n".join(memories)
        self.ap.logger.info(f"召回L2记忆：\n\n{msg}")
        return "已打印"

    def get_last_l3_recall_memories(self) -> str:
        memories = []
        for weight, jaccard, similarity, summary,tags in self._last_l3_recall_memories:
            tags_str = ",".join(tags)
            memories.append(f"L3权重：{weight:.2f} Jaccard: {jaccard:.2f} 相似度：{similarity:.2f} 记忆：{summary} 标签:[{tags_str}]")
        msg = "\n\n".join(memories)
        self.ap.logger.info(f"召回L3记忆：\n\n{msg}")
        return "已打印"

    def get_last_l4_recall_memories(self) -> str:
        memories = []
        for weight, similarity, summary,tags in self._last_l4_recall_memories:
            tags_str = ",".join(tags)
            memories.append(f"L4权重：{weight:.2f} 相似度：{similarity:.2f} 记忆：{summary} 标签:[{tags_str}]")
        msg = "\n\n".join(memories)
        self.ap.logger.info(f"召回L4记忆：\n\n{msg}")
        return "已打印"

    def get_last_l5_recall_memories(self) -> str:
        memories = []
        for weight, similarity, summary,tags in self._last_l5_recall_memories:
            tags_str = ",".join(tags)
            memories.append(f"L5权重：{weight:.2f} 相似度：{similarity:.2f} 记忆：{summary} 标签:[{tags_str}]")
        msg = "\n\n".join(memories)
        self.ap.logger.info(f"召回L5记忆：\n\n{msg}")
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

    def _calc_tag_boost_rate(self, hits: int, total_input_cnt: int) -> float:
        hit_parm = float(hits ** 1.5)
        cnt_parm = float(total_input_cnt)
        rate = hit_parm / cnt_parm
        rate = min(rate, 2.5)
        rate = max(rate, 0.8)
        return rate

    def _emulate_weight(self, hits:int) -> tuple[float, float,float]:
        total = hits + max(2,hits//2)
        max_tags = self._summary_max_tags + 4
        tags:list[str] = []
        total_tags:list[str] = []

        for i in range(total):
            tags.append(f"TAG{i}")

        for i in range(max_tags):
            total_tags.append(f"TAG{i}")

        input_vec = np.zeros(max_tags + total - hits)
        memory_vec = np.zeros(max_tags + total - hits)

        for i in range(hits):
            input_vec[i] = 1

        for i in range(max_tags,max_tags + total - hits):
            input_vec[i] = 1

        for i in range(max_tags):
            memory_vec[i] = 1

        similarity = self._cosine_similarity(input_vec, memory_vec)
        jaccard = len(set(tags) & set(total_tags)) / len(set(tags) | set(total_tags))
        tag_boost = self._calc_tag_boost_rate(hits, total)
        return (similarity, jaccard, tag_boost)

    def format_thresholds(self) -> str:
        text = ""
        text += f"L0阈值:{self._l0_threshold:.3f}\n"
        text += f"L1基础阈值:{self._l1_base:.3f} L1最小阈值:{self._l1_threshold_floor:.3f} L1阈值衰减率:{self._l1_hour_reduction_rate:.3f}\n"
        text += f"L2阈值:{self._l2_threshold:.3f} L2 Jaccard准入:{self._l2_jaccard:.3f} L2相似度准入:{self._l2_similarity:.3f}\n"
        text += f"L3阈值:{self._l3_threshold:.3f} L3 Jaccard准入:{self._l3_jaccard_floor:.3f}\n"
        text += f"L4阈值:{self._l4_threshold:.3f} L4 紧急通道准入:{self._l4_emergency:.3f}\n"
        text += f"L5阈值:{self._l5_threshold:.3f}\n"
        return text

    def _print_thresholds(self):
        self.ap.logger.info(f"当前记忆系统阈值：\n{self.format_thresholds()}")
        return

    def _adjust_memory_thresholds(self):
        """根据模拟结果动态调整各层级记忆系统的阈值
        """

        noise_hits = 1
        low_hits = 2
        mid_hits = 4
        hight_hits = 6

        noise_similarity,noise_jaccard,noise_tag_boost = self._emulate_weight(noise_hits)
        low_similarity,low_jaccard,low_tag_boost = self._emulate_weight(low_hits)
        mid_similarity,mid_jaccard,mid_tag_boost = self._emulate_weight(mid_hits)
        hight_similarity,hight_jaccard,hight_tag_boost = self._emulate_weight(hight_hits)

        noise_weight = noise_similarity * noise_tag_boost
        low_weight = low_similarity * low_tag_boost
        mid_weight = mid_similarity * mid_tag_boost
        hight_weight = hight_similarity * hight_tag_boost

        self.ap.logger.info(f"噪声：相似度：{noise_similarity:.2f} Jaccard: {noise_jaccard:.2f} TagBoost: {noise_tag_boost:.2f} 相似度权重: {noise_weight:.2f}")
        self.ap.logger.info(f"低指向：相似度：{low_similarity:.2f} Jaccard: {low_jaccard:.2f} TagBoost: {low_tag_boost:.2f} 相似度权重: {low_weight:.2f}")
        self.ap.logger.info(f"中指向：相似度：{mid_similarity:.2f} Jaccard: {mid_jaccard:.2f} TagBoost: {mid_tag_boost:.2f} 相似度权重: {mid_weight:.2f}")
        self.ap.logger.info(f"高指向：相似度：{hight_similarity:.2f} Jaccard: {hight_jaccard:.2f} TagBoost: {hight_tag_boost:.2f} 相似度权重: {hight_weight:.2f}")

        self._l0_threshold = round(noise_weight + (low_weight - noise_weight) * 0.3, 3)


        self._l1_base = low_weight
        self._l1_threshold_floor = round(low_weight * 0.6, 3)  # 最低不应低于低指向的60%
        # 噪声和低指向权重差距越小，衰减率越低(更谨慎)
        gap_ratio = (low_weight - noise_weight) / low_weight
        self._l1_hour_reduction_rate = min(0.5, gap_ratio * 0.8)

        self._l2_threshold = round(low_weight, 3)  # 基本阈值等于低指向
        self._l2_jaccard = max(0.05, round(low_jaccard - 0.03, 3)) # 略低于低指向的jaccard
        self._l2_similarity = round(low_similarity * 1.05, 3)  # 略高于低指向的相似度

        self._l3_threshold = round(low_weight * 1.1, 3)  # 高于L2
        self._l3_jaccard_floor = 0.03  # 保持较低的基础匹配要求

        self._l4_threshold = round(mid_weight * 0.6, 3)  # 中等程度阈值
        self._l4_emergency = round(hight_similarity * 1.2, 3)  # 高于高指向相似度

        self._l5_threshold = round(mid_weight * 1.15, 3)  # 高于中指向权重

        self._print_thresholds()

        return

    def _retrieve_related_l0_memories(self, input_tags: typing.List[str]) -> typing.List[tuple[float, MemoryItem]]:
        self.ap.logger.info(f"开始L0记忆召回 Tags: {', '.join(input_tags)}")
        current_time = datetime.now()
        input_vector = self._get_tag_vector(input_tags)
        l0_memories = []
        self._last_l0_recall_memories = []

        # L0配置（0-24小时）
        DECAY_RATE_PER_MIN = 0.002
        MAX_HOURS = 24
        COMBO_THRESHOLD = self._l0_threshold  # 权重门槛

        if len(self._long_term_memory) == 0:
            return []

        # 不考虑最新的记忆
        for summary, tags in self._long_term_memory[:len(self._long_term_memory) - 1]:
            # 提取元标签
            (_,time_tags) = self._extract_time_tag(tags)
            summary_time = datetime.fromtimestamp(self._backoff_timestamp)
            if time_tags != "":
                summary_time = self.get_time_form_str(time_tags)
            else:
                time_tags = summary_time.strftime("%Y-%m-%d %H:%M:%S")

            delta = current_time - summary_time
            # 时间过滤与权重计算
            delta_hours = delta.total_seconds()/3600
            if delta_hours > MAX_HOURS:
                # 记忆按时间排序
                break

            # 分钟级衰减计算
            delta_min = delta.total_seconds() / 60
            time_weight = math.exp(-DECAY_RATE_PER_MIN * delta_min)
            similarity = self._cosine_similarity(input_vector, self._get_tag_vector(tags))

            input_set = set(input_tags)
            mem_tags = set(self._get_real_tags(tags))
            hits = len(input_set & mem_tags)  # 实际命中标签数

            recency_boost = 1.2   # 衰减斜率降低
            similarity_weight = similarity * self._calc_tag_boost_rate(hits,len(input_set))
            weight = similarity_weight * (time_weight**0.8)  * recency_boost  # 添加指数平滑

            weight = min(weight, self._memory_weight_max)  # 限制最大权重

            # 准入规则
            if weight >= COMBO_THRESHOLD:
                result_mem = MemoryItem(summary,tags)
                l0_memories.append((weight,result_mem))

            self._last_l0_recall_memories.append((weight, similarity, summary[:40],tags))


        l0_memories.sort(reverse=True, key=lambda x: x[0])
        return l0_memories[: self._memories_recall_once]

    def _retrieve_related_l1_memories(self, input_tags: typing.List[str]) -> typing.List[tuple[float, MemoryItem]]:
        self.ap.logger.info(f"开始L1记忆召回 Tags: {', '.join(input_tags)}")
        current_time = datetime.now()
        input_vector = self._get_tag_vector(input_tags)
        l1_memories = []
        self._last_l1_recall_memories = []

        # L1配置（1-3天）
        DECAY_RATE_PER_HOUR = 0.02
        MIN_HOURS, MAX_HOURS = 19, 72

        if len(self._long_term_memory) == 0:
            return []

        # 不考虑最新的记忆
        for summary, tags in self._long_term_memory[:len(self._long_term_memory) - 1]:
            # 提取元标签
            (_,time_tags) = self._extract_time_tag(tags)
            summary_time = datetime.fromtimestamp(self._backoff_timestamp)
            if time_tags != "":
                summary_time = self.get_time_form_str(time_tags)
            else:
                time_tags = summary_time.strftime("%Y-%m-%d %H:%M:%S")

            # 严格时间过滤
            delta_hours = (current_time - summary_time).total_seconds() / 3600

            if delta_hours > MAX_HOURS:
                # 记忆按时间排序
                break

            if not (MIN_HOURS <= delta_hours <= MAX_HOURS):
                continue


            # 时间敏感度检测
            time_weight = math.exp(-DECAY_RATE_PER_HOUR * delta_hours)
            similarity = self._cosine_similarity(input_vector, self._get_tag_vector(tags))
            # 新增命中数计算
            input_set = set(input_tags)
            mem_tags = set(self._get_real_tags(tags))
            hits = len(input_set & mem_tags)

            similarity_weight = similarity * self._calc_tag_boost_rate(hits,len(input_set))
            weight = similarity_weight * time_weight

            weight = min(weight, self._memory_weight_max)  # 限制最大权重

            self._last_l1_recall_memories.append((weight, similarity, summary[:40],tags))

            # 动态准入（随时间放宽阈值）
            hour_factor = (delta_hours - MIN_HOURS) / (MAX_HOURS - MIN_HOURS)  # 0~1
            dynamic_th = self._l1_base * (1 - self._l1_hour_reduction_rate * hour_factor)
            dynamic_th = max(dynamic_th,self._l1_threshold_floor)
            if weight > dynamic_th:
                result_mem = MemoryItem(summary,tags)
                l1_memories.append((weight, result_mem))

        l1_memories.sort(reverse=True, key=lambda x: x[0])
        return l1_memories[: self._memories_recall_once]

    def _retrieve_related_l2_memories(self, input_tags: typing.List[str]) -> typing.List[tuple[float, MemoryItem]]:
        self.ap.logger.info(f"开始L2记忆召回 Tags: {', '.join(input_tags)}")
        current_time = datetime.now()
        input_vector = self._get_tag_vector(input_tags)
        l2_memories = []

        # L2配置（3-7天）
        TIME_DECAY_RATE = 0.0002 # 小时级衰减
        SIMILARITY_THRESHOLD = self._l2_threshold
        MIN_DAYS, MAX_DAYS = 2.4, 7
        TOPIC_WEIGHT = 1.2
        BASE_VALUE = 0.7

        if len(self._long_term_memory) == 0:
            return []

        # 不考虑最新的记忆
        for summary, tags in self._long_term_memory[:len(self._long_term_memory) - 1]:
            # 提取元标签
            (_,time_tags) = self._extract_time_tag(tags)
            summary_time = datetime.fromtimestamp(self._backoff_timestamp)
            if time_tags != "":
                summary_time = self.get_time_form_str(time_tags)
            else:
                time_tags = summary_time.strftime("%Y-%m-%d %H:%M:%S")

            delta_days = (current_time - summary_time).days

            if delta_days > MAX_DAYS:
                # 记忆按时间排序
                break

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
            # 新增命中数计算
            input_set = set(input_tags)
            mem_tags = set(self._get_real_tags(tags))
            hits = len(input_set & mem_tags)

            # 修改权重公式
            similarity_weight = similarity * self._calc_tag_boost_rate(hits,len(input_set))
            weight = similarity_weight * (time_weight ** 0.4) * (BASE_VALUE + TOPIC_WEIGHT * jaccard)

            weight = min(weight, self._memory_weight_max)  # 限制最大权重

            self._last_l2_recall_memories.append((weight,jaccard, similarity, summary[:40],tags))

            # 分级准入
            if weight >= SIMILARITY_THRESHOLD or (jaccard >= self._l2_jaccard and similarity >= self._l2_similarity):
                result_mem = MemoryItem(summary,tags)
                l2_memories.append((weight, result_mem))

        l2_memories.sort(reverse=True, key=lambda x: x[0])
        return l2_memories[: self._memories_recall_once]

    def _retrieve_related_l3_memories(self, input_tags: typing.List[str]) -> typing.List[tuple[float, MemoryItem]]:
        self.ap.logger.info(f"开始L3记忆召回 Tags: {', '.join(input_tags)}")
        current_time = datetime.now()
        input_vector = self._get_tag_vector(input_tags)
        l3_memories = []

        # L3配置（7-30天）
        DECAY_RATE = 0.01  # 天级衰减
        SIMILARITY_THRESHOLD = self._l3_threshold
        MIN_DAYS, MAX_DAYS = 5.6, 30
        JACCARD_FLOOR = self._l3_jaccard_floor  # 最低标签匹配

        if len(self._long_term_memory) == 0:
            return []

        # 不考虑最新的记忆
        for summary, tags in self._long_term_memory[:len(self._long_term_memory) - 1]:
            # 提取元标签
            (_,time_tags) = self._extract_time_tag(tags)
            summary_time = datetime.fromtimestamp(self._backoff_timestamp)
            if time_tags != "":
                summary_time = self.get_time_form_str(time_tags)
            else:
                time_tags = summary_time.strftime("%Y-%m-%d %H:%M:%S")

            delta_days = (current_time - summary_time).days

            if delta_days > MAX_DAYS:
                # 记忆按时间排序
                break

            if not (MIN_DAYS <= delta_days <= MAX_DAYS):
                continue

            # 混合匹配计算
            mem_tags = set(self._get_real_tags(tags))
            input_set = set(input_tags)
            jaccard = len(input_set & mem_tags) / len(input_set | mem_tags) if input_set else 0

            similarity = self._cosine_similarity(input_vector, self._get_tag_vector(tags))
            time_weight = math.exp(-DECAY_RATE * delta_days)
            # 新增命中数计算
            input_set = set(input_tags)
            mem_tags = set(self._get_real_tags(tags))
            hits = len(input_set & mem_tags)
            # 修改权重计算
            similarity_weight = similarity * self._calc_tag_boost_rate(hits,len(input_set))
            weight = (similarity_weight * 0.4 + jaccard * 0.6) * (time_weight**0.2)

            weight = min(weight, self._memory_weight_max)  # 限制最大权重

            if delta_days > 15:
                weight *= 1.2 - 0.01*(delta_days-15)

            self._last_l3_recall_memories.append((weight, jaccard, similarity, summary[:40],tags))

            # 准入规则
            if weight >= SIMILARITY_THRESHOLD and jaccard >= JACCARD_FLOOR:
                result_mem = MemoryItem(summary,tags)
                l3_memories.append((weight, result_mem))

        l3_memories.sort(reverse=True, key=lambda x: x[0])
        return l3_memories[: self._memories_recall_once]

    def _retrieve_related_l4_memories(self, input_tags: typing.List[str]) -> typing.List[tuple[float, MemoryItem]]:
        self.ap.logger.info(f"开始L4记忆召回 Tags: {', '.join(input_tags)}")
        current_time = datetime.now()
        input_vector = self._get_tag_vector(input_tags)
        l4_memories = []

        # L4配置（30天到365天）
        DECAY_RATE = 0.00003  # 超低衰减率
        EMERGENCY_THRESHOLD = self._l4_emergency
        SIMILARITY_THRESHOLD = self._l4_threshold
        MIN_DAYS = 24
        MAX_DAYS = 365

        if len(self._long_term_memory) == 0:
            return []

        # 不考虑最新的记忆
        for summary, tags in self._long_term_memory[:len(self._long_term_memory) - 1]:
            # 提取元标签
            (_,time_tags) = self._extract_time_tag(tags)
            summary_time = datetime.fromtimestamp(self._backoff_timestamp)
            if time_tags != "":
                summary_time = self.get_time_form_str(time_tags)
            else:
                time_tags = summary_time.strftime("%Y-%m-%d %H:%M:%S")

            delta_days = (current_time - summary_time).days

            if delta_days > MAX_DAYS:
                # 记忆按时间排序
                break

            if not (MIN_DAYS <= delta_days <= MAX_DAYS):
                continue

            # 优化衰减公式（添加非线性因子）
            decay_factor = 1 + 0.8 * (delta_days//180)
            time_weight = math.exp(-DECAY_RATE * delta_days * decay_factor)

            # 命中数计算
            input_set = set(input_tags)
            mem_tags = set(self._get_real_tags(tags))
            hits = len(input_set & mem_tags)

            # 纯语义匹配
            similarity = self._cosine_similarity(input_vector, self._get_tag_vector(tags))
            similarity_weight = similarity * self._calc_tag_boost_rate(hits,len(input_set))

            weight = similarity_weight * time_weight

            weight = min(weight, self._memory_weight_max)  # 限制最大权重

            self._last_l4_recall_memories.append((weight, similarity, summary[:40],tags))

            # 紧急通道 + 正常准入
            if weight >= SIMILARITY_THRESHOLD or similarity >= EMERGENCY_THRESHOLD and len(tags) >= 5:
                result_mem = MemoryItem(summary,tags)
                l4_memories.append((weight, result_mem))

        l4_memories.sort(reverse=True, key=lambda x: x[0])
        return l4_memories[: self._memories_recall_once]

    def _retrieve_related_l5_memories(self, input_tags: typing.List[str]) -> typing.List[tuple[float, MemoryItem]]:
        self.ap.logger.info(f"开始L5记忆召回 Tags: {', '.join(input_tags)}")
        current_time = datetime.now()
        input_vector = self._get_tag_vector(input_tags)
        l5_memories = []

        self._last_l5_recall_memories = []

        # L5配置（1年以上记忆）
        DECAY_RATE = 0.00003  # 极低衰减率（十年后保留≈e^(-0.00001 * 3650)=0.964）
        SIMILARITY_THRESHOLD = self._l5_threshold  # 高精度阈值
        MIN_DAYS = 365  # 1年+

        if len(self._long_term_memory) == 0:
            return []

        # 不考虑最新的记忆
        for summary, tags in self._long_term_memory[:len(self._long_term_memory) - 1]:
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

            # 纯语义匹配（可扩展点：未来在此添加事件触发逻辑）
            similarity = self._cosine_similarity(input_vector, self._get_tag_vector(tags))
            decay_factor = 1 + 0.5 * (delta_days//180)
            time_weight = math.exp(-DECAY_RATE * delta_days * decay_factor)
            # 新增命中数计算
            input_set = set(input_tags)
            mem_tags = set(self._get_real_tags(tags))
            hits = len(input_set & mem_tags)
            similarity_weight = similarity * self._calc_tag_boost_rate(hits,len(input_set))
            weight = similarity_weight * time_weight

            weight = min(weight, self._memory_weight_max)  # 限制最大权重

            if delta_days > 730:  # 2年以上的记忆
                weight *= 1.3  # 给予历史记忆加成

            self._last_l5_recall_memories.append((weight, similarity, summary[:40],tags))

            # 准入规则（可扩展点：未来添加人工审核接口）
            if weight >= SIMILARITY_THRESHOLD:
                result_mem = MemoryItem(summary,tags)
                l5_memories.append((weight,result_mem))

        l5_memories.sort(reverse=True, key=lambda x: x[0])
        return l5_memories[: self._memories_recall_once]

    def _clear_memories_session(self):
        self._memories_session = []
        self.ap.logger.info("记忆池已清空")

    def _update_memories_session(self, new_memories: typing.List[tuple[MemoryItem,float]]):
        """更新记忆池"""
        self.ap.logger.info(f"更新记忆池，当前内容：{self.get_memories_session()}")
        self.ap.logger.info(f"新记忆数量：{len(new_memories)}")
        good_memory_weight = 0.7
        mid_memory_weight = 0.4

        updated = {}  # 临时存储(内容, 权重)
        memory_times:dict[str,datetime] = {}  # 临时存储时间信息

        # 步骤1：衰减旧记忆权重，保留时间
        for mem, old_score, mem_time in self._memories_session:
            # 根据记忆质量调整衰减率
            decay_rate = 0.6
            if old_score >= good_memory_weight:
                decay_rate = 0.9
            elif old_score >= mid_memory_weight:
                decay_rate = 0.8
            new_score = old_score * decay_rate
            updated[mem] = new_score
            memory_times[mem] = mem_time  # 保留原始时间信息

        # 步骤2：计算动态增量
        for mem, old_score, mem_time in self._memories_session:
            if mem in [k for k, _ in new_memories]:
                similarity = 0.0
                for new_mem, weight in new_memories:
                    if new_mem == mem:
                        similarity = weight
                        break
                # 计算剩余增长空间
                headroom = self._memory_weight_max - old_score
                # 动态增长率 = 基础因子 × 剩余空间的平方占比
                base_growth = self._memory_base_growth * (1 + similarity * 0.3)
                growth_rate = base_growth * (headroom ** 1.0 / self._memory_weight_max)
                new_score = old_score + growth_rate
                updated[mem] = min(new_score, 1.0)

        # 步骤3：合并新记忆，提取时间信息
        for memory_item, weight in new_memories:
            mem = memory_item.summary()
            mem_time = memory_item.time()

            if mem in updated:
                continue

            init_score = min(weight, self._memory_weight_max * 0.8)  # 设置上限
            updated[mem] = init_score
            memory_times[mem] = mem_time  # 存储时间信息

        # 步骤4：合并旧记忆时间信息
        for mem, old_score, mem_time in self._memories_session:
            if mem in updated:
                continue
            updated[mem] = updated.get(mem, old_score)
            memory_times[mem] = mem_time  # 保留时间信息

        # 步骤5：按权重排序，转换回带有时间信息的元组列表
        sorted_mem = []
        for mem, score in sorted(updated.items(), key=lambda x: -x[1])[:self._memories_session_capacity]:
            if score >= 0.2:  # 过滤噪音
                sorted_mem.append((mem, score, memory_times[mem]))

        self._memories_session = sorted_mem

        # 调试日志
        print_info = []
        for mem, score, mem_time in self._memories_session:
            time_str = mem_time.strftime("%m月%d日 %H:%M")
            print_info.append(f"记忆：{mem} 权重：{score:.2f} 时间：{time_str}")
        msg = "\n\n".join(print_info)
        self.ap.logger.info(f"记忆池更新完成，当前内容：{msg}")

    def get_latest_memory(self) -> str:
        """获取最新记忆"""
        if len(self._long_term_memory) > 0:
            latest = self._long_term_memory[-1][0]
            return latest
        return ""

    def _get_memories_session(self) -> typing.List[typing.Tuple[datetime,str]]:
        """获取当前记忆池"""
        memories:typing.List[typing.Tuple[datetime,str]] = []
        for mem,_,time in self._memories_session:
            memories.append((time,mem))
        memories.sort(key=lambda x: x[0])
        return memories

    def get_memories_session(self) -> str:
        """获取当前记忆池"""
        memories = []
        for mem, score,_ in self._memories_session:
            memories.append(f"记忆：{mem} 权重：{score:.2f}")
        return "\n\n".join(memories)

    def _normalize_weight(self,raw_weight, max_weight):
        compressed = math.log1p(raw_weight * 10)  # 对数压缩增强小值差异
        return round(compressed / math.log1p(max_weight * 10), 2) * 0.7

    def _get_time_window(self,days:int)->int:
        if days <= 1:
            return days
        sorted_level = [
            (1,2),
            (3,3),
            (7,4),
            (30,5),
            (90,6),
            (180,7),
            (360,8)
        ]
        sorted_level.reverse()
        for day_limit,level in sorted_level:
            if days >= day_limit:
                return level
        self.ap.logger.error(f"时间窗口出错 {days}天")
        return -1

    def _recall_memories(self,input_tags:typing.List[str]) -> typing.List[tuple[MemoryItem,float]]:
        self.ap.logger.info(f"开始多级记忆召回 Tags: {', '.join(input_tags)}")
        self._recall_keywords = input_tags

        # 获取各层记忆结果（带权重）
        l0_results = []
        l1_results =[]
        l2_results = []
        l3_results = []
        l4_results = []
        l5_results = []

        # 防止前面层级过度召回导致后面的层级无法召回
        recall_threshold = self._memories_recall_once * 3
        current_recall_count = 0

        if current_recall_count < recall_threshold:
            l0_results = self._retrieve_related_l0_memories(input_tags)
            current_recall_count += len(l0_results)

        if current_recall_count < recall_threshold:
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

        if current_recall_count < recall_threshold:
            l5_results = self._retrieve_related_l5_memories(input_tags)
            current_recall_count += len(l5_results)

        # 构建带权记忆池
        self.ap.logger.info("开始合并记忆")
        weighted_memories:typing.List[tuple[float,MemoryItem]] = []
        weighted_memories.extend(l0_results)
        weighted_memories.extend(l1_results)
        weighted_memories.extend(l2_results)
        weighted_memories.extend(l3_results)
        weighted_memories.extend(l4_results)
        weighted_memories.extend(l5_results)

        self.ap.logger.info("计算时间窗口")
        current_time = datetime.now()
        time_group = defaultdict(list)
        for weight, memory in weighted_memories:
            delta_days = (current_time - memory.time()).days
            time_window = self._get_time_window(delta_days)  # 映射到预设时间窗口
            time_group[time_window].append((weight,memory))

        self.ap.logger.info("计算时间窗口最大值权重")
        time_group_max = {}
        for time_window,memories in time_group.items():
            if len(memories) != 0:
                time_group_max[time_window] = max([w for (w,_) in memories])


        self.ap.logger.info("结果归一化")
        memory_dict:dict[str,tuple[float,MemoryItem]] = {}
        for time_window,memories in time_group.items():
            for (w,mem) in memories:
                delta_days = (current_time - mem.time()).days
                time_window = self._get_time_window(delta_days)
                max_weight = time_group_max[time_window]
                final_weight = self._normalize_weight(w,max_weight)
                key = mem.summary()
                if key not in memory_dict or final_weight > memory_dict[key][0]:
                    memory_dict[key] = (final_weight,mem)


        # 按最终权重排序
        sorted_memories = sorted(memory_dict.items(), key=lambda x: x[1][0], reverse=True)
        self.ap.logger.info(f"加权合并完成，共召回{len(sorted_memories)}条记忆")
        sorted_memories = [(mem,weight) for _, (weight,mem) in sorted_memories]
        sorted_memories = sorted_memories[:self._memories_recall_once]
        return sorted_memories

    def _low_value_keywords(self) -> typing.List[str]:
        # 低价值关键词
        current_time = datetime.now()
        low_value_keywords = [
            "今天", "昨天", "明天", "前天", "后天",
            "早上", "中午", "晚上", "凌晨", "傍晚",
            "上午", "下午", "晚上", "清晨",
            f"{current_time.year}年",
            self.assistant_name,self.user_name
        ]
        for i in range(1, 13):
            low_value_keywords.append(f"{i}月")
        for i in range(1, 32):
            low_value_keywords.append(f"{i}日")
            low_value_keywords.append(f"{i}号")
        return low_value_keywords

    def _cluster_keywords(self, keywords: list[str], input_tags: list[str]) -> list[tuple[str, list[str]]]:
        """将联想词聚类成不同主题（模拟人类思维中的语义聚类）"""
        # 简化实现：基于与原始标签的关联度分组
        clusters = defaultdict(list)

        for keyword in keywords:
            # 找出与该关键词最相关的输入标签
            max_strength = 0
            best_match = input_tags[0] if input_tags else "default"

            for tag in input_tags:
                strength = self._memory_graph.get_connection_strength(keyword, tag)
                if strength > max_strength:
                    max_strength = strength
                    best_match = tag

            clusters[best_match].append((keyword, max_strength))

        # 对每个簇内部按强度排序
        result = []
        for topic, word_pairs in clusters.items():
            sorted_words = [w for w, _ in sorted(word_pairs, key=lambda x: -x[1])]
            result.append((topic, sorted_words))

        # 按簇的大小和强度排序
        result.sort(key=lambda x: -len(x[1]))
        return result

    def _format_sorted_memories(self, memories: typing.List[tuple[datetime, str]]) -> typing.List[str]:
        if not memories:
            return []

        memories = sorted(memories, key=lambda x: x[0])

        formatted_memories = []
        now = datetime.now()

        current_date = memories[0][0].strftime("%Y年%m月%d日 %H:%M:%S")
        formatted_memories.append(f"记忆时间线开始于 {current_date}")

        for i, (mem_time, memory) in enumerate(memories):
            if i > 0 and mem_time.date() != memories[i-1][0].date():
                day_transition = mem_time.strftime("%Y年%m月%d日 %H:%M:%S")
                formatted_memories.append(f"时间转至 {day_transition}")

            formatted_memories.append(memory)

        if memories[-1][0].date() != now.date():
            today = now.strftime("%Y年%m月%d日 %H:%M:%S")
            formatted_memories.append(f"以上记忆均发生在过去，当前时间是 {today}")

        return formatted_memories

    def _retrieve_related_memories(self, input_tags: typing.List[str]) -> typing.List[str]:
        # 第一步：进行标签联想
        keywords = self._memory_graph.get_related_keywords(set(input_tags))
        low_value_keywords = self._low_value_keywords()
        keywords = [k for k in keywords if k not in low_value_keywords]

        # 第二步：对联想词进行分组
        keyword_groups = self._cluster_keywords(keywords, input_tags)

        # 第三步：动态调整每个主题的联想词数量
        importance_factor = min(1.5, max(0.5, len(input_tags)/3))  # 输入标签越多，表明话题越复杂
        topic_limit = math.ceil(3 * importance_factor)  # 确定主题数量上限

        avg_degree = self._memory_graph.get_avg_degree()
        max_per_topic = 1
        max_total = 5
        # 第四步：根据图密度调整总体联想词数量
        if avg_degree < 30:
            max_per_topic = 3  # 图稀疏时，每个主题可以有更多联想词
            max_total = 9
        elif avg_degree < 60:
            max_per_topic = 2  # 图中等密度时，每个主题的联想词数量减少
            max_total = 7

        query_degrees = self._memory_graph.get_avg_degree_of_tags(set(input_tags))
        if query_degrees != 0:
            # 如果局部区域特别稀疏，适当增加联想词
            if query_degrees < avg_degree * 0.5:
                max_per_topic += 1
                max_total += 2
            # 如果局部区域特别密集，适当减少联想词
            elif query_degrees > avg_degree * 1.5:
                max_per_topic = max(1, max_per_topic - 1)
                max_total = max(2, max_total - 2)

        # 第五步：从每个主题中选取有限数量的代表词
        new_keywords = list(input_tags)  # 保留原始标签
        total_added = 0

        for topic, words in keyword_groups[:topic_limit]:  # 限制主题数
            self.ap.logger.info(f"主题: {topic} 关键词: {', '.join(words[:max_per_topic])}")
            added_from_topic = 0
            for word in words:
                if word not in new_keywords and added_from_topic < max_per_topic:
                    new_keywords.append(word)
                    added_from_topic += 1
                    total_added += 1
                    if total_added >= max_total:
                        break
            if total_added >= max_total:
                break

        self.ap.logger.info(f"原关键词： {', '.join(input_tags)} 联想后关键词：{', '.join(new_keywords)}")
        input_tags = new_keywords

        if len(input_tags) != 0:
            sorted_memories = self._recall_memories(input_tags)
            for mem,_ in sorted_memories:
                self.ap.logger.info(f"召回记忆: {mem.summary()}")
            self.ap.logger.info(f"召回并选择了{len(sorted_memories)}条记忆")

            # 更新记忆池
            self.ap.logger.info(f"召回数量：{len(sorted_memories)}")

            result = [(mem.summary(), weight) for mem, weight in sorted_memories]
            self._last_recall_memories = result

            self._update_memories_session(sorted_memories)

        memories = self._get_memories_session()[: self._retrieve_top_n]

        # 强制添加最新记忆保持连续
        if len(self._long_term_memory) != 0:
            latest = self._long_term_memory[-1]
            tags = latest[1]
            time_tags = self._extract_time_tag(tags)[1]
            if time_tags != "":
                summary_time = self.get_time_form_str(time_tags)
                latest = latest[0]
                if latest not in memories:
                    memories.append((summary_time,latest))

        return self._format_sorted_memories(memories)

    def _calc_short_term_memory_size(self) -> int:
        size = 0
        for conversation in self.short_term_memory:
            if conversation.content != None:
                size += len(conversation.content)
        return size

    def _drop_short_term_memory(self,limit:int):
        memories = self.short_term_memory.copy()
        memories.reverse()
        size = 0
        max_cnt = 0
        for i in range(len(memories)):
            mem = memories[i]
            if mem.content != None:
                size += len(mem.content)
                if size >= limit:
                    break
            max_cnt += 1
        self.short_term_memory = self.short_term_memory[-max_cnt:]
        return

    async def save_memory(self, role: str, content: str):
        time = self._generator.get_chinese_current_time()
        conversation = llm_entities.Message(role=role, content=f"[{time}]{content}")
        self.short_term_memory.append(conversation)
        self._save_short_term_memory_to_file()
        self._save_conversations_to_file([conversation])
        current_size = self._calc_short_term_memory_size()
        self.ap.logger.info(f"当前短期记忆大小: {current_size} 字符, 允许最大值: {self._short_term_memory_size} 字符")

        if current_size >= self._short_term_memory_size:
            if self._summarization_mode:
                await self._tag_and_add_conversations()
            else:
                max_remain = self._short_term_memory_size//2
                self._drop_short_term_memory(max_remain)

    async def remove_last_memory(self) -> str:
        if len(self.short_term_memory) > 0:
            last_conversation = self.short_term_memory.pop().get_content_platform_message_chain()
            self._save_short_term_memory_to_file()
            return last_conversation # type: ignore
        return ""

    async def load_memory(self, conversations: typing.List[llm_entities.Message]) -> typing.List[str]:
        if not self._long_term_memory:
            return []
        _, tags = await self._tag_conversations(conversations, False)
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
        self._memory_graph.clear()
        self.ap.logger.info("Cleared short-term and long-term memories")

    def _save_long_term_memory_to_file(self):
        tmpFile = "{}.tmp".format(self._long_term_memory_file)
        try:
            with open(tmpFile, "w", encoding="utf-8") as file:
                json.dump({"long_term": [{"summary": summary, "tags": tags} for summary, tags in self._long_term_memory], "tags_index": self._tags_index}, file, ensure_ascii=False, indent=4)
                file.flush()
        except Exception as e:
            self.ap.logger.error(f"Error saving memory to file '{self._long_term_memory_file}': {e}")

        try:
            os.replace(tmpFile, self._long_term_memory_file)
        except Exception as e:
            self.ap.logger.error(f"Error replacing memory file '{self._long_term_memory_file}': {e}")

    def _save_short_term_memory_to_file(self):
        tmpFile = "{}.tmp".format(self._short_term_memory_file)
        try:
            with open(tmpFile, "w", encoding="utf-8") as file:
                json.dump([{"role": conv.role, "content": conv.content} for conv in self.short_term_memory], file, ensure_ascii=False, indent=4)
                file.flush()
        except Exception as e:
            self.ap.logger.error(f"Error saving memory to file '{self._short_term_memory_file}': {e}")
            return

        try:
            os.replace(tmpFile, self._short_term_memory_file)
        except Exception as e:
            self.ap.logger.error(f"Error replacing memory file '{self._short_term_memory_file}': {e}")

    def _build_memory_graph(self):
        self.ap.logger.info("开始构建记忆图谱")
        for summary, tags in self._long_term_memory:
            mem = MemoryItem(summary, tags)
            self._memory_graph.add_memory(mem)
        self._memory_graph.print_graph()

    def _adjust_long_term_memory_tags(self):
        tag_cnt = self._summary_max_tags + self._meta_tag_count
        for i in range(len(self._long_term_memory)):
            (mem,tags) = self._long_term_memory[i]
            if len(tags) > tag_cnt:
                time_tag = self._extract_time_tag(tags)[1]
                num = len(tags) - tag_cnt
                tags = tags[:tag_cnt]
                find_time_tag = self._extract_time_tag(tags)[1]
                if find_time_tag == "" and time_tag != "":
                    tags.append(time_tag)
                self._long_term_memory[i] = (mem,tags)
                msg = ",".join(tags)
                self.ap.logger.info(f"截断记忆标签： {mem} 总数量:{tag_cnt} 截断数量:{num} 标签：{msg}")
            elif len(tags) < tag_cnt:
                num = tag_cnt - len(tags)
                for j in range(num):
                    tags.append(f"PADDING: {j}")
                self._long_term_memory[i] = (mem,tags)
                msg = ",".join(tags)
                self.ap.logger.info(f"填充记忆标签： {mem} 总数量:{tag_cnt} 填充数量:{num} 标签: {msg}")

    def _trim_for_tags(self,tags:typing.List[str]) -> typing.List[str]:
        for i in range(len(tags)):
            t = self._remove_prefix_suffix_from_tag(tags[i])
            if t == "":
                continue
            tags[i] = t
            if tags[i].startswith("DATETIME:") and tags[i].count(" ") == 0:
                ymd = tags[i][:len("DATETIME:") + 10]
                tags[i] = tags[i].replace(ymd,f"{ymd} ")
            if tags[i].count(":") == 0 and tags[i].isalnum():
                tags[i] = tags[i].lower()
        return tags

    def _load_long_term_memory_from_file(self):
        try:
            with open(self._long_term_memory_file, "r", encoding="utf-8") as file:
                file_content = file.read()
                if not file_content.strip():
                    self.ap.logger.warning(f"Memory file '{self._long_term_memory_file}' is empty. Starting with empty memory.")
                    return

                data = json.loads(file_content)
                self._long_term_memory = [(item["summary"], self._trim_for_tags(item["tags"])) for item in data["long_term"]]
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

