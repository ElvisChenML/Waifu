import asyncio
import typing
import os
import random
import re
import copy
import shutil
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
from plugins.Waifu.cells.emoji import EmojiManager
from plugins.Waifu.organs.memories import Memory
from plugins.Waifu.systems.narrator import Narrator
from plugins.Waifu.systems.value_game import ValueGame
from plugins.Waifu.organs.thoughts import Thoughts
from plugins.Waifu.cells.painting import Painting
from plugins.Waifu.cells.time_service import TimeService

COMMANDS = {
    "列出命令": "列出目前支援所有命令及介绍，用法：[列出命令]。",
    "全部记忆": "显示目前所有长短期记忆，用法：[全部记忆]。",
    "删除记忆": "删除所有长短期记忆，用法：[删除记忆]。",
    "删除个人模式记忆": "删除个人模式下的用户记忆，用法：[删除个人模式记忆]删除所有个人用户记忆，[删除个人模式记忆+QQID]删除指定用户记忆。",
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
    "加载表情": "重新加载表情包，用法：[加载表情]。",
    "表情开关": "开启或关闭表情包功能，用法：[表情开关]。",
    "绘画": "使用AI生成图片，用法：[绘画][提示词] 竖着/横着。",
    "群聊模式": "切换到群聊统一回复模式，用法：[群聊模式]",
    "个人模式": "切换到用户单独聊天模式，用法：[个人模式]",
    "个性化提示词": "管理个性化提示词(仅个人模式下生效)，用法：[个性化提示词]查看当前状态，[个性化提示词开启/关闭]开启或关闭功能。",
    "个人好感度": "查看个人模式下指定用户的好感度，用法：[个人好感度+QQID]查看指定用户好感度。",
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
        self.time_service = TimeService(ap)  # 初始化时间服务
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
        self.use_emoji = True  # 是否使用表情包
        self.emoji_rate = 0.5  # 表情包发送频率
        self.group_mode = True  # 默认群聊模式
        self.user_sessions = {}  # 存储用户单独会话


@runner.runner_class("waifu-mode")
class WaifuRunner(runner.RequestRunner):
    async def run(self, query: core_entities.Query):
        # 为了适配其他插件，以屏蔽runner的方式取代ctx.prevent_default()
        # 不需在配置文件中手动配置运行器，将在插件加载过程强制指定为waifu-mode
        # 返回一个空的异步生成器
        if False:  # 永远不会执行，但保留生成器语法
            yield
        return


@register(name="Waifu", description="Cuter than real waifu!", version="1.9.9", author="ElvisChenML")
class Waifu(BasePlugin):
    # 修改 __init__ 方法，初始化表情包管理器
    def __init__(self, host: APIHost):
        self.ap = host.ap
        self._ensure_required_files_exist()
        self._generator = Generator(self.ap)
        self.waifu_cache: typing.Dict[str, WaifuCache] = {}
        self._emoji_manager = EmojiManager(self.ap)  # 初始化表情包管理器
        self._painting = Painting(self.ap, self._emoji_manager)  # 初始化绘画管理器
        self._set_permissions_recursively("data/plugins/Waifu/", 0o777)

    async def initialize(self):
        await self._set_runner("waifu-mode")
        # 为新用户创建配置文件
        config_mgr = ConfigManager(f"data/plugins/Waifu/config/waifu", "plugins/Waifu/templates/waifu")
        await config_mgr.load_config(completion=True)
        # 确保表情包目录存在
        os.makedirs("data/plugins/Waifu/images", exist_ok=True)

    async def destroy(self):
        await self._set_runner(self.ap.provider_cfg.data['runner'])

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
        mode = self.ap.pipeline_cfg.data["access-control"]["mode"]
        sess_list = set(self.ap.pipeline_cfg.data["access-control"].get(mode, []))

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
        cmd_prefix = self.ap.command_cfg.data.get("command-prefix", [])
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

    @handler(GroupMessageReceived)
    @handler(GroupNormalMessageReceived)
    async def group_message_received(self, ctx: EventContext):
        if not await self._access_control_check(ctx):
            return

        # 获取用户信息
        sender_id = ctx.event.sender_id
        sender_name = ctx.event.query.message_event.sender.member_name
        
        # 创建用户专属会话ID
        user_launcher_id = f"{ctx.event.launcher_id}_user_{sender_id}"
        
        # 在GroupNormalMessageReceived的ctx.event.query.message_chain会将At移除
        # 所以这在经过主项目处理前先进行备份
        self.waifu_cache[ctx.event.launcher_id].group_message_chain = copy.deepcopy(ctx.event.query.message_chain)

        need_assistant_reply, need_save_memory = await self._handle_command(ctx)
        if need_assistant_reply:
            # 检查是否为个人模式
            if not self.waifu_cache[ctx.event.launcher_id].group_mode:
                # 确保用户专属配置已加载
                if user_launcher_id not in self.waifu_cache:
                    await self._load_config(user_launcher_id, "person")
                
                # 存储用户信息
                self.waifu_cache[user_launcher_id].user_info = {
                    "qq_id": sender_id,
                    "qq_name": sender_name
                }
                
                # 使用用户专属ID处理请求
                await self._request_personal_group_reply(ctx, user_launcher_id)
            else:
                # 使用群聊模式处理请求
                await self._request_group_reply(ctx)

    async def _load_config(self, launcher_id: str, launcher_type: str):
        self.waifu_cache[launcher_id] = WaifuCache(self.ap, launcher_id, launcher_type)
        cache = self.waifu_cache[launcher_id]

        config_mgr = ConfigManager(f"data/plugins/Waifu/config/waifu", "plugins/Waifu/templates/waifu", launcher_id)
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
        # 在_load_config方法中添加
        cache.use_emoji = config_mgr.data.get("use_emoji", True)
        cache.emoji_rate = config_mgr.data.get("emoji_rate", 0.5)
        cache.use_personal_prompts = config_mgr.data.get("use_personal_prompts", False)
        self._emoji_manager.use_superbed = config_mgr.data.get("use_superbed", True)  # 默认不使用聚合图床
        self._emoji_manager.superbed_token = config_mgr.data.get("superbed_token", "123456789")
        # 加载时间服务配置
        await cache.time_service.load_config(launcher_id)
        await cache.memory.load_config(character, launcher_id, launcher_type)
        await cache.value_game.load_config(character, launcher_id, launcher_type)
        await cache.cards.load_config(character, launcher_type)
        await cache.narrator.load_config()

        self._set_jail_break(cache, "off")
        if cache.jail_break_mode in ["before", "after", "end", "all"]:
            self._set_jail_break(cache, cache.jail_break_mode)

        self._set_permissions_recursively("data/plugins/Waifu/", 0o777)

    async def _set_runner(self, runner_name: str):
        """用于设置 RunnerManager 的 using_runner"""
        runner_mgr = self.ap.runner_mgr
        if runner_mgr:
            for r in runner.preregistered_runners:
                if r.name == runner_name:
                    runner_mgr.using_runner = r(self.ap)
                    await runner_mgr.using_runner.initialize()
                    self.ap.logger.info(f"已设置运行器为 {runner_name}")
                    break
            else:
                raise Exception(
                    f"Runner '{runner_name}' not found in preregistered_runners."
                )

    # 修改 _handle_command 方法，添加表情包相关命令
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
        elif msg == "删除记忆":
            response = self._stop_timer(launcher_id)
            config.memory.delete_local_files()
            config.value_game.reset_value()
            response += "记忆已删除。"
        elif msg.startswith("删除个人模式记忆"):
            content = msg[8:].strip()
            if content:
                # 删除指定用户的记忆
                user_id = str(content)  # 确保user_id是字符串类型
                try:
                    # 验证是否为有效的QQ号
                    int(user_id)
                    user_launcher_id = f"{launcher_id}_user_{user_id}"
                    if user_launcher_id in self.waifu_cache:
                        self._stop_timer(user_launcher_id)
                        self.waifu_cache[user_launcher_id].memory.delete_local_files()
                        self.waifu_cache[user_launcher_id].value_game.reset_value()
                        # 从缓存中移除该用户
                        del self.waifu_cache[user_launcher_id]
                        response = f"已删除用户 {user_id} 的个人模式记忆。"
                    else:
                        response = f"未找到用户 {user_id} 的个人模式记忆。"
                except ValueError:
                    response = "请输入有效的用户ID（纯数字）"
            else:
                # 删除所有个人用户的记忆
                deleted_count = 0
                user_ids_to_delete = []
                
                # 先收集需要删除的用户ID
                for cache_id in list(self.waifu_cache.keys()):
                    if "_user_" in cache_id and cache_id.startswith(f"{launcher_id}_user_"):
                        user_ids_to_delete.append(cache_id)
                
                # 然后删除这些用户的记忆
                for user_launcher_id in user_ids_to_delete:
                    try:
                        self._stop_timer(user_launcher_id)
                        self.waifu_cache[user_launcher_id].memory.delete_local_files()
                        self.waifu_cache[user_launcher_id].value_game.reset_value()
                        del self.waifu_cache[user_launcher_id]
                        deleted_count += 1
                    except Exception as e:
                        self.ap.logger.error(f"删除用户记忆时出错 {user_launcher_id}: {str(e)}")
                
                if deleted_count > 0:
                    response = f"已删除所有个人模式记忆，共 {deleted_count} 个用户。"
                else:
                    response = "没有找到个人模式记忆。"
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
        # 添加表情包相关命令
        elif msg == "加载表情":
            response = self._emoji_manager.reload_emojis()
        elif msg == "表情开关":
            config.use_emoji = not config.use_emoji
            status = "开启" if config.use_emoji else "关闭"
            response = f"表情包功能已{status}"
        # 继续处理其他命令
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
        elif msg.startswith("绘画"):
            content = msg[2:].strip()
            parts = content.split(" ")
            if len(parts) == 2:
                prompt = parts[0].strip()
                orientation = parts[1].strip()
                if orientation in ["竖着", "横着"]:
                    await self._painting.send_image(ctx, prompt, orientation)
                    return False, False
                else:
                    response = "请指定正确的方向（竖着/横着）"
            else:
                response = "请提供正确的参数（提示词 竖着/横着）"
            await ctx.event.query.adapter.reply_message(ctx.event.query.message_event, platform_message.MessageChain([str(response)]), False)
            return False, False
        elif msg == "群聊模式":
            config.group_mode = True
            response = "已切换到群聊统一回复模式"
            self.ap.logger.info(response)
            # 在群聊中输出当前模式，但不要设置response变量
            await self._reply(ctx, response)
            return False, False  # 直接返回，避免重复发送
        elif msg == "个人模式":
            config.group_mode = False 
            response = "已切换到用户单独聊天模式"
            self.ap.logger.info(response)
            # 在群聊中输出当前模式，但不要设置response变量
            await self._reply(ctx, response)
            return False, False  # 直接返回，避免重复发送
        elif msg.startswith("个性化提示词"):
            if not config.group_mode:  # 只在个人模式下处理个性化提示词命令
                if msg == "个性化提示词":
                    status = "开启" if config.use_personal_prompts else "关闭"
                    response = f"个性化提示词功能当前状态：{status}"
                elif msg == "个性化提示词开启":
                    config.use_personal_prompts = True
                    response = "个性化提示词功能已开启"
                elif msg == "个性化提示词关闭":
                    config.use_personal_prompts = False
                    response = "个性化提示词功能已关闭"
            else:
                response = "个性化提示词功能仅在个人模式下可用，请先使用[个人模式]命令切换模式"
        elif msg.startswith("个人好感度"):
            content = msg[5:].strip()
            if config.group_mode:
                response = "此命令只有在个人模式下可以使用，群聊模式请直接使用[态度]命令查看好感度。"
            else:
                # 获取群聊ID
                group_id = launcher_id
                
                if not content:
                    # 不再支持查看所有用户好感度，需要指定用户ID
                    response = "请指定要查询的用户ID，例如：个人好感度123456789"
                else:
                    # 查看特定用户好感度
                    user_id = content
                    try:
                        # 验证是否为有效的QQ号
                        int(user_id)
                        user_launcher_id = f"{group_id}_user_{user_id}"
                        
                        if user_launcher_id in self.waifu_cache:
                            user_cache = self.waifu_cache[user_launcher_id]
                            value = user_cache.value_game._value
                            manner = user_cache.value_game.get_manner_description()
                            user_name = user_cache.user_info.get("qq_name", user_id) if hasattr(user_cache, "user_info") else user_id
                            
                            response = f"用户 {user_name}({user_id}) 的好感度为: {value}\n态度: {manner}"
                        else:
                            response = f"未找到用户 {user_id} 的个人模式记录"
                    except ValueError:
                        response = "请输入有效的QQ号"
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

    # 修改 _ensure_required_files_exist 方法，确保表情包目录存在
    def _ensure_required_files_exist(self):
        directories = [
            "data/plugins/Waifu/cards", 
            "data/plugins/Waifu/config", 
            "data/plugins/Waifu/data",
            "data/plugins/Waifu/images",  # 添加表情包目录
            "data/plugins/Waifu/config/personalConfiguration"  # 个性化配置目录
        ]
    
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
        sender_id = ctx.event.sender_id
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
            # 添加用户信息
            if not config.group_mode and hasattr(config, 'user_info'):
                response += f"\n用户：{config.user_info['qq_id']}-{config.user_info['qq_name']}"
            await self._send_personate_reply(ctx, response)
        else:
            await self._reply(ctx, f"{response}", True)

    async def _request_personal_group_reply(self, ctx: EventContext, user_launcher_id: str):
        """
        处理个人模式下的群聊消息
        """
        group_launcher_id = ctx.event.launcher_id
        group_config = self.waifu_cache[group_launcher_id]
        user_config = self.waifu_cache[user_launcher_id]

        sender = ctx.event.query.message_event.sender.member_name
        sender_id = ctx.event.sender_id
        msg = await self._vision(ctx)  # 处理消息内容

        # 在个人模式下启用个性化提示词
        if group_config.use_personal_prompts:
            # 构建个性化配置文件路径
            personal_config_path = f"data/plugins/Waifu/config/personalConfiguration/{group_launcher_id}_{sender_id}.yaml"
            if os.path.exists(personal_config_path):
                # 加载个性化配置
                personal_config = ConfigManager(f"data/plugins/Waifu/config/personalConfiguration/{group_launcher_id}_{sender_id}", None)
                await personal_config.load_config(completion=False)
                # 合并个性化配置到用户的角色卡
                user_config.cards.merge_personal_config(personal_config.data)
                self.ap.logger.info(f"已加载用户 {sender_id} 的个性化提示词配置")

        # 保存到用户专属记忆
        await user_config.memory.save_memory(role=sender, content=msg)
        user_config.unreplied_count += 1

        # 使用用户专属配置处理回复
        await self._personal_group_reply(ctx, user_launcher_id)

    async def _personal_group_reply(self, ctx: EventContext, user_launcher_id: str):
        """
        个人模式下的群聊回复逻辑
        """
        group_launcher_id = ctx.event.launcher_id
        group_config = self.waifu_cache[group_launcher_id]
        user_config = self.waifu_cache[user_launcher_id]
        
        need_assistant_reply = False
        
        # 检查是否需要回复
        if group_config.group_message_chain and group_config.group_message_chain.has(platform_message.At(ctx.event.query.adapter.bot_account_id)):
            need_assistant_reply = True
        if user_config.unreplied_count >= user_config.memory.response_min_conversations:
            if random.random() < user_config.response_rate:
                need_assistant_reply = True
        
        group_config.group_message_chain = None
        
        if need_assistant_reply:
            if not user_config.response_timers_flag:
                user_config.response_timers_flag = True
                # 使用用户专属配置生成回复
                asyncio.create_task(self._delayed_personal_group_reply(ctx, user_launcher_id))

    async def _delayed_personal_group_reply(self, ctx: EventContext, user_launcher_id: str):
        """
        延迟处理个人模式下的群聊回复
        """
        group_launcher_id = ctx.event.launcher_id
        user_config = self.waifu_cache[user_launcher_id]
        
        # 使用群聊的延迟设置
        delay = self.waifu_cache[group_launcher_id].group_response_delay
        self.ap.logger.info(f"等待个人模式群聊回复 {user_launcher_id} {delay}秒")
        await asyncio.sleep(delay)
        
        try:
            # 重置未回复计数
            user_config.unreplied_count = 0
            user_config.response_timers_flag = False
            
            # 加载相关记忆
            if user_config.summarization_mode:
                _, unreplied_conversations = user_config.memory.get_unreplied_msg(user_config.unreplied_count)
                related_memories = await user_config.memory.load_memory(unreplied_conversations)
                if related_memories:
                    user_config.cards.set_memory(related_memories)
            
            # 生成系统提示
            system_prompt = user_config.memory.to_custom_names(user_config.cards.generate_system_prompt())
            
            # 获取用户提示
            user_prompt = user_config.memory.get_normalize_short_term_memory()
            
            # 思考模式处理
            if user_config.thinking_mode_flag:
                user_prompt, analysis = await user_config.thoughts.generate_group_prompt(user_config.memory, user_config.cards, 0)
                if user_config.display_thinking and user_config.conversation_analysis_flag:
                    await self._reply(ctx, f"【分析】：{analysis}")
            
            # 生成回复
            self._generator.set_speakers([user_config.memory.assistant_name])
            response = await self._generator.return_chat(user_prompt, system_prompt)
            
            # 添加用户信息标识
            if hasattr(user_config, 'user_info'):
                response += f"\n用户：{user_config.user_info['qq_id']}-{user_config.user_info['qq_name']}"
            
            # 保存回复到记忆
            await user_config.memory.save_memory(role="assistant", content=response)
            
            # 发送回复
            if user_config.personate_mode:
                await self._send_personate_reply(ctx, response)
            else:
                await self._reply(ctx, f"{response}", True)
            
        except Exception as e:
            self.ap.logger.error(f"个人模式群聊回复出错: {e}")
            user_config.response_timers_flag = False

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
            await self._person_reply(ctx)  # 检查是否回复期间又满足响应条件

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
        response = await self._generator.return_chat(user_prompt, system_prompt)
        await config.memory.save_memory(role="assistant", content=response)

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

    # 修改 _send_personate_reply 方法，支持表情包
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
            # 如果启用表情包且是最后一段，添加表情包
            if config.use_emoji and part == combined_parts[-1]:
                emotion = self._emoji_manager.analyze_emotion(part)
                message_chain = self._emoji_manager.create_emoji_message(part, emotion, config.emoji_rate)
                await ctx.event.query.adapter.reply_message(ctx.event.query.message_event, message_chain, False)
            else:
                await self._reply(ctx, f"{part}", False)  # 非最后一段不触发事件
            
            self.ap.logger.info(f"发送：{part}")
            if config.personate_delay != 0:
                await asyncio.sleep(config.personate_delay)
            else:
                await asyncio.sleep(len(part) / 2)  # 根据字数计算延迟时间，假设每2个字符1秒
            
            # 如果有分段回复，最后一段已经发送，需要触发事件
            if combined_parts:
                await self._emit_responded_event(ctx, combined_parts[-1])

    async def _vision(self, ctx: EventContext) -> str:
        # 参考自preproc.py PreProcessor
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

    def _remove_blank_lines(self, text: str) -> str:
        lines = text.split("\n")
        non_blank_lines = [line for line in lines if line.strip() != ""]
        return "\n".join(non_blank_lines)

    async def _reply(self, ctx: EventContext, response: str, event_trigger: bool = False):
        response_fixed = self._remove_blank_lines(response)
        
        # 检查是否需要添加表情包
        launcher_id = ctx.event.launcher_id
        config = self.waifu_cache.get(launcher_id)
        
        try:
            if config and config.use_emoji and event_trigger:
                # 使用大模型分析情绪并获取表情包
                # 确保正确等待异步操作完成
                message_chain = await self._emoji_manager.create_emoji_message(
                    response_fixed, 
                    self._generator, 
                    config.emoji_rate
                )
                # 确保message_chain不为None
                if message_chain:
                    await ctx.event.query.adapter.reply_message(ctx.event.query.message_event, message_chain, False)
                else:
                    # 如果message_chain为None，使用纯文本回复
                    await ctx.event.query.adapter.reply_message(
                        ctx.event.query.message_event, 
                        platform_message.MessageChain([platform_message.Plain(response_fixed)]), 
                        False
                    )
            else:
                await ctx.event.query.adapter.reply_message(
                    ctx.event.query.message_event, 
                    platform_message.MessageChain([platform_message.Plain(response_fixed)]), 
                    False
                )
            
            if event_trigger:
                await self._emit_responded_event(ctx, response_fixed)
        except Exception as e:
            self.ap.logger.error(f"回复消息时出错: {e}")
            # 出错时尝试使用纯文本回复
            try:
                await ctx.event.query.adapter.reply_message(
                    ctx.event.query.message_event, 
                    platform_message.MessageChain([platform_message.Plain(response_fixed)]), 
                    False
                )
                if event_trigger:
                    await self._emit_responded_event(ctx, response_fixed)
            except Exception as e2:
                self.ap.logger.error(f"尝试纯文本回复也失败: {e2}")

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
        """
        功能测试：隐藏指令，功能测试会清空记忆，请谨慎执行。
        """
        # 修改配置以优化测试效果
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
        # 测试流程
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
        await self._test_command(ctx, "重载配置#加载配置")  # 强制执行，将修改的配置改回来
        await self._reply(ctx, "【测试结束】")

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
