import typing
from pkg.core.bootutils import config
from pkg.plugin.context import APIHost

class Cards:
    def __init__(self, host: APIHost):
        self.host = host
        self.ap = host.ap
        self._character_config = {}
        self._user_name = "用户"
        self._assistant_name = "助手"
        self._language = "简体中文"
        self._profile = []
        self._skills = []
        self._background = []
        self._output_format = []
        self._rules = []
        self._manner = ""
        self._memories = []
        self._init = ""
        self._current = []

    async def load_config(self, character: str):
        self._character_config = await config.load_json_config(
            f"plugins/Waifu/water/cards/{character}.json",
            "plugins/Waifu/water/templates/default_card.json",
            completion=False,
        )
        self._parse_system_prompt()

    def _parse_system_prompt(self):
        system_prompt = self._character_config.data.get("system_prompt", {})
        self._user_name = system_prompt.get("user_name", "用户")
        self._assistant_name = system_prompt.get("assistant_name", "助手")
        self._language = system_prompt.get("language", "简体中文")
        self._profile = system_prompt.get("Profile", [])
        self._skills = system_prompt.get("Skills", [])
        self._background = system_prompt.get("Background", [])
        self._background.append(f"你是{self._assistant_name}，我是{self._user_name}。")
        self._output_format = system_prompt.get("OutputFormat", [])
        self._rules = system_prompt.get("Rules", [])
        self._init = system_prompt.get("Init", "")
        self._current = []

    def set_memory(self, memories: typing.List[str]):
        self._memories = memories

    def set_manner(self, manner: str):
        self._manner = manner

    def set_life_description(self, time_text: str, location: str, action: str):
        self._current.clear()
        self._current.append(f"现在是{time_text}，你在{location}。")
        if action:
            self._current.append(action)

    def get_background(self) -> str:
        return "".join(self._background) if isinstance(self._background, list) else self._background

    def get_profile(self) -> str:
        return "".join(self._profile)

    def generate_system_prompt(self) -> str:
        sections = self._collect_prompt_sections()
        return self._assemble_prompt(sections)

    def _collect_prompt_sections(self) -> typing.List[typing.Tuple[str, typing.Any]]:
        return [
            ("# Role", self._assistant_name),
            ("## Profile", self._profile),
            ("## Skills", self._skills),
            ("## Background", self._background),
            ("## OutputFormat", self._output_format),
            ("## Rules", self._rules),
            ("## Manner", self._manner),
            ("## Memories", self._memories),
            ("## Current", self._current),
            ("## Init", self._generate_init_section())
        ]

    def _generate_init_section(self) -> str:
        init_parts = [f"作为<Role>"]
        if self._rules:
            init_parts.append("，你必须遵守<Rules>")
        if self._manner:
            init_parts.append("，你必须遵守<Manner>")
        if self._language:
            init_parts.append("，你必须用默认的<language>与我交谈")
        init_parts.append("。")
        return "".join(init_parts)

    def _assemble_prompt(self, sections: typing.List[typing.Tuple[str, typing.Any]]) -> str:
        prompt_parts = [f"# Role: {self._assistant_name}\n"]
        for title, content_list in sections:
            if content_list:
                content = "\n".join(content_list) if isinstance(content_list, list) else content_list
                prompt_parts.append(f"{title}\n{content}\n")
        return "".join(prompt_parts)
