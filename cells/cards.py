import typing
import re
from pkg.plugin.context import APIHost
from plugins.Waifu.cells.config import ConfigManager


class Cards:
    def __init__(self, host: APIHost):
        self.host = host
        self.ap = host.ap
        self._user_name = "user"
        self._assistant_name = "assistant"
        self._language = ""
        self._profile = []
        self._skills = []
        self._background = []
        self._output_format = []
        self._rules = []
        self._manner = ""
        self._memories = []
        self._speaking = []
        self._restrictions = []
        self._prologue = ""
        self._additional_keys = {}
        self._has_preset = True

    async def load_config(self, character: str, launcher_type: str):
        if character == "off":
            self._has_preset = False
            return        
        self._has_preset = True

        config = ConfigManager(f"data/plugins/Waifu/cards/{character}", f"plugins/Waifu/templates/default_{launcher_type}")
        await config.load_config(completion=False)
        self._user_name = config.data.get("user_name", "用户")
        self._assistant_name = config.data.get("assistant_name", "助手")
        self._language = config.data.get("language", "简体中文")
        self._profile = config.data.get("Profile", [])
        self._profile = [f"你是{self._assistant_name}。"] + self._profile
        self._skills = config.data.get("Skills", [])
        self._background = config.data.get("Background", [])
        if launcher_type == "person":
            self._background.append(f"你是{self._assistant_name}，用户是{self._user_name}。")
        self._rules = config.data.get("Rules", [])
        self._speaking = config.data.get("Speaking", [])
        self._restrictions = config.data.get("Restrictions", [])
        self._prologue = config.data.get("Prologue", "")

        # Collect additional keys
        predefined_keys = {"user_name", "assistant_name", "language", "Profile", "Skills", "Background", "Rules", "Speaking", "Restrictions", "Prologue", "max_manner_change", "value_descriptions"}
        self._additional_keys = {key: value for key, value in config.data.items() if key not in predefined_keys}

    def set_memory(self, memories: typing.List[str]):
        self._memories = memories

    def set_manner(self, manner: str):
        self._manner = manner

    def get_background(self) -> str:
        return self._list_to_prompt_str(self._background)

    def get_profile(self) -> str:
        return self._list_to_prompt_str(self._profile)

    def get_restrictions(self) -> str:
        return self._list_to_prompt_str(self._restrictions)

    def get_manner(self) -> str:
        return self._manner

    def get_prologue(self) -> str:
        return self._list_to_prompt_str(self._prologue, link="\n")

    def get_rules(self) -> str:
        init_parts = []
        if self._rules:
            init_parts.append(self._list_to_prompt_str(self._rules, "你必须遵守"))
        if self._manner:
            init_parts.append(self._list_to_prompt_str(self._manner, "你必须遵守"))
        if self._language:
            init_parts.append(f"你必须用默认的{self._language}与我交谈。")
        return "".join(init_parts)

    def get_speaking(self) -> str:
        return self._list_to_prompt_str(self._speaking)

    def generate_system_prompt(self) -> str:
        sections = self._collect_prompt_sections()
        return self._assemble_prompt(sections)

    def _collect_prompt_sections(self) -> typing.List[typing.Tuple[str, typing.Any]]:
        sections = [
            ("Profile", self._profile),
            ("Speaking Style", self._speaking),
            ("Skills", self._skills),
            ("Background", self._background),
            ("Memories", self._memories),
            ("Restrictions", self._restrictions),
            ("Rules", self.get_rules()),
        ]
        # Add additional keys to sections
        for key, value in self._additional_keys.items():
            sections.append((key, value))
        return sections

    def _assemble_prompt(self, sections: typing.List[typing.Tuple[str, typing.Any]]) -> str:
        prompt_parts = []
        for title, content_list in sections:
            if content_list:
                prompt_parts.append(f"{title}\n{self._list_to_prompt_str(content_list)}\n")
        return "".join(prompt_parts)

    def _ensure_punctuation(self, text: str | None) -> str:
        if isinstance(text, str):
            # 定义中英文标点符号
            punctuation = r"[。.，,？?；;]"
            # 如果末尾没有标点符号，则添加一个句号
            if not re.search(punctuation + r"$", text):
                return text + "。"
            return text
        else:
            return ""

    def _list_to_prompt_str(self, content: list | str | None, prefix: str = "", link: str = "") -> str:
        if isinstance(content, list):
            return link.join([prefix + self._ensure_punctuation(item) for item in content if isinstance(item, str)])
        elif isinstance(content, str):
            return self._ensure_punctuation(content)
        else:
            return ""
