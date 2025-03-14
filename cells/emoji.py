import os
import random
import re
from pkg.core import app
from pkg.platform.types import message as platform_message

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

    def analyze_emotion(self, text):
        """分析文本情绪"""
        # 简单的情绪分析，基于关键词
        emotions = {
            "开心": ["开心", "高兴", "快乐", "兴奋", "喜悦", "笑", "哈哈"],
            "悲伤": ["悲伤", "难过", "伤心", "痛苦", "哭", "泪"],
            "生气": ["生气", "愤怒", "恼火", "烦躁", "怒"],
            "惊讶": ["惊讶", "震惊", "吃惊", "惊喜", "哇"],
            "疑问": ["疑问", "困惑", "不解", "为什么", "怎么", "啊？", "嗯？"],
            "害羞": ["害羞", "羞涩", "不好意思", "脸红"],
            "爱心": ["爱", "喜欢", "爱心", "心动", "❤"],
            "无奈": ["无奈", "无语", "叹气", "唉", "哎"]
        }
        
        # 默认情绪
        default_emotion = "开心"
        
        # 检查文本中是否包含情绪关键词
        for emotion, keywords in emotions.items():
            for keyword in keywords:
                if keyword in text:
                    return emotion
        
        return default_emotion

    def create_emoji_message(self, text, emotion, emoji_rate=1.0):
        """创建带表情包的消息
        
        Args:
            text: 文本消息
            emotion: 情绪
            emoji_rate: 表情包发送频率，范围0-1
        
        Returns:
            MessageChain: 消息链
        """
        # 根据频率决定是否发送表情包
        if random.random() > emoji_rate:
            return platform_message.MessageChain([text])
            
        emoji_file = self.get_emoji_for_emotion(emotion)
        if not emoji_file:
            # 如果没有匹配的表情包，只返回文本
            return platform_message.MessageChain([text])
        
        # 构建完整的表情包路径
        emoji_path = os.path.join(self.emoji_dir, emoji_file)
        
        try:
            # 使用 Image.from_local 创建图片消息
            image = platform_message.Image.from_local(emoji_path)
            return platform_message.MessageChain([text, image])
        except Exception as e:
            self.ap.logger.error(f"加载表情包失败: {e}")
            return platform_message.MessageChain([text])