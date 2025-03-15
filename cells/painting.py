import requests
import asyncio
from pkg.core import app
from pkg.platform.types import message as platform_message
from plugins.Waifu.cells.emoji import EmojiManager

class Painting:
    def __init__(self, ap: app.Application, emoji_manager: EmojiManager):
        self.ap = ap
        self.emoji_manager = emoji_manager
        self.model = "wanx2.1-t2i-turbo"
        self.api_key = "your_api_key_here"

    async def generate_image(self, prompt: str, orientation: str) -> str:
        size = "1280*720" if orientation == "横着" else "720*1280"
        url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
        headers = {
            'X-DashScope-Async': 'enable',
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        data = {
            "model": self.model,
            "input": {
                "prompt": prompt
            },
            "parameters": {
                "size": size,
                "n": 1,
                "prompt_extend": True
            }
        }
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            response_data = response.json()
            if "data" in response_data and "results" in response_data["data"]:
                image_url = response_data["data"]["results"][0]["url"]
                return image_url
        self.ap.logger.error(f"Failed to generate image: {response.text}")
        return None

    async def send_image(self, ctx, prompt: str, orientation: str):
        image_url = await self.generate_image(prompt, orientation)
        if image_url:
            image = platform_message.Image(url=image_url)
            message_chain = platform_message.MessageChain([image])
            await ctx.event.query.adapter.reply_message(ctx.event.query.message_event, message_chain, False)
        else:
            await ctx.event.query.adapter.reply_message(ctx.event.query.message_event, platform_message.MessageChain(["图片生成失败"]), False)