import typing
import re
from pkg.plugin.context import APIHost
from plugins.Waifu.cells.config import ConfigManager


class Cards:
    def __init__(self, host: APIHost):
        self.host = host
        self.ap = host.ap
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

    async def load_config(self, character: str, launcher_type: str):
        config = ConfigManager(f"plugins/Waifu/water/cards/{character}", f"plugins/Waifu/water/templates/default_{launcher_type}")
        await config.load_config(completion=False)
        self._user_name = config.data.get("user_name", "用户")
        self._assistant_name = config.data.get("assistant_name", "助手")
        self._language = config.data.get("language", "简体中文")
        self._profile = config.data.get("Profile", [])
        self._profile = [f"你叫{self._assistant_name}。"] + self._profile
        self._skills = config.data.get("Skills", [])
        self._background = config.data.get("Background", [])
        if launcher_type == "person":
            self._background.append(f"你是{self._assistant_name}，我是{self._user_name}。")
        self._rules = config.data.get("Rules", [])
        self._init = config.data.get("Init", "")

    def set_memory(self, memories: typing.List[str]):
        self._memories = memories

    def set_manner(self, manner: str):
        self._manner = manner

    def get_background(self) -> str:
        return "".join(self._background) if isinstance(self._background, list) else self._background

    def get_profile(self) -> str:
        return "".join(self._profile)

    def generate_system_prompt(self) -> str:
        sections = self._collect_prompt_sections()
        return self._assemble_prompt(sections)

    def _collect_prompt_sections(self) -> typing.List[typing.Tuple[str, typing.Any]]:
        return [
            ("Profile", [f"你叫{self._assistant_name}。"] + self._profile),
            ("Skills", self._skills),
            ("Background", self._background),
            ("Memories", self._memories),
            ("Init", self.get_rules()),
        ]

    def get_rules(self) -> str:
        init_parts = []
        if self._rules:
            init_parts.append(self._list_to_prompt_str(self._rules, "你必须遵守"))
        if self._manner:
            init_parts.append(self._list_to_prompt_str(self._manner, "你必须遵守"))
        if self._language:
            init_parts.append(f"你必须用默认的{self._language}与我交谈。")
        return "".join(init_parts)

    def _assemble_prompt(self, sections: typing.List[typing.Tuple[str, typing.Any]]) -> str:
        prompt_parts = []
        for title, content_list in sections:
            if content_list:
                prompt_parts.append(f"{title}\n{self._list_to_prompt_str(content_list)}\n")
        return "".join(prompt_parts)

    def _ensure_punctuation(self, text: str) -> str:
        # 定义中英文标点符号
        punctuation = r"[。.，,？?；;]"
        # 如果末尾没有标点符号，则添加一个句号
        if not re.search(punctuation + r"$", text):
            return text + "。"
        return text

    def _list_to_prompt_str(self, content_list: list, prefix: str = "") -> str:
        if isinstance(content_list, list):
            return "".join([prefix + self._ensure_punctuation(item) for item in content_list])
        else:
            return self._ensure_punctuation(content_list)
