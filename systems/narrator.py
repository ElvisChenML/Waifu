import typing
import json
import math
from datetime import datetime
from pkg.plugin.context import APIHost
from pkg.core.bootutils import config
from pkg.provider import entities as llm_entities
from plugins.Waifu.cells.generator import Generator
from plugins.Waifu.organs.memories import Memory


class Narrator:

    def __init__(self, host: APIHost, launcher_id: str):
        self.host = host
        self.ap = host.ap
        self._generator = Generator(host)
        self._life_data_file = f"plugins/Waifu/water/data/life_{launcher_id}.json"
        self._profile = ""
        self._action = ""
        self._life_data = {}

    async def load_config(self):
        self._load_life_data()

    async def narrate(self, memory: Memory, profile: str) -> str:
        conversations = memory.short_term_memory[-memory.narrate_max_conversations :]

        time_text, description = await self.get_assistant_life_description(profile)
        user_prompt = f"""现在是{time_text}，{memory.assistant_name}往常这时候在“{description}。”"""

        speakers, conversations_str = memory.get_conversations_str_for_person(conversations)
        last_role = memory.get_last_role(conversations)
        if last_role == "narrator":
            user_prompt += f"""续写“{conversations_str}”中“{"、".join(speakers)}”之后的身体动作。"""
        else:
            user_prompt += f"""分析“{conversations_str}”中{"、".join(speakers)}的身体动作并续写之后的身体动作。"""
        user_prompt += f"""不需要描述目前的身体动作，续写应与目前身体动作自然的衔接。每个身体动作都应以{"、".join(speakers)}其中一个开头，明确谁在进行身体动作。”。续写应富有创意、明确且诱人。只提供一个30字以内的身体动作描述，不需要其他说明。不可以在续写中替“{"、".join(speakers)}”发言。"""
        self._action = await self._generator.return_string(user_prompt)
        return self._action

    def get_action(self) -> str:
        return self._action

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

    async def _generate_life_description(self, profile: str, time_text: str):
        user_prompt = f"""作为“{profile}”在{time_text}时往常会在哪里？只提供位置名称，不需要任何解释。"""
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

    async def get_assistant_life_description(self, profile: str) -> typing.Tuple[str, str]:
        current_time_text = self._get_current_time_text()
        if current_time_text not in self._life_data:
            await self._generate_life_description(profile, current_time_text)
        description = self._life_data.get(current_time_text, "")
        return current_time_text, description

    def get_time_table(self) -> str:
        time_table = ""
        for time_text, description in self._life_data.items():
            time_table += f"{time_text}: {description}\n"
        return time_table
