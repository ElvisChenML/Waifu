from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import PersonNormalMessageReceived
from pkg.provider import entities as llm_entities
from plugins.Waifu.cells.generator import Generator


# 注册插件
@register(name="Hello", description="hello world", version="0.1", author="ElvisChenML")
class MyPlugin(BasePlugin):

    # 插件加载时触发
    def __init__(self, host: APIHost):
        self.host = host
        self.ap = host.ap
        self.generator = Generator(host)

    # 异步初始化
    async def initialize(self):
        pass

    # 当收到个人消息时触发
    @handler(PersonNormalMessageReceived)
    async def person_normal_message_received(self, ctx: EventContext):
        msg = (
            ctx.event.text_message
        )  # 这里的 event 即为 PersonNormalMessageReceived 的对象
        if msg == "hello":  # 如果消息为 hello, 则对LLM发送"HELLO"并将回复记录于日志

            # 获取问好的方式列表
            response = await self.generator.open_ended_question("请设计问好的方式")
            # 将回复记录日志
            # hello response: assistant: Hello! How can I assist you today?
            self.ap.logger.info("hello response: {}".format(response))

            if response:  # 确保获取到的响应非空
                # 选择最随和的问候方式
                selected_greeting = await self.generator.select_from_list(
                    "请选择最随和的问候方式", response
                )

                # 将选择的结果记录日志
                self.ap.logger.info("Selected greeting: {}".format(selected_greeting))

            # 阻止该事件默认行为
            ctx.prevent_default()

    # 插件卸载时触发
    def __del__(self):
        pass
