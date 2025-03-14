import os
import random
import re
import json
import requests
from pkg.core import app
from pkg.platform.types import message as platform_message
from pkg.provider import entities as llm_entities

class EmojiManager:
    """表情包管理器，负责选择和发送表情包"""

    ap: app.Application

    def __init__(self, ap: app.Application):
        self.ap = ap
        self.emoji_dir = "data/plugins/Waifu/images"
        self.emoji_cache = {}
        self.superbed_token = "123456789"  # 请替换为您的实际token
        self.use_superbed = True  # 设置为False可以暂时禁用聚合图床功能
        self.superbed_image_cache = {}  # 缓存图床中的图片
        self._ensure_emoji_dir_exists()
        self._load_emojis()
        if self.use_superbed:
            self._load_superbed_images()
        self.last_emoji_time = 0  # 上次发送表情包的时间

    def _ensure_emoji_dir_exists(self):
        """确保表情包目录存在"""
        if not os.path.exists(self.emoji_dir):
            os.makedirs(self.emoji_dir)
            self.ap.logger.info(f"表情包目录已创建: {self.emoji_dir}")

    def _load_emojis(self):
        """加载所有表情包到缓存"""
        if not os.path.exists(self.emoji_dir):
            return
        
        self.emoji_cache = {}
        for file in os.listdir(self.emoji_dir):
            if file.endswith(('.jpg', '.jpeg', '.png', '.gif')):
                # 提取文件名作为情绪标签
                emotion = os.path.splitext(file)[0]
                if emotion not in self.emoji_cache:
                    self.emoji_cache[emotion] = []
                self.emoji_cache[emotion].append(file)  # 只存储文件名，不包含完整路径
        
        self.ap.logger.info(f"已加载 {sum(len(files) for files in self.emoji_cache.values())} 个表情包")

    def _load_superbed_images(self):
        """从聚合图床加载图片"""
        try:
            url = "https://api.superbed.cn/timeline"
            params = {
                "token": self.superbed_token,
                "f": "json",
                "size": 100  # 获取最多100张图片
            }
            
            self.ap.logger.info(f"正在从聚合图床加载图片，URL: {url}")
            
            response = requests.get(url, params=params)
            self.ap.logger.info(f"聚合图床API响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                # 打印原始响应内容，帮助调试
                response_text = response.text
                self.ap.logger.info(f"聚合图床API响应内容前100个字符: {response_text[:100] if response_text else '空响应'}")
                
                # 检查响应是否为空
                if not response_text:
                    self.ap.logger.warning("聚合图床API返回了空响应")
                    return
                    
                try:
                    data = response.json()
                    
                    if data.get("code") == 200:
                        images = data.get("data", {}).get("images", [])
                        
                        # 清空现有缓存
                        self.superbed_image_cache = {}
                        
                        # 处理图片数据
                        for image in images:
                            # 从文件名中提取情绪标签
                            filename = image.get("filename", "")
                            emotion = os.path.splitext(filename)[0]
                            
                            # 获取图片URL
                            image_url = image.get("url")
                            if image_url and emotion:
                                if emotion not in self.superbed_image_cache:
                                    self.superbed_image_cache[emotion] = []
                                self.superbed_image_cache[emotion].append(image_url)
                        
                        self.ap.logger.info(f"已从聚合图床加载 {sum(len(urls) for urls in self.superbed_image_cache.values())} 个表情包")
                    else:
                        self.ap.logger.warning(f"从聚合图床加载图片失败: {data.get('message')}, 错误码: {data.get('code')}")
                except json.JSONDecodeError as json_err:
                    self.ap.logger.error(f"解析聚合图床API响应JSON失败: {json_err}, 响应内容: {response_text[:200]}")
            else:
                self.ap.logger.warning(f"从聚合图床加载图片失败，HTTP状态码: {response.status_code}, 响应内容: {response.text[:200]}")
        except requests.RequestException as req_err:
            self.ap.logger.error(f"请求聚合图床API时出错: {req_err}")
        except Exception as e:
            self.ap.logger.error(f"从聚合图床加载图片时出错: {e}")

    def reload_emojis(self):
        """重新加载表情包"""
        self._load_emojis()
        self._load_superbed_images()
        local_count = sum(len(files) for files in self.emoji_cache.values())
        superbed_count = sum(len(urls) for urls in self.superbed_image_cache.values())
        return f"已重新加载 {local_count} 个本地表情包和 {superbed_count} 个图床表情包"

    def get_available_emotions(self):
        """获取所有可用的情绪标签"""
        # 合并本地和图床的情绪标签
        emotions = set(self.emoji_cache.keys())
        emotions.update(self.superbed_image_cache.keys())
        return list(emotions)

    def get_emoji_for_emotion(self, emotion):
        """根据情绪获取表情包URL或本地文件名"""
        # 优先使用图床中的图片
        if emotion in self.superbed_image_cache and self.superbed_image_cache[emotion]:
            return {"type": "url", "value": random.choice(self.superbed_image_cache[emotion])}
        
        # 如果图床中没有，尝试部分匹配图床图片
        for key in self.superbed_image_cache:
            if emotion in key or key in emotion:
                return {"type": "url", "value": random.choice(self.superbed_image_cache[key])}
        
        # 如果图床中没有，使用本地图片
        if emotion in self.emoji_cache and self.emoji_cache[emotion]:
            return {"type": "local", "value": random.choice(self.emoji_cache[emotion])}
        
        # 如果本地也没有完全匹配，尝试部分匹配本地图片
        for key in self.emoji_cache:
            if emotion in key or key in emotion:
                return {"type": "local", "value": random.choice(self.emoji_cache[key])}
        
        # 如果没有匹配，返回None
        return None

    async def create_emoji_message(self, text, generator, emoji_rate=1.0):
        """创建带表情包的消息
        
        Args:
            text: 文本消息
            generator: 生成器对象，用于调用大模型
            emoji_rate: 表情包发送频率，范围0-1
        
        Returns:
            MessageChain: 消息链
        """
        # 根据频率决定是否发送表情包
        if random.random() > emoji_rate:
            return platform_message.MessageChain([platform_message.Plain(text)])
            
        try:
            # 使用大模型分析情绪
            emotion = await self.analyze_emotion_with_llm(text, generator)
            
            # 如果没有获取到情绪，直接返回纯文本
            if emotion is None:
                return platform_message.MessageChain([platform_message.Plain(text)])
                
            emoji_info = self.get_emoji_for_emotion(emotion)
            
            if not emoji_info:
                # 如果没有匹配的表情包，只返回文本
                return platform_message.MessageChain([platform_message.Plain(text)])
            
            # 根据表情包类型创建图片消息
            if emoji_info["type"] == "url":
                # 使用URL创建图片消息
                image = platform_message.Image(url=emoji_info["value"])
            else:
                # 使用本地文件创建图片消息
                emoji_path = os.path.join(self.emoji_dir, emoji_info["value"])
                image = platform_message.Image(path=emoji_path)
            
            # 确保返回的是一个有效的MessageChain对象
            return platform_message.MessageChain([platform_message.Plain(text), image])
        except Exception as e:
            self.ap.logger.error(f"加载表情包失败: {e}")
            # 出错时返回纯文本消息
            return platform_message.MessageChain([platform_message.Plain(text)])

    async def analyze_emotion_with_llm(self, text, generator):
        """使用大模型分析文本情绪并选择合适的表情包
        
        Args:
            text: 文本消息
            generator: 生成器对象，用于调用大模型
            
        Returns:
            str: 选择的表情名称
        """
        available_emotions = self.get_available_emotions()
        if not available_emotions:
            return random.choice(list(self.emoji_cache.keys())) if self.emoji_cache else None
            
        # 构建提示语
        emoticon_list = ", ".join(available_emotions)
        prompt = f"""分析以下文本的情感和语气，并从给定的表情列表中选择一个最合适的表情。
文本: "{text}"
可用表情: {emoticon_list}
请只回复一个表情名称，不要添加任何其他内容。"""
        
        try:
            # 修正参数数量，根据Generator.return_string的实际参数要求调整
            # 查看Generator.return_string方法签名，只传入必要的参数
            emotion = await generator.return_string(prompt)
            emotion = emotion.strip()
            
            # 检查返回的表情是否在可用列表中
            if emotion in available_emotions:
                return emotion
                
            # 如果不在列表中，尝试部分匹配
            for key in available_emotions:
                if emotion in key or key in emotion:
                    return key
                    
            # 如果仍然没有匹配，随机选择一个
            return random.choice(available_emotions)
        except Exception as e:
            self.ap.logger.error(f"使用大模型分析情绪失败: {e}")
            # 失败时回退到随机选择
            return random.choice(available_emotions) if available_emotions else None