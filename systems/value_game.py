import json
from plugins.Waifu.cells.config import ConfigManager
from plugins.Waifu.cells.generator import Generator
from plugins.Waifu.organs.memories import Memory
from pkg.plugin.context import APIHost


class ValueGame:

    def __init__(self, host: APIHost):
        self.host = host
        self.ap = host.ap
        self._generator = Generator(host)
        self._value = 0
        self._manner_descriptions = []
        self._actions_type = {}
        self._last_choice = ""
        self._config = None
        self._status_file = ""

    async def load_config(self, character: str, launcher_id: str, launcher_type: str):
        self._status_file = f"plugins/Waifu/water/data/{character}_{launcher_id}.json"

        character_config_path = f"plugins/Waifu/water/cards/{character}"
        self._config = ConfigManager(character_config_path, f"plugins/Waifu/water/templates/default_{launcher_type}")
        await self._config.load_config(completion=False)     

        try:
            with open(self._status_file, 'r') as file:
                data = json.load(file)
                self._value = data.get("value", 0)
        except FileNotFoundError:
            self._value = 0

        self._manner_descriptions = self._config.data.get("value_descriptions", [])
        self._actions_type = {action["type"]: action["value_change"] for action in self._config.data.get("actions_type", [])}
        self._actions_type[""] = 0

    async def determine_manner_change(self, memory: Memory):
        conversations = memory.short_term_memory[-memory.value_game_max_conversations:]
        _, conversations_str = memory.get_conversations_str_for_person(conversations)
        last_speaker = memory.get_last_speaker(conversations)
        if last_speaker != memory.user_name:  # 只有用户发言可以影响到Value值变化
            self._last_choice = ""
            return
        last_content = memory.get_last_content(conversations)
        question = f"""分析{conversations_str}中{memory.assistant_name}对{memory.user_name}说{last_content}的含义，最符合列表中哪一个选项？请确认输出的选项在选项列表中，完全相同。"""
        options = list(self._actions_type.keys())

        result = await self._generator.select_from_list(question, options)
        if result in self._actions_type:
            self._last_choice = result
            self._change_manner_value(self._actions_type[result])
        else:
            self._last_choice = ""

    def add_manner_value(self, content: str) -> str:
        value_change = self._actions_type[self._last_choice]
        if value_change > 0:
            value_change_str = f" {self._last_choice} +{value_change}"
        elif value_change < 0:
            value_change_str = f" {self._last_choice} {value_change}"
        else:
            return content  # 非user发言以及未知的情况不添加该数值栏位
        content = f"{content}\n【💕值：{self._value}{value_change_str}】"
        return content

    def get_manner_description(self) -> str:
        for description in self._manner_descriptions:
            if self._value <= description["max"]:
                return description["description"]
        return "正常相处"

    def _change_manner_value(self, amount: int):
        self._value = max(0, min(10000, self._value + amount))
        self._save_value_to_status_file()

    def _save_value_to_status_file(self):
        with open(self._status_file, 'w') as file:
            json.dump({"value": self._value}, file)

    def reset_value(self):
        self._value = 0
