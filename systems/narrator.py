import typing
import json
import math
from datetime import datetime
from pkg.plugin.context import APIHost
from pkg.core.bootutils import config
from pkg.provider import entities as llm_entities
from plugins.Waifu.cells.generator import Generator


class Narrator:
    def __init__(self, host: APIHost):
        self.host = host
        self.ap = host.ap
        self._generator = Generator(host)
        self._user_name = "用户"
        self._assistant_name = "助手"
        self._life_data_file = "plugins/Waifu/water/data/life.json"
        self._profile = ""
        self._action = ""
        self._life_data = {}
        self._narrat_max_conversations = 8

    async def load_config(self, profile: str):
        self._config = await config.load_json_config(
            "plugins/Waifu/water/config/waifu.json",
            "plugins/Waifu/water/templates/waifu.json",
            completion=False,
        )
        self._narrat_max_conversations = self._config.data.get("narrat_max_conversations", 8)
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
        self._profile = profile
        self._load_life_data()

    async def narrate(self, conversations: typing.List[llm_entities.Message]) -> str:
        return await self._narrate_simple(conversations)

    async def _narrate_simple(self, conversations: typing.List[llm_entities.Message]) -> str:
        conversations = conversations[-self._narrat_max_conversations:]
        self._action = await self.analyze_current_action(conversations)
        self.ap.logger.info("current_action: {}".format(self._action))
        narration = await self._narrate_by_action(conversations)
        return narration

    async def _narrate_by_action(self, conversations: typing.List[llm_entities.Message]) -> str:
        system_prompt = """你的存在只是为了通过100字以内的描述性文字推动故事发展，你会积极推进故事并引入意外和不可预测的元素。你不会总结过去事件，只会描述新的行为。你会不惜一切代价避免重复，不会重复已经描述过的行为或想法。你只会描述场景中的可观察行为。你会确保你的描述在考虑时间因素和对话上下文后感觉自然。"""

        _, conversations_str = self._generator.get_conversations_str_for_prompt(conversations)
        user_prompt = f"""对互动“{self._action}”进行简短描述。请确认描述与记录“{conversations_str}”情境及语气相符合。你会确保你的描述语句通顺并且在考虑记录上下文后感觉自然。不可以在描述中替role发言。"""

        narration = await self._generator.return_string(user_prompt, [], system_prompt)
        return narration

    def get_action(self) -> str:
        return self._generator.to_custom_names(self._action)

    async def analyze_current_action(self, conversations: typing.List[llm_entities.Message]) -> str:
        time_text, description = await self.get_assistant_life_description()
        user_prompt = f"""现在是{time_text}，{self._assistant_name}往常这时候在“{description}。”"""

        speakers, conversations_str = self._generator.get_conversations_str_for_prompt(conversations)
        last_speaker = self._generator.get_last_speaker(conversations)
        last_role = self._generator.get_last_role(conversations)
        last_content = self._generator.get_last_content(conversations)
        if last_role == "narrator":
            user_prompt += f"""请分析“{conversations_str}”中“{last_content}”里“{"、".join(speakers)}”之间的物理互动，推测并描述他们后续的物理互动。"""
        else:
            user_prompt += f"""请分析“{conversations_str}”中{last_speaker}说“{last_content}”时与{"、".join(speakers)}之间的物理互动，推测并描述他们后续的物理互动。"""

        if self._action:
            user_prompt += f"""描述的物理互动必须与之前发生过的“{self._action}”状态不同。"""
        user_prompt += f"""每个互动都应以“assistant”或{last_speaker}开头，明确谁在进行互动。”。描述应富有创意、明确且诱人。只提供一个30字以内的物理互动描述，不需要其他说明。"""
        analysis_result = await self._generator.return_string(user_prompt)
        return analysis_result

    def _get_time_passed(self, conversations: typing.List[llm_entities.Message]) -> int:
        latest_response = self._generator.clean_response(conversations[-1].readable_str())
        time_str = latest_response.split("]")[0][1:]  # Extract the time part
        latest_time = datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S")
        current_time = datetime.now()
        return math.ceil((current_time - latest_time).total_seconds() / 60)  # Calculate time passed in minutes

    def _get_current_time_text(self) -> str:
        now = datetime.now()
        days = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        day_of_week = days[now.weekday()]
        hour = now.hour
        minute = now.minute

        if 0 <= hour < 6:
            period = f"凌晨{hour}点"
        elif 6 <= hour < 12:
            period = f"上午{hour}点"
        elif 12 <= hour < 14:
            period = f"中午{hour}点"
        elif 14 <= hour < 18:
            period = f"下午{hour-12}点"
        elif 18 <= hour < 21:
            period = f"傍晚{hour-12}点"
        else:
            period = f"晚上{hour-12}点"

        return f"{day_of_week}{period}"

    async def _generate_life_description(self, time_text: str):
        user_prompt = f"""作为“{self._profile}”在{time_text}时往常会在哪里？只提供位置名称，不需要任何解释。"""
        location = await self._generator.return_string(user_prompt, [])
        self._life_data[time_text] = location

        with open(self._life_data_file, "w") as f:
            json.dump(self._life_data, f, ensure_ascii=False, indent=4)

    def _load_life_data(self):
        try:
            with open(self._life_data_file, "r") as f:
                self._life_data = json.load(f)
        except FileNotFoundError:
            self._life_data = {}

    async def get_assistant_life_description(self) -> typing.Tuple[str, str]:
        current_time_text = self._get_current_time_text()
        if current_time_text not in self._life_data:
            await self._generate_life_description(current_time_text)
        description = self._life_data.get(current_time_text, "")
        return current_time_text, description

    def get_time_table(self) -> str:
        time_table = ""
        for time_text, description in self._life_data.items():
            time_table += f"{time_text}: {description}\n"
        return time_table
