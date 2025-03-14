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
                self.emoji_cache[emotion].append(os.path.join(self.emoji_dir, file))
        
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
        
        # 如果没有匹配，返回随机表情包
        if self.emoji_cache:
            random_emotion = random.choice(list(self.emoji_cache.keys()))
            return random.choice(self.emoji_cache[random_emotion])
        
        return None

    def analyze_emotion(self, text):
        """分析文本情绪，返回情绪标签"""
        # 简单的情绪关键词匹配
        emotion_keywords = {
            "开心": ["开心", "高兴", "快乐", "兴奋", "喜悦", "笑", "哈哈", "嘻嘻"],
            "难过": ["难过", "伤心", "悲伤", "哭", "泪", "呜呜"],
            "生气": ["生气", "愤怒", "恼火", "火大", "气愤"],
            "惊讶": ["惊讶", "震惊", "吃惊", "惊喜", "哇"],
            "害羞": ["害羞", "羞涩", "脸红", "不好意思"],
            "无奈": ["无奈", "叹气", "唉", "算了"],
            "疑惑": ["疑惑", "困惑", "不解", "为什么", "？"],
            "期待": ["期待", "盼望", "希望", "等待"],
            "尴尬": ["尴尬", "尬", "不自在"],
            "思考": ["思考", "想", "考虑", "嗯"],
        }
        
        # 检查文本中是否包含情绪关键词
        for emotion, keywords in emotion_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    return emotion
        
        # 如果没有匹配到关键词，检查是否有可用的表情包
        available_emotions = self.get_available_emotions()
        if available_emotions:
            return random.choice(available_emotions)
        
        return None

    def create_emoji_message(self, text, emotion=None):
        """创建带表情包的消息"""
        if not emotion:
            emotion = self.analyze_emotion(text)
        
        emoji_path = self.get_emoji_for_emotion(emotion) if emotion else None
        
        if emoji_path and os.path.exists(emoji_path):
            return platform_message.MessageChain([
                platform_message.Plain(text),
                platform_message.Image(path=emoji_path)
            ])
        else:
            return platform_message.MessageChain([platform_message.Plain(text)])