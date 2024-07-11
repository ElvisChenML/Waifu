import typing
from pkg.plugin.context import APIHost
from plugins.Waifu.cells.generator import Generator
from plugins.Waifu.organs.memories import Memory
from plugins.Waifu.cells.cards import Cards
from pkg.provider import entities as llm_entities

class Thoughts:
    def __init__(self, host: APIHost):
        self.host = host
        self.ap = host.ap
        self._generator = Generator(host)

    async def _analyze_person_conversations(self, memory: Memory, profile: str, background: str) -> str:
        conversations = memory.short_term_memory[-memory.analyze_max_conversations:]
        speakers, conversations_str = memory.get_conversations_str_for_person(conversations)

        last_role = memory.get_last_role(conversations)
        last_content = memory.get_last_content(conversations)
        user_prompt = ""
        if profile:
            user_prompt += profile
        if background:
            user_prompt += background
        user_prompt += f"请作为{memory.assistant_name}"
        if last_role == "narrator":
            user_prompt += f"""分析“{conversations_str}”中“{last_content}”里“{"、".join(speakers)}”之间的行为及事件。"""
        else:
            user_prompt += f"分析“{conversations_str}”中{memory.assistant_name}听到{last_role}说“{last_content}”的心理活动。"

        user_prompt += f"""确保分析是站在{memory.assistant_name}的角度思考。确保分析简明扼要，意图明确。只提供30字以内的分析内容，不需要其他说明。"""
        analysis_result = await self._generator.return_string(user_prompt)
        return analysis_result

    async def generate_person_prompt(self, memory: Memory, card: Cards) -> typing.Tuple[str, str]:
        conversations = memory.short_term_memory
        profile = card.get_profile()
        background = card.get_background()
        rules = card.get_rules()
        analysis = await self._analyze_person_conversations(memory, profile, background)
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
        user_prompt += f"只提供{memory.assistant_name}的发言内容，不需要其他说明。"

        return user_prompt, analysis

    async def _analyze_group_conversations(self, memory: Memory, profile: str, background: str) -> str:
        conversations = memory.short_term_memory[-memory.analyze_max_conversations :]
        user_prompt = ""
        if profile:
            user_prompt += profile
        if background:
            user_prompt += background
        user_prompt += f"""请站在{memory.assistant_name}的角度分析{memory.assistant_name}看完群聊消息记录“{memory.get_conversations_str_for_group(conversations)}”后的心理活动。"""
        user_prompt += f"""消息格式为群友昵称说：“”。确保分析是站在{memory.assistant_name}的角度思考。确保分析简明扼要，意图明确。只提供30字以内的分析内容，不需要其他说明。"""

        analysis_result = await self._generator.return_string(user_prompt)
        return analysis_result

    async def generate_group_prompt(self, memory: Memory, card: Cards, unreplied_count: int) -> typing.Tuple[str, str]:
        conversations = memory.short_term_memory
        count, unreplied_conversations = memory.get_unreplied_msg(unreplied_count)
        replied_conversations = conversations[:-count]

        profile = card.get_profile()
        background = card.get_background()
        rules = card.get_rules()

        unreplied_conversations_str = memory.get_conversations_str_for_group(unreplied_conversations)
        replied_conversations_str = memory.get_conversations_str_for_group(replied_conversations)

        analysis = await self._analyze_group_conversations(memory, profile, background)
        user_prompt = ""
        if replied_conversations_str:
            user_prompt += f"这是之前的群聊消息记录“{replied_conversations_str}”，"
        user_prompt += f"这是未回复的群聊消息记录“{unreplied_conversations_str}”，你的思绪：“{analysis}”。消息格式为群友昵称说：“”。请作为{memory.assistant_name}，根据以上信息，对未回复的群聊消息记录做出适当回复。"
        if background:
            user_prompt += f"请确认你记得你的背景“{background}”,"
        if rules:
            user_prompt += rules
        user_prompt += f"不称呼群友昵称，使用你或你们代指群友。只提供{memory.assistant_name}的发言内容，不需要消息记录格式。"

        return user_prompt, analysis

    async def analyze_picture(self, content_list: list[llm_entities.ContentElement]) -> str:
        text_msg = ""
        new_content_list = []
        user_prompt = f"""请查看以下图片，并用详细的文字描述图片中的人物、物体、环境、背景、颜色和动作等细节。如果图片中有文字，请指出并转录这些文字。尽可能详细地描述每个细节，包括颜色、形状、尺寸、位置等。确保描述中没有主观评价，只包含客观的观察。只提供50字以内的描述，不需要其他说明。"""
        new_content_list.append(llm_entities.ContentElement.from_text(user_prompt))
        for ce in content_list:
            if ce.type == "text" and ce.text:
                if text_msg:
                    text_msg += " "
                text_msg += ce.text
            elif ce.type == "image_url":
                new_content_list.append(ce)
                if ce.image_url.url.startswith("http"):
                    self.ap.logger.info(f"image url: {ce.image_url.url}")
                else:  # base64
                    b64_str = ce.image_url.url
                    if b64_str.startswith("data:"):
                        b64_str = b64_str.split(",")[1]
                    self.ap.logger.info(f"image b64: {b64_str}")
        analysis = await self._generator.return_image(new_content_list)
        msg = f"发送了图片:“{analysis}”。" 
        if text_msg:
            msg += text_msg
        return msg
