import typing
from pkg.plugin.context import APIHost
from plugins.Waifu.cells.generator import Generator
from plugins.Waifu.organs.memories import Memory


class Thoughts:
    def __init__(self, host: APIHost):
        self.host = host
        self.ap = host.ap
        self._generator = Generator(host)

    async def _analyze_person_conversations(self, memory: Memory, background: str) -> str:
        conversations = memory.short_term_memory[-memory.analyze_max_conversations:]
        speakers, conversations_str = memory.get_conversations_str_for_person(conversations)

        last_role = memory.get_last_role(conversations)
        last_content = memory.get_last_content(conversations)
        user_prompt = f"参考{memory.assistant_name}的背景设定：“{background}”，请站在{memory.assistant_name}的角度"
        if last_role == "narrator":
            user_prompt += f"""分析“{conversations_str}”中“{last_content}”里“{"、".join(speakers)}”之间的行为及事件。"""
        else:
            user_prompt += f"分析“{conversations_str}”中{memory.assistant_name}听到{last_role}说“{last_content}”的心理活动。"

        user_prompt += f"""确保分析是站在{memory.assistant_name}的角度思考。确保分析简明扼要，意图明确。只提供30字以内的分析内容，不需要其他说明。"""
        analysis_result = await self._generator.return_string(user_prompt)
        return analysis_result

    async def generate_person_prompt(self, memory: Memory, background: str, rules: str) -> typing.Tuple[str, str]:
        conversations = memory.short_term_memory
        analysis = await self._analyze_person_conversations(memory, background)
        _, conversations_str = memory.get_conversations_str_for_person(conversations)
        user_prompt = f"这是之前的记录：“{conversations_str}”，你的思绪：“{analysis}”。你作为{memory.assistant_name}，"

        last_speaker = memory.get_last_speaker(conversations)
        last_role = memory.get_last_role(conversations)
        last_content = memory.get_last_content(conversations)

        if last_role == "narrator":
            user_prompt += f"你根据最后发生的事情“{last_content}”对{last_speaker}做出适当的回复。"
        else:
            user_prompt += f"你要对{last_speaker}说的“{last_content}”对{last_speaker}做出适当的回复。"

        if background:
            user_prompt += f"请确认你记得你的背景“{background}”,"
        if rules:
            user_prompt += rules
        user_prompt += "只提供回复内容，不需要其他说明。"

        return user_prompt, analysis

    async def _analyze_group_conversations(self, memory: Memory, background: str) -> str:
        conversations = memory.short_term_memory[-memory.analyze_max_conversations :]
        user_prompt = f"""参考{memory.assistant_name}的背景设定：“{background}”，请站在{memory.assistant_name}的角度分析“{memory.get_conversations_str_for_group(conversations)}”中{memory.assistant_name}的心理活动。"""
        user_prompt += f"""确保分析是站在{memory.assistant_name}的角度思考。确保分析简明扼要，意图明确。只提供30字以内的分析内容，不需要其他说明。"""

        analysis_result = await self._generator.return_string(user_prompt)
        return analysis_result

    async def generate_group_prompt(self, memory: Memory, background: str, rules: str, unreplied_msg: int) -> typing.Tuple[str, str]:
        conversations = memory.short_term_memory
        count, unreplied_conversations = memory.get_unreplied_msg(unreplied_msg)
        replied_conversations = conversations[:-count]

        unreplied_conversations_str = memory.get_conversations_str_for_group(unreplied_conversations)
        replied_conversations_str = memory.get_conversations_str_for_group(replied_conversations)

        analysis = await self._analyze_group_conversations(memory, background)
        user_prompt = ""
        if replied_conversations_str:
            user_prompt += f"这是之前的群聊消息记录“{replied_conversations_str}”，"
        user_prompt += f"这是未回复的群聊消息记录“{unreplied_conversations_str}”，你的思绪：“{analysis}”。请作为{memory.assistant_name}，根据以上信息，对未回复的群聊消息记录做出适当回复。"
        if background:
            user_prompt += f"请确认你记得你的背景“{background}”,"
        if rules:
            user_prompt += rules
        user_prompt += "只提供回复内容，不需要其他说明。"

        return user_prompt, analysis
