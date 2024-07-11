import asyncio
import typing
import os
import mirai
import random
import re
import copy
from datetime import datetime
from mirai import MessageChain
from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import PersonNormalMessageReceived, GroupMessageReceived, GroupNormalMessageReceived
from pkg.provider import entities as llm_entities
from plugins.Waifu.cells.config import ConfigManager
from plugins.Waifu.cells.generator import Generator
from plugins.Waifu.cells.cards import Cards
from plugins.Waifu.organs.memories import Memory
from plugins.Waifu.systems.narrator import Narrator
from plugins.Waifu.systems.value_game import ValueGame
from plugins.Waifu.organs.thoughts import Thoughts

COMMANDS = {
    "列出命令": "列出目前支援所有命令及介绍，用法：[列出命令]。",
    "全部记忆": "显示目前所有长短期记忆，用法：[全部记忆]。",
    "删除记忆": "删除所有长短期记忆，用法：[删除记忆]。",
    "修改数值": "修改Value Game的数字，用法：[修改数值][数值]。",
    "态度": "显示当前Value Game所对应的“态度Manner”，用法：[态度]。",
    "加载配置": "重新加载所有配置文件（仅Waifu），用法：[加载配置]。",
    "停止活动": "停止旁白计时器，用法：[停止活动]。",
    "旁白": "主动触发旁白推进剧情，用法：[旁白]。",
    "时间表": "列出模型生成的Waifu时间表，用法：[时间表]。",
    "控制人物": "控制角色行动或发言，用法：[控制人物][角色名称/assistant]|[发言/(行动)]。",
    "撤回": "从短期记忆中删除最后的对话，用法：[撤回]。",
    "请设计": "调试：设计一个列表，用法：[请设计][设计内容]。",
    "请选择": "调试：从给定列表中选择，用法：[请选择][问题]|[选项1,选项2,……]。",
    "回答数字": "调试：返回数字答案，用法：[回答数字][问题]。",
    "回答问题": "调试：可自定系统提示的问答模式，用法：[回答问题][系统提示语]|[用户提示语] / [回答问题][用户提示语]。",
}


