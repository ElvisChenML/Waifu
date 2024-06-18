import json
import typing
import re
from pkg.plugin.context import APIHost
from pkg.provider import entities as llm_entities
from pkg.core.bootutils import config


class Generator:
    def __init__(self, host: APIHost):
        self.host = host
        self.ap = host.ap
        self._user_name = "用户"
        self._assistant_name = "助手"

    def get_full_prompts(
        self, user_prompt: str, conversations: typing.List[llm_entities.Message] = [], output_format: str = "JSON list", system_prompt: str = None
    ) -> typing.List[llm_entities.Message]:
        messages = []
        if system_prompt:
            messages.append(llm_entities.Message(role="system", content=system_prompt))

        task = {
            "task": user_prompt,
            "output_format": output_format,
        }
        if conversations:
            conversations_str = [message.readable_str() for message in conversations]
            task["conversations"] = conversations_str

        task_json = json.dumps(task, ensure_ascii=False)
        messages.append(llm_entities.Message(role="user", content=task_json.strip()))
        return messages

    def get_chat_prompts(self, user_prompt: str, system_prompt: str = None) -> typing.List[llm_entities.Message]:
        messages = []
        if system_prompt:
            messages.append(llm_entities.Message(role="system", content=system_prompt))
        messages.append(llm_entities.Message(role="user", content=user_prompt))
        return messages

    async def select_from_list(self, question: str, options: list, conversations: typing.List[llm_entities.Message] = [], system_prompt: str = None) -> str:
        model_info = await self.ap.model_mgr.get_model_by_name(self.ap.provider_cfg.data["model"])
        prompt = f"""Please select the most suitable option from the given list based on the question. Question: {question} List: {options}. Ensure your answer contains only one option from the list and no additional explanation or context."""
        messages = self.get_full_prompts(prompt, conversations, output_format="text", system_prompt=system_prompt)

        response = await model_info.requester.call(model=model_info, messages=messages)
        cleaned_response = self.clean_response(response.readable_str())

        self.ap.logger.info("Current prompts: \n{}".format(self.messages_to_readable_str(messages)))
        self.ap.logger.info("response: {}".format(cleaned_response))

        return cleaned_response

    async def return_list(self, question: str, conversations: typing.List[llm_entities.Message] = [], system_prompt: str = None, generate_tags: bool = False) -> list:
        model_info = await self.ap.model_mgr.get_model_by_name(self.ap.provider_cfg.data["model"])
        prompt = f"""Please design a list of types based on the question and return the answer in JSON list format. Question: {question} Ensure your answer is strictly in JSON list format, for example: ["Type1", "Type2", ...]."""
        messages = self.get_full_prompts(prompt, conversations, output_format="JSON list", system_prompt=system_prompt)

        response = await model_info.requester.call(model=model_info, messages=messages)
        cleaned_response = self.clean_response(response.readable_str())

        self.ap.logger.info("Current prompts: \n{}".format(self.messages_to_readable_str(messages)))
        self.ap.logger.info("response: {}".format(cleaned_response))

        return self._parse_json_list(cleaned_response, generate_tags)

    async def return_number(self, question: str, conversations: typing.List[llm_entities.Message] = [], system_prompt: str = None) -> int:
        model_info = await self.ap.model_mgr.get_model_by_name(self.ap.provider_cfg.data["model"])
        prompt = f"""Please determine the numeric answer based on the question and return the answer as a number. Ensure your answer is a single number with no additional explanation or context. Question: {question}"""
        messages = self.get_full_prompts(prompt, conversations, output_format="number", system_prompt=system_prompt)

        response = await model_info.requester.call(model=model_info, messages=messages)
        cleaned_response = self.clean_response(response.readable_str())

        self.ap.logger.info("Current prompts: \n{}".format(self.messages_to_readable_str(messages)))
        self.ap.logger.info("response: {}".format(cleaned_response))

        return self._parse_number(cleaned_response)

    async def return_string(self, question: str, conversations: typing.List[llm_entities.Message] = [], system_prompt: str = None) -> str:
        model_info = await self.ap.model_mgr.get_model_by_name(self.ap.provider_cfg.data["model"])
        messages = self.get_full_prompts(question, conversations, output_format="text", system_prompt=system_prompt)

        response = await model_info.requester.call(model=model_info, messages=messages)
        cleaned_response = self.clean_response(response.readable_str())

        self.ap.logger.info("Current prompts: \n{}".format(self.messages_to_readable_str(messages)))
        self.ap.logger.info("response: {}".format(cleaned_response))

        return cleaned_response

    async def return_chat(self, request: str, system_prompt: str = None) -> str:
        model_info = await self.ap.model_mgr.get_model_by_name(self.ap.provider_cfg.data["model"])
        messages = self.get_chat_prompts(request, system_prompt)

        response = await model_info.requester.call(model=model_info, messages=messages)
        cleaned_response = self.clean_response(response.readable_str())

        self.ap.logger.info("Current prompts: \n{}".format(self.messages_to_readable_str(messages)))
        self.ap.logger.info("response: {}".format(cleaned_response))

        return cleaned_response

    def clean_response(self, response: str) -> str:
        colon_index = response.find(": ")
        if colon_index != -1:
            return response[colon_index + 2 :]
        else:
            self.ap.logger.info("Unexpected reply: {}".format(response))
            return "Unexpected reply"

    async def set_character(self, character: str):
        self._character_config = await config.load_json_config(
            f"plugins/Waifu/water/cards/{character}.json",
            "plugins/Waifu/water/templates/default_card.json",
            completion=False,
        )
        system_prompt = self._character_config.data.get("system_prompt", {})
        self._user_name = system_prompt.get("user_name", "用户")
        self._assistant_name = system_prompt.get("assistant_name", "助手")

    def set_names(self, user_name: str, assistant_name: str):
        self._user_name = user_name
        self._assistant_name = assistant_name

    def _parse_json_list(self, response: str, generate_tags: bool = False) -> list:
        try:
            # Fix unbalanced square brackets and quotes in the whole response
            if not self._is_balanced(response, "[", "]"):
                response += "]"

            start_index = response.find("[")
            end_index = response.rfind("]") + 1

            if start_index == -1 or end_index == 0:
                self.ap.logger.info("No valid JSON array found in the response")
                return []

            # Extract the JSON part of the response
            json_str = response[start_index:end_index]

            json_str = re.sub(r",\s*(?=])", "", json_str)  # Remove trailing commas before closing bracket
            json_str = re.sub(r"[^\u4e00-\u9fa5A-Za-z\s\[\],\":]", " ", json_str).strip()  # Remove invalid characters and strip

            parsed_list = json.loads(json_str)

            if isinstance(parsed_list, list):
                if generate_tags:
                    # In terms of tag generation, the tested deepseek behaves abnormally unstable, and other models may also be unstable. Splitting into single words is a compromise.
                    unique_tags = {word.strip() for tag in parsed_list for word in tag.split() if word.strip()}
                    return list(unique_tags)
                else:
                    return parsed_list
            else:
                self.ap.logger.info("Parsed JSON is not a list: {}".format(parsed_list))
                return []
        except json.JSONDecodeError as e:
            self.ap.logger.info(f"JSON Decode Error: {e} | Response: {response}")
            return []

    def _parse_number(self, response: str) -> int:
        try:
            return int(response)
        except ValueError:
            self.ap.logger.info("Value Error: {}".format(response))
            return 0

    def _is_balanced(self, string: str, open_char: str, close_char: str) -> bool:
        return string.count(open_char) == string.count(close_char)

    def messages_to_readable_str(self, messages: typing.List[llm_entities.Message]) -> str:
        return "\n".join(message.readable_str() for message in messages)

    def get_conversations_str_for_prompt(self, conversations: typing.List[llm_entities.Message]) -> typing.Tuple[typing.List[str], str]:
        speakers = []
        conversations_str = ""
        for message in conversations:
            role = self.to_custom_names(message.role)
            # 提取括号后的内容
            content = str(message.get_content_mirai_message_chain()).split("] ", 1)[-1]

            if role == "narrator":
                conversations_str += f"然后{content}，"
            else:
                listener = self._assistant_name
                if speakers:  # 聆听者为上一个发言者
                    listener = speakers[-1]
                elif role == self._assistant_name:
                    listener = self._user_name
                conversations_str += f"{role}对{listener}说：“{content}”，"
                if role in speakers: # 该容器兼顾保存最后一个发言者，不是单纯的set
                    speakers.remove(role)
                speakers.append(role)
        return speakers, conversations_str

    def get_last_speaker(self, conversations: typing.List[llm_entities.Message]) -> str:
        for message in reversed(conversations):
            if message.role not in {"narrator", "assistant"}:
                return self.to_custom_names(message.role)
        return ""

    def get_last_role(self, conversations: typing.List[llm_entities.Message]) -> str:
        return self.to_custom_names(conversations[-1].role) if conversations else ""

    def get_last_content(self, conversations: typing.List[llm_entities.Message]) -> str:
        return str(conversations[-1].get_content_mirai_message_chain()).split("] ", 1)[-1] if conversations else ""

    def to_custom_names(self, text: str) -> str:
        text = text.replace("User", self._user_name)
        text = text.replace("user", self._user_name)
        text = text.replace("用户", self._user_name)
        text = text.replace("Assistant", self._assistant_name)
        text = text.replace("assistant", self._assistant_name)
        text = text.replace("助理", self._assistant_name)
        return text

    def to_generic_names(self, text: str) -> str:
        text = text.replace("User", "user")
        text = text.replace("用户", "user")
        text = text.replace("Assistant", "assistant")
        text = text.replace("助理", "assistant")
        text = text.replace(self._user_name, "user")
        text = text.replace(self._assistant_name, "assistant")
        return text
