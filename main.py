import asyncio
import typing
import os
from datetime import datetime
from mirai import MessageChain # type: ignore
from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import PersonNormalMessageReceived
from pkg.core.bootutils import config
from pkg.provider import entities as llm_entities
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


@register(name="Waifu", description="Cuter than real waifu!", version="1.0", author="ElvisChenML")
class Waifu(BasePlugin):
    def __init__(self, host: APIHost):
        self.host = host
        self.ap = host.ap
        self._ensure_directories_exist()
        self._generator = Generator(host)
        self._memory = Memory(host)
        self._narrator = Narrator(host)
        self._value_game = ValueGame(host)
        self._cards = Cards(host)
        self._thoughts = Thoughts(host)
        self._character = "default"
        self._system_prompt = ""
        self._user_name = "用户"
        self._assistant_name = "助手"
        self._intervals = []
        self._timer_task = None

    async def initialize(self):
        await self._load_config()

    @handler(PersonNormalMessageReceived)
    async def person_normal_message_received(self, ctx: EventContext):
        msg = ctx.event.text_message.strip()

        need_assistant_reply, msg = await self._handle_command(ctx, msg)
        if need_assistant_reply:
            await self.request_assistant_reply(ctx, msg)
            asyncio.create_task(self._handle_narration(ctx))

        ctx.prevent_default()

    async def _handle_command(self, ctx: EventContext, msg: str) -> typing.Tuple[bool, str]:
        need_assistant_reply = True
        response = ""
        if msg.startswith("请设计"):
            content = msg[3:].strip()
            response = await self._generator.return_list(content)
            need_assistant_reply = False
        elif msg.startswith("请选择"):
            content = msg[3:].strip()
            parts = content.split("|")
            if len(parts) == 2:
                question = parts[0].strip()
                options = [opt.strip() for opt in parts[1].split(",")]
                response = await self._generator.select_from_list(question, options)
                need_assistant_reply = False
        elif msg.startswith("回答数字"):
            content = msg[4:].strip()
            response = await self._generator.return_number(content)
            need_assistant_reply = False
        elif msg.startswith("回答问题"):
            content = msg[4:].strip()
            parts = content.split("|")
            system_prompt = None
            if len(parts) == 2:
                system_prompt = parts[0].strip()
                user_prompt = parts[1].strip()
            else:
                user_prompt = content
            need_assistant_reply = False
            response = await self._generator.return_string(user_prompt, [], system_prompt)
        elif msg == "全部记忆":
            response = self._memory.get_all_memories()
            need_assistant_reply = False
        elif msg == "删除记忆":
            response = self._stop_timer()
            self._memory.delete_local_files()
            self._value_game.reset_value()
            response += "记忆已删除。"
            need_assistant_reply = False
        elif msg.startswith("修改数值"):
            value = int(msg[4:].strip())
            self._value_game._change_manner_value(value)
            response = f"数值已改变：{value}"
            need_assistant_reply = False
        elif msg == "态度":
            response = f"Manner：{self._value_game.get_manner_description()}"
            need_assistant_reply = False
        elif msg == "加载配置":
            await self._load_config()
            response = "配置已重载"
            need_assistant_reply = False
        elif msg == "停止活动":
            response = self._stop_timer()
            need_assistant_reply = False
        elif msg == "旁白":
            await self._narrate(ctx)
            need_assistant_reply = False
        elif msg == "时间表":
            response = f"时间表：\n{self._narrator.get_time_table()}"
            need_assistant_reply = False
        elif msg.startswith("控制人物"):
            content = msg[4:].strip()
            parts = content.split("|")
            if len(parts) == 2:
                role = parts[0].strip()
                prompt = parts[1].strip()
                current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                await self._memory.save_memory(role=role, content=prompt, time=current_time)
                msg = "" # 清空msg以告诉后续函数非user发言
            need_assistant_reply = True
        elif msg == "撤回":
            response = f"已撤回：\n{await self._memory.remove_last_memory()}"
            need_assistant_reply = False
        elif msg == "列出命令":
            response = self._list_commands()
            need_assistant_reply = False

        if response:
            ctx.add_return("reply", [str(response)])
        return need_assistant_reply, msg

    def _list_commands(self) -> str:
        return "\n\n".join([f"{cmd}: {desc}" for cmd, desc in COMMANDS.items()])

    def _stop_timer(self):
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None
            return "计时器已停止。"
        else:
            return "没有正在运行的计时器。"

    async def _load_config(self):
        self._waifu_config = await config.load_json_config(
            "plugins/Waifu/water/config/waifu.json",
            "plugins/Waifu/water/templates/waifu.json",
            completion=False,
        )
        self._character = self._waifu_config.data["character"]
        self._intervals = self._waifu_config.data.get("intervals", [])
        await self._generator.set_character(self._character)
        await self._memory.load_config()
        await self._value_game.load_config()
        await self._cards.load_config(self._character)
        await self._narrator.load_config(self._cards.get_profile())  # 在cards之后加载
        await self._thoughts.load_config()
        self.set_permissions_recursively("plugins/Waifu/water", 0o777)

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

    async def request_assistant_reply(self, ctx: EventContext, msg: str = ""):
        current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        if msg:  # 此处仅处理user的发言，保存至短期记忆
            await self._memory.save_memory(role="user", content=msg, time=current_time)

        await self._set_life_description()
        manner = self._value_game.get_manner_description()
        self._cards.set_manner(manner)
        related_memories = await self._memory.load_memory(llm_entities.Message(role="user", content=msg))
        self._cards.set_memory(related_memories)

        # user_prompt不直接从msg生成，而是先将msg保存至短期记忆，再由短期记忆生成。
        # 好处是不论旁白或是控制人物，都能直接调用记忆生成回复
        system_prompt = self._cards.generate_system_prompt()
        background = self._cards.get_background()
        user_prompt, analysis = await self._thoughts.generate_user_prompt(self._memory.short_term_memory, background, manner)
        await ctx.event.query.adapter.reply_message(ctx.event.query.message_event, MessageChain([f"【分析】：{analysis}"]), False)
        response = await self._generator.return_chat(user_prompt, system_prompt)

        response_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        await self._memory.save_memory(role="assistant", content=response, time=response_time)

        await self._value_game.determine_manner_change(self._memory.short_term_memory)
        response = self._value_game.add_manner_value(response)

        await ctx.event.query.adapter.reply_message(ctx.event.query.message_event, MessageChain([f"{response}"]), False)
        return

    async def _set_life_description(self):
        time_text, description = await self._narrator.get_assistant_life_description()
        action = self._narrator.get_action()
        self._cards.set_life_description(time_text, description, action)

    async def _handle_narration(self, ctx: EventContext):
        if self._timer_task:
            self._timer_task.cancel()

        self._timer_task = asyncio.create_task(self._timed_narration_task(ctx))

    async def _timed_narration_task(self, ctx: EventContext):
        try:
            for interval in self._intervals:
                self.ap.logger.info("start timer: {}".format(interval))
                await asyncio.sleep(interval)
                await self._narrate(ctx)

            self.ap.logger.info("All intervals completed.")
        except asyncio.CancelledError:
            self.ap.logger.info("Timed narration task cancelled.")
            pass

    async def _narrate(self, ctx: EventContext):
        conversations = self._memory.short_term_memory
        if len(conversations) < 2:
            return

        narration = await self._narrator.narrate(conversations)

        if narration:
            await ctx.event.query.adapter.reply_message(ctx.event.query.message_event, MessageChain([f"({self._generator.to_custom_names(narration)})"]), False)
            current_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            narration = self._generator.to_generic_names(narration)  # Ensure characters in stored narrations remain consistent in any context
            await self._memory.save_memory(role="narrator", content=narration, time=current_time)

    def __del__(self):
        if self._timer_task:
            self._timer_task.cancel()
