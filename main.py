import asyncio
import typing
import os
import random
import re
import copy
import shutil
import base64
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
from plugins.Waifu.cells.emoji import EmojiManager  # 导入表情包管理类
from plugins.Waifu.organs.memories import Memory
from plugins.Waifu.systems.narrator import Narrator
from plugins.Waifu.systems.value_game import ValueGame
from plugins.Waifu.organs.thoughts import Thoughts

# 定义支持的命令及其说明
COMMANDS = {
    "列出命令": "列出目前支援所有命令及介绍，用法：[列出命令]。",
    "全部记忆": "显示目前所有长短期记忆，用法：[全部记忆]。",
    "删除记忆": "删除所有长短期记忆，用法：[删除记忆]。",
    "修改数值": "修改Value Game的数字，用法：[修改数值][数值]。",
    "态度": "显示当前Value Game所对应的态度Manner，用法：[态度]。",
    "加载配置": "重新加载所有配置文件（仅Waifu），用法：[加载配置]。",
    "停止活动": "停止旁白计时器，用法：[停止活动]。",
    "开场场景": "主动触发旁白输出角色卡中的开场场景Prologue，用法：[开场场景]。",
    "旁白": "主动触发旁白推进剧情，用法：[旁白]。",
    "继续": "主动触发Bot继续回复推进剧情，用法：[继续]。",
    "控制人物": "控制角色发言（行动）或触发AI生成角色消息，用法：[控制人物][角色名称/assistant]|[发言(行动)/继续]。",
    "推进剧情": "自动依序调用：旁白 -> 控制人物，角色名称省略默认为user，用法：[推进剧情][角色名称]。",
    "撤回": "从短期记忆中删除最后的对话，用法：[撤回]。",
    "请设计": "调试：设计一个列表，用法：[请设计][设计内容]。",
    "请选择": "调试：从给定列表中选择，用法：[请选择][问题]|[选项1,选项2,……]。",
    "回答数字": "调试：返回数字答案，用法：[回答数字][问题]。",
    "回答问题": "调试：可自定系统提示的问答模式，用法：[回答问题][系统提示语]|[用户提示语] / [回答问题][用户提示语]。",
    "表情开关": "开启或关闭表情包功能，用法：[表情开关]。",  # 新增表情包开关命令
    "刷新表情": "重新扫描表情包目录并更新索引，用法：[刷新表情]。",
}

# 定义缓存类，用于存储与特定用户的交互数据
class WaifuCache:
    def __init__(self, ap: app.Application, launcher_id: str, launcher_type: str):
        self.launcher_id = launcher_id  # 用户ID
        self.launcher_type = launcher_type  # 用户类型（群聊或私聊）
        self.langbot_group_rule = False  # 是否启用群聊规则
        self.memory = Memory(ap, launcher_id, launcher_type)  # 内存管理
        self.value_game = ValueGame(ap)  # 数值游戏管理
        self.cards = Cards(ap)  # 卡片管理
        self.narrator = Narrator(ap, launcher_id)  # 旁白管理
        self.thoughts = Thoughts(ap)  # 思维管理
        self.emoji_manager = EmojiManager(ap)  # 表情包管理
        self.conversation_analysis_flag = True  # 是否启用对话分析
        self.thinking_mode_flag = True  # 是否启用思考模式
        self.story_mode_flag = True  # 是否启用故事模式
        self.display_thinking = True  # 是否显示思考过程
        self.display_value = True  # 是否显示数值变化
        self.response_rate = 0.7  # 回复概率
        self.narrate_intervals = []  # 旁白间隔时间
        self.launcher_timer_tasks = None  # 计时器任务
        self.unreplied_count = 0  # 未回复的消息计数
        self.continued_rate = 0.2  # 继续回复的概率
        self.continued_count = 0  # 当前连续回复次数
        self.continued_max_count = 2  # 最大连续回复次数
        self.summarization_mode = True  # 是否启用摘要模式
        self.personate_mode = True  # 是否启用拟人化模式
        self.jail_break_mode = "off"  # 越狱模式状态
        self.response_timers_flag = False  # 是否启用回复定时器
        self.bracket_rate = []  # 括号使用概率
        self.group_response_delay = 3  # 群聊回复延迟
        self.person_response_delay = 0  # 私聊回复延迟
        self.personate_delay = 0  # 拟人化延迟
        self.group_message_chain = None  # 群聊消息链备份
        self.blacklist = []  # 黑名单
        self.ignore_prefix = []  # 忽略前缀

