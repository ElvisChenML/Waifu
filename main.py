import asyncio
import datetime
import json
import traceback
import typing
import os
import yaml
import random
import re
import copy
import shutil
from pkg.platform.sources.aiocqhttp import AiocqhttpAdapter
from pkg.provider import runner
from pkg.core import app
from pkg.core import entities as core_entities
from pkg.platform.types import message as platform_message
from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import PersonMessageReceived, GroupMessageReceived, NormalMessageResponded, GroupNormalMessageReceived
from pkg.provider import entities as llm_entities
from plugins.Waifu.cells.config import ConfigManager
from plugins.Waifu.cells.generator import Generator
from plugins.Waifu.cells.cards import Cards
from plugins.Waifu.organs.memories import Memory
from plugins.Waifu.systems.narrator import Narrator
from plugins.Waifu.systems.value_game import ValueGame
from plugins.Waifu.organs.thoughts import Thoughts
from pkg.platform.types.message import MessageChain, Plain, logger


COMMANDS = {
    "列出命令": "列出目前支援所有命令及介绍，用法：[列出命令]。",
    "全部记忆": "显示目前所有长短期记忆，用法：[全部记忆]。",
    "会话记忆":"显示当前会话使用的记忆，用法：[会话记忆]。",
    "最近记忆": "显示最近的长期记忆，用法：[最近记忆]。",
    "最近召回": "显示最近召回的记忆，用法：[最近召回]。",
    "最近L0召回": "显示最近召回的记忆，用法：[最近L0召回]。",
    "最近L1召回": "显示最近召回的记忆，用法：[最近L1召回]。",
    "最近L2召回": "显示最近召回的记忆，用法：[最近L2召回]。",
    "最近L3召回": "显示最近召回的记忆，用法：[最近L3召回]。",
    "最近L4召回": "显示最近召回的记忆，用法：[最近L4召回]。",
    "最近L5召回": "显示最近召回的记忆，用法：[最近L5召回]。",
    "召回阈值": "显示召回阈值，用法：[召回阈值]。",
    "删除记忆": "删除所有长短期记忆，用法：[删除记忆]。",
    "修改数值": "修改Value Game的数字，用法：[修改数值][数值]。",
    "态度": "显示当前Value Game所对应的“态度Manner”，用法：[态度]。",
    "加载配置": "重新加载所有配置文件（仅Waifu），用法：[加载配置]。",
    "停止活动": "停止旁白计时器，用法：[停止活动]。",
    "开场场景": "主动触发旁白输出角色卡中的“开场场景Prologue”，用法：[开场场景]。",
    "旁白": "主动触发旁白推进剧情，用法：[旁白]。",
    "继续": "主动触发Bot继续回复推进剧情，用法：[继续]。",
    "控制人物": "控制角色发言（行动）或触发AI生成角色消息，用法：[控制人物][角色名称/assistant]|[发言(行动)/继续]。",
    "推进剧情": "自动依序调用：旁白 -> 控制人物，角色名称省略默认为user，用法：[推进剧情][角色名称]。",
    "撤回": "从短期记忆中删除最后的对话，用法：[撤回]。",
    "请设计": "调试：设计一个列表，用法：[请设计][设计内容]。",
    "请选择": "调试：从给定列表中选择，用法：[请选择][问题]|[选项1,选项2,……]。",
    "回答数字": "调试：返回数字答案，用法：[回答数字][问题]。",
    "回答问题": "调试：可自定系统提示的问答模式，用法：[回答问题][系统提示语]|[用户提示语] / [回答问题][用户提示语]。",
}


class WaifuCache:

    ap: app.Application

    def __init__(self, ap: app.Application, launcher_id: str, launcher_type: str):
        self.launcher_id = launcher_id
        self.launcher_type = launcher_type
        self.langbot_group_rule = False
        self.memory = Memory(ap, launcher_id, launcher_type)
        self.value_game = ValueGame(ap)
        self.cards = Cards(ap)
        self.narrator = Narrator(ap, launcher_id)
        self.thoughts = Thoughts(ap)
        self.conversation_analysis_flag = True
        self.thinking_mode_flag = True
        self.story_mode_flag = True
        self.display_thinking = True
        self.display_value = True
        self.response_rate = 0.7
        self.narrate_intervals = []
        self.launcher_timer_tasks = None
        self.unreplied_count = 0
        self.continued_rate = 0.2
        self.continued_count = 0
        self.continued_max_count = 2
        self.summarization_mode = True
        self.personate_mode = True
        self.jail_break_mode = "off"
        self.response_timers_flag = False
        self.bracket_rate = []
        self.group_response_delay = 3
        self.person_response_delay = 0
        self.personate_delay = 0
        self.group_message_chain = None
        self.blacklist = []
        self.ignore_prefix = []

        self.proactive_greeting_enabled: bool = False
        self.proactive_greeting_probability: int = 0
        self.proactive_min_inactive_hours = 3.0
        self.proactive_do_not_disturb_start = "23:00"
        self.proactive_do_not_disturb_end = "8:00"
       # self.target_user_id = ""




@runner.runner_class("waifu-mode")
class WaifuRunner(runner.RequestRunner):
    async def run(self, query: core_entities.Query):
        # 为了适配其他插件，以屏蔽runner的方式取代ctx.prevent_default()
        # 不需在配置文件中手动配置运行器，将在插件加载过程强制指定为waifu-mode
        # 返回一个空的异步生成器
        if False:  # 永远不会执行，但保留生成器语法
            yield
        return

