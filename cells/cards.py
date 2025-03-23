import typing
import re
from pkg.core import app
from plugins.Waifu.cells.config import ConfigManager


class Cards:

    ap: app.Application

    def __init__(self, ap: app.Application):
        self.ap = ap
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
        if isinstance(self._profile, list) and self._assistant_name != "助手":
            self._profile = [f"你是{self._assistant_name}。"] + self._profile
        self._skills = config.data.get("Skills", [])
        self._background = config.data.get("Background", [])
        if isinstance(self._background, list) and launcher_type == "person" and self._assistant_name != "助手" and self._user_name != "用户":
            self._background = self._background + [f"你是{self._assistant_name}，用户是{self._user_name}。"]
        self._rules = config.data.get("Rules", [])
        self._prologue = config.data.get("Prologue", "")

        # Collect additional keys
        predefined_keys = {"user_name", "assistant_name", "language", "Profile", "Skills", "Background", "Rules", "Prologue", "max_manner_change", "value_descriptions"}
        self._additional_keys = {key: value for key, value in config.data.items() if key not in predefined_keys}

    def set_memory(self, memories: typing.List[str]):
        self._memories = memories

    def set_manner(self, manner: str):
        self._manner = manner

    def get_background(self) -> str:
        return self._format_value(self._background)

    def get_profile(self) -> str:
        return self._format_value(self._profile)

    def get_manner(self) -> str:
        return self._manner

    def get_prologue(self) -> str:
        return self._format_value(self._prologue)

    def get_rules(self) -> str:
        init_parts = []
        if self._rules:
            init_parts.append(self._format_value(self._rules, "你必须遵守"))
        if self._manner:
            init_parts.append(self._format_value(self._manner, "你必须遵守"))
        if self._language:
            init_parts.append(f"你必须用默认的{self._language}与我交谈。")
        return "".join(init_parts)

    def generate_system_prompt(self) -> str:
        return self._format_value(self._collect_prompt_sections())

    def _collect_prompt_sections(self) -> typing.List[typing.Tuple[str, typing.Any]]:
        sections = []

        # 逐一检查每个部分，如果非空，则添加到 sections 中
        if self._profile:
            sections.append(("Profile", self._profile))
        if self._skills:
            sections.append(("Skills", self._skills))
        if self._background:
            sections.append(("Background", self._background))
        if self._memories:
            sections.append(("Memories", self._memories))
        rules = self.get_rules()
        if rules:
            sections.append(("Rules", rules))

        # 添加额外的 key，如果 value 非空
        for key, value in self._additional_keys.items():
            if value:  # 检查值是否为空
                sections.append((key, value))

        return sections

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

    def _format_value(self, value: typing.Any, prefix: str = "", link: str = "") -> str:
        """
        统一处理 list、dict、str 等类型，并支持嵌套结构。
        """
        if isinstance(value, dict):
            # 处理字典，递归格式化
            formatted = []
            for k, v in value.items():
                formatted.append(f"{prefix}{k}:")
                formatted.append(self._format_value(v, prefix, link))
            return link.join(formatted)

        elif isinstance(value, list):
            # 处理列表，递归格式化每个元素
            formatted = []
            for item in value:
                formatted.append(self._format_value(item, prefix, link))
            return link.join(formatted)

        elif isinstance(value, str):
            # 处理字符串，确保末尾标点
            return prefix + self._ensure_punctuation(value)

        else:
            # 其他类型，强制转换为字符串
            return prefix + str(value)

    def merge_personal_config(self, personal_config: dict):
        """合并个性化提示词配置"""
        if not personal_config:
            return
            
        # 合并基本配置
        if "user_name" in personal_config:
            self._user_name = personal_config["user_name"]
        if "assistant_name" in personal_config:
            self._assistant_name = personal_config["assistant_name"]
        if "language" in personal_config:
            self._language = personal_config["language"]
            
        # 合并列表类型的配置
        self._profile = personal_config.get("Profile", self._profile)
        self._skills = personal_config.get("Skills", self._skills)
        self._background = personal_config.get("Background", self._background)
        self._rules = personal_config.get("Rules", self._rules)
        
        # 合并其他配置
        if "Prologue" in personal_config:
            self._prologue = personal_config["Prologue"]
