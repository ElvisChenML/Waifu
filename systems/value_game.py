import json
import re
from plugins.Waifu.cells.text_analyzer import TextAnalyzer
from plugins.Waifu.cells.config import ConfigManager
from plugins.Waifu.cells.generator import Generator
from plugins.Waifu.organs.memories import Memory
from pkg.plugin.context import APIHost


class ValueGame:

    def __init__(self, host: APIHost):
        self.host = host
        self.ap = host.ap
        self._generator = Generator(host)
        self._text_analyzer = TextAnalyzer(host)
        self._value = 0
        self._manner_descriptions = []
        self._max_manner_change = 10
        self._value_change = None
        self._config = None
        self._status_file = ""

    async def load_config(self, character: str, launcher_id: str, launcher_type: str):
        self._status_file = f"plugins/Waifu/water/data/{character}_{launcher_id}.json"

        character_config_path = f"plugins/Waifu/water/cards/{character}"
        self._config = ConfigManager(character_config_path, f"plugins/Waifu/water/templates/default_{launcher_type}")
        await self._config.load_config(completion=False)

        try:
            with open(self._status_file, "r") as file:
                data = json.load(file)
                self._value = data.get("value", 0)
        except FileNotFoundError:
            self._value = 0

        self._manner_descriptions = self._config.data.get("value_descriptions", [])
        self._max_manner_change = self._config.data.get("max_manner_change", 10)

    async def determine_manner_change(self, memory: Memory, continued_count: int):
        last_speaker = memory.get_last_speaker(memory.short_term_memory)
        if last_speaker != memory.user_name:  # 只有用户发言可以影响到Value值变化
            self._value_change = None
            return
        count = continued_count + 1  # 继续发言次数 + 正常回复
        conversations = memory.short_term_memory[-count:]
        last_content = memory.get_last_content(conversations)

        # self.ap.logger.info(f"情绪分析: {last_content}")
        sentiment_result = await self._text_analyzer.sentiment(text=last_content)
        positive_emotions = sentiment_result.get("positive_num", 0)
        negative_emotions = sentiment_result.get("negative_num", 0)

        sentiment_score = (positive_emotions - negative_emotions) / (positive_emotions + negative_emotions + 1)
        if sentiment_score == 0:  # 不抵触时默认微量增加
            sentiment_score = 0.1
        self.ap.logger.info(f"分析结果: {sentiment_score} {sentiment_result}")

        change_amount = int(sentiment_score * self._max_manner_change)

        self.change_manner_value(change_amount)
        self._value_change = change_amount

    def get_manner_value_str(self) -> str:
        value_change = self._value_change
        if value_change is None:
            return ""  # 非user发言以及未知的情况不添加该数值栏位
        value_change_str = ""
        if value_change > 0:
            value_change_str = f"+{value_change}"
        elif value_change < 0:
            value_change_str = f"{value_change}"
        content = f"【💕值：{self._value}】"
        if value_change_str:
            content += f"（{value_change_str}）"
        return content

    def get_value(self) -> int:
        return self._value

    def get_manner_description(self) -> str:
        last_description = "正常相处"
        for desc in self._manner_descriptions:
            last_description = self._list_to_prompt_str(desc["description"])
            if self._value <= desc["max"]:
                return last_description
        return last_description

    def _ensure_punctuation(self, text: str) -> str:
        # 定义中英文标点符号
        punctuation = r"[。.，,？?；;]"
        # 如果末尾没有标点符号，则添加一个句号
        if not re.search(punctuation + r"$", text):
            return text + "。"
        return text

    def _list_to_prompt_str(self, content: list | str, prefix: str = "") -> str:
        if isinstance(content, list):
            return "".join([prefix + self._ensure_punctuation(item) for item in content])
        else:
            return self._ensure_punctuation(content)

    def change_manner_value(self, amount: int):
        self._value = max(0, min(10000, self._value + amount))
        self._save_value_to_status_file()

    def _save_value_to_status_file(self):
        with open(self._status_file, "w") as file:
            json.dump({"value": self._value}, file)

    def reset_value(self):
        self._value = 0

    def set_jail_break(self, jail_break: str, type: str):
        self._generator.set_jail_break(jail_break, type)