@register(name="Waifu", description="Cuter than real waifu!", version="1.2", author="ElvisChenML")
class Waifu(BasePlugin):
    def __init__(self, host: APIHost):
        self.host = host
        self.ap = host.ap
        self._ensure_directories_exist()
        self._generator = Generator(host)
        self._memory: typing.Dict[str, Memory] = {}
        self._narrator: typing.Dict[str, Narrator] = {}
        self._value_game: typing.Dict[str, ValueGame] = {}
        self._cards: typing.Dict[str, Cards] = {}
        self._thoughts = Thoughts(host)
        self._story_mode_flag: typing.Dict[str, bool] = {}
        self._display_thinking: typing.Dict[str, bool] = {}
        self._response_rate: typing.Dict[str, float] = {}
        self._launcher_intervals: typing.Dict[str, list] = {}
        self._launcher_timer_tasks: typing.Dict[str, asyncio.Task] = {}
        self._unreplied_count: typing.Dict[str, int] = {}
        self._summarization_mode: typing.Dict[str, bool] = {}
        self._personate_mode: typing.Dict[str, bool] = {}
        self._response_timers_flag: typing.Dict[str, bool] = {}
        self._bracket_rate: typing.Dict[str, list] = {}
        self._group_response_delay: typing.Dict[str, int] = {}
        self._person_response_delay: typing.Dict[str, int] = {}
        self._group_message_chain: typing.Dict[str, mirai.MessageChain] = {}

    async def initialize(self):
        self.set_permissions_recursively("plugins/Waifu/water", 0o777)

    @handler(PersonNormalMessageReceived)
    async def person_normal_message_received(self, ctx: EventContext):
        launcher_id = ctx.event.launcher_id
        if launcher_id not in self._memory:
            launcher_type = ctx.event.launcher_type
            await self._load_config(launcher_id, launcher_type)

        need_assistant_reply, need_save_memory = await self._handle_command(ctx)
        if need_assistant_reply:
            await self.request_person_reply(ctx, need_save_memory)
            asyncio.create_task(self._handle_narration(ctx, launcher_id))
        ctx.prevent_default()

    @handler(GroupMessageReceived)
    async def group_normal_message_received(self, ctx: EventContext):
        # 在GroupNormalMessageReceived的ctx.event.query.message_chain会将At移除
        # 所以这在经过主项目处理前先进行备份
        self._group_message_chain[ctx.event.launcher_id] = copy.deepcopy(ctx.event.message_chain)
        # 群聊忽视默认命令防止误触
        if str(ctx.event.message_chain).startswith("!") or str(ctx.event.message_chain).startswith("！"):
            self.ap.logger.info(f"Waifu插件已屏蔽群聊主项目指令: {str(ctx.event.message_chain)}，请于私聊中发送指令。")
            ctx.prevent_default()

    @handler(GroupNormalMessageReceived)
    async def group_normal_message_received(self, ctx: EventContext):
        launcher_id = ctx.event.launcher_id
        if launcher_id not in self._memory:
            launcher_type = ctx.event.launcher_type
            await self._load_config(launcher_id, launcher_type)

        need_assistant_reply, _ = await self._handle_command(ctx)
        if need_assistant_reply:
            await self.request_group_reply(ctx)
        ctx.prevent_default()

    async def _load_config(self, launcher_id: str, launcher_type: str):
        self._memory[launcher_id] = Memory(self.host, launcher_id, launcher_type)
        self._value_game[launcher_id] = ValueGame(self.host)
        self._cards[launcher_id] = Cards(self.host)
        self._narrator[launcher_id] = Narrator(self.host, launcher_id)
        self._launcher_intervals[launcher_id] = []
        self._unreplied_count[launcher_id] = 0

        waifu_config = ConfigManager(f"plugins/Waifu/water/config/waifu", "plugins/Waifu/water/templates/waifu", launcher_id)
        await waifu_config.load_config(completion=True)

        character = waifu_config.data.get("character", f"default")
        if character == "default":  # 区分私聊和群聊的模板
            character = f"default_{launcher_type}"
        self._launcher_intervals[launcher_id] = waifu_config.data.get("intervals", [])
        self._story_mode_flag[launcher_id] = waifu_config.data.get("story_mode", True)
        self._display_thinking[launcher_id] = waifu_config.data.get("display_thinking", True)
        self._response_rate[launcher_id] = waifu_config.data.get("response_rate", 0.7)
        self._summarization_mode[launcher_id] = waifu_config.data.get("summarization_mode", False)
        self._personate_mode[launcher_id] = waifu_config.data.get("personate_mode", True)
        self._bracket_rate[launcher_id] = waifu_config.data.get("bracket_rate", [])
        self._group_response_delay[launcher_id] = waifu_config.data.get("group_response_delay", 10)
        self._person_response_delay[launcher_id] = waifu_config.data.get("person_response_delay", 5)
        await self._memory[launcher_id].load_config(character, launcher_id, launcher_type)
        await self._value_game[launcher_id].load_config(character, launcher_id, launcher_type)
        await self._cards[launcher_id].load_config(character, launcher_type)
        await self._narrator[launcher_id].load_config()
        self.set_permissions_recursively("plugins/Waifu/water", 0o777)

    async def _handle_command(self, ctx: EventContext) -> typing.Tuple[bool, bool]:
        need_assistant_reply = False
        need_save_memory = False
        response = ""
        launcher_id = ctx.event.launcher_id
        launcher_type = ctx.event.launcher_type
        msg = str(ctx.event.query.message_chain)
        self.ap.logger.info(f"Waifu处理消息:{msg}")
        memory = self._memory[launcher_id]
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
            response = memory.get_all_memories()
        elif msg == "删除记忆":
            response = self._stop_timer(launcher_id)
            memory.delete_local_files()
            self._value_game[launcher_id].reset_value()
            response += "记忆已删除。"
        elif msg.startswith("修改数值"):
            value = int(msg[4:].strip())
            self._value_game[launcher_id]._change_manner_value(value)
            response = f"数值已改变：{value}"
        elif msg == "态度":
            response = f"Manner：{self._value_game[launcher_id].get_manner_description()}"
        elif msg == "加载配置":
            launcher_type = ctx.event.launcher_type
            await self._load_config(launcher_id, launcher_type)
            response = "配置已重载"
        elif msg == "停止活动":
            response = self._stop_timer(launcher_id)
        elif msg == "旁白":
            await self._narrate(ctx, launcher_id)
        elif msg == "时间表":
            response = f"时间表：\n{self._narrator[launcher_id].get_time_table()}"
        elif launcher_type != "group" and msg.startswith("控制人物"):
            content = msg[4:].strip()
            parts = content.split("|")
            if len(parts) == 2:
                role = parts[0].strip()
                prompt = parts[1].strip()
                await memory.save_memory(role=role, content=prompt)
                msg = ""  # 清空msg以告诉后续函数非user发言
            need_assistant_reply = True
            need_save_memory = False
        elif msg == "撤回":
            response = f"已撤回：\n{await memory.remove_last_memory()}"
        elif msg == "列出命令":
            response = self._list_commands()
        else:
            need_assistant_reply = True
            need_save_memory = True

        if response:
            ctx.add_return("reply", [str(response)])
        return need_assistant_reply, need_save_memory

    def _list_commands(self) -> str:
        return "\n\n".join([f"{cmd}: {desc}" for cmd, desc in COMMANDS.items()])

    def _stop_timer(self, launcher_id: str):
        if launcher_id in self._launcher_timer_tasks and self._launcher_timer_tasks[launcher_id]:
            self._launcher_timer_tasks[launcher_id].cancel()
            self._launcher_timer_tasks[launcher_id] = None
            return "计时器已停止。"
        else:
            return "没有正在运行的计时器。"

    def _ensure_directories_exist(self):
        directories = ["plugins/Waifu/water/cards", "plugins/Waifu/water/config", "plugins/Waifu/water/data"]

        for directory in directories:
            if not os.path.exists(directory):
                os.makedirs(directory)
                self.ap.logger.info(f"Directory created: {directory}")

    def set_permissions_recursively(self, path, mode):
        for root, dirs, files in os.walk(path):
            for dirname in dirs:
                os.chmod(os.path.join(root, dirname), mode)
            for filename in files:
                os.chmod(os.path.join(root, filename), mode)

    async def request_group_reply(self, ctx: EventContext):
        launcher_id = ctx.event.launcher_id
        memory = self._memory[launcher_id]
        sender = ctx.event.query.message_event.sender.member_name
        msg = await self._vision(ctx)  # 用眼睛看消息？
        await memory.save_memory(role=sender, content=msg)
        self._unreplied_count[launcher_id] += 1
        await self._group_reply(ctx)

    async def _group_reply(self, ctx: EventContext):
        launcher_id = ctx.event.launcher_id
        memory = self._memory[launcher_id]
        need_assistant_reply = False
        if self._group_message_chain[launcher_id] and self._group_message_chain[launcher_id].has(mirai.At(ctx.event.query.adapter.bot_account_id)):
            need_assistant_reply = True
        if self._unreplied_count[launcher_id] >= memory.response_min_conversations:
            if random.random() < self._response_rate[launcher_id]:
                need_assistant_reply = True

        self._group_message_chain[launcher_id] = None
        if need_assistant_reply:
            if launcher_id not in self._response_timers_flag or not self._response_timers_flag[launcher_id]:
                self._response_timers_flag[launcher_id] = True
                asyncio.create_task(self._delayed_group_reply(ctx))

    async def _delayed_group_reply(self, ctx: EventContext):
        launcher_id = ctx.event.launcher_id
        self.ap.logger.info(f"wait group {launcher_id} for {self._group_response_delay[launcher_id]}s")
        await asyncio.sleep(self._group_response_delay[launcher_id])
        self.ap.logger.info(f"generating group {launcher_id} response")
        memory = self._memory[launcher_id]
        cards = self._cards[launcher_id]

        try:
            if self._summarization_mode[launcher_id]:
                _, unreplied_conversations = memory.get_unreplied_msg(self._unreplied_count[launcher_id])
                related_memories = await memory.load_memory(unreplied_conversations)
                if related_memories:
                    cards.set_memory(related_memories)

            system_prompt = cards.generate_system_prompt()
            # 备份然后重置避免回复过程中接收到新讯息导致计数错误
            unreplied_count = self._unreplied_count[launcher_id]
            self._unreplied_count[launcher_id] = 0
            user_prompt, analysis = await self._thoughts.generate_group_prompt(memory, cards, unreplied_count)
            if self._display_thinking[launcher_id]:
                await ctx.event.query.adapter.reply_message(ctx.event.query.message_event, MessageChain([f"【分析】：{analysis}"]), False)
            response = await self._generator.return_chat(user_prompt, system_prompt)
            await memory.save_memory(role="assistant", content=response)

            if self._personate_mode[launcher_id]:
                await self._send_personate_reply(ctx, response, launcher_id)
            else:
                await ctx.event.query.adapter.reply_message(ctx.event.query.message_event, MessageChain([f"{response}"]), False)

            await self._group_reply(ctx)  # 检查是否回复期间又满足响应条件

        except Exception as e:
            self.ap.logger.error(f"Error occurred during group reply: {e}")
            raise

        finally:
            self._response_timers_flag[launcher_id] = False

    async def request_person_reply(self, ctx: EventContext, need_save_memory: bool):
        launcher_id = ctx.event.launcher_id
        memory = self._memory[launcher_id]

        if need_save_memory:  # 此处仅处理user的发言，保存至短期记忆
            msg = await self._vision(ctx)  # 用眼睛看消息？
            await memory.save_memory(role="user", content=msg)
        self._unreplied_count[launcher_id] += 1
        await self._person_reply(ctx)

    async def _person_reply(self, ctx: EventContext):
        launcher_id = ctx.event.launcher_id
        if self._unreplied_count[launcher_id] > 0:
            if launcher_id not in self._response_timers_flag or not self._response_timers_flag[launcher_id]:
                self._response_timers_flag[launcher_id] = True
                asyncio.create_task(self._delayed_person_reply(ctx))

    async def _delayed_person_reply(self, ctx: EventContext):
        launcher_id = ctx.event.launcher_id
        self.ap.logger.info(f"wait person {launcher_id} for {self._person_response_delay[launcher_id]}s")
        await asyncio.sleep(self._person_response_delay[launcher_id])
        self.ap.logger.info(f"generating person {launcher_id} response")
        memory = self._memory[launcher_id]
        cards = self._cards[launcher_id]
        _, unreplied_conversations = memory.get_unreplied_msg(self._unreplied_count[launcher_id])

        try:
            if self._story_mode_flag[launcher_id]:
                value_game = self._value_game[launcher_id]
                manner = value_game.get_manner_description()
                cards.set_manner(manner)
            if self._summarization_mode[launcher_id]:
                related_memories = await memory.load_memory(unreplied_conversations)
                cards.set_memory(related_memories)

            # user_prompt不直接从msg生成，而是先将msg保存至短期记忆，再由短期记忆生成。
            # 好处是不论旁白或是控制人物，都能直接调用记忆生成回复
            system_prompt = cards.generate_system_prompt()
            self._unreplied_count[launcher_id] = 0
            user_prompt, analysis = await self._thoughts.generate_person_prompt(memory, cards)
            if self._display_thinking[launcher_id]:
                await ctx.event.query.adapter.reply_message(ctx.event.query.message_event, MessageChain([f"【分析】：{analysis}"]), False)

            response = await self._generator.return_chat(user_prompt, system_prompt)
            await self._memory[launcher_id].save_memory(role="assistant", content=response)

            if self._story_mode_flag[launcher_id]:
                value_game = self._value_game[launcher_id]
                await value_game.determine_manner_change(self._memory[launcher_id])
                response = value_game.add_manner_value(response)

            if not self._story_mode_flag[launcher_id] and self._personate_mode[launcher_id]:
                await self._send_personate_reply(ctx, response, launcher_id)
            else:
                await ctx.event.query.adapter.reply_message(ctx.event.query.message_event, MessageChain([f"{response}"]), False)

            await self._person_reply(ctx)

        except Exception as e:
            self.ap.logger.error(f"Error occurred during person reply: {e}")
            raise

        finally:
            self._response_timers_flag[launcher_id] = False

    async def _handle_narration(self, ctx: EventContext, launcher_id: str):
        if launcher_id in self._launcher_timer_tasks and self._launcher_timer_tasks[launcher_id]:
            self._launcher_timer_tasks[launcher_id].cancel()

        self._launcher_timer_tasks[launcher_id] = asyncio.create_task(self._timed_narration_task(ctx, launcher_id))

    async def _timed_narration_task(self, ctx: EventContext, launcher_id: str):
        try:
            for interval in self._launcher_intervals.get(launcher_id, []):
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
        memory = self._memory[launcher_id]
        conversations = memory.short_term_memory
        if len(conversations) < 2:
            return

        narrator = self._narrator[launcher_id]
        narration = await narrator.narrate(memory, self._cards[launcher_id].get_profile())

        if narration:
            await ctx.event.query.adapter.reply_message(ctx.event.query.message_event, MessageChain([f"({memory.to_custom_names(narration)})"]), False)
            narration = memory.to_generic_names(narration)
            await memory.save_memory(role="narrator", content=narration)

    async def _send_personate_reply(self, ctx: EventContext, response: str, launcher_id: str):
        parts = re.split(r"([，。？！,.?!\n])", response)  # 保留分隔符
        combined_parts = []
        temp_part = ""

        for part in parts:
            part = part.strip()
            if not part:
                continue
            if part in ["，", "。", ",", ".", "\n"]:  # 跳过标点符号
                continue
            elif part in ["？", "！", "?", "!"]:  # 保留？和！
                if combined_parts:
                    combined_parts[-1] += part
                else:
                    temp_part += part
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

        if combined_parts:
            try:
                if random.random() < self._bracket_rate[launcher_id][0]:  # 老互联网冲浪人士了（）
                    combined_parts[-1] += "（）"
                elif random.random() < self._bracket_rate[launcher_id][1]:
                    combined_parts[-1] += "（"
            except:
                pass

        for part in combined_parts:
            await ctx.event.query.adapter.reply_message(ctx.event.query.message_event, MessageChain([part]), False)
            self.ap.logger.info(f"Send:{part}")
            await asyncio.sleep(len(part) / 2)  # 根据字数计算延迟时间，假设每2个字符1秒

    async def _vision(self, ctx: EventContext) -> str:
        # 参考自preproc.py PreProcessor
        query = ctx.event.query
        hasImage = False
        content_list = []
        for me in query.message_chain:
            if isinstance(me, mirai.Plain):
                content_list.append(llm_entities.ContentElement.from_text(me.text))
            elif isinstance(me, mirai.Image):
                if self.ap.provider_cfg.data["enable-vision"] and query.use_model.vision_supported:
                    if me.url is not None:
                        hasImage = True
                        content_list.append(llm_entities.ContentElement.from_image_url(str(me.url)))
        if not hasImage:
            return str(ctx.event.query.message_chain)
        else:
            return await self._thoughts.analyze_picture(content_list)

    def __del__(self):
        for timer_task in self._launcher_timer_tasks.values():
            if timer_task:
                timer_task.cancel()
