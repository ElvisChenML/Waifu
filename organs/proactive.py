import asyncio
import datetime
import json
import traceback
import typing
import os
import yaml
import random
from pkg.platform.sources.aiocqhttp import AiocqhttpAdapter
from pkg.platform.types import message as platform_message
from plugins.Waifu.cells.generator import Generator


class ProactiveGreeter:
    def __init__(self,ap,host,shared_plugin_waifu_cache):
        self.ap = ap
        self.host = host
        self._generator = Generator(ap)
        self.target_qq = None
        self.current_config = None
        self.proactive_greeting_enabled = False
        self._main_task: typing.Optional[asyncio.Task] = None   #loop状态
        self._shared_waifu_cache = shared_plugin_waifu_cache #初始化可能传递过来是空的
        asyncio.create_task(self.activate())

        enabled_adapters = self.host.get_platform_adapters()
        for adapter in enabled_adapters:
            if isinstance(adapter, AiocqhttpAdapter):  # 选择qq适配器
                self.first_adapter = adapter
                self.ap.logger.info(f"获取到qqapdater :{self.first_adapter}")
                break
            else:
                self.ap.logger.error(f"Can't find apdater for qq!!")
        self.ap.logger.info("WaifuPlugin: __init__ completed.")


    async def activate(self):
        global_config = "plugins/Waifu/templates/waifu.yaml"
        self.target_qq = self.load_target_qq(global_config)   #获取templates设置里的qq号

        if self._main_task and not self._main_task.done():
            self.ap.logger.info(
                f"ProactiveGreeter: activate() 被调用，但主任务 ({self._main_task.get_name()}) 已在运行。") #防止多次调用
            return
        self.ap.logger.info("准备启动 start_loop 任务...")

        self._main_task = asyncio.create_task(self.start_loop()) #创建任务并且标记为target_qq 名称

        if hasattr(self._main_task, 'set_name'):
            self._main_task.set_name(
                f"start_loop_for_{self.target_qq if self.target_qq else 'unknown_target'}")
        self.ap.logger.info(
            f"start_loop 任务已创建并启动: {self._main_task.get_name() if hasattr(self._main_task, 'get_name') else self._main_task}")



    async def start_loop(self):
        await asyncio.sleep(60)
        self.ap.logger.info(f"等待60s冷启动")

        try:
            count = 0
            initial_loop_delay = 60 #while循环间隔
            while True:
                if not self.target_qq:
                    global_config = "plugins/Waifu/templates/waifu.yaml"
                    self.target_qq = self.load_target_qq(global_config)
                    self.ap.logger.info(f"ProactiveGreeter: 使用 {self.target_qq} 调用 _load_config")
                else:
                    active_waifu_cache_config = None
                    if self._shared_waifu_cache:  # 确保共享缓存引用有效
                        active_waifu_cache_config = self._shared_waifu_cache.get(self.target_qq) #获取当前config最新实例
                    
                    if not active_waifu_cache_config:  # 如果获取不到，则无法继续
                        self.ap.logger.warning(
                            f"ProactiveGreeter ({self.target_qq}): 在 _check_user_inactivity1 中未能获取到有效的 WaifuCache 实例。将不执行主动问候检查。")
                        await asyncio.sleep(initial_loop_delay)
                        count += 1

                    if active_waifu_cache_config:
                            self.ap.logger.info(f"start to loop for {self.target_qq}")
                            await  self._proactive_loop()  #进入第二循环，并结束当前while循环
                            break

                    else:  #如果waifu_cache对象仍然未加载
                        await asyncio.sleep(initial_loop_delay)
                        self.ap.logger.info(f"fail to find waifu_cache,sleep for {initial_loop_delay}seconds and try again")
                        count+=1

                    if count == 10:  #最多循环10次，仍然未找到则结束任务
                        self.ap.logger.error(f"proactive:fail to find waifu_cache")
                        break

        except Exception as e:
            self.ap.logger.error(
                f"CRITICAL_ERROR: 调用 _load_target_qq_from_global_config_file 时异常: {type(e)} - {str(e)}")
            traceback.print_exc()



    async def _proactive_loop(self):
        active_waifu_cache_config = None
        if self._shared_waifu_cache:  # 确保共享缓存引用有效并更新最新的config
            active_waifu_cache_config = self._shared_waifu_cache.get(self.target_qq)

        if not active_waifu_cache_config:
            self.ap.logger.warning(
                f"ProactiveGreeter ({self.target_qq}): 在 _check_user_inactivity2 中未能获取到有效的 WaifuCache 实例。将不执行主动问候检查。")
            return

        if active_waifu_cache_config.proactive_greeting_enabled and active_waifu_cache_config.summarization_mode:
            self.ap.logger.info(
                f"Proactive loop started.")
            initial_loop_delay = 30

            await self._generator._initialize_model_config() #加载generator model配置
            self.ap.logger.info(f"model info is {self._generator.selected_model_info}")

            try:
                await asyncio.sleep(initial_loop_delay)
            except asyncio.CancelledError:
                self.ap.logger.info("cancelled during initial delay.")
                return

            while True:
                active_waifu_cache_config = None
                if self._shared_waifu_cache:  # 确保共享缓存引用有效并更新最新的config
                    active_waifu_cache_config = self._shared_waifu_cache.get(self.target_qq)

                if not active_waifu_cache_config:
                    self.ap.logger.warning(
                        f"ProactiveGreeter ({self.target_qq}): 在 _check_user_inactivity3 中未能获取到有效的 WaifuCache 实例。将不执行主动问候检查。")
                    return

                if active_waifu_cache_config:
                    try:
                            probability_to_greet = active_waifu_cache_config.proactive_greeting_probability
                            self.ap.logger.info(
                                f"probability:{probability_to_greet}")
                            if random.randint(1, 100) <= probability_to_greet:  # 几率

                                await self._check_user_inactivity()  # 进入检测用户活跃时间

                            if not active_waifu_cache_config :
                                self.ap.logger.warning(
                                    f"ProactiveGreeter ({self.target_qq}): current_config or latest_waifu_cache_instance 无效，暂停此次主动行为周期。")
                                await asyncio.sleep(initial_loop_delay)
                                continue

                    except asyncio.CancelledError:
                        self.ap.logger.info("Proactive loop cancelled during check/greet.")
                        break
                    except Exception as e_loop:
                        self.ap.logger.error(f"ERROR in proactive greeting loop: {e_loop}")
                        traceback.print_exc()

                    self.ap.logger.info(f"Check finished. Sleeping for {active_waifu_cache_config.loop_time} seconds...")
                    try:
                        await asyncio.sleep(active_waifu_cache_config.loop_time)
                    except asyncio.CancelledError:
                        self.ap.logger.info("WaifuPlugin: Proactive greeting loop cancelled during sleep.")
                        break

    async def _check_user_inactivity(self):  # 检测用户活跃时长

        active_waifu_cache_config = None
        if self._shared_waifu_cache:
            active_waifu_cache_config = self._shared_waifu_cache.get(self.target_qq)
        if not active_waifu_cache_config:
            self.ap.logger.warning(
                f"ProactiveGreeter ({self.target_qq}): 在 _check_user_inactivity4 中未能获取到有效的 WaifuCache 实例。将不执行主动问候检查。")
            return

        if active_waifu_cache_config:
            current_time = datetime.datetime.now()
            last_message_time = active_waifu_cache_config.memory.get_lastest_time(active_waifu_cache_config.memory.short_term_memory)  # 时间差值
            if not last_message_time:
                self.ap.logger.error(f"Could not extract last message time for user")
                return
            time_difference = current_time - last_message_time
            inactive_minutes = time_difference.total_seconds()
            inactive_minutes_float = float(inactive_minutes) / 60
            inactivity_threshold_minutes = active_waifu_cache_config.proactive_min_inactive_hours
            inactivity_threshold_minutes_float = float(inactivity_threshold_minutes) * 60
            self.ap.logger.info(f"time_difference are {inactivity_threshold_minutes_float}")
            self.ap.logger.info(f"inactivity minutes are {inactivity_threshold_minutes_float}")


            if inactive_minutes_float > inactivity_threshold_minutes_float:  # 差值大于规定最小时间
                current_time_hm_only = current_time.time()
                proactive_do_not_disturb_start = active_waifu_cache_config.proactive_do_not_disturb_start
                proactive_do_not_disturb_end = active_waifu_cache_config.proactive_do_not_disturb_end
                time_format = "%H:%M"
                dnd_start_time_obj = datetime.datetime.strptime(proactive_do_not_disturb_start, time_format).time()
                dnd_end_time_obj = datetime.datetime.strptime(proactive_do_not_disturb_end, time_format).time()

                is_currently_do_not_disturb = False
                self.ap.logger.info(
                    f"Check: Current time: {current_time_hm_only.strftime(time_format)}, Period: {proactive_do_not_disturb_start} - {proactive_do_not_disturb_end}")
                if dnd_start_time_obj > dnd_end_time_obj:  # 跨夜
                    if current_time_hm_only >= dnd_start_time_obj or current_time_hm_only < dnd_end_time_obj:
                        is_currently_do_not_disturb = True
                else:  # 不跨夜
                    if dnd_start_time_obj <= current_time_hm_only < dnd_end_time_obj:
                        is_currently_do_not_disturb = True
                if is_currently_do_not_disturb:
                    self.ap.logger.info(
                        f"勿扰时间")
                else:
                    self.ap.logger.info(f"bot will send to message!")
                    asyncio.create_task(self.proactive_send())   # 主动发消息
        else:
            self.ap.logger.info(f"ERROR Inactivity: Could not send greeting ")
            return


    async def proactive_send(self):  # 主动发送消息功能
        try:
            adapter_instance = self.first_adapter  # 获取适配器
            if adapter_instance:
                message_to_send_str = await self.proactive_greeting()  # 返回message
                self.ap.logger.info(f"wait to send{self.target_qq}\n")
                await adapter_instance.send_message(
                    target_type="person",
                    target_id=self.target_qq,
                    message=platform_message.MessageChain([message_to_send_str])
                )
            else:
                self.ap.logger.error("ERROR: Could not get adapter instance for proactive send.")
        except Exception as e:
            self.ap.logger.error(f"ERROR during proactive send: {e}")
            traceback.print_exc()
        self.ap.logger.info("proactive_send() task completed.")


    async def proactive_greeting(self):  ##主动问候生成词
        active_waifu_cache_config = None
        if self._shared_waifu_cache:
            active_waifu_cache_config = self._shared_waifu_cache.get(self.target_qq)

        if not active_waifu_cache_config:
            self.ap.logger.warning(
                f"ProactiveGreeter ({self.target_qq}): 在 _check_user_inactivity5 中未能获取到有效的 WaifuCache 实例。将不执行主动问候检查。")
            return None


        loop = asyncio.get_running_loop()
        folder_path = "plugins/Waifu/templates"
        filename = f"card_summary_{self.target_qq}.txt"
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
            raw_prompt = active_waifu_cache_config.cards.generate_system_prompt()  # 获取角色卡
            full_card_prompt_text = active_waifu_cache_config.memory.to_custom_names(raw_prompt)
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

        conversations = active_waifu_cache_config.memory.get_normalize_short_term_memory()
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
        await active_waifu_cache_config.memory.save_memory(role="assistant", content=response)  # 主动发言存入到历史记忆当中
        return response  # 返回LLM 回应


    def _get_tag_summary(self):
        active_waifu_cache_config = None
        if self._shared_waifu_cache:  # 确保共享缓存引用有效并更新最新的config
            active_waifu_cache_config = self._shared_waifu_cache.get(self.target_qq)

        if not active_waifu_cache_config:  # 如果获取不到，则无法继续
            self.ap.logger.warning(
                f"ProactiveGreeter ({self.target_qq}): 在 _check_user_inactivity2 中未能获取到有效的 WaifuCache 实例。将不执行主动问候检查。")
            return None

        try:
            fixed_file_path = f"data/plugins/Waifu/data/memories_{self.target_qq}.json"
            self.ap.logger.info(f"Attempting to read LTM file: {fixed_file_path}")
        except Exception as e:
            self.ap.logger.error(f"ERROR: Attribute 'target_qq' not found on self: {e}\\n")
            return None, None

        try:
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



    def load_target_qq(self: object, file_path: str) -> typing.Optional[str]:
        if not os.path.exists(file_path):
            self.ap.logger.error(f"ERROR: file not found: {file_path}")
            return None
        config_data: typing.Optional[dict] = None  # 初始化 config_data
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)
        except yaml.YAMLError as ye:
            self.ap.logger.error(f"ERROR: YAML parsing error in {file_path}: {ye}")
            return None
        except IOError as ioe:
            self.ap.logger.error(f"ERROR: Could not read file {file_path}: {ioe}")
            return None
        except Exception as e_file:
            self.ap.logger.error(f"ERROR: Unexpected error processing file {file_path}: {e_file}")
            traceback.print_exc()
            return None
        else:
            if not config_data or not isinstance(config_data, dict):
                self.ap.logger.error(f"ERROR: file {file_path} is empty or not a valid YAML dictionary after loading.")
                return None

            target_qq_from_config = config_data.get("target_user_id")
            if target_qq_from_config and isinstance(target_qq_from_config, str) and target_qq_from_config.strip():
                cleaned_target_qq = target_qq_from_config.strip()
                if cleaned_target_qq:  # 再次确认 strip 后不是空字符串
                    self.ap.logger.info(f"Successfully loaded target_user_id: {cleaned_target_qq}")
                    return int(cleaned_target_qq)
                else:
                    self.ap.logger.error(
                        f"ERROR: 'target_user_id' in {file_path} is an empty string after stripping. Value was: '{target_qq_from_config}'")
                    return None
            else:
                self.ap.logger.error(
                    f"ERROR: 'target_user_id' not found, is not a string, or is an empty string in {file_path}. Value was: '{target_qq_from_config}'")
                return None

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