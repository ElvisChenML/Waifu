import os
import random
import re
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
        self._ensure_emoji_dir_exists()
        self._load_emojis()
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

    def reload_emojis(self):
        """重新加载表情包"""
        self._load_emojis()
        return f"已重新加载 {sum(len(files) for files in self.emoji_cache.values())} 个表情包"

    def get_available_emotions(self):
        """获取所有可用的情绪标签"""
        return list(self.emoji_cache.keys())

    def get_emoji_for_emotion(self, emotion):
        """根据情绪获取表情包"""
        if not self.emoji_cache:
            return None
        
        # 如果找到完全匹配的情绪
        if emotion in self.emoji_cache and self.emoji_cache[emotion]:
            return random.choice(self.emoji_cache[emotion])
        
        # 如果没有完全匹配，尝试部分匹配
        for key in self.emoji_cache:
            if emotion in key or key in emotion:
                return random.choice(self.emoji_cache[key])
        
        # 如果没有匹配，返回None
        return None

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
            return None
            
        # 构建提示语
        emoticon_list = ", ".join(available_emotions)
        prompt = f"""分析以下文本的情感和语气，并从给定的表情列表中选择一个最合适的表情。
文本: "{text}"
可用表情: {emoticon_list}
请只回复一个表情名称，不要添加任何其他内容。"""
        
        try:
            # 修正参数数量，根据Generator.return_string的实际参数要求调整
            system_prompt = "你是一个情感分析专家，擅长从文本中识别情绪并选择合适的表情"
            emotion = await generator.return_string(prompt, system_prompt)
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
            return random.choice(available_emotions)

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
            emoji_file = self.get_emoji_for_emotion(emotion)
            
            if not emoji_file:
                # 如果没有匹配的表情包，只返回文本
                return platform_message.MessageChain([platform_message.Plain(text)])
            
            # 构建完整的表情包路径
            emoji_path = os.path.join(self.emoji_dir, emoji_file)
            
            # 使用 Image.from_local 创建图片消息
            image = platform_message.Image.from_local(emoji_path)
            return platform_message.MessageChain([platform_message.Plain(text), image])
        except Exception as e:
            self.ap.logger.error(f"加载表情包失败: {e}")
            return platform_message.MessageChain([platform_message.Plain(text)])