import asyncio
import dashscope
from dashscope import ImageSynthesis
from pkg.core import app
from pkg.platform.types import message as platform_message
from plugins.Waifu.cells.emoji import EmojiManager
from plugins.Waifu.cells.config import ConfigManager

class Painting:
    def __init__(self, ap: app.Application, emoji_manager: EmojiManager):
        self.ap = ap
        self.emoji_manager = emoji_manager
        self.model = "wanx2.1-t2i-turbo"
        self.api_key = "your_api_key_here"
        # 初始化时加载配置
        asyncio.create_task(self.load_config())
        
    async def load_config(self):
        """从配置文件加载绘画相关设置"""
        try:
            config_mgr = ConfigManager(f"data/plugins/Waifu/config/waifu", "plugins/Waifu/templates/waifu")
            await config_mgr.load_config(completion=True)
            self.model = config_mgr.data.get("model", self.model)
            self.api_key = config_mgr.data.get("api_key", self.api_key)
            # 设置 dashscope 的 API Key
            dashscope.api_key = self.api_key
            self.ap.logger.info(f"绘画配置已加载，使用模型: {self.model}")
        except Exception as e:
            self.ap.logger.error(f"加载绘画配置失败: {e}")

    async def generate_image(self, prompt: str, orientation: str) -> str:
        """使用 dashscope 库生成图片"""
        try:
            size = "1280*720" if orientation == "横着" else "720*1280"
            
            # 使用 dashscope 的 ImageSynthesis 类
            response = ImageSynthesis.call(
                model=self.model,
                prompt=prompt,
                n=1,
                size=size,
                prompt_extend=True
            )
            
            # 检查响应状态
            if response.status_code == 200:
                # 从响应中获取图片 URL
                if response.output and response.output.results and len(response.output.results) > 0:
                    image_url = response.output.results[0].url
                    return image_url
                else:
                    self.ap.logger.error(f"生成图片失败: 响应中没有图片URL")
            else:
                self.ap.logger.error(f"生成图片失败: {response.status_code}, {response.message}")
            
            return None
        except Exception as e:
            self.ap.logger.error(f"生成图片时发生异常: {e}")
            return None

    async def send_image(self, ctx, prompt: str, orientation: str):
        """发送生成的图片"""
        image_url = await self.generate_image(prompt, orientation)
        if image_url:
            image = platform_message.Image(url=image_url)
            message_chain = platform_message.MessageChain([image])
            await ctx.event.query.adapter.reply_message(ctx.event.query.message_event, message_chain, False)
        else:
            await ctx.event.query.adapter.reply_message(ctx.event.query.message_event, platform_message.MessageChain(["图片生成失败"]), False)