from pkg.plugin.context import register, handler, BasePlugin, APIHost, EventContext
from pkg.plugin.events import PersonNormalMessageReceived
from pkg.provider import entities as llm_entities


# 注册插件
@register(name="Hello", description="hello world", version="0.1", author="ElvisChenML")
class MyPlugin(BasePlugin):

    # 插件加载时触发
    def __init__(self, host: APIHost):
        self.host = host
        self.ap = host.ap

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

            # 发送消息并获取回复
            model_info = await self.ap.model_mgr.get_model_by_name(
                self.ap.provider_cfg.data["model"]
            )
            response = await model_info.requester.call(
                model=model_info,
                messages=[llm_entities.Message(role="user", content=msg)],
            )

            # 将回复记录日志
            # hello response: assistant: Hello! How can I assist you today?
            self.ap.logger.info("hello response: {}".format(response.readable_str()))

            # 阻止该事件默认行为
            ctx.prevent_default()

    # 插件卸载时触发
    def __del__(self):
        pass
