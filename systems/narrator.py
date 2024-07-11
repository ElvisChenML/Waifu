import typing
import json
import math
from datetime import datetime
from pkg.plugin.context import APIHost
from pkg.core.bootutils import config
from pkg.provider import entities as llm_entities
from plugins.Waifu.cells.generator import Generator
from plugins.Waifu.organs.memories import Memory


class Narrator:

    def __init__(self, host: APIHost, launcher_id: str):
        self.host = host
        self.ap = host.ap
        self._generator = Generator(host)
        self._life_data_file = f"plugins/Waifu/water/data/life_{launcher_id}.json"
        self._profile = ""
        self._action = ""
        self._life_data = {}

    async def load_config(self):
        self._load_life_data()

    async def narrate(self, memory: Memory, profile: str) -> str:
        conversations = memory.short_term_memory[-memory.narrate_max_conversations :]

        user_prompt = ""
        speakers, conversations_str = memory.get_conversations_str_for_person(conversations)
        last_role = memory.get_last_role(conversations)
        if last_role == "narrator":
            user_prompt += f"""续写“{conversations_str}”中“{"、".join(speakers)}”之后的身体动作。"""
        else:
            user_prompt += f"""分析“{conversations_str}”中{"、".join(speakers)}的身体动作并续写之后的身体动作。"""
        user_prompt += f"""不需要描述目前的身体动作，续写应与目前身体动作自然的衔接。每个身体动作都应以{"、".join(speakers)}其中一个开头，明确谁在进行身体动作。”。续写应富有创意、明确且诱人。只提供一个30字以内的身体动作描述，不需要其他说明。不可以在续写中替“{"、".join(speakers)}”发言。"""
        self._action = await self._generator.return_string(user_prompt)
        return self._action

    def _load_life_data(self):
        try:
            with open(self._life_data_file, "r") as f:
                self._life_data = json.load(f)
        except FileNotFoundError:
            self._life_data = {}