@register(name="Waifu", description="Cuter than real waifu!", version="1.9.8", author="ElvisChenML")
class WaifuPlugin(BasePlugin):
    def __init__(self, host: APIHost):


        super().__init__(host)
      #  self.proactive_check_interval_seconds = 60 # 测试循环间隔
        self.ap = host.ap
        self._ensure_required_files_exist()
        self._generator = Generator(self.ap)
        self.waifu_cache: typing.Dict[str, WaifuCache] = {}
        self._set_permissions_recursively("data/plugins/Waifu/", 0o777)

        enabled_adapters = self.host.get_platform_adapters()

        #self.first_adapter = enabled_adapters[0]


        for adapter in enabled_adapters:
            if isinstance(adapter, AiocqhttpAdapter): # 选择qq适配器
                self.first_adapter = adapter
                self.ap.logger.info(f"获取到qqapdater :{self.first_adapter}")
                break
            else:
                self.ap.logger.error(f"Can't find apdater for qq!!")

        print("WaifuPlugin: __init__ completed.")



    async def initialize(self):  #重写初始化
        await super().initialize()

        #初始化 Generator 的模型配置 ---
        if hasattr(self, '_generator') and hasattr(self._generator, '_initialize_model_config'):
            self.ap.logger.info("WaifuPlugin: Initializing Generator's model configuration...")
            try:
                await self._generator._initialize_model_config()  # 主动调用初始化方法
                if self._generator.selected_model_info:
                    self.generator_model_ready = True
                    self.ap.logger.info(
                        f"WaifuPlugin: Generator model selected: {self._generator.selected_model_info.model_entity.name}")
            except Exception as e:
                self.ap.logger.error(f"WaifuPlugin: Error during Generator model initialization: {e}")
                self.ap.logger.error(traceback.format_exc())
        else:
            self.ap.logger.error("WaifuPlugin: _generator or _generator._initialize_model_config not found!")


        global_config = "data/plugins/Waifu/config/waifu.yaml"
        self.target_qq = self._load_target_qq_from_global_config_file(global_config)  #在plugins/Waifu/templates/waifu.yaml 读取qq号
        print(self.target_qq)

        asyncio.create_task(self._proactive_loop())   #创建检测用户活跃任务
        self.ap.logger.info(f"start to proactive_loop")





    ##读取tag和summary
    def _get_tag_summary(self):

        try:
            fixed_file_path = f"data/plugins/Waifu/data/memories_{self.target_qq}.json"
            print(f"Attempting to read LTM file: {fixed_file_path}")
        except Exception as e:
            print(f"ERROR: Attribute 'target_qq' not found on self: {e}\\n")
            return None, None


        try:
            with open(fixed_file_path, "r", encoding="utf-8") as file:
                data = json.load(file)  # 解析整个JSON数据

            if "long_term" in data and isinstance(data["long_term"], list) and data["long_term"]:
                latest_entry = data["long_term"][-1]  # 获取列表的最后一个元素
                print(f"latest_entry:{latest_entry}")

                if isinstance(latest_entry, dict) and "summary" in latest_entry and "tags" in latest_entry:
                    summary_text = latest_entry["summary"]
                    tags_list = latest_entry["tags"]

                    processed_summary = summary_text   ## ----处理summary_text
                    status_tracking_marker = "状态追踪："
                    important_affairs_marker = "重要事务："
                    status_tracking_start_index = summary_text.find(status_tracking_marker)

                    if status_tracking_start_index != -1:
                        narrative_part = summary_text[:status_tracking_start_index].strip()
                        important_affairs_start_index = summary_text.find(important_affairs_marker,
                                                                          status_tracking_start_index)
                        if important_affairs_start_index != -1:
                            # 提取 "重要事务：" 之后的内容
                            important_affairs_content = summary_text[important_affairs_start_index + len(
                                important_affairs_marker):].strip()   # 去掉多余的换行
                            lines = [line.strip() for line in important_affairs_content.split('\n') if line.strip()]
                            important_affairs_part_extracted = "\n我们之前提到的一些重要事情有：" + "\n    ".join(
                                lines[:3])  # 前3个事务
                            processed_summary = f"{narrative_part}{important_affairs_part_extracted}"
                        else:
                            processed_summary = narrative_part  # 只用叙事部分
                    else:
                        print(
                            "DEBUG LTM Processed: '状态追踪：' marker not found. Using summary as is (or potentially truncated).")
                    return processed_summary, tags_list    #返回tag和summary
                else:
                    print("ERROR: Latest LTM entry has unexpected format or missing 'summary'/'tags'.")
                    return None, None
            else:
                print("ERROR: No 'long_term' list found in the JSON data, or it is empty.")
                return None, None
        except FileNotFoundError:
            print(f"ERROR: File not found at path: {fixed_file_path}")
            return None, None
        except json.JSONDecodeError as e:
            print(f"ERROR: Could not decode JSON from file. Error: {e}")
            return None, None
        except Exception as e:
            print(f"ERROR: An unexpected error occurred: {e}")
            traceback.print_exc()
            return None, None



    # async def _get_target_adapter_for_test(self): #获取机器人实例
    #     if not hasattr(self.host, 'get_platform_adapters'):
    #         print("WaifuPlugin Test ERROR: self.host has no 'get_platform_adapters' method.")
    #         return None
    #

    #    # platform_manager = self.ap.platform_mgr

    #    # runtime_bot = await platform_manager.get_bot_by_uuid(self.test_target_bot_uuid)
    #   #  return runtime_bot.adapter




    async def proactive_greeting(self):   ##主动问候生成词

        summary_text, tags_list =  self._get_tag_summary()  #获取tag和summary
        #filtered_tags = [tag for tag in tags_list if not tag.startswith("PADDING:") and not tag.startswith("DATETIME:")] # 简单筛选 tags

        await self._load_config(self.target_qq, "person")
        config = self.waifu_cache[self.target_qq]

        raw_prompt = config.cards.generate_system_prompt()   #获取角色卡
        full_card_prompt_text = config.memory.to_custom_names(raw_prompt)

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

            except Exception as e:
                print(f"ERROR during LLM call for card summary: {e}")
        else:
            print("ERROR: Generator or its model is not ready for card summary call.")

        conversations = config.memory.get_normalize_short_term_memory()
        conversation = conversations[-5:]  #获取历史对话切片
        formatted_history_lines = []
        for msg_obj in conversation:
            content_text = str(msg_obj.content).strip()
            formatted_history_lines.append(f"\n{content_text}")

        if formatted_history_lines:
            recent_dialogue_str = "\n".join(formatted_history_lines)   #简单处理对话

        summary_snippet = summary_text[:150] + "..." if len(summary_text) > 150 else summary_text  # 取 summary 的前一部分作为上下文，避免过长
        system_prompt_with_ltm = (
            f"你的角色设定是这样的:'{card_summary_text}\n'"
           # f"对方可能有一段时间没有说话了。"
            f"我们最近的对话中，有一个总结大致是这样的：'{summary_snippet}'\n"
         #   f"并且涉及到的一些话题标签有：'{filtered_tags}'。\n"  
            f"作为参考，以下是我们最近的一些对话内容：[对话开始\n{recent_dialogue_str}\n对话结束]\n\n" 
            f"请你基于这些信息，自然地对他发起一个主动的问候或对话。"
            f"请直接说出非常简短的问候内容，大约一句话，简短精炼，不要带上你的名字作为前缀。"
        )
        user_request_for_greeting = " "
        response = await self._generator.return_chat(
            request=user_request_for_greeting,
            system_prompt=system_prompt_with_ltm
        )
        await config.memory.save_memory(role="assistant", content=response)  #主动发言存入到历史记忆当中
        return response  #返回LLM 回应


    async def proactive_send(self):  #主动发送消息功能
        try:
            #adapter_instance = await self._get_target_adapter_for_test()
            adapter_instance = self.first_adapter   #获取适配器

            if adapter_instance:
                message_to_send_str = await self.proactive_greeting()  #返回message
                print(f"wait to send{self.target_qq}\n")

                await adapter_instance.send_message(
                    target_type="person",
                    target_id=self.target_qq,
                    message=platform_message.MessageChain([message_to_send_str])
                )
            else:
                print("ERROR: Could not get adapter instance for proactive send.")

        except Exception as e:
            print(f"ERROR during proactive send: {e}")
            traceback.print_exc()
        print("proactive_send() task completed.")


    async def _check_user_inactivity(self):  #检测用户活跃时长

        await self._load_config(self.target_qq, "person")  # 读取配置
        config = self.waifu_cache[self.target_qq]
        current_time = datetime.datetime.now()
        last_message_time = config.memory.get_lastest_time(config.memory.short_term_memory)  #时间差值
        if not last_message_time:
            print(f"Could not extract last message time for user")
            return

        time_difference = current_time - last_message_time
        inactive_minutes = time_difference.total_seconds()
        inactive_minutes_float = float(inactive_minutes) / 60

        inactivity_threshold_minutes = config.proactive_min_inactive_hours
        inactivity_threshold_minutes_float = float(inactivity_threshold_minutes) * 60

        print(inactive_minutes_float)
        print(inactivity_threshold_minutes_float)

        if inactive_minutes_float > inactivity_threshold_minutes_float:  #差值大于规定最小时间

            current_time_hm_only = current_time.time()
            proactive_do_not_disturb_start = config.proactive_do_not_disturb_start
            proactive_do_not_disturb_end = config.proactive_do_not_disturb_end
            time_format = "%H:%M"
            dnd_start_time_obj = datetime.datetime.strptime(proactive_do_not_disturb_start, time_format).time()
            dnd_end_time_obj = datetime.datetime.strptime(proactive_do_not_disturb_end, time_format).time()

            is_currently_do_not_disturb = False
            print(
                f"Check: Current time: {current_time_hm_only.strftime(time_format)}, Period: {proactive_do_not_disturb_start} - {proactive_do_not_disturb_end}")
            if dnd_start_time_obj > dnd_end_time_obj:  # 跨夜
                if current_time_hm_only >= dnd_start_time_obj or current_time_hm_only < dnd_end_time_obj:
                    is_currently_do_not_disturb = True
            else:  # 不跨夜
                if dnd_start_time_obj <= current_time_hm_only < dnd_end_time_obj:
                    is_currently_do_not_disturb = True
            if is_currently_do_not_disturb:
                print(
                    f"勿扰时间")
            else:
                print(f"bot开始主动发送消息!")
                asyncio.create_task(self.proactive_send())  #主动发消息
        else:
            print(f"ERROR Inactivity: Could not send greeting ")
            return


    async def _proactive_loop(self):
        print("!!_proactive_loop:!!\n")
        if not self.target_qq:  # 检查是否为空或只包含空白
            print("ERROR:self.target_qq is not configured correctly. .\n")
            self.ap.logger.error("self.target_qq is invalid..\n")
            return # 直接退出循环任务

        await self._load_config(self.target_qq, "person")  # 读取配置


        config = self.waifu_cache[self.target_qq]
        self.ap.logger.info(f"proactive_mode : {config.proactive_greeting_enabled} ")
        self.ap.logger.info(f"summarization_mode : {config.summarization_mode} ")

        if config.proactive_greeting_enabled and config.summarization_mode:
            self.ap.logger.info(
                f"WaifuPlugin: Proactive loop started.")
            initial_loop_delay = 30  # 冷启动

            try:
                await asyncio.sleep(initial_loop_delay)
            except asyncio.CancelledError:
                self.ap.logger.info("WaifuPlugin:cancelled during initial delay.")
                return

            while True:  #循环检测用户状态
                self.ap.logger.info(f"WaifuPlugin Loop: Running inactivity check for user {self.target_qq}...")
                try:
                    probability_to_greet = config.proactive_greeting_probability
                    self.ap.logger.info(
                        f"probability:{probability_to_greet}")
                    if random.randint(1, 100) <= probability_to_greet:  #几率
                        await self._check_user_inactivity()  #进入检测用户活跃时间


                except asyncio.CancelledError:
                    self.ap.logger.info("WaifuPlugin: Proactive loop cancelled during check/greet.")
                    break
                except Exception as e_loop:
                    self.ap.logger.error(f"WaifuPlugin ERROR in proactive greeting loop: {e_loop}")
                    traceback.print_exc()  # 打印错误

                loop_time = 1800  #每三十分钟进行一次检查

                self.ap.logger.info(f"WaifuPlugin Loop: Check finished. Sleeping for {loop_time} seconds...")

                try:
                    await asyncio.sleep(loop_time)
                except asyncio.CancelledError:
                    self.ap.logger.info("WaifuPlugin: Proactive greeting loop cancelled during sleep.")
                    break  # 退出循环