# 定义Runner类，用于处理Waifu模式的请求
@runner.runner_class("waifu-mode")
class WaifuRunner(runner.RequestRunner):
    async def run(self, query: core_entities.Query):
        if False:  # 永远不会执行，但保留生成器语法
            yield
        return

# 定义Waifu插件类
@register(name="Waifu_Expression_package", description="会发表情包的可爱老婆！", version="1.0.0", author="Cheng-MaoMao")
class Waifu(BasePlugin):
    def __init__(self, host: APIHost):
        self.ap = host.ap  # 应用程序实例
        self._ensure_required_files_exist()  # 确保所需文件存在
        self._generator = Generator(self.ap)  # 初始化生成器
        self.waifu_cache: typing.Dict[str, WaifuCache] = {}  # 缓存字典
        self._set_permissions_recursively("data/plugins/Waifu/", 0o777)  # 设置目录权限

    # 插件初始化方法
    async def initialize(self):
        await self._set_runner("waifu-mode")  # 设置运行器为Waifu模式
        config_mgr = ConfigManager(f"data/plugins/Waifu/config/waifu", "plugins/Waifu/templates/waifu")
        await config_mgr.load_config(completion=True)  # 加载配置文件

    # 插件销毁方法
    async def destroy(self):
        await self._set_runner(self.ap.provider_cfg.data['runner'])  # 恢复默认运行器

    # 访问控制检查方法
    async def _access_control_check(self, ctx: EventContext) -> bool:
        bot_account_id = ctx.event.query.adapter.bot_account_id  # 获取机器人账号ID
        text_message = str(ctx.event.query.message_chain)  # 获取消息内容
        launcher_id = ctx.event.launcher_id  # 获取发起者ID
        sender_id = ctx.event.sender_id  # 获取发送者ID
        launcher_type = ctx.event.launcher_type  # 获取发起者类型
        event_type = "PMR"  # 默认事件类型为私聊消息接收

        # 根据事件类型调整event_type
        if isinstance(ctx.event, GroupNormalMessageReceived):
            event_type = "GNMR"
        elif isinstance(ctx.event, GroupMessageReceived):
            event_type = "GMR"

        # 黑白名单检查
        mode = self.ap.pipeline_cfg.data["access-control"]["mode"]
        sess_list = set(self.ap.pipeline_cfg.data["access-control"].get(mode, []))
        found = (launcher_type == "group" and "group_*" in sess_list) or (
            launcher_type == "person" and "person_*" in sess_list) or f"{launcher_type}_{launcher_id}" in sess_list

        if (mode == "whitelist" and not found) or (mode == "blacklist" and found):
            reason = "不在白名单中" if mode == "whitelist" else "在黑名单中"
            self.ap.logger.info(f"拒绝访问: {launcher_type}_{launcher_id} {reason}。")
            return False

        # 如果缓存中没有该用户的数据，则加载配置
        if launcher_id not in self.waifu_cache:
            await self._load_config(launcher_id, ctx.event.launcher_type)
        waifu_data = self.waifu_cache.get(launcher_id, None)
        if waifu_data:
            waifu_data.memory.bot_account_id = bot_account_id

        # 根据配置判断是否忽略某些事件
        if event_type == "GMR" and waifu_data.langbot_group_rule == True:
            return False
        if event_type == "GNMR" and waifu_data.langbot_group_rule == False:
            return False

        # 排除主项目命令和特定前缀的消息
        cmd_prefix = self.ap.command_cfg.data.get("command-prefix", [])
        if any(text_message.startswith(prefix) for prefix in cmd_prefix):
            return False
        if waifu_data and any(text_message.startswith(prefix) for prefix in waifu_data.ignore_prefix):
            return False

        # 检查发送者是否在黑名单中
        if waifu_data and sender_id in waifu_data.blacklist:
            self.ap.logger.info(f"已屏蔽黑名单中{sender_id}的发言: {str(text_message)}。")
            return False

        return True

    # 处理私聊消息接收事件
    @handler(PersonMessageReceived)
    async def person_message_received(self, ctx: EventContext):
        if not await self._access_control_check(ctx):
            return

        need_assistant_reply, need_save_memory = await self._handle_command(ctx)
        if need_assistant_reply:
            await self._request_person_reply(ctx, need_save_memory)
            asyncio.create_task(self._handle_narration(ctx, ctx.event.launcher_id))

    # 处理群聊消息接收事件
    @handler(GroupMessageReceived)
    @handler(GroupNormalMessageReceived)
    async def group_message_received(self, ctx: EventContext):
        if not await self._access_control_check(ctx):
            return

        self.waifu_cache[ctx.event.launcher_id].group_message_chain = copy.deepcopy(ctx.event.query.message_chain)

        need_assistant_reply, _ = await self._handle_command(ctx)
        if need_assistant_reply:
            await self._request_group_reply(ctx)

    # 加载配置方法
    async def _load_config(self, launcher_id: str, launcher_type: str):
        self.waifu_cache[launcher_id] = WaifuCache(self.ap, launcher_id, launcher_type)
        cache = self.waifu_cache[launcher_id]

        config_mgr = ConfigManager(f"data/plugins/Waifu/config/waifu", "plugins/Waifu/templates/waifu", launcher_id)
        await config_mgr.load_config(completion=True)

        character = config_mgr.data.get("character", f"default")
        if character == "default":
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

        await cache.memory.load_config(character, launcher_id, launcher_type)
        await cache.value_game.load_config(character, launcher_id, launcher_type)
        await cache.cards.load_config(character, launcher_type)
        await cache.narrator.load_config()

        self._set_jail_break(cache, "off")
        if cache.jail_break_mode in ["before", "after", "end", "all"]:
            self._set_jail_break(cache, cache.jail_break_mode)

        self._set_permissions_recursively("data/plugins/Waifu/", 0o777)

    # 设置运行器方法
    async def _set_runner(self, runner_name: str):
        runner_mgr = self.ap.runner_mgr
        if runner_mgr:
            for r in runner.preregistered_runners:
                if r.name == runner_name:
                    runner_mgr.using_runner = r(self.ap)
                    await runner_mgr.using_runner.initialize()
                    self.ap.logger.info(f"已设置运行器为 {runner_name}")
                    break
            else:
                raise Exception(f"Runner '{runner_name}' not found in preregistered_runners.")

    # 处理命令方法
    async def _handle_command(self, ctx: EventContext) -> typing.Tuple[bool, bool]:
        need_assistant_reply = False
        need_save_memory = False
        response = ""
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache[launcher_id]
        msg = str(ctx.event.query.message_chain)
    
        # 根据不同命令执行相应操作
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
                    if user_prompt:
                        self._generator.set_speakers([role])
                        prompt = await self._generator.return_chat(user_prompt)
                        response = f"{role}：{prompt}"
                        await config.memory.save_memory(role=role, content=prompt)
                        need_assistant_reply = True
                    else:
                        response = f"错误：该命令不支援的该角色"
                else:
                    await config.memory.save_memory(role=role, content=prompt)
                    need_assistant_reply = True
        elif msg.startswith("推进剧情"):
            role = msg[4:].strip()
            if not role:
                role = "user"
            ctx.event.query.message_chain = platform_message.MessageChain(["旁白"])
            need_assistant_reply, need_save_memory = await self._handle_command(ctx)
            ctx.event.query.message_chain = platform_message.MessageChain([f"控制人物{role}|继续"])
            need_assistant_reply, need_save_memory = await self._handle_command(ctx)
        elif msg == "撤回":
            response = f"已撤回：\n{await config.memory.remove_last_memory()}"
        elif msg == "表情开关":
            enabled = config.emoji_manager.toggle_emoji()
            response = f"表情包功能已{'开启' if enabled else '关闭'}"
        elif msg == "刷新表情":
            config.emoji_manager._scan_and_create_index()
            response = f"表情包索引已更新，共 {len(config.emoji_manager.emoji_index)} 个情感类别"
        elif msg == "列出命令":
            response = self._list_commands()
        else:
            need_assistant_reply = True
            need_save_memory = True
    
        if response:
            await ctx.event.query.adapter.reply_message(ctx.event.query.message_event, platform_message.MessageChain([str(response)]), False)
        return need_assistant_reply, need_save_memory

    # 列出所有命令的方法
    def _list_commands(self) -> str:
        return "\n\n".join([f"{cmd}: {desc}" for cmd, desc in COMMANDS.items()])

    # 停止计时器方法
    def _stop_timer(self, launcher_id: str):
        if launcher_id in self.waifu_cache and self.waifu_cache[launcher_id].launcher_timer_tasks:
            self.waifu_cache[launcher_id].launcher_timer_tasks.cancel()
            self.waifu_cache[launcher_id].launcher_timer_tasks = None
            return "计时器已停止。"
        else:
            return "没有正在运行的计时器。"

    # 确保所需文件存在的方法
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
                shutil.copyfile(template_path, file_path)

    # 递归设置目录权限的方法
    def _set_permissions_recursively(self, path, mode):
        for root, dirs, files in os.walk(path):
            for dirname in dirs:
                os.chmod(os.path.join(root, dirname), mode)
            for filename in files:
                os.chmod(os.path.join(root, filename), mode)

    # 请求群聊回复的方法
    async def _request_group_reply(self, ctx: EventContext):
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache[launcher_id]
        sender = ctx.event.query.message_event.sender.member_name
        msg = await self._vision(ctx)
        await config.memory.save_memory(role=sender, content=msg)
        config.unreplied_count += 1
        await self._group_reply(ctx)

    # 群聊回复逻辑方法
    async def _group_reply(self, ctx: EventContext):
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache[launcher_id]
        need_assistant_reply = False

        if config.group_message_chain and config.group_message_chain.has(platform_message.At(ctx.event.query.adapter.bot_account_id)):
            need_assistant_reply = True
        if config.unreplied_count >= config.memory.response_min_conversations:
            if random.random() < config.response_rate:
                need_assistant_reply = True

        config.group_message_chain = None
        if need_assistant_reply:
            if launcher_id not in self.waifu_cache or not config.response_timers_flag:
                config.response_timers_flag = True
                asyncio.create_task(self._delayed_group_reply(ctx))

    # 延迟群聊回复方法
    async def _delayed_group_reply(self, ctx: EventContext):
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache[launcher_id]
        await asyncio.sleep(config.group_response_delay)
        try:
            response = self._response_presets(launcher_id)
            if response:
                config.unreplied_count = 0
                await config.memory.save_memory(role="assistant", content=response)
                await self._reply(ctx, f"{response}", True)
            else:
                await self._send_group_reply(ctx)
        except Exception as e:
            self.ap.logger.error(f"Error occurred during group reply: {e}")
        finally:
            config.response_timers_flag = False

    # 发送群聊回复方法
    async def _send_group_reply(self, ctx: EventContext):
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache[launcher_id]
        if config.summarization_mode:
            _, unreplied_conversations = config.memory.get_unreplied_msg(config.unreplied_count)
            related_memories = await config.memory.load_memory(unreplied_conversations)
            if related_memories:
                config.cards.set_memory(related_memories)

        system_prompt = config.memory.to_custom_names(config.cards.generate_system_prompt())
        user_prompt = config.memory.get_normalize_short_term_memory()
        if config.thinking_mode_flag:
            user_prompt, analysis = await config.thoughts.generate_group_prompt(config.memory, config.cards, config.unreplied_count)
            if config.display_thinking and config.conversation_analysis_flag:
                await self._reply(ctx, f"【分析】：{analysis}")
        self._generator.set_speakers([config.memory.assistant_name])
        response = await self._generator.return_chat(user_prompt, system_prompt)
        await config.memory.save_memory(role="assistant", content=response)
        if config.personate_mode:
            await self._send_personate_reply(ctx, response)
        else:
            await self._reply(ctx, f"{response}", True)

    # 请求私聊回复方法
    async def _request_person_reply(self, ctx: EventContext, need_save_memory: bool):
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache[launcher_id]
        if need_save_memory:
            msg = await self._vision(ctx)
            await config.memory.save_memory(role="user", content=msg)
        config.unreplied_count += 1
        await self._person_reply(ctx)

    # 私聊回复逻辑方法
    async def _person_reply(self, ctx: EventContext):
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache[launcher_id]
        if config.unreplied_count > 0:
            if launcher_id not in self.waifu_cache or not config.response_timers_flag:
                config.response_timers_flag = True
                asyncio.create_task(self._delayed_person_reply(ctx))

    # 延迟私聊回复方法
    async def _delayed_person_reply(self, ctx: EventContext):
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache[launcher_id]
        await asyncio.sleep(config.person_response_delay)
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

            user_prompt = config.memory.get_normalize_short_term_memory()
            if config.thinking_mode_flag:
                user_prompt, analysis = await config.thoughts.generate_person_prompt(config.memory, config.cards)
                if config.display_thinking and config.conversation_analysis_flag:
                    await self._reply(ctx, f"【分析】：{analysis}")
            await self._send_person_reply(ctx, user_prompt)

            if config.story_mode_flag:
                value_game = config.value_game
                await value_game.determine_manner_change(config.memory, config.continued_count)
                if config.display_value:
                    response = value_game.get_manner_value_str()
                    if response:
                        await self._reply(ctx, f"{response}")
            config.continued_count = 0
        except Exception as e:
            self.ap.logger.error(f"Error occurred during person reply: {e}")
        finally:
            config.response_timers_flag = False

    # 发送私聊回复方法
    async def _send_person_reply(self, ctx: EventContext, user_prompt: str | list[llm_entities.ContentElement]):
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache[launcher_id]
        system_prompt = config.memory.to_custom_names(config.cards.generate_system_prompt())
        self._generator.set_speakers([config.memory.assistant_name])
        response = await self._generator.return_chat(user_prompt, system_prompt)
        await config.memory.save_memory(role="assistant", content=response)
        if config.personate_mode:
            await self._send_personate_reply(ctx, response)
        else:
            await self._reply(ctx, f"{response}", True)

    # 继续私聊回复方法
    async def _continue_person_reply(self, ctx: EventContext):
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache[launcher_id]
        user_prompt = await config.thoughts.generate_person_continue_prompt(config.memory)
        await self._send_person_reply(ctx, user_prompt)

    # 处理旁白方法
    async def _handle_narration(self, ctx: EventContext, launcher_id: str):
        if launcher_id in self.waifu_cache and self.waifu_cache[launcher_id].launcher_timer_tasks:
            self.waifu_cache[launcher_id].launcher_timer_tasks.cancel()
        self.waifu_cache[launcher_id].launcher_timer_tasks = asyncio.create_task(self._timed_narration_task(ctx, launcher_id))

    # 定时旁白任务方法
    async def _timed_narration_task(self, ctx: EventContext, launcher_id: str):
        try:
            config = self.waifu_cache[launcher_id]
            for interval in config.narrate_intervals:
                await self._sleep_and_narrate(ctx, launcher_id, interval)
        except asyncio.CancelledError:
            pass

    # 延迟并旁白方法
    async def _sleep_and_narrate(self, ctx: EventContext, launcher_id: str, interval: int):
        await asyncio.sleep(interval)
        await self._narrate(ctx, launcher_id)

    # 旁白方法
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

    # 发送拟人化回复方法
    async def _send_personate_reply(self, ctx: EventContext, response: str):
        config = self.waifu_cache[ctx.event.launcher_id]
        parts = re.split(r"(?<!\d)[，。？！,.?!\n~〜](?!\d)", response)
        combined_parts = []
        temp_part = ""

        for part in parts:
            part = part.strip()
            if not part:
                continue
            if part in ["，", "。", ",", "."]:
                continue
            elif part in ["？", "！", "?", "!", "~", "〜"]:
                if temp_part or not combined_parts:
                    temp_part += part
                else:
                    combined_parts[-1] += part
            else:
                temp_part += " " + part
                if len(temp_part) >= 3:
                    combined_parts.append(temp_part.strip())
                    temp_part = ""

        if temp_part:
            combined_parts.append(temp_part.strip())

        if not combined_parts:
            combined_parts.append(response)

        if combined_parts and len(config.bracket_rate) == 2:
            try:
                if random.random() < config.bracket_rate[0]:
                    combined_parts[-1] += "（）"
                elif random.random() < config.bracket_rate[1]:
                    combined_parts[-1] += "（"
            except Exception as e:
                self.ap.logger.error(f"Bracket addition failed: {e}")

        for part in combined_parts:
            await self._reply(ctx, f"{part}", True)
            if config.personate_delay != 0:
                await asyncio.sleep(config.personate_delay)
            else:
                await asyncio.sleep(len(part) / 2)

    # 处理图片消息方法
    async def _vision(self, ctx: EventContext) -> str:
        query = ctx.event.query
        has_image = False
        content_list = []

        session = await self.ap.sess_mgr.get_session(query)
        conversation = await self.ap.sess_mgr.get_conversation(session)
        use_model = conversation.use_model

        for me in query.message_chain:
            if isinstance(me, platform_message.Plain):
                content_list.append(llm_entities.ContentElement.from_text(me.text))
            elif isinstance(me, platform_message.Image):
                if self.ap.provider_cfg.data["enable-vision"] and use_model:
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

    # 删除空白行方法
    def _remove_blank_lines(self, text: str) -> str:
        lines = text.split("\n")
        non_blank_lines = [line for line in lines if line.strip() != ""]
        return "\n".join(non_blank_lines)

    # 回复消息方法
    async def _reply(self, ctx: EventContext, response: str, event_trigger: bool = False):
        response_fixed = self._remove_blank_lines(response)
        
        # 检查是否需要发送表情包
        emoji_path = None
        if event_trigger and ctx.event.launcher_id in self.waifu_cache:
            config = self.waifu_cache[ctx.event.launcher_id]
            emoji_path = config.emoji_manager.get_emoji_for_emotion(response_fixed)
        
        message_chain = []
        message_chain.append(f"{response_fixed}")
        
        # 如果有匹配的表情包，添加到消息链中
        if emoji_path and os.path.exists(emoji_path):
            try:
                with open(emoji_path, "rb") as f:
                    image_data = f.read()
                message_chain.append(platform_message.Image(base64=image_data))
                self.ap.logger.info(f"发送表情包: {emoji_path}")
            except Exception as e:
                self.ap.logger.error(f"发送表情包失败: {e}")
        
        await ctx.event.query.adapter.reply_message(
            ctx.event.query.message_event, 
            platform_message.MessageChain(message_chain), 
            False
        )
        
        if event_trigger:
            await self._emit_responded_event(ctx, response_fixed)

    # 触发已回复事件方法
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

    # 预设回复方法
    def _response_presets(self, launcher_id: int):
        return self._check_repeat(launcher_id)

    # 检查重复消息方法
    def _check_repeat(self, launcher_id: int) -> str:
        return self.waifu_cache[launcher_id].memory.get_repeat_msg()

    # 设置越狱模式方法
    def _set_jail_break(self, cache: WaifuCache, type: str):
        self._generator.set_jail_break(type, cache.memory.user_name)
        cache.memory.set_jail_break(type, cache.memory.user_name)
        cache.value_game.set_jail_break(type, cache.memory.user_name)
        cache.narrator.set_jail_break(type, cache.memory.user_name)
        cache.thoughts.set_jail_break(type, cache.memory.user_name)

    # 功能测试方法
    async def _test(self, ctx: EventContext):
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache[launcher_id]
        config.narrate_intervals = []
        config.story_mode_flag = True
        config.display_thinking = True
        config.display_value = True
        config.personate_mode = False
        config.jail_break_mode = "off"
        config.person_response_delay = 0
        config.continued_rate = 0
        config.continued_max_count = 0
        config.summarization_mode = True
        config.memory.max_narrat_words = 30
        config.memory.max_thinking_words = 30
        config.memory._short_term_memory_size = 10
        config.memory._memory_batch_size = 5
        await self._reply(ctx, "温馨提示：测试结束会提示【测试结束】。")
        await self._reply(ctx, "【测试开始】")
        await self._test_command(ctx, "清空记忆#删除记忆")
        await self._test_command(ctx, "调用开场场景#开场场景")
        await self._test_command(ctx, "手动书写自己发言（等同于直接发送）#控制人物user|哇！")
        config.display_thinking = False
        config.person_response_delay = 5
        config.jail_break_mode = "all"
        self._set_jail_break(config, config.jail_break_mode)
        await self._test_command(ctx, "手动书写“指定角色”发言#控制人物快递员|叮咚~有人在家吗，有你们的快递！")
        config.jail_break_mode = "off"
        self._set_jail_break(config, "off")
        await self._test_command(ctx, "手动书写旁白#控制人物narrator|（neko兴奋的跳了起来。）")
        config.personate_mode = True
        config.bracket_rate = [1, 1]
        await self._test_command(ctx, "请AI生成旁白#旁白")
        config.personate_mode = False
        config.continued_rate = 1
        config.continued_max_count = 2
        await self._test_command(ctx, "请AI生成“指定角色”发言#控制人物快递员|继续")
        config.continued_rate = 0
        config.continued_max_count = 0
        await self._test_command(ctx, "使用“指定角色”推进剧情#推进剧情")
        await self._test_command(ctx, "停止旁白计时器#停止活动")
        await self._test_command(ctx, "查看当前态度数值及当前行为准则（Manner）#态度")
        await self._test_command(ctx, "撤回最后一条对话#撤回")
        await self._test_command(ctx, "查看当前长短期记忆#全部记忆")
        await self._test_command(ctx, "清空记忆#删除记忆")
        await self._test_command(ctx, "重载配置#加载配置")
        await self._reply(ctx, "【测试结束】")

    # 测试命令方法
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
