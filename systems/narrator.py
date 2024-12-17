import json
from pkg.core import app
from plugins.Waifu.cells.generator import Generator
from plugins.Waifu.organs.memories import Memory
from plugins.Waifu.cells.cards import Cards


class Narrator:

    ap: app.Application

    def __init__(self, ap: app.Application, launcher_id: str):
        self.ap = ap
        self._generator = Generator(ap)
        self._life_data_file = f"data/plugins/Waifu/data/life_{launcher_id}.json"
        self._profile = ""
        self._action = ""
        self._life_data = {}

    async def load_config(self):
        self._load_life_data()

    async def narrate(self, memory: Memory, card: Cards) -> str:
        conversations = memory.short_term_memory[-memory.narrate_max_conversations :]

        profile = memory.to_custom_names(card.get_profile() + card.get_background())

        user_prompt = ""
        if profile:
            user_prompt += f"这是{memory.assistant_name}的个人信息：“{profile}”。"
        speakers, conversations_str = memory.get_conversations_str_for_person(conversations)
        last_role = memory.get_last_role(conversations)
        if last_role == "narrator":
            user_prompt += f"""续写“{conversations_str}”中“{"、".join(speakers)}”之后的身体动作。"""
        else:
            user_prompt += f"""分析“{conversations_str}”中{"、".join(speakers)}的身体动作并续写之后的身体动作。"""
        user_prompt += f"""先判断{"、".join(speakers)}是否在一个场景，若不在一个场景，则只描述{memory.assistant_name}的身体动作。不需要描述目前的身体动作，续写应与目前身体动作自然的衔接。每个身体动作都应以{"、".join(speakers)}其中一个做主语，明确谁在进行身体动作。续写应富有创意、明确且诱人。续写应只描写身体动作，不可以包含发言内容。"""
        if profile:
            user_prompt += f"确保续写符合{memory.assistant_name}个人信息,"
        user_prompt += f"""不可以描述过去对话内容，不可以在续写中替“{"、".join(speakers)}”发言。不可以输出是否在同一个场景的判断结果，只提供一个{memory.max_narrat_words}字以内的身体动作描述。确保续写仅描述身体动作，不需要描述其他内容。"""
        self._generator.set_speakers(speakers)
        self._action = await self._generator.return_string(user_prompt)
        return self._action

    def _load_life_data(self):
        try:
            with open(self._life_data_file, "r") as f:
                self._life_data = json.load(f)
        except FileNotFoundError:
            self._life_data = {}

    def set_jail_break(self, type: str, user_name: str):
        self._generator.set_jail_break(type, user_name)