#---------


    async def destroy(self):
        self.ap.logger.warning("Waifu插件正在退出....")
    # @handler(NormalMessageResponded)
    # async def normal_message_responded(self, ctx: EventContext):
    #     self.ap.logger.info(f"LangGPT的NormalMessageResponded: {str(ctx.event.response_text)}。")

    async def _access_control_check(self, ctx: EventContext) -> bool:
        """
        访问控制检查，根据配置判断是否允许继续处理
        :param ctx: 包含事件上下文信息的 EventContext 对象
        :return: True if allowed to continue, False otherwise
        """
        bot_account_id = ctx.event.query.adapter.bot_account_id
        text_message = str(ctx.event.query.message_chain)
        launcher_id = ctx.event.launcher_id
        sender_id = ctx.event.sender_id
        launcher_type = ctx.event.launcher_type
        event_type = "PMR"
        if isinstance(ctx.event, GroupNormalMessageReceived):
            event_type = "GNMR"
        elif isinstance(ctx.event, GroupMessageReceived):
            event_type = "GMR"

        # 黑白名单检查
        mode = self.ap.instance_config.data.get("pipeline", {}).get("access-control", {}).get("mode")
        sess_list = set(self.ap.instance_config.data.get("pipeline", {}).get("access-control", {}).get(mode, []))

        found = (launcher_type == "group" and "group_*" in sess_list) or (launcher_type == "person" and "person_*" in sess_list) or f"{launcher_type}_{launcher_id}" in sess_list

        if (mode == "whitelist" and not found) or (mode == "blacklist" and found):
            reason = "不在白名单中" if mode == "whitelist" else "在黑名单中"
            self.ap.logger.info(f"拒绝访问: {launcher_type}_{launcher_id} {reason}。")
            return False

        # 检查配置是否存在，若不存在则加载配置
        if launcher_id not in self.waifu_cache:
            await self._load_config(launcher_id, ctx.event.launcher_type)
        waifu_data = self.waifu_cache.get(launcher_id, None)
        if waifu_data:
            waifu_data.memory.bot_account_id = bot_account_id
        # 继承LangBot的群消息响应规则时忽略 GroupMessageReceived 信号
        if event_type == "GMR" and waifu_data.langbot_group_rule == True:
            return False
        # 仅由Waifu管理群聊响应规则时忽略 GroupNormalMessageReceived 信号
        if event_type == "GNMR" and waifu_data.langbot_group_rule == False:
            return False

        # 排除主项目命令
        cmd_prefix = self.ap.instance_config.data.get("command", {}).get("command-prefix", [])
        if any(text_message.startswith(prefix) for prefix in cmd_prefix):
            return False

        # 排除特定前缀
        if waifu_data and any(text_message.startswith(prefix) for prefix in waifu_data.ignore_prefix):
            return False

        # Waifu 群聊成员黑名单
        if waifu_data and sender_id in waifu_data.blacklist:
            self.ap.logger.info(f"已屏蔽黑名单中{sender_id}的发言: {str(text_message)}。")
            return False

        return True

    @handler(PersonMessageReceived)
    async def person_message_received(self, ctx: EventContext):
        if not await self._access_control_check(ctx):
            return

        need_assistant_reply, need_save_memory = await self._handle_command(ctx)
        if need_assistant_reply:
            await self._request_person_reply(ctx, need_save_memory)
            asyncio.create_task(self._handle_narration(ctx, ctx.event.launcher_id))
            ctx.prevent_default()  # 阻止 LangBot 的默认回复行为

    @handler(GroupMessageReceived)
    @handler(GroupNormalMessageReceived)
    async def group_message_received(self, ctx: EventContext):
        if not await self._access_control_check(ctx):
            return

        # 在GroupNormalMessageReceived的ctx.event.query.message_chain会将At移除
        # 所以这在经过主项目处理前先进行备份
        self.waifu_cache[ctx.event.launcher_id].group_message_chain = copy.deepcopy(ctx.event.query.message_chain)

        need_assistant_reply, _ = await self._handle_command(ctx)
        if need_assistant_reply:
            await self._request_group_reply(ctx)
            ctx.prevent_default()  # 阻止 LangBot 的默认回复行为

    async def _load_config(self, launcher_id: str, launcher_type: str):    ##加载配置
        self.waifu_cache[launcher_id] = WaifuCache(self.ap, launcher_id, launcher_type)
        cache = self.waifu_cache[launcher_id]

        config_mgr = ConfigManager(f"data/plugins/Waifu/config/waifu", "plugins/Waifu/templates/waifu", launcher_id) #读取用户配置
        await config_mgr.load_config(completion=True)

        character = config_mgr.data.get("character", f"default")
        if character == "default":  # 区分私聊和群聊的模板
            character = f"default_{launcher_type}"
        else:
            character = character.replace(".yaml", "")

        cache.narrate_intervals = config_mgr.data.get("intervals", [])
        cache.story_mode_flag = config_mgr.data.get("story_mode", True)
        cache.thinking_mode_flag = config_mgr.data.get("thinking_mode", True)
        cache.conversation_analysis_flag = config_mgr.data.get("conversation_analysis", True)
        cache.display_thinking = config_mgr.data.get("display_thinking", True)
        cache.display_value = config_mgr.data.get("display_value", False)
        cache.response_rate = config_mgr.data.get("response_rate", 0.7)
        cache.summarization_mode = config_mgr.data.get("summarization_mode", False)
        cache.personate_mode = config_mgr.data.get("personate_mode", True)
        cache.jail_break_mode = config_mgr.data.get("jail_break_mode", "off")
        cache.bracket_rate = config_mgr.data.get("bracket_rate", [])
        cache.group_response_delay = config_mgr.data.get("group_response_delay", 10)
        cache.person_response_delay = config_mgr.data.get("person_response_delay", 0)
        cache.personate_delay = config_mgr.data.get("personate_delay", 0)
        cache.continued_rate = config_mgr.data.get("continued_rate", 0.5)
        cache.continued_max_count = config_mgr.data.get("continued_max_count", 2)
        cache.blacklist = config_mgr.data.get("blacklist", [])
        cache.langbot_group_rule = config_mgr.data.get("langbot_group_rule", False)
        cache.ignore_prefix = config_mgr.data.get("ignore_prefix", [])

        cache.proactive_greeting_enabled = config_mgr.data.get("proactive_greeting_enabled", False)
        cache.proactive_greeting_probability = config_mgr.data.get("proactive_greeting_probability", 0)
        cache.proactive_min_inactive_hours = config_mgr.data.get("proactive_min_inactive_hours", 3.0)
        cache.proactive_max_inactive_hours = config_mgr.data.get("proactive_max_inactive_hours", 4.0)
        if cache.proactive_max_inactive_hours < cache.proactive_min_inactive_hours:
            cache.proactive_max_inactive_hours = cache.proactive_min_inactive_hours

        cache.proactive_do_not_disturb_start = config_mgr.data.get("proactive_do_not_disturb_start","23:00")
        cache.proactive_do_not_disturb_end = config_mgr.data.get("proactive_do_not_disturb_end","08:00")
     #   cache.target_user_id = config_mgr.data.get("target_user_id","")


        await cache.memory.load_config(character, launcher_id, launcher_type)
        await cache.value_game.load_config(character, launcher_id, launcher_type)
        await cache.cards.load_config(character, launcher_type)
        await cache.narrator.load_config()

        self._set_jail_break(cache, "off")
        if cache.jail_break_mode in ["before", "after", "end", "all"]:
            self._set_jail_break(cache, cache.jail_break_mode)

        self._set_permissions_recursively("data/plugins/Waifu/", 0o777)

    async def _handle_command(self, ctx: EventContext) -> typing.Tuple[bool, bool]:
        need_assistant_reply = False
        need_save_memory = False
        response = ""
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache[launcher_id]
        msg = str(ctx.event.query.message_chain)
        self.ap.logger.info(f"Waifu处理消息:{msg}")

        if msg.startswith("请设计"):
            content = msg[3:].strip()
            response = await self._generator.return_list(content)
        elif msg.startswith("请选择"):
            content = msg[3:].strip()
            parts = content.split("|")
            if len(parts) == 2:
                question = parts[0].strip()
                options = [opt.strip() for opt in parts[1].split(",")]
                response = await self._generator.select_from_list(question, options)
        elif msg.startswith("回答数字"):
            content = msg[4:].strip()
            response = await self._generator.return_number(content)
        elif msg.startswith("回答问题"):
            content = msg[4:].strip()
            parts = content.split("|")
            system_prompt = None
            if len(parts) == 2:
                system_prompt = parts[0].strip()
                user_prompt = parts[1].strip()
            else:
                user_prompt = content
            response = await self._generator.return_string(user_prompt, [], system_prompt)
        elif msg == "全部记忆":
            response = config.memory.get_all_memories()
        elif msg == "会话记忆":
            response = config.memory.get_memories_session()
        elif msg == "最近记忆":
            response = config.memory.get_latest_memory()
        elif msg == "最近召回":
            response = config.memory.get_last_recall_memories()
        elif msg == "最近L0召回":
            response = config.memory.get_last_l0_recall_memories()
        elif msg == "最近L1召回":
            response = config.memory.get_last_l1_recall_memories()
        elif msg == "最近L2召回":
            response = config.memory.get_last_l2_recall_memories()
        elif msg == "最近L3召回":
            response = config.memory.get_last_l3_recall_memories()
        elif msg == "最近L4召回":
            response = config.memory.get_last_l4_recall_memories()
        elif msg == "最近L5召回":
            response = config.memory.get_last_l5_recall_memories()
        elif msg == "召回阈值":
            response = config.memory.format_thresholds()
        elif msg == "删除记忆":
            response = self._stop_timer(launcher_id)
            config.memory.delete_local_files()
            config.value_game.reset_value()
            response += "记忆已删除。"
        elif msg.startswith("修改数值"):
            value = int(msg[4:].strip())
            config.value_game.change_manner_value(value)
            response = f"数值已改变：{value}"
        elif msg == "态度":
            manner = config.value_game.get_manner_description()
            if manner:
                response = f"💕值：{config.value_game.get_value()}\n态度：{manner}"
            else:
                response = f"错误：未正确设定态度值相关配置"
        elif msg == "加载配置":
            launcher_type = ctx.event.launcher_type
            await self._load_config(launcher_id, launcher_type)
            response = "配置已重载"
        elif msg == "停止活动":
            response = self._stop_timer(launcher_id)
        elif msg == "开场场景":
            response = config.memory.to_custom_names(config.cards.get_prologue())
            ctx.event.query.message_chain = platform_message.MessageChain([f"控制人物narrator|{response}"])
            need_assistant_reply, need_save_memory = await self._handle_command(ctx)
        elif msg == "旁白":
            await self._narrate(ctx, launcher_id)
        elif msg == "继续":
            await self._continue_person_reply(ctx)
        elif msg.startswith("控制人物"):
            content = msg[4:].strip()
            parts = content.split("|")
            if len(parts) == 2:
                role = parts[0].strip()
                if role.lower() == "user":
                    role = config.memory.user_name
                prompt = parts[1].strip()
                if prompt == "继续":
                    user_prompt = await config.thoughts.generate_character_prompt(config.memory, config.cards, role)
                    if user_prompt:  # 自动生成角色发言
                        self._generator.set_speakers([role])
                        prompt = await self._generator.return_chat(user_prompt)
                        response = f"{role}：{prompt}"
                        await config.memory.save_memory(role=role, content=prompt)
                        need_assistant_reply = True
                    else:
                        response = f"错误：该命令不支援的该角色"
                else:  # 人工指定角色发言
                    await config.memory.save_memory(role=role, content=prompt)
                    need_assistant_reply = True
        elif msg.startswith("推进剧情"):
            role = msg[4:].strip()
            if not role:  # 若不指定哪个角色推进剧情，默认为user
                role = "user"
            ctx.event.query.message_chain = platform_message.MessageChain(["旁白"])
            need_assistant_reply, need_save_memory = await self._handle_command(ctx)  # 此时不会触发assistant回复
            ctx.event.query.message_chain = platform_message.MessageChain([f"控制人物{role}|继续"])
            need_assistant_reply, need_save_memory = await self._handle_command(ctx)
        elif msg.startswith("功能测试"):
            # 隐藏指令，功能测试会清空记忆，请谨慎执行。
            await self._test(ctx)
        elif msg == "撤回":
            response = f"已撤回：\n{await config.memory.remove_last_memory()}"
        elif msg == "列出命令":
            response = self._list_commands()
        else:
            need_assistant_reply = True
            need_save_memory = True

        if response:
            await ctx.event.query.adapter.reply_message(ctx.event.query.message_event, platform_message.MessageChain([str(response)]), False)
        return need_assistant_reply, need_save_memory

    def _list_commands(self) -> str:
        return "\n\n".join([f"{cmd}: {desc}" for cmd, desc in COMMANDS.items()])

    def _stop_timer(self, launcher_id: str):
        if launcher_id in self.waifu_cache and self.waifu_cache[launcher_id].launcher_timer_tasks:
            self.waifu_cache[launcher_id].launcher_timer_tasks.cancel()
            self.waifu_cache[launcher_id].launcher_timer_tasks = None
            return "计时器已停止。"
        else:
            return "没有正在运行的计时器。"

    def _ensure_required_files_exist(self):
        directories = ["data/plugins/Waifu/cards", "data/plugins/Waifu/config", "data/plugins/Waifu/data"]

        for directory in directories:
            if not os.path.exists(directory):
                os.makedirs(directory)
                self.ap.logger.info(f"Directory created: {directory}")

        files = ["jail_break_before.txt", "jail_break_after.txt", "jail_break_end.txt", "tidy.py"]
        for file in files:
            file_path = f"data/plugins/Waifu/config/{file}"
            template_path = f"plugins/Waifu/templates/{file}"
            if not os.path.exists(file_path) and os.path.exists(template_path):
                # 如果配置文件不存在，并且提供了模板，则使用模板创建配置文件
                shutil.copyfile(template_path, file_path)

    def _set_permissions_recursively(self, path, mode):
        for root, dirs, files in os.walk(path):
            for dirname in dirs:
                os.chmod(os.path.join(root, dirname), mode)
            for filename in files:
                os.chmod(os.path.join(root, filename), mode)

    async def _request_group_reply(self, ctx: EventContext):
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache[launcher_id]
        sender = ctx.event.query.message_event.sender.member_name
        msg = await self._vision(ctx)  # 用眼睛看消息？
        await config.memory.save_memory(role=sender, content=msg)
        config.unreplied_count += 1
        await self._group_reply(ctx)

    async def _group_reply(self, ctx: EventContext):
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache[launcher_id]
        need_assistant_reply = False
        if config.group_message_chain and config.group_message_chain.has(platform_message.At(ctx.event.query.adapter.bot_account_id)):
            need_assistant_reply = True
        if config.unreplied_count >= config.memory.response_min_conversations:
            if random.random() < config.response_rate:
                need_assistant_reply = True
        else:
            self.ap.logger.info(f"群聊{launcher_id}还差{config.memory.response_min_conversations - config.unreplied_count}条消息触发回复")

        config.group_message_chain = None
        if need_assistant_reply:
            if launcher_id not in self.waifu_cache or not config.response_timers_flag:
                config.response_timers_flag = True
                asyncio.create_task(self._delayed_group_reply(ctx))

    async def _delayed_group_reply(self, ctx: EventContext):
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache[launcher_id]
        self.ap.logger.info(f"wait group {launcher_id} for {config.group_response_delay}s")
        await asyncio.sleep(config.group_response_delay)
        self.ap.logger.info(f"generating group {launcher_id} response")

        try:
            # 触发回复后，首先检查是否满足预设回复形式，预设回复不用脑子，不走模型。
            response = self._response_presets(launcher_id)
            if response:
                config.unreplied_count = 0
                await config.memory.save_memory(role="assistant", content=response)
                await self._reply(ctx, f"{response}", True)
            else:
                await self._send_group_reply(ctx)

            config.response_timers_flag = False
            await self._group_reply(ctx)  # 检查是否回复期间又满足响应条件

        except Exception as e:
            self.ap.logger.error(f"Error occurred during group reply: {e}")
            raise

        finally:
            config.response_timers_flag = False

    async def _send_group_reply(self, ctx: EventContext):
        """
        调用模型生成群聊回复
        """
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache[launcher_id]
        if config.summarization_mode:
            _, unreplied_conversations = config.memory.get_unreplied_msg(config.unreplied_count)
            related_memories = await config.memory.load_memory(unreplied_conversations)
            if related_memories:
                config.cards.set_memory(related_memories)
        # 如果是群聊则不修改为自定义角色名
        system_prompt = config.memory.to_custom_names(config.cards.generate_system_prompt())
        # 备份然后重置避免回复过程中接收到新讯息导致计数错误
        unreplied_count = config.unreplied_count
        config.unreplied_count = 0
        user_prompt = config.memory.get_normalize_short_term_memory()  # 默认为当前short_term_memory_size条聊天记录
        if config.thinking_mode_flag:
            user_prompt, analysis = await config.thoughts.generate_group_prompt(config.memory, config.cards, unreplied_count)
            if config.display_thinking and config.conversation_analysis_flag:
                await self._reply(ctx, f"【分析】：{analysis}")
        self._generator.set_speakers([config.memory.assistant_name])
        response = await self._generator.return_chat(user_prompt, system_prompt)
        await config.memory.save_memory(role="assistant", content=response)

        if config.personate_mode:
            await self._send_personate_reply(ctx, response)
        else:
            await self._reply(ctx, f"{response}", True)

    async def _request_person_reply(self, ctx: EventContext, need_save_memory: bool):
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache[launcher_id]

        if need_save_memory:  # 此处仅处理user的发言，保存至短期记忆
            msg = await self._vision(ctx)  # 用眼睛看消息？
            await config.memory.save_memory(role="user", content=msg)
        config.unreplied_count += 1
        await self._person_reply(ctx)

    async def _person_reply(self, ctx: EventContext):   #私聊回复
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache[launcher_id]


        if config.unreplied_count > 0:
            if launcher_id not in self.waifu_cache or not config.response_timers_flag:
                if self.generator_model_ready:
                    config.response_timers_flag = True
                    asyncio.create_task(self._delayed_person_reply(ctx))  # 创建任务



    async def _delayed_person_reply(self, ctx: EventContext):
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache[launcher_id]
        self.ap.logger.info(f"wait person {launcher_id} for {config.person_response_delay}s")
        await asyncio.sleep(config.person_response_delay)
        self.ap.logger.info(f"generating person {launcher_id} response")

        try:
            config.unreplied_count = 0
            if config.story_mode_flag:
                value_game = config.value_game
                manner = value_game.get_manner_description()
                if manner:
                    config.cards.set_manner(manner)
            if config.summarization_mode:
                _, unreplied_conversations = config.memory.get_unreplied_msg(config.unreplied_count)
                related_memories = await config.memory.load_memory(unreplied_conversations)
                config.cards.set_memory(related_memories)

            # user_prompt不直接从msg生成，而是先将msg保存至短期记忆，再由短期记忆生成。
            # 好处是不论旁白或是控制人物，都能直接调用记忆生成回复
            user_prompt = config.memory.get_normalize_short_term_memory()  # 默认为当前short_term_memory_size条聊天记录
            if config.thinking_mode_flag:
                user_prompt, analysis = await config.thoughts.generate_person_prompt(config.memory, config.cards)
                if config.display_thinking and config.conversation_analysis_flag:
                    await self._reply(ctx, f"【分析】：{analysis}")
            await self._send_person_reply(ctx, user_prompt)  # 生成回复并发送

            if config.story_mode_flag:
                value_game = config.value_game
                await value_game.determine_manner_change(config.memory, config.continued_count)
                if config.display_value:  # 是否开启数值显示
                    response = value_game.get_manner_value_str()
                    if response:
                        await self._reply(ctx, f"{response}")
            config.continued_count = 0

            config.response_timers_flag = False
          #  await self._person_reply(ctx)  # 检查是否回复期间又满足响应条件

        except Exception as e:
            self.ap.logger.error(f"Error occurred during person reply: {e}")
            raise
        finally:
            config.response_timers_flag = False

    async def _send_person_reply(self, ctx: EventContext, user_prompt: str | list[llm_entities.ContentElement]):
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache[launcher_id]
        system_prompt = config.memory.to_custom_names(config.cards.generate_system_prompt())
        self._generator.set_speakers([config.memory.assistant_name])
        response = await self._generator.return_chat(user_prompt, system_prompt)   #发消息
        await config.memory.save_memory(role="assistant", content=response)  #存入消息对话

        if config.personate_mode:
            await self._send_personate_reply(ctx, response)
        else:
            await self._reply(ctx, f"{response}", True)

        if random.random() < config.continued_rate and config.continued_count < config.continued_max_count:  # 机率触发继续发言
            if not config.personate_mode:  # 拟人模式使用默认打字时间，非拟人模式喘口气
                await asyncio.sleep(1)
            if config.unreplied_count == 0:  # 用户未曾打断
                config.continued_count += 1
                self.ap.logger.info(f"模型触发继续回复{config.continued_count}次")
                await self._continue_person_reply(ctx)

    async def _continue_person_reply(self, ctx: EventContext):
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache[launcher_id]
        user_prompt = await config.thoughts.generate_person_continue_prompt(config.memory)
        await self._send_person_reply(ctx, user_prompt)  # 生成回复并发送

    async def _handle_narration(self, ctx: EventContext, launcher_id: str):
        if launcher_id in self.waifu_cache and self.waifu_cache[launcher_id].launcher_timer_tasks:
            self.waifu_cache[launcher_id].launcher_timer_tasks.cancel()

        self.waifu_cache[launcher_id].launcher_timer_tasks = asyncio.create_task(self._timed_narration_task(ctx, launcher_id))

    async def _timed_narration_task(self, ctx: EventContext, launcher_id: str):
        try:
            config = self.waifu_cache[launcher_id]
            for interval in config.narrate_intervals:
                self.ap.logger.info("Start narrate timer: {}".format(interval))
                await asyncio.create_task(self._sleep_and_narrate(ctx, launcher_id, interval))

            self.ap.logger.info("All intervals completed")
        except asyncio.CancelledError:
            self.ap.logger.info("Narrate timer stoped")
            pass

    async def _sleep_and_narrate(self, ctx: EventContext, launcher_id: str, interval: int):
        await asyncio.sleep(interval)
        await self._narrate(ctx, launcher_id)

    async def _narrate(self, ctx: EventContext, launcher_id: str):
        config = self.waifu_cache[launcher_id]
        conversations = config.memory.short_term_memory
        if len(conversations) < 2:
            return

        narration = await config.narrator.narrate(config.memory, config.cards)
        if narration:
            await self._reply(ctx, f"{config.memory.to_custom_names(narration)}")
            narration = config.memory.to_generic_names(narration)
            await config.memory.save_memory(role="narrator", content=narration)

    async def _send_personate_reply(self, ctx: EventContext, response: str):
        config = self.waifu_cache[ctx.event.launcher_id]
        parts = re.split(r"(?<!\d)[，。？！,.?!\n~〜](?!\d)", response)  # 保留分隔符(避免分割小数)
        combined_parts = []
        temp_part = ""

        for part in parts:
            part = part.strip()
            if not part:
                continue
            if part in ["，", "。", ",", ".", "\n"]:  # 删除的标点符号
                continue
            elif part in ["？", "！", "?", "!", "~", "〜"]:  # 保留的标点符号
                if temp_part or not combined_parts:
                    temp_part += part
                else:
                    combined_parts[-1] += part
            else:
                temp_part += " " + part
                if len(temp_part) >= 3:
                    combined_parts.append(temp_part.strip())
                    temp_part = ""

        if temp_part:  # 添加剩余部分
            combined_parts.append(temp_part.strip())

        # 如果response未使用分段标点符号，combined_parts为空，添加整个response作为一个单独的部分
        if not combined_parts:
            combined_parts.append(response)

        if combined_parts and len(config.bracket_rate) == 2:
            try:
                if random.random() < config.bracket_rate[0]:  # 老互联网冲浪人士了（）
                    combined_parts[-1] += "（）"
                elif random.random() < config.bracket_rate[1]:
                    combined_parts[-1] += "（"
            except Exception as e:
                self.ap.logger.error(f"Bracket addition failed: {e}")

        for part in combined_parts:
            await self._reply(ctx, f"{part}", True)
            self.ap.logger.info(f"发送：{part}")
            if config.personate_delay != 0:
                await asyncio.sleep(config.personate_delay)
            else:
                await asyncio.sleep(len(part) / 2)  # 根据字数计算延迟时间，假设每2个字符1秒

    async def _vision(self, ctx: EventContext) -> str:
        # 参考自preproc.py PreProcessor
        query = ctx.event.query
        has_image = False
        content_list = []

        session = await self.ap.sess_mgr.get_session(query)

        # 尝试从 query.pipeline_config 中获取 prompt_config
        # 假设 pipeline 配置中有一个名为 'initial_prompt' 的键，其值为 list[dict]
        # 如果没有，则使用一个空列表作为默认值
        prompt_config_from_pipeline = []
        if query.pipeline_config:
            prompt_config_from_pipeline = query.pipeline_config.get('initial_prompt', [])
            if not isinstance(prompt_config_from_pipeline, list):
                self.ap.logger.warning(f"Pipeline config 'initial_prompt' is not a list, using empty prompt for get_conversation. Found: {prompt_config_from_pipeline}")
                prompt_config_from_pipeline = []
        else:
            self.ap.logger.warning("query.pipeline_config is None, using empty prompt for get_conversation.")

        conversation = await self.ap.sess_mgr.get_conversation(query, session, prompt_config_from_pipeline)

        use_model = conversation.use_llm_model # Changed from conversation.use_model

        for me in query.message_chain:
            if isinstance(me, platform_message.Plain):
                content_list.append(llm_entities.ContentElement.from_text(me.text))
            elif isinstance(me, platform_message.Image):
                if self.ap.instance_config.data["enable-vision"] and use_model:
                    if me.url is not None:
                        has_image = True
                        content_list.append(llm_entities.ContentElement.from_image_url(str(me.url)))
                    elif me.base64 is not None:
                        has_image = True
                        content_list.append(llm_entities.ContentElement.from_image_base64(str(me.base64)))
        if not has_image:
            return str(query.message_chain)
        else:
            return await self.waifu_cache[ctx.event.launcher_id].thoughts.analyze_picture(content_list)

    def _remove_blank_lines(self, text: str) -> str:
        lines = text.split("\n")
        non_blank_lines = [line for line in lines if line.strip() != ""]
        return "\n".join(non_blank_lines)

    async def _reply(self, ctx: EventContext, response: str, event_trigger: bool = False):
        response_fixed = self._remove_blank_lines(response)
        await ctx.event.query.adapter.reply_message(ctx.event.query.message_event, platform_message.MessageChain([f"{response_fixed}"]), False)
        if event_trigger:
            await self._emit_responded_event(ctx, response_fixed)

    async def _emit_responded_event(self, ctx: EventContext, response: str):
        query = ctx.event.query
        session = await self.ap.sess_mgr.get_session(query)
        await self.ap.plugin_mgr.emit_event(
            event=NormalMessageResponded(
                launcher_type=query.launcher_type.value,
                launcher_id=query.launcher_id,
                sender_id=query.sender_id,
                session=session,
                prefix="",
                response_text=response,
                finish_reason="stop",
                funcs_called=[],
                query=query,
            )
        )

    def _response_presets(self, launcher_id: int):
        """
        预设形式的回复：复读
        """
        response = self._check_repeat(launcher_id)
        return response

    def _check_repeat(self, launcher_id: int) -> str:
        return self.waifu_cache[launcher_id].memory.get_repeat_msg()

    def _set_jail_break(self, cache: WaifuCache, type: str):
        self._generator.set_jail_break(type, cache.memory.user_name)
        cache.memory.set_jail_break(type, cache.memory.user_name)
        cache.value_game.set_jail_break(type, cache.memory.user_name)
        cache.narrator.set_jail_break(type, cache.memory.user_name)
        cache.thoughts.set_jail_break(type, cache.memory.user_name)

    async def _test(self, ctx: EventContext):
        # 保存当前配置状态
        original_config = WaifuCache(self.ap, ctx.event.launcher_id, ctx.event.launcher_type)
        current_cache = self.waifu_cache.get(ctx.event.launcher_id)
        if current_cache:
            # 深拷贝可变对象，如列表和字典
            for attr, value in vars(current_cache).items():
                if isinstance(value, (list, dict)):
                    setattr(original_config, attr, copy.deepcopy(value))
                else:
                    setattr(original_config, attr, value)

        config = self.waifu_cache[ctx.event.launcher_id]
        config.langbot_group_rule = True
        await self._test_command(ctx, "测试群聊规则#你好")
        config.langbot_group_rule = False
        await self._test_command(ctx, "测试群聊规则#你好")
        config.narrate_intervals = [3,5]
        await self._test_command(ctx, "测试旁白#你好")
        config.story_mode_flag = False
        await self._test_command(ctx, "关闭故事模式#你好")
        config.story_mode_flag = True
        await self._test_command(ctx, "开启故事模式#你好")
        config.thinking_mode_flag = False
        await self._test_command(ctx, "关闭思考模式#你好")
        config.thinking_mode_flag = True
        await self._test_command(ctx, "开启思考模式#你好")
        config.conversation_analysis_flag = False
        await self._test_command(ctx, "关闭会话分析#你好")
        config.conversation_analysis_flag = True
        await self._test_command(ctx, "开启会话分析#你好")
        config.display_thinking = False
        await self._test_command(ctx, "关闭显示思考过程#你好")
        config.display_thinking = True
        await self._test_command(ctx, "开启显示思考过程#你好")
        config.display_value = False
        await self._test_command(ctx, "关闭显示数值#你好")
        config.display_value = True
        await self._test_command(ctx, "开启显示数值#你好")
        config.response_rate = 0
        await self._test_command(ctx, "关闭回复#你好")
        config.response_rate = 1
        await self._test_command(ctx, "开启回复#你好")
        config.summarization_mode = False
        await self._test_command(ctx, "关闭总结模式#你好")
        config.summarization_mode = True
        await self._test_command(ctx, "开启总结模式#你好")
        config.personate_mode = False
        await self._test_command(ctx, "关闭拟人模式#你好")
        config.personate_mode = True
        await self._test_command(ctx, "开启拟人模式#你好")
        config.jail_break_mode = "all"
        self._set_jail_break(config, config.jail_break_mode)
        await self._test_command(ctx, "手动书写“指定角色”发言#控制人物快递员|叮咚~有人在家吗，有你们的快递！")
        config.jail_break_mode = "off"
        self._set_jail_break(config, "off")
        config.personate_delay = 3
        await self._test_command(ctx, "主动触发旁白推进剧情#旁白")
        config.personate_delay = 0
        config.continued_rate = 1
        config.continued_max_count = 2
        await self._test_command(ctx, "请AI生成“指定角色”发言#控制人物快递员|继续")
        config.continued_rate = 0
        config.continued_max_count = 0
        await self._test_command(ctx, "使用“指定角色”推进剧情#推进剧情")
        await self._test_command(ctx, "停止旁白计时器#停止活动")
        await self._test_command(ctx, "查看当前态度数值及当前行为准则（Manner）#态度")
        await self._test_command(ctx, "更改态度数值#修改数值5")
        await self._test_command(ctx, "删除所有记忆#删除记忆")
        await self._test_command(ctx, "显示最近的长期记忆#最近记忆")
        await self._test_command(ctx, "显示最近召回的记忆#最近召回")
        await self._test_command(ctx, "列出目前支援所有命令#列出命令")
        # 恢复原始配置
        for attr, value in vars(original_config).items():
            if hasattr(self.waifu_cache[ctx.event.launcher_id], attr):
                setattr(self.waifu_cache[ctx.event.launcher_id], attr, value)

        # 特别处理需要重新设置的属性
        self._set_jail_break(self.waifu_cache[ctx.event.launcher_id], original_config.jail_break_mode)
        if original_config.narrate_intervals:
            asyncio.create_task(self._handle_narration(ctx, ctx.event.launcher_id))
        else:
            self._stop_timer(ctx.event.launcher_id)

        await ctx.reply(platform_message.MessageChain([platform_message.Plain("测试完成，已恢复配置。")]))

    async def _test_command(self, ctx: EventContext, command: str):
        parts = command.split("#")
        if len(parts) == 2:
            note = parts[0].strip()
            cmd = parts[1].strip()
        await self._reply(ctx, f"【模拟发送】（{note}）\n{cmd}")
        ctx.event.query.message_chain = platform_message.MessageChain([cmd])
        need_assistant_reply, need_save_memory = await self._handle_command(ctx)
        if need_assistant_reply:
            if need_save_memory:
                msg = await self._vision(ctx)
                await self.waifu_cache[ctx.event.launcher_id].memory.save_memory(role="user", content=msg)
            await self._delayed_person_reply(ctx)

    def __del__(self):
        for config in self.waifu_cache.values():
            if config.launcher_timer_tasks:
                config.launcher_timer_tasks.cancel()




    def _load_target_qq_from_global_config_file(self,file_path: str) -> typing.Optional[str]:  #加载plugins/Waifu/templates/waifu.yaml 里配置的qq号

        if not os.path.exists(file_path):
            print(f"ERROR: file not found: {file_path}\\n")
            return None

        config_data: typing.Optional[dict] = None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)
        except yaml.YAMLError as ye:
            print(f"ERROR: YAML parsing error in {file_path}: {ye}\\n")
            return None
        except IOError as ioe:
            print(f"ERROR: Could not read file {file_path}: {ioe}\\n")
            return None
        except Exception as e_file:
            print(f"ERROR: Unexpected error opening/reading file {file_path}: {e_file}\\n")
            traceback.print_exc()
            return None

        if not config_data or not isinstance(config_data, dict):
            print(f"ERROR: file {file_path} is empty or not a valid YAML dictionary after loading.\\n")
            return None

        target_qq_from_config = config_data.get("target_user_id")  #获取qq号

        if target_qq_from_config and isinstance(target_qq_from_config, str) and target_qq_from_config.strip():

            cleaned_target_qq = target_qq_from_config.strip()
            print(f"Successfully loaded default_proactive_target_qq: {cleaned_target_qq}")
            return cleaned_target_qq
        else:
            print(
                f"ERROR: 'target_qq' not found, or is empty in {file_path}. Value was: '{target_qq_from_config}'\\n")
            return None
