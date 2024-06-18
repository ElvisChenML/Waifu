import typing
import json
from plugins.Waifu.cells.generator import Generator
from pkg.plugin.context import APIHost
from pkg.provider import entities as llm_entities
from pkg.core.bootutils import config


class ValueGame:
    def __init__(self, host: APIHost):
        self.host = host
        self.ap = host.ap
        self._generator = Generator(host)
        self._value = 0
        self._manner_descriptions = []
        self._actions_type = {}
        self._last_choice = ""
        self._character_config_path = ""
        self._value_game_max_conversations = 9
        self._user_name = "用户"
        self._assistant_name = "助手"

    async def load_config(self):
        self._config = await config.load_json_config(
            "plugins/Waifu/water/config/waifu.json",
            "plugins/Waifu/water/templates/waifu.json",
            completion=False,
        )
        self._value_game_conversations = self._config.data.get("value_game_conversations", 5)
        character = self._config.data["character"]
        self._character_config_path = f"plugins/Waifu/water/cards/{character}.json"
        self._character_config = await config.load_json_config(
            self._character_config_path,
            "plugins/Waifu/water/templates/default_card.json",
            completion=False,
        )
        manner = self._character_config.data.get("manner", {})
        self._value = manner.get("value", 0)
        self._manner_descriptions = manner.get("value_descriptions", [])
        self._actions_type = {action["type"]: action["value_change"] for action in manner.get("actions_type", [])}
        self._actions_type[""] = 0
        system_prompt = self._character_config.data.get("system_prompt", {})
        self._user_name = system_prompt.get("user_name", "用户")
        self._assistant_name = system_prompt.get("assistant_name", "助手")
        self._generator.set_names(self._user_name, self._assistant_name)

    async def determine_manner_change(self, conversations: typing.List[llm_entities.Message]):
        conversations = conversations[-self._value_game_max_conversations:]
        _, conversations_str = self._generator.get_conversations_str_for_prompt(conversations)
        last_speaker = self._generator.get_last_speaker(conversations)
        if last_speaker != self._user_name: # 只有用户发言可以影响到Value值变化
            self._last_choice = ""
            return
        last_content = self._generator.get_last_content(conversations)
        question = f"""分析{conversations_str}中{self._assistant_name}对{self._user_name}说{last_content}的含义，最符合列表中哪一个选项？请确认输出的选项在选项列表中，完全相同。"""
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
        self._save_value_to_config()

    def _save_value_to_config(self):
        if not self._character_config_path:
            return
        self._character_config.data["manner"]["value"] = self._value
        with open(self._character_config_path, "w", encoding="utf-8") as f:
            json.dump(self._character_config.data, f, ensure_ascii=False, indent=4)

    def reset_value(self):
        self._value = 0
        self._save_value_to_config()
