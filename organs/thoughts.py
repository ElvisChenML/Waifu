import typing
from pkg.plugin.context import APIHost
from pkg.core.bootutils import config
from pkg.provider import entities as llm_entities
from plugins.Waifu.cells.generator import Generator


class Thoughts:
    def __init__(self, host: APIHost):
        self.host = host
        self.ap = host.ap
        self._generator = Generator(host)
        self._user_name = "用户"
        self._assistant_name = "助手"
        self._current_emotion = "普通"
        self._analyze_max_conversations = 9

    async def load_config(self):
        self._config = await config.load_json_config(
            "plugins/Waifu/water/config/waifu.json",
            "plugins/Waifu/water/templates/waifu.json",
            completion=False,
        )
        self._analyze_max_conversations = self._config.data.get("analyze_max_conversations", 9)
        character = self._config.data["character"]
        self._character_config = await config.load_json_config(
            f"plugins/Waifu/water/cards/{character}.json",
            "plugins/Waifu/water/templates/default_card.json",
            completion=False,
        )
        system_prompt = self._character_config.data.get("system_prompt", {})
        self._user_name = system_prompt.get("user_name", "用户")
        self._assistant_name = system_prompt.get("assistant_name", "助手")
        self._generator.set_names(self._user_name, self._assistant_name)

    async def analyze_conversations(self, conversations: typing.List[llm_entities.Message], background: str) -> str:
        conversations = conversations[-self._analyze_max_conversations :]
        speakers, conversations_str = self._generator.get_conversations_str_for_prompt(conversations)

        last_role = self._generator.get_last_role(conversations)
        last_content = self._generator.get_last_content(conversations)
        user_prompt = f"参考{self._assistant_name}的背景设定：“{background}”，请站在{self._assistant_name}的角度"
        if last_role == "narrator":
            user_prompt += f"""分析“{conversations_str}”中“{last_content}”里“{"、".join(speakers)}”之间的行为及事件。"""
        else:
            user_prompt += f"分析“{conversations_str}”中{last_role}对{self._assistant_name}说“{last_content}”的意图。"

        user_prompt += f"""确保分析是站在{self._assistant_name}的角度思考。确保分析简明扼要，意图明确。只提供30字以内的分析内容，不需要其他说明。"""
        analysis_result = await self._generator.return_string(user_prompt)
        return analysis_result

    async def generate_user_prompt(self, conversations: typing.List[llm_entities.Message] = [], background: str = "", manner: str = "") -> typing.Tuple[str, str]:
        analysis = await self.analyze_conversations(conversations, background)
        _, conversations_str = self._generator.get_conversations_str_for_prompt(conversations)
        user_prompt = f"这是之前的记录：“{conversations_str}”，经过分析记录，你得出“{analysis}”。你作为{self._assistant_name}，"

        last_speaker = self._generator.get_last_speaker(conversations)
        last_role = self._generator.get_last_role(conversations)
        last_content = self._generator.get_last_content(conversations)

        if last_role == "narrator":
            user_prompt += f"你根据最后发生的事情“{last_content}”对{last_speaker}做出适当的回复。"
        else:
            user_prompt += f"你要对{last_speaker}说的“{last_content}”对{last_speaker}做出适当的回复。"

        user_prompt += f"请确认你记得<background>“{background}”，请确认你的回复符合你的<manner>“{manner}”。只提供回复内容，不需要其他说明。"

        return user_prompt, analysis
