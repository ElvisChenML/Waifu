import typing
import numpy as np
import json
import os
from plugins.Waifu.cells.generator import Generator
from pkg.plugin.context import APIHost
from pkg.provider import entities as llm_entities
from plugins.Waifu.cells.config import ConfigManager


class Memory:
    def __init__(self, host: APIHost, launcher_id: str, launcher_type: str):
        self.host = host
        self.ap = host.ap
        self.short_term_memory: typing.List[llm_entities.Message] = []
        self.analyze_max_conversations = 9
        self.narrate_max_conversations = 8
        self.value_game_max_conversations = 5
        self.response_min_conversations = 5
        self.response_rate = 0.7
        self.user_name = "用户"
        self.assistant_name = "助手"
        self._launcher_id = launcher_id
        self._launcher_type = launcher_type
        self._generator = Generator(host)
        self._long_term_memory: typing.List[typing.Tuple[str, typing.List[str]]] = []
        self._tags_index = {}
        self._short_term_memory_size = 100
        self._memory_batch_size = 50
        self._retrieve_top_n = 5
        self._summary_min_tags = 20
        self._long_term_memory_file = f"plugins/Waifu/water/data/memories_{launcher_id}.json"
        self._conversations_file = f"plugins/Waifu/water/data/conversations_{launcher_id}.log"
        self._short_term_memory_file = f"plugins/Waifu/water/data/short_term_memory_{launcher_id}.json"
        self._summarization_mode = False
        self._load_long_term_memory_from_file()
        self._load_short_term_memory_from_file()
        self._status_file = ""

    async def load_config(self, character: str, launcher_id: str, launcher_type: str):
        self._status_file = f"plugins/Waifu/water/data/{character}_{launcher_id}.json"

        waifu_config = ConfigManager(f"plugins/Waifu/water/config/waifu", "plugins/Waifu/water/templates/waifu", launcher_id)
        await waifu_config.load_config(completion=True)

        self._short_term_memory_size = waifu_config.data["short_term_memory_size"]
        self._memory_batch_size = waifu_config.data["memory_batch_size"]
        self._retrieve_top_n = waifu_config.data["retrieve_top_n"]
        self._summary_min_tags = waifu_config.data["summary_min_tags"]
        self._summarization_mode = waifu_config.data.get("summarization_mode", False)

        self.analyze_max_conversations = waifu_config.data.get("analyze_max_conversations", 9)
        self.narrate_max_conversations = waifu_config.data.get("narrat_max_conversations", 8)
        self.value_game_max_conversations = waifu_config.data.get("value_game_max_conversations", 5)
        self.response_min_conversations = waifu_config.data.get("response_min_conversations", 5)
        self.response_rate = waifu_config.data.get("response_rate", 0.7)

        character_config = ConfigManager(f"plugins/Waifu/water/cards/{character}", f"plugins/Waifu/water/templates/default_{launcher_type}")
        await character_config.load_config(completion=False)
        self.user_name = character_config.data.get("user_name", "用户")
        self.assistant_name = character_config.data.get("assistant_name", "助手")

    async def _tag_conversations(self, conversations: typing.List[llm_entities.Message]) -> typing.Tuple[str, typing.List[str]]:
        if len(conversations) > 1:
            memory = await self._generate_summary(conversations)
            user_prompt_tags = f"""请为这份摘要“{memory}”生成有意义且具有代表性的标签。"""
        else:
            memory = conversations[0].content
            user_prompt_tags = f"请为这段文字“{memory}”生成有意义且具有代表性的标签。"

        user_prompt_tags += f"""关注对话中的关键信息和主要讨论主题。提供至少{self._summary_min_tags}个简体中文标签。忽略时间戳和不相关的细节。确保输出是仅包含标签的有效JSON列表。不要包含任何附加信息、评论或解释。标签应格式为单词或简短短语，每个标签不超过3个字。"""

        system_prompt_tags = "你是总结对话并生成简明标签的专家。确保输出是仅包含标签的有效 JSON 列表。不要包含任何附加信息、评论或解释。"

        tags = await self._generator.return_list(user_prompt_tags, [], system_prompt_tags, True)
        return memory, tags

    async def _generate_summary(self, conversations: typing.List[llm_entities.Message]) -> str:
        _, conversations_str = self.get_conversations_str_for_person(conversations)
        user_prompt_summary = f"""总结以下对话中的最重要细节和事件: "{conversations_str}"。将总结限制在200字以内。总结应使用中文书写，并以过去式书写。你的回答应仅包含总结。"""

        return await self._generator.return_string(user_prompt_summary)

    async def _tag_and_add_conversations(self):
        if self.short_term_memory:
            summary, tags = await self._tag_conversations(self.short_term_memory[:self._memory_batch_size])
            self._log_new_memories(summary, tags)
            self._add_conversations(summary, tags)
            self.short_term_memory = self.short_term_memory[self._memory_batch_size:]
            self._save_long_term_memory_to_file()
            self._save_short_term_memory_to_file()

    def _log_new_memories(self, summary: str, tags: typing.List[str]):
        short_term_memory_str = " | ".join([conv.readable_str() for conv in self.short_term_memory[:self._memory_batch_size]])
        formatted_tags = ", ".join(tags)
        self.ap.logger.info(f"New memories: {short_term_memory_str}\nSummary: {summary}\nTags: {formatted_tags}")

    def _save_conversations_to_file(self, conversations: typing.List[llm_entities.Message]):
        try:
            with open(self._conversations_file, "a", encoding="utf-8") as file:
                for conv in conversations:
                    file.write(conv.readable_str() + "\n")
        except Exception as e:
            self.ap.logger.error(f"Error saving conversations to file '{self._conversations_file}': {e}")

    def _add_conversations(self, summary: str, tags: typing.List[str]):
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
            self.ap.logger.info(f"Similarity: {similarity}, Tags: {tags}")

        similarities.sort(reverse=True, key=lambda x: x[0])
        return [summary for _, summary in similarities[:self._retrieve_top_n]]

    async def save_memory(self, role: str, content: str, time: str):
        content_with_time = f"[{time}] {content}"
        conversation = llm_entities.Message(role=role, content=content_with_time)
        self.short_term_memory.append(conversation)
        self._save_short_term_memory_to_file()
        self._save_conversations_to_file([conversation])

        if len(self.short_term_memory) >= self._short_term_memory_size:
            if self._summarization_mode:
                await self._tag_and_add_conversations()
            else:
                self.short_term_memory = self.short_term_memory[self._short_term_memory_size:]

    async def remove_last_memory(self) -> str:
        if self.short_term_memory:
            last_conversation = self.short_term_memory.pop().get_content_mirai_message_chain()
            self._save_short_term_memory_to_file()
            return last_conversation

    async def load_memory(self, conversations: typing.List[llm_entities.Message]) -> typing.List[str]:
        if not self._long_term_memory:
            return []
        _, tags = await self._tag_conversations(conversations)
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
            f"plugins/Waifu/water/cards/default_{self._launcher_type}.yaml",
            f"plugins/Waifu/water/data/life_{self._launcher_id}.json",
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
                json.dump(
                    {
                        "long_term": [{"summary": summary, "tags": tags} for summary, tags in self._long_term_memory],
                        "tags_index": self._tags_index
                    },
                    file, ensure_ascii=False, indent=4
                )
        except Exception as e:
            self.ap.logger.error(f"Error saving memory to file '{self._long_term_memory_file}': {e}")

    def _save_short_term_memory_to_file(self):
        try:
            with open(self._short_term_memory_file, "w", encoding="utf-8") as file:
                json.dump(
                    [{"role": conv.role, "content": conv.content} for conv in self.short_term_memory],
                    file, ensure_ascii=False, indent=4
                )
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
        for message in conversations:
            role = self.to_custom_names(message.role)
            # 提取括号后的内容
            content = str(message.get_content_mirai_message_chain()).split("] ", 1)[-1]

            if role == "narrator":
                conversations_str += f"{self.to_custom_names(content)}"
            else:                
                if speakers:  # 聆听者为上一个发言者
                    if role != speakers[-1]: # 不为连续发言
                        listener = speakers[-1]
                elif role == self.assistant_name: # 仅speaker为空时生效
                    listener = self.user_name
                conversations_str += f"{role}对{listener}说：“{content}”。"
                if role in speakers:  # 该容器兼顾保存最后一个发言者，不是单纯的set
                    speakers.remove(role)
                speakers.append(role)
        return speakers, conversations_str

    def get_conversations_str_for_group(self, conversations: typing.List[llm_entities.Message]) -> str:
        conversations_str = ""
        for message in conversations:
            role = message.role
            if role == "assistant":
                role = "你"
            # 提取括号后的内容
            content = str(message.get_content_mirai_message_chain()).split("] ", 1)[-1]
            conversations_str += f"{role}说：“{content}”。"
        return conversations_str

    def get_unreplied_msg(self, unreplied_msg: int) -> typing.Tuple[int, typing.List[llm_entities.Message]]:
        count = 0  # 未回复的数量 + 穿插的自己发言的数量 用以正确区分 replied 及 unreplied 分界线
        messages = []
        for message in reversed(self.short_term_memory):
            count += 1
            if message.role != "assistant":
                messages.insert(0, message)
                if len(messages) >= unreplied_msg:
                    return count, messages
        return count, messages

    def get_last_speaker(self, conversations: typing.List[llm_entities.Message]) -> str:
        for message in reversed(conversations):
            if message.role not in {"narrator", "assistant"}:
                return self.to_custom_names(message.role)
        return ""

    def get_last_role(self, conversations: typing.List[llm_entities.Message]) -> str:
        return self.to_custom_names(conversations[-1].role) if conversations else ""

    def get_last_content(self, conversations: typing.List[llm_entities.Message]) -> str:
        return str(conversations[-1].get_content_mirai_message_chain()).split("] ", 1)[-1] if conversations else ""

    def to_custom_names(self, text: str) -> str:
        text = text.replace("User", self.user_name)
        text = text.replace("user", self.user_name)
        text = text.replace("用户", self.user_name)
        text = text.replace("Assistant", self.assistant_name)
        text = text.replace("assistant", self.assistant_name)
        text = text.replace("助理", self.assistant_name)
        return text

    def to_generic_names(self, text: str) -> str:
        text = text.replace("User", "user")
        text = text.replace("用户", "user")
        text = text.replace("Assistant", "assistant")
        text = text.replace("助理", "assistant")
        text = text.replace(self.user_name, "user")
        text = text.replace(self.assistant_name, "assistant")
        return text
