import typing
from pkg.core import app
from plugins.Waifu.cells.generator import Generator
from plugins.Waifu.organs.memories import Memory
from plugins.Waifu.cells.cards import Cards
from pkg.provider import entities as llm_entities


class Thoughts:

    ap: app.Application

    def __init__(self, ap: app.Application):
        self.ap = ap
        self._generator = Generator(ap)

    async def _analyze_person_conversations(self, memory: Memory, profile: str, background: str, manner: str) -> str:
        conversations = memory.short_term_memory[-memory.analyze_max_conversations :]
        speakers, conversations_str = memory.get_conversations_str_for_person(conversations)

        last_role = memory.get_last_role(conversations)
        last_content = memory.get_last_content(conversations)
        last_speaker = memory.get_last_speaker(conversations)
        user_prompt = f"这是之前记录：“{conversations_str}”。"
        if profile or background:
            user_prompt += f"这是{memory.assistant_name}的角色设定“{profile}{background}”。"
        if manner:
            user_prompt += f"这是你的行为准则“{manner}”。"
        if last_role == "narrator":
            user_prompt += f"""分析之前记录中“{last_content}”里“{"、".join(speakers)}”之间的行为及事件。"""
        else:
            user_prompt += f"分析之前记录中{last_speaker}对{memory.assistant_name}说“{last_content}”的意图。"
        time = self._generator.get_chinese_current_time()
        user_prompt += f"""确保分析是站在{memory.assistant_name}的角度思考。确保分析简明扼要，意图明确。确保分析考虑到当前时间是{time}，并且应符合{memory.assistant_name}的角色设定。只提供{memory.max_thinking_words}字以内的分析结果，不需要其他说明。"""
        self._generator.set_speakers(speakers)
        analysis_result = await self._generator.return_string(user_prompt)
        return analysis_result

    async def generate_person_prompt(self, memory: Memory, card: Cards) -> typing.Tuple[str, str]:
        conversations = memory.short_term_memory
        _, conversations_str = memory.get_conversations_str_for_person(conversations)
        user_prompt = f"这是之前记录：“{conversations_str}”。"
        analysis = ""

        last_speaker = memory.get_last_speaker(conversations)
        last_role = memory.get_last_role(conversations)
        last_content = memory.get_last_content(conversations)

        if memory.conversation_analysis_flag:
            profile = memory.to_custom_names(card.get_profile())
            background = memory.to_custom_names(card.get_background())
            manner = memory.to_custom_names(card.get_manner())
            analysis = await self._analyze_person_conversations(memory, profile, background, manner)

            if last_role == "narrator":
                user_prompt += f"你要作为{memory.assistant_name}根据最后发生的事情“{last_content}”参考分析结果“{analysis}”对{last_speaker}做出符合{memory.assistant_name}角色设定的回复。"
            else:
                user_prompt += f"你要作为{memory.assistant_name}参考分析结果“{analysis}”对{last_speaker}做出符合{memory.assistant_name}角色设定的回复。"
        else:
            if last_role == "narrator":
                user_prompt += f"你要作为{memory.assistant_name}根据最后发生的事情“{last_content}”做出符合{memory.assistant_name}角色设定的回复。"
            else:
                user_prompt += f"你要作为{memory.assistant_name}对{last_speaker}做出符合{memory.assistant_name}角色设定的回复。"

        time = self._generator.get_chinese_current_time()
        user_prompt += f"确保回复时考虑到当前时间是{time}，并且应符合{memory.assistant_name}的角色设定。确保回复充分体现{memory.assistant_name}的性格特征和情感反应。"
        user_prompt += f"只提供{memory.assistant_name}的回复内容，不需要其他说明。"

        return user_prompt, analysis

    async def generate_character_prompt(self, memory: Memory, card: Cards, character: str) -> typing.Tuple[str, str]:
        unsupport_list = [f"{memory.assistant_name.lower()}", "assistant", "旁白", "narrator"]
        if character.lower() in unsupport_list:
            return ""
        profile = memory.to_custom_names(card.get_profile() + card.get_background() + card.get_manner())
        # 其他角色的人称需要额外处理
        profile = profile.replace("你", memory.assistant_name)
        profile = profile.replace("我", memory.user_name)

        conversations = memory.short_term_memory
        _, conversations_str = memory.get_conversations_str_for_person(conversations)

        user_prompt = ""
        if profile:
            user_prompt += f"这是{memory.assistant_name}的角色设定“{profile}”。"
        user_prompt += f"这是之前记录：“{conversations_str}”。你需要依据{memory.assistant_name}角色设定和上下文推测{character}和{memory.assistant_name}之间的关系以及{character}的角色设定。"

        last_role = memory.get_last_role(conversations)
        last_content = memory.get_last_content(conversations)

        if last_role == "narrator":
            user_prompt += f"你要作为{character}根据最后发生的事情“{last_content}”对{memory.assistant_name}做出符合{character}角色设定的回复。"
        else:
            user_prompt += f"你要作为{character}对{memory.assistant_name}做出符合{character}角色设定的回复。"
        user_prompt += f"只提供{character}的回复内容，不需要其他说明。"

        return user_prompt

    async def generate_person_continue_prompt(self, memory: Memory) -> str:
        conversations = memory.short_term_memory
        _, conversations_str = memory.get_conversations_str_for_person(conversations)
        last_speaker = memory.get_last_speaker(conversations)
        last_content = memory.get_last_content(conversations)
        user_prompt = f"这是之前记录：“{conversations_str}”。你要作为{memory.assistant_name}在对{last_speaker}说完“{last_content}”后继续对{last_speaker}做出符合{memory.assistant_name}角色设定的回复。回复应与“{last_content}”自然的衔接。"
        user_prompt += f"确保回复符合{memory.assistant_name}角色设定。确保回复充分体现{memory.assistant_name}的性格特征和情感反应。确保回复与“{last_content}”不雷同。确保回复开头没有使用“好的，”、“{memory.user_name}，”等形式。"
        user_prompt += f"只提供{memory.assistant_name}的回复内容，不需要其他说明。"

        return user_prompt

    async def _analyze_group_conversations(self, memory: Memory, profile: str, background: str) -> str:
        conversations = memory.short_term_memory[-memory.analyze_max_conversations :]
        user_prompt = ""
        if profile or background:
            user_prompt += f"这是{memory.assistant_name}的角色设定“{profile}{background}”。"
        user_prompt += f"""站在{memory.assistant_name}的角度分析群聊消息记录“{memory.get_conversations_str_for_group(conversations)}”群友们的意图。"""
        user_prompt += f"""消息格式为群友昵称说：“”。确保分析简明扼要，意图明确。只提供{memory.max_thinking_words}字以内的分析结果，不需要其他说明。"""

        self._generator.set_speakers([memory.assistant_name])
        analysis_result = await self._generator.return_string(user_prompt)
        return analysis_result

    async def generate_group_prompt(self, memory: Memory, card: Cards, unreplied_count: int) -> typing.Tuple[str, str]:
        conversations = memory.short_term_memory
        count, unreplied_conversations = memory.get_unreplied_msg(unreplied_count)
        replied_conversations = conversations[:-count]

        unreplied_conversations_str = memory.get_conversations_str_for_group(unreplied_conversations)
        replied_conversations_str = memory.get_conversations_str_for_group(replied_conversations)

        user_prompt = ""
        analysis = ""
        if replied_conversations_str:
            user_prompt += f"这是之前群聊消息记录“{replied_conversations_str}”，"

        if memory.conversation_analysis_flag:
            profile = memory.to_custom_names(card.get_profile())
            background = memory.to_custom_names(card.get_background())
            analysis = await self._analyze_group_conversations(memory, profile, background)
            user_prompt += f"这是未回复的群聊消息记录“{unreplied_conversations_str}”。消息格式为群友昵称说：“”。你要作为{memory.assistant_name}参考群聊消息记录分析结果“{analysis}”对未回复的群聊消息记录做出符合{memory.assistant_name}角色设定的回复。确保回复充分体现{memory.assistant_name}的性格特征和情感反应。"
        else:
            user_prompt += f"这是未回复的群聊消息记录“{unreplied_conversations_str}”。消息格式为群友昵称说：“”。你要作为{memory.assistant_name}对未回复的群聊消息记录做出符合{memory.assistant_name}角色设定的回复。确保回复充分体现{memory.assistant_name}的性格特征和情感反应。"

        user_prompt += f"不称呼群友昵称，使用你或你们代指群友。只提供{memory.assistant_name}的回复内容，不需要消息记录格式。"

        return user_prompt, analysis

    async def analyze_picture(self, content_list: list[llm_entities.ContentElement]) -> str:
        text_msg = ""
        new_content_list = []
        user_prompt = f"""查看以下图片，并用详细的文字描述图片中的人物、物体、环境、背景、颜色和动作等细节。如果图片中有文字，指出并转录这些文字。尽可能详细地描述每个细节，包括颜色、形状、尺寸、位置等。确保描述中没有主观评价，只包含客观的观察。只提供50字以内的描述，不需要其他说明。"""
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
                    self.ap.logger.info(f"image base64: {b64_str[:10]}...")
        analysis = await self._generator.return_image(new_content_list)
        msg = f"发送了图片:“{analysis}”。"
        if text_msg:
            msg += text_msg
        return msg

    def set_jail_break(self, type: str, user_name: str):
        self._generator.set_jail_break(type, user_name)
