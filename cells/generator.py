import json
import typing
import re
import functools
import os
from typing import Any, Coroutine
import asyncio
import yaml
from datetime import datetime
from pkg.core import app
from pkg.plugin.context import APIHost
from pkg.provider import entities as llm_entities
from pkg.provider.modelmgr import errors


def handle_errors(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except errors.RequesterError as e:
            args[0].ap.logger.error(f"请求错误：{e}")
            raise
        except Exception as e:
            args[0].ap.logger.error(f"未处理的异常：{e}")
            raise

    return wrapper


class Generator:
    ap: app.Application

    def __init__(self, ap: app.Application):
        self.ap = ap
        self._jail_break_dict = {}
        self._jail_break_type = ""
        self._speakers = []
        self.model_config_path = "data/plugins/Waifu/config/model_config.yaml"
        self.selected_model_info = None
        self.model_config = {}


    async def _initialize_model_config(self):
        """Loads or creates the model configuration and sets the selected model."""
        await self._load_or_create_model_config()
        await self._set_selected_model()

    async def _load_or_create_model_config(self):
        """加载或创建 model_config.yaml，仅当模型列表变化时才更新"""
        config_dir = os.path.dirname(self.model_config_path)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir, exist_ok=True)

        # 构建新的模型列表数据
        new_model_list_data = []
        default_model_uuid = ""
        if self.ap.model_mgr.llm_models:
            for model_info in self.ap.model_mgr.llm_models:
                base_url = ""
                if model_info.model_entity.requester_config:
                    base_url = model_info.model_entity.requester_config.get('base_url',
                                model_info.model_entity.requester_config.get('api_base_url',
                                model_info.model_entity.requester_config.get('api_base', '')))
                new_model_list_data.append({
                    "model_name": model_info.model_entity.name,
                    "model_uuid": model_info.model_entity.uuid,
                    "model_baseurl": base_url if base_url else ""
                })
            if new_model_list_data:
                default_model_uuid = new_model_list_data[0]["model_uuid"]
        else:
            self.ap.logger.warning("LangBot中没有加载任何可用模型。请先在LangBot中配置模型。")

        old_config = {}
        if os.path.exists(self.model_config_path):
            try:
                with open(self.model_config_path, 'r', encoding='utf-8') as f:
                    old_config = yaml.safe_load(f) or {}
                old_model_list = old_config.get("model_list", [])
                if old_model_list == new_model_list_data:
                    self.ap.logger.info(f"模型列表未发生变化，跳过更新 {self.model_config_path}")
                    self.model_config = old_config
                    return
                else:
                    self.ap.logger.info(f"检测到模型列表变化，将更新配置文件 {self.model_config_path}")
            except Exception as e:
                self.ap.logger.warning(f"读取旧配置失败: {e}，将强制重建配置文件")
        else:
            self.ap.logger.info(f"{self.model_config_path} 不存在，正在创建新的配置文件")

        # 构建新配置并保留原 model_uuid（如果存在）
        new_model_uuid = old_config.get("model_uuid") if old_config else default_model_uuid
        if new_model_uuid not in [m["model_uuid"] for m in new_model_list_data]:
            new_model_uuid = default_model_uuid  # fallback to default if invalid

        self.model_config = {
            "model_uuid": new_model_uuid,
            "model_list": new_model_list_data
        }

        # 写入 YAML 文件
        try:
            with open(self.model_config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.model_config, f, allow_unicode=True, sort_keys=False)
            # 添加注释行
            with open(self.model_config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            with open(self.model_config_path, 'w', encoding='utf-8') as f:
                f.write("# model_uuid: 填写你要使用的模型的UUID，uuid 从下面列表中选择\n")
                f.write(content)
            self.ap.logger.info(f"模型配置文件已更新于 {self.model_config_path}")
            self._set_permissions(self.model_config_path, 0o666)
        except Exception as e:
            self.ap.logger.error(f"写入模型配置文件失败: {e}")

    async def _set_selected_model(self):
        """Sets the model to be used based on the loaded configuration."""
        target_uuid = self.model_config.get("model_uuid")
        self.selected_model_info = None
        if target_uuid:
            for model_info in self.ap.model_mgr.llm_models:
                if model_info.model_entity.uuid == target_uuid:
                    self.selected_model_info = model_info
                    self.ap.logger.info(f"根据配置文件选定模型: {model_info.model_entity.name} (UUID: {target_uuid})")
                    break
            if not self.selected_model_info:
                self.ap.logger.warning(f"配置文件中指定的模型UUID '{target_uuid}' 未在LangBot中找到。")
        if not self.selected_model_info and self.ap.model_mgr.llm_models:
            self.selected_model_info = self.ap.model_mgr.llm_models[0]
            new_selected_uuid = self.selected_model_info.model_entity.uuid
            self.ap.logger.warning(f"将使用LangBot中第一个可用模型: {self.selected_model_info.model_entity.name} (UUID: {new_selected_uuid})")
            if self.model_config.get("model_uuid") != new_selected_uuid:
                self.model_config["model_uuid"] = new_selected_uuid
                try:
                    with open(self.model_config_path, "w", encoding="utf-8") as f:
                        yaml.dump(self.model_config, f, allow_unicode=True, sort_keys=False)
                    self.ap.logger.info(f"模型配置文件 {self.model_config_path} 中的 model_uuid 已更新为 {new_selected_uuid}。")
                    self._set_permissions(self.model_config_path, 0o666)
                except Exception as e:
                    self.ap.logger.error(f"更新模型配置文件 {self.model_config_path} 失败: {e}")
        if not self.selected_model_info:
            self.ap.logger.error(
                "Waifu 插件未能找到或选定任何可用的大语言模型。请确保LangBot中已加载模型，并检查插件配置。")

    def _set_permissions(self, path, mode):
        try:
            os.chmod(path, mode)
        except Exception as e:
            self.ap.logger.warning(f"设置文件权限失败 {path}: {e}")

    def _get_question_prompts(self, user_prompt: str, output_format: str = "JSON list",
                              system_prompt: str = None) -> typing.List[llm_entities.Message]:
        messages = []
        if self._jail_break_type in ["before", "all"] and "before" in self._jail_break_dict:
            messages.append(llm_entities.Message(role="system", content=self._jail_break_dict["before"]))
        if system_prompt:
            messages.append(llm_entities.Message(role="system", content=system_prompt))
        if self._jail_break_type in ["after", "all"] and "after" in self._jail_break_dict:
            messages.append(llm_entities.Message(role="system", content=self._jail_break_dict["after"]))
        task = {
            "task": user_prompt,
            "output_format": output_format,
        }
        user_prompt = json.dumps(task, ensure_ascii=False).strip()
        if self._jail_break_type in ["end", "all"] and "end" in self._jail_break_dict:
            user_prompt += self._jail_break_dict["end"]
        messages.append(llm_entities.Message(role="user", content=user_prompt))
        return messages

    def _get_question_prompts_without_jail_break(self, user_prompt: str, output_format: str = "JSON list",
                                                 system_prompt: str = None) -> typing.List[
        llm_entities.Message]:
        messages = []
        if system_prompt:
            messages.append(llm_entities.Message(role="system", content=system_prompt))
        task = {
            "task": user_prompt,
            "output_format": output_format,
        }
        user_prompt = json.dumps(task, ensure_ascii=False).strip()
        messages.append(llm_entities.Message(role="user", content=user_prompt))
        return messages

    def _get_chat_prompts(self, user_prompt: str | typing.List[llm_entities.Message],
                          system_prompt: str = None) -> typing.List[llm_entities.Message]:
        messages = []
        if self._jail_break_type in ["before", "all"] and "before" in self._jail_break_dict:
            messages.append(llm_entities.Message(role="system", content=self._jail_break_dict["before"]))
        if system_prompt:
            messages.append(llm_entities.Message(role="system", content=system_prompt))
        if self._jail_break_type in ["after", "all"] and "after" in self._jail_break_dict:
            messages.append(llm_entities.Message(role="system", content=self._jail_break_dict["after"]))
        if self._jail_break_type in ["end", "all"] and "end" in self._jail_break_dict:
            if isinstance(user_prompt, list):
                user_prompt[-1].content += self._jail_break_dict["end"]
            else:
                user_prompt += self._jail_break_dict["end"]
        if isinstance(user_prompt, list):
            messages.extend(user_prompt)
        else:
            messages.append(llm_entities.Message(role="user", content=user_prompt))
        return messages

    def _get_image_prompts(self, content_list: list[llm_entities.ContentElement],
                           system_prompt: str = None) -> typing.List[llm_entities.Message]:
        messages = []
        if system_prompt:
            messages.append(llm_entities.Message(role="system", content=system_prompt))
        messages.append(llm_entities.Message(role="user", content=content_list))
        return messages

    @handle_errors
    async def select_from_list(self, question: str, options: list, system_prompt: str = None) -> str:
        if not self.selected_model_info:
            error_msg = "Waifu 插件未能找到或选定任何可用的大语言模型。请确保LangBot中已加载模型，并检查插件配置。"
            self.ap.logger.error(error_msg)
            raise ValueError(error_msg)
        model_info = self.selected_model_info
        self.ap.logger.info(f"Waifu 插件使用模型: {model_info.model_entity.name} (UUID: {model_info.model_entity.uuid})")
        prompt = f"""Please select the most suitable option from the given list based on the question. Question: {question} List: {options}. Ensure your answer contains only one option from the list and no additional explanation or context."""
        messages = self._get_question_prompts(prompt, output_format="text", system_prompt=system_prompt)
        self.ap.logger.info("发送请求：\n{}".format(self.messages_to_readable_str(messages)))
        response = await model_info.requester.invoke_llm(None, model=model_info, messages=messages)
        cleaned_response = self.clean_response(response.content)
        self.ap.logger.info("模型回复：\n{}".format(cleaned_response))
        return cleaned_response

    @handle_errors
    async def return_list(self, question: str, system_prompt: str = None, generate_tags: bool = False) -> list:
        if not self.selected_model_info:
            error_msg = "Waifu 插件未能找到或选定任何可用的大语言模型。请确保LangBot中已加载模型，并检查插件配置。"
            self.ap.logger.error(error_msg)
            raise ValueError(error_msg)

        model_info = self.selected_model_info
        self.ap.logger.info(f"Waifu 插件使用模型: {model_info.model_entity.name} (UUID: {model_info.model_entity.uuid})")

        prompt = f"""Please design a list of types based on the question and return the answer in JSON list format. Question: {question} Ensure your answer is strictly in JSON list format, for example: [\"Type1\", \"Type2\", ...]."""
        messages = self._get_question_prompts(prompt, output_format="JSON list", system_prompt=system_prompt)

        self.ap.logger.info("发送请求：\n{}".format(self.messages_to_readable_str(messages)))

        response = await model_info.requester.invoke_llm(None, model=model_info, messages=messages)
        cleaned_response = self.clean_response(response.content)

        self.ap.logger.info("模型回复：\n{}".format(cleaned_response))
        return self._parse_json_list(cleaned_response, generate_tags)

    @handle_errors
    async def return_json(self, question: str, system_prompt: str = None) -> list:
        if not self.selected_model_info:
            error_msg = "Waifu 插件未能找到或选定任何可用的大语言模型。请确保LangBot中已加载模型，并检查插件配置。"
            self.ap.logger.error(error_msg)
            raise ValueError(error_msg)
        
        model_info = self.selected_model_info
        self.ap.logger.info(f"Waifu 插件使用模型: {model_info.model_entity.name} (UUID: {model_info.model_entity.uuid})")
        
        messages = self._get_question_prompts(question, output_format="JSON", system_prompt=system_prompt)

        self.ap.logger.info("发送请求：\n{}".format(self.messages_to_readable_str(messages)))

        response = await model_info.requester.invoke_llm(None, model=model_info, messages=messages)
        cleaned_response = self.clean_response(response.content)

        self.ap.logger.info("模型回复：\n{}".format(cleaned_response))
        return cleaned_response

    @handle_errors
    async def return_number(self, question: str, system_prompt: str = None) -> int:
        if not self.selected_model_info:
            error_msg = "Waifu 插件未能找到或选定任何可用的大语言模型。请确保LangBot中已加载模型，并检查插件配置。"
            self.ap.logger.error(error_msg)
            raise ValueError(error_msg)
        
        model_info = self.selected_model_info
        self.ap.logger.info(f"Waifu 插件使用模型: {model_info.model_entity.name} (UUID: {model_info.model_entity.uuid})")
        
        prompt = f"""Please determine the numeric answer based on the question and return the answer as a number. Ensure your answer is a single number with no additional explanation or context. Question: {question}"""
        messages = self._get_question_prompts(prompt, output_format="number", system_prompt=system_prompt)

        self.ap.logger.info("发送请求：\n{}".format(self.messages_to_readable_str(messages)))

        response = await model_info.requester.invoke_llm(None, model=model_info, messages=messages)
        cleaned_response = self.clean_response(response.content)

        self.ap.logger.info("模型回复：\n{}".format(cleaned_response))
        return self._parse_number(cleaned_response)

    @handle_errors
    async def return_string(self, question: str, system_prompt: str = None) -> str:
        if not self.selected_model_info:
            error_msg = "Waifu 插件未能找到或选定任何可用的大语言模型。请确保LangBot中已加载模型，并检查插件配置。"
            self.ap.logger.error(error_msg)
            raise ValueError(error_msg)
        
        model_info = self.selected_model_info
        self.ap.logger.info(f"Waifu 插件使用模型: {model_info.model_entity.name} (UUID: {model_info.model_entity.uuid})")
        
        messages = self._get_question_prompts(question, output_format="text", system_prompt=system_prompt)

        self.ap.logger.info("发送请求：\n{}".format(self.messages_to_readable_str(messages)))

        response = await model_info.requester.invoke_llm(None, model=model_info, messages=messages)
        cleaned_response = self.clean_response(response.content)

        self.ap.logger.info("模型回复：\n{}".format(cleaned_response))
        return cleaned_response

    @handle_errors
    async def return_string_without_jail_break(self, question: str, system_prompt: str = None) -> None:
        if not self.selected_model_info:
            error_msg = "Waifu 插件未能找到或选定任何可用的大语言模型。请确保LangBot中已加载模型，并检查插件配置。"
            self.ap.logger.error(error_msg)
            raise ValueError(error_msg)

        model_info = self.selected_model_info
        self.ap.logger.info(
            f"Waifu 插件使用模型: {model_info.model_entity.name} (UUID: {model_info.model_entity.uuid})")

        messages = self._get_question_prompts_without_jail_break(question, output_format="text",
                                                                     system_prompt=system_prompt)

        self.ap.logger.info("发送请求：\n{}".format(self.messages_to_readable_str(messages)))

        response = await model_info.requester.invoke_llm(None, model=model_info, messages=messages)
        cleaned_response = self.clean_response(response.content)

        self.ap.logger.info("模型回复：\n{}".format(cleaned_response))
        return cleaned_response





    @handle_errors
    async def return_image(self, content_list: list[llm_entities.ContentElement], system_prompt: str = None) -> str:
        if not self.selected_model_info:
            error_msg = "Waifu 插件未能找到或选定任何可用的大语言模型。请确保LangBot中已加载模型，并检查插件配置。"
            self.ap.logger.error(error_msg)
            raise ValueError(error_msg)

        model_info = self.selected_model_info
        self.ap.logger.info(f"Waifu 插件使用模型: {model_info.model_entity.name} (UUID: {model_info.model_entity.uuid})")
        
        messages = self._get_image_prompts(content_list, system_prompt)

        self.ap.logger.info("发送请求：\n{}".format(self.messages_to_readable_str(messages)))

        response = await model_info.requester.invoke_llm(None, model=model_info, messages=messages)
        cleaned_response = self.clean_response(response.content)

        self.ap.logger.info("模型回复：\n{}".format(cleaned_response))
        return cleaned_response

    @handle_errors
    async def return_chat(self, request: str | typing.List[llm_entities.Message], system_prompt: str = None) -> str:
        if not self.selected_model_info:
            error_msg = "Waifu 插件未能找到或选定任何可用的大语言模型。请确保LangBot中已加载模型，并检查插件配置。"
            self.ap.logger.error(error_msg)
            raise ValueError(error_msg)

        model_info = self.selected_model_info
        self.ap.logger.info(f"Waifu 插件使用模型: {model_info.model_entity.name} (UUID: {model_info.model_entity.uuid})")
        
        messages = self._get_chat_prompts(request, system_prompt=system_prompt)
        request_model = model_info

        self.ap.logger.info("发送请求：\n{}".format(self.messages_to_readable_str(messages)))

        response = await model_info.requester.invoke_llm(None, model=model_info, messages=messages)
        cleaned_response = self.clean_response(response.content)

        self.ap.logger.info("模型回复：\n{}".format(cleaned_response))
        return cleaned_response

    def clean_response(self, response: str) -> str:
        if self._speakers:
            # 使用正则去掉self._speakers中的任何名称，后跟冒号或中文冒号及其后的空格
            speakers_pattern = "|".join([re.escape(speaker) for speaker in self._speakers])
            pattern = rf"^(?:{speakers_pattern})[:：]\s*"
            cleaned_response = re.sub(pattern, "", response)
        else:
            cleaned_response = response
        cleaned_response = self._remove_all_quotes(cleaned_response)
        # 移除消息中的所有think标签及其内容
        cleaned_response = self._remove_think_content(cleaned_response)
        # 删除特定破甲字符串
        cleaned_response = cleaned_response.replace("<结束无效提示>", "")
        # 删除回复中的时间戳
        cleaned_response = self.get_content_str_without_timestamp(cleaned_response)

        return cleaned_response

    def _remove_all_quotes(self, text: str) -> str:
        # 定义匹配中英文单双引号的正则表达式
        pattern = r'["\u201C\u201D\u2018\u2019\u300C\u300D]'
        # 使用正则表达式替换所有匹配的引号
        return re.sub(pattern, "", text)

    def _remove_think_content(self, text: str) -> str:
        pattern = r'<think>[\s\S]*?</think>'

        result = text
        iteration = 0
        max_iterations = 10

        while "<think>" in result and iteration < max_iterations:
            if not re.findall(pattern, result):
                break
            result = re.sub(pattern, '', result)
            result = re.sub(r'\n\s*\n', '\n', result.strip())
            iteration += 1

        if iteration >= max_iterations:
            self.ap.logger.warning(f"达到最大迭代次数 {max_iterations}，可能存在异常标签")
        # 针对启航API的返回信息不全的处理
        if "<think>" in result:
            self.ap.logger.warning("未能完全删除think标签")
            self.ap.logger.warning(result)
            result = ""
        return result

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

            json_str = json_str.replace("，", ",")  # Replace Chinese commas with English commas
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

    def get_content_str_without_timestamp(self, message: llm_entities.Message | str) -> str:
        message_content = ""
        if isinstance(message, llm_entities.Message):
            message_content = str(message.get_content_platform_message_chain())
        else:
            message_content = message

        # 使用 re.sub 移除所有时间戳
        message_content = re.sub(r"\[\d{2}年\d{2}月\d{2}日(上午|下午)?\d{2}时\d{2}分\]", "", message_content)

        return message_content.strip()

    def messages_to_readable_str(self, messages: typing.List[llm_entities.Message]) -> str:
        return "\n".join(message.readable_str() for message in messages)

    def get_chinese_current_time(self):
        current_time = datetime.now()
        hour = current_time.hour
        period = "上午"
        if hour >= 12:
            period = "下午"
        chinese_time = current_time.strftime(f"%y年%m月%d日{period}%H时%M分")
        return chinese_time

    def set_jail_break(self, jail_break_type: str, user_name: str):
        self._jail_break_type = jail_break_type
        self._jail_break_dict = {}
        base_filepath = "data/plugins/Waifu/config/"

        if jail_break_type == "all":
            # Load all jail break files
            for type_name in ["before", "after", "end"]:
                filepath = f"{base_filepath}jail_break_{type_name}.txt"
                if os.path.exists(filepath):
                    with open(filepath, "r", encoding="utf-8") as f:
                        self._jail_break_dict[type_name] = f.read().replace("{{user}}", user_name)
        else:
            # Load a specific jail break type
            filepath = f"{base_filepath}jail_break_{jail_break_type}.txt"
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    self._jail_break_dict[jail_break_type] = f.read().replace("{{user}}", user_name)

    def set_speakers(self, speakers: list):
        self._speakers = speakers
