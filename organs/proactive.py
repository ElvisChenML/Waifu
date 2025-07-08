import asyncio
import datetime
import json
import traceback
import typing
import os
import yaml
import random
from pkg.core import app
from pkg.platform.sources.aiocqhttp import AiocqhttpAdapter
from pkg.platform.types import message as platform_message
from pkg.plugin.context import APIHost
from plugins.Waifu.cells.generator import Generator
from plugins.Waifu.cells.config import ConfigManager
from plugins.Waifu.organs.memories import Memory


class ProactiveGreeter:
    ap: app.Application

    def __init__(self, host: APIHost, ap: app.Application, launcher_id: str):
        self.ap = ap
        self.host = host
        self._generator = Generator(ap)

        self._main_task: typing.Optional[asyncio.Task] = None   #loop状态
        self._first_adapter: typing.Optional[AiocqhttpAdapter] = None
        self._memory = None
        self._launcher_id = launcher_id
        self._proactive_target_user_id = "off"
        self._proactive_greeting_enabled: bool = False
        self._proactive_greeting_probability: int = 0
        self._proactive_min_inactive_hours = 3.0
        self._proactive_do_not_disturb_start = "23:00"
        self._proactive_do_not_disturb_end = "8:00"
        self._loop_time = 1800

        enabled_adapters = self.host.get_platform_adapters()
        for adapter in enabled_adapters:
            if isinstance(adapter, AiocqhttpAdapter):  # 选择qq适配器
                self._first_adapter = adapter
                self.ap.logger.info(f"获取到qqapdater :{self._first_adapter}")
                break
            else:
                self.ap.logger.error(f"Can't find apdater for qq!!")

    async def load_config(self, memory: Memory):
        waifu_config = ConfigManager(f"data/plugins/Waifu/config/waifu", "plugins/Waifu/templates/waifu", self._launcher_id)
        await waifu_config.load_config(completion=True)
        self._memory = memory
        self._proactive_target_user_id = waifu_config.data.get("proactive_target_user_id", "off")
        self._proactive_greeting_enabled = waifu_config.data.get("proactive_greeting_enabled", False)
        self._proactive_greeting_probability = waifu_config.data.get("proactive_greeting_probability", 0)
        self._proactive_min_inactive_hours = waifu_config.data.get("proactive_min_inactive_hours", 3.0)
        self._proactive_max_inactive_hours = waifu_config.data.get("proactive_max_inactive_hours", 4.0)
        if self._proactive_max_inactive_hours < self._proactive_min_inactive_hours:
            self._proactive_max_inactive_hours = self._proactive_min_inactive_hours
        self._proactive_do_not_disturb_start = waifu_config.data.get("proactive_do_not_disturb_start","23:00")
        self._proactive_do_not_disturb_end = waifu_config.data.get("proactive_do_not_disturb_end","08:00")
        self._loop_time = waifu_config.data.get("loop_time",1800)

        if self._proactive_greeting_enabled and self._summarization_mode and self._proactive_target_user_id != "off" and self._proactive_target_user_id != "":
            self.ap.logger.info(f"ProactiveGreeter: 配置加载完成，启动主动问候")
            asyncio.create_task(self.activate())
        else:
            self.ap.logger.info(f"ProactiveGreeter: 配置加载完成，不满足启动条件。")

    async def activate(self):
        if self._main_task and not self._main_task.done():
            self.ap.logger.info(
                f"ProactiveGreeter: activate() 被调用，但主任务 ({self._main_task.get_name()}) 已在运行。") #防止多次调用
            return
        self._main_task = asyncio.create_task(self.start_loop()) #创建任务并且标记为target_qq 名称

        if hasattr(self._main_task, 'set_name'):
            self._main_task.set_name(f"start_loop_for_{self._proactive_target_user_id if self._proactive_target_user_id else 'unknown_target'}")
        self.ap.logger.info(
            f"start_loop 任务已创建并启动: {self._main_task.get_name() if hasattr(self._main_task, 'get_name') else self._main_task}")

    async def start_loop(self):
        await asyncio.sleep(60)
        self.ap.logger.info(f"等待60s冷启动")

        try:
            self.ap.logger.info(f"start to loop for {self._proactive_target_user_id}")
            await  self._proactive_loop()  #进入第二循环，并结束当前while循环
        except Exception as e:
            self.ap.logger.error(f"CRITICAL_ERROR: 调用 start_loop 时异常: {type(e)} - {str(e)}")
            traceback.print_exc()

    async def _proactive_loop(self):
        self.ap.logger.info(f"Proactive loop started.")
        initial_loop_delay = 30

        await self._generator._initialize_model_config() #加载generator model配置
        self.ap.logger.info(f"model info is {self._generator.selected_model_info}")

        try:
            await asyncio.sleep(initial_loop_delay)
        except asyncio.CancelledError:
            self.ap.logger.info("cancelled during initial delay.")
            return

        while True:
            try:
                self.ap.logger.info(f"probability:{self._proactive_greeting_probability}")
                if random.randint(1, 100) <= self._proactive_greeting_probability:  # 几率
                    await self._check_user_inactivity()  # 进入检测用户活跃时间
            except asyncio.CancelledError:
                self.ap.logger.info("Proactive loop cancelled during check/greet.")
                break
            except Exception as e_loop:
                self.ap.logger.error(f"ERROR in proactive greeting loop: {e_loop}")
                traceback.print_exc()

            self.ap.logger.info(f"Check finished. Sleeping for {self._loop_time} seconds...")
            try:
                await asyncio.sleep(self._loop_time)
            except asyncio.CancelledError:
                self.ap.logger.info("WaifuPlugin: Proactive greeting loop cancelled during sleep.")
                break
            

    async def _check_user_inactivity(self):  # 检测用户活跃时长
        current_time = datetime.datetime.now()
        last_message_time = self._memory.get_lastest_time(self._memory.short_term_memory)  # 时间差值
        if not last_message_time:
            self.ap.logger.error(f"Could not extract last message time for user")
            return
        time_difference = current_time - last_message_time
        inactive_minutes = time_difference.total_seconds()
        inactive_minutes_float = float(inactive_minutes) / 60
        inactivity_threshold_minutes = self._proactive_min_inactive_hours
        inactivity_threshold_minutes_float = float(inactivity_threshold_minutes) * 60
        self.ap.logger.info(f"time_difference are {inactive_minutes_float}")
        self.ap.logger.info(f"inactivity minutes are {inactivity_threshold_minutes_float}")

        if inactive_minutes_float > inactivity_threshold_minutes_float:  # 差值大于规定最小时间
            current_time_hm_only = current_time.time()
            proactive_do_not_disturb_start = self._proactive_do_not_disturb_start
            proactive_do_not_disturb_end = self._proactive_do_not_disturb_end
            time_format = "%H:%M"
            dnd_start_time_obj = datetime.datetime.strptime(proactive_do_not_disturb_start, time_format).time()
            dnd_end_time_obj = datetime.datetime.strptime(proactive_do_not_disturb_end, time_format).time()

            is_currently_do_not_disturb = False
            self.ap.logger.info(f"Check: Current time: {current_time_hm_only.strftime(time_format)}, Period: {proactive_do_not_disturb_start} - {proactive_do_not_disturb_end}")
            if dnd_start_time_obj > dnd_end_time_obj:  # 跨夜
                if current_time_hm_only >= dnd_start_time_obj or current_time_hm_only < dnd_end_time_obj:
                    is_currently_do_not_disturb = True
            else:  # 不跨夜
                if dnd_start_time_obj <= current_time_hm_only < dnd_end_time_obj:
                    is_currently_do_not_disturb = True
            if is_currently_do_not_disturb:
                self.ap.logger.info(f"勿扰时间")
            else:
                self.ap.logger.info(f"bot will send to message!")
                asyncio.create_task(self.proactive_send())   # 主动发消息

    async def proactive_send(self):  # 主动发送消息功能
        try:
            adapter_instance = self._first_adapter  # 获取适配器
            if adapter_instance:
                message_to_send_str = await self.proactive_greeting()  # 返回message
                self.ap.logger.info(f"wait to send{self._proactive_target_user_id}\n")
                await adapter_instance.send_message(
                    target_type="person",
                    target_id=self._proactive_target_user_id,
                    message=platform_message.MessageChain([message_to_send_str])
                )
            else:
                self.ap.logger.error("ERROR: Could not get adapter instance for proactive send.")
        except Exception as e:
            self.ap.logger.error(f"ERROR during proactive send: {e}")
            traceback.print_exc()
        self.ap.logger.info("proactive_send() task completed.")

    async def proactive_greeting(self):  ##主动问候生成词
        loop = asyncio.get_running_loop()
        folder_path = f"data/plugins/Waifu/data/"
        filename = f"card_summary_{self._launcher_id}_{self._proactive_target_user_id}.txt"
        full_path = os.path.join(folder_path, filename)
        summary_text, tags_list = self._get_tag_summary()  # 获取tag和summary
        if summary_text is None:
            summary_text = ""   #避免为空
        file_exists = await loop.run_in_executor(None, os.path.exists, full_path)
        if file_exists:
            card_summary_text = await loop.run_in_executor(
                None,
                self.read_text_from_file_sync,
                full_path
            )
        else:
            raw_prompt = self._cards.generate_system_prompt()  # 获取角色卡
            full_card_prompt_text = self._memory.to_custom_names(raw_prompt)
            system_prompt_for_summarizing_card = (
                f"请阅读这张角色卡，并从中提取出最能代表该角色核心性格、行为方式关键要点。"
                f"总结应非常简短精炼\n"
                f"请直接输出大概一句话的文本摘要\n"
            )
            if self._generator and self._generator.selected_model_info:
                try:
                    if hasattr(self._generator, 'set_speakers'):
                        self._generator.set_speakers([])  # 清空或不设置特定speaker
                        card_summary_text = await self._generator.return_chat(
                        request=full_card_prompt_text,
                        system_prompt=system_prompt_for_summarizing_card  # 指示LLM进行总结的系统提示
                    )
                    await loop.run_in_executor(
                        None,
                        self.write_text_to_file_sync,
                        full_path,
                        card_summary_text
                    )
                except Exception as e:
                    self.ap.logger.error(f"ERROR during LLM call for card summary: {e}")
            else:
                self.ap.logger.error("ERROR: Generator or its model is not ready for card summary call.")

        conversations = self._memory.get_normalize_short_term_memory()
        conversation = conversations[-5:]  # 获取历史对话切片
        formatted_history_lines = []
        for msg_obj in conversation:
            content_text = str(msg_obj.content).strip()
            formatted_history_lines.append(f"\n{content_text}")
        if formatted_history_lines:
            recent_dialogue_str = "\n".join(formatted_history_lines)  # 简单处理对话

        summary_snippet = summary_text[:150] + "..." if len(
            summary_text) > 150 else summary_text  # 取 summary 的前一部分作为上下文，避免过长
        system_prompt_with_ltm = (
            f"你的角色设定是这样的:'{card_summary_text}\n'"
            f"我们最近的对话中，有一个总结大致是这样的：'{summary_snippet}'\n"
            f"作为参考，以下是我们最近的一些对话内容：[对话开始\n{recent_dialogue_str}\n对话结束]\n\n"
            f"请你基于这些信息，自然地对他发起一个主动的问候或对话。"
            f"请直接说出非常简短的问候内容，大约一句话，简短精炼，不要带上你的名字作为前缀。"
        )
        user_request_for_greeting = " "
        response = await self._generator.return_chat(
            request=user_request_for_greeting,
            system_prompt=system_prompt_with_ltm
        )
        await self._memory.save_memory(role="assistant", content=response)  # 主动发言存入到历史记忆当中
        return response  # 返回LLM 回应

    def _get_tag_summary(self):
        try:
            fixed_file_path = f"data/plugins/Waifu/data/memories_{self._proactive_target_user_id}.json"
            with open(fixed_file_path, "r", encoding="utf-8") as file:
                data = json.load(file)  # 解析整个JSON数据
            if "long_term" in data and isinstance(data["long_term"], list) and data["long_term"]:
                latest_entry = data["long_term"][-1]  # 获取列表的最后一个元素
                if isinstance(latest_entry, dict) and "summary" in latest_entry and "tags" in latest_entry:
                    summary_text = latest_entry["summary"]
                    tags_list = latest_entry["tags"]
                    processed_summary = summary_text  ## ----处理summary_text
                    status_tracking_marker = "状态追踪："
                    important_affairs_marker = "重要事务："
                    status_tracking_start_index = summary_text.find(status_tracking_marker)
                    if status_tracking_start_index != -1:
                        narrative_part = summary_text[:status_tracking_start_index].strip()
                        important_affairs_start_index = summary_text.find(important_affairs_marker,
                                                                          status_tracking_start_index)
                        if important_affairs_start_index != -1:
                            important_affairs_content = summary_text[important_affairs_start_index + len(
                                important_affairs_marker):].strip()  # 去掉多余的换行
                            lines = [line.strip() for line in important_affairs_content.split('\n') if line.strip()]
                            important_affairs_part_extracted = "\n我们之前提到的一些重要事情有：" + "\n    ".join(
                                lines[:3])  # 前3个事务
                            processed_summary = f"{narrative_part}{important_affairs_part_extracted}"
                        else:
                            processed_summary = narrative_part  # 只用叙事部分
                    else:
                        self.ap.logger.error(
                            "'状态追踪：' marker not found. Using summary as is (or potentially truncated).")
                    return processed_summary, tags_list  # 返回tag和summary
                else:
                    self.ap.logger.error("ERROR: Latest LTM entry has unexpected format or missing 'summary'/'tags'.")
                    return None, None
            else:
                self.ap.logger.error("ERROR: No 'long_term' list found in the JSON data, or it is empty.")
                return None, None
        except FileNotFoundError:
            self.ap.logger.error(f"ERROR: File not found at path: {fixed_file_path}")
            return None, None
        except json.JSONDecodeError as e:
            self.ap.logger.error(f"ERROR: Could not decode JSON from file. Error: {e}")
            return None, None
        except Exception as e:
            self.ap.logger.error(f"ERROR: An unexpected error occurred: {e}")
            traceback.print_exc()
            return None, None

    def write_text_to_file_sync(self,file_path, content):
        folder = os.path.dirname(file_path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(file_path, mode='w', encoding='utf-8') as f:
            f.write(content)
    def read_text_from_file_sync(self,file_path):
        try:
            with open(file_path, mode='r', encoding='utf-8') as f:
                content = f.read()
            return content
        except FileNotFoundError:
            self.ap.logger.error(f"Error: File not found at {file_path}")
            return None
        except Exception as e:
            self.ap.logger.error(f"Error reading file {file_path}: {e}")
            return None

    async def stop_main_task(self):
        if self._main_task and not self._main_task.done():
            task_name = self._main_task.get_name() if hasattr(self._main_task, 'get_name') else "ProactiveGreeterTask"
            self.ap.logger.info(f"ProactiveGreeter: 收到停止请求，正在取消主任务 ({task_name})...")
            self._main_task.cancel()  # 发出取消请求
            try:
                await self._main_task  # 等待任务响应取消并实际结束
            except asyncio.CancelledError:
                self.ap.logger.info(f"ProactiveGreeter: 主任务 ({task_name}) 已成功取消。")
            except Exception as e:
                self.ap.logger.error(f"ProactiveGreeter: 在等待主任务 ({task_name}) 取消时发生意外错误: {e}",
                                     exc_info=True)
            finally:
                self._main_task = None  # 清理任务引用
        elif self._main_task and self._main_task.done():
            task_name = self.main_task.get_name() if hasattr(self._main_task,
                                                             'get_name') else "ProactiveGreeterTask"
            self.ap.logger.info(f"ProactiveGreeter: 主任务 ({task_name}) 已经被请求停止或已自行完成。")
            self._main_task = None
        else:
            self.ap.logger.info("ProactiveGreeter: 没有正在运行的主任务需要停止。")
