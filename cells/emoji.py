import os
import json
import random
import typing
from pkg.core import app

class EmojiManager:
    def __init__(self, ap: app.Application):
        self.ap = ap
        self.emoji_dir = "data/plugins/Waifu/config/waifu/images"
        self.emoji_index_file = os.path.join(self.emoji_dir, "emoji_index.json")
        self.emoji_index = {}
        self.emotion_keywords = {
            "开心": ["开心", "高兴", "快乐", "喜悦", "兴奋", "笑", "愉快", "欢乐"],
            "悲伤": ["悲伤", "难过", "伤心", "痛苦", "哭", "忧郁", "沮丧", "失落"],
            "愤怒": ["愤怒", "生气", "恼火", "暴怒", "怒火", "不满", "烦躁", "恼怒"],
            "惊讶": ["惊讶", "震惊", "吃惊", "惊喜", "意外", "惊愕", "惊恐", "惊慌"],
            "害羞": ["害羞", "羞涩", "腼腆", "不好意思", "羞耻", "羞赧", "难为情"],
            "爱意": ["爱", "喜欢", "爱意", "爱慕", "爱恋", "暗恋", "恋爱", "心动"],
            "无奈": ["无奈", "无语", "无助", "无力", "叹气", "叹息", "苦笑", "尴尬"],
            "期待": ["期待", "盼望", "希望", "渴望", "憧憬", "向往", "等待", "企盼"],
            "困惑": ["困惑", "疑惑", "迷茫", "不解", "不明白", "迷惑", "费解", "困扰"],
            "调皮": ["调皮", "顽皮", "捣蛋", "淘气", "恶作剧", "俏皮", "嬉皮", "嘻嘻"],
            "默认": []  # 默认情绪，没有关键词
        }
        self.emoji_enabled = True  # 表情包功能开关
        self.emoji_threshold = 0.6  # 表情包匹配阈值
        self._ensure_emoji_dir()
        self._load_or_create_index()

    def _ensure_emoji_dir(self):
        """确保表情包目录存在"""
        if not os.path.exists(self.emoji_dir):
            os.makedirs(self.emoji_dir)
            self.ap.logger.info(f"创建表情包目录: {self.emoji_dir}")

    def _load_or_create_index(self):
        """加载或创建表情包索引"""
        if os.path.exists(self.emoji_index_file):
            try:
                with open(self.emoji_index_file, 'r', encoding='utf-8') as f:
                    self.emoji_index = json.load(f)
                self.ap.logger.info(f"加载表情包索引: {len(self.emoji_index)} 个表情包")
            except Exception as e:
                self.ap.logger.error(f"加载表情包索引失败: {e}")
                self._scan_and_create_index()
        else:
            self._scan_and_create_index()

    def _scan_and_create_index(self):
        """扫描表情包目录并创建索引"""
        self.emoji_index = {}
        if not os.path.exists(self.emoji_dir):
            return

        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
        for filename in os.listdir(self.emoji_dir):
            file_path = os.path.join(self.emoji_dir, filename)
            if os.path.isfile(file_path) and any(filename.lower().endswith(ext) for ext in image_extensions):
                # 从文件名中提取情感标签
                emotion = self._extract_emotion_from_filename(filename)
                if emotion not in self.emoji_index:
                    self.emoji_index[emotion] = []
                self.emoji_index[emotion].append(filename)

        # 保存索引到文件
        try:
            with open(self.emoji_index_file, 'w', encoding='utf-8') as f:
                json.dump(self.emoji_index, f, ensure_ascii=False, indent=2)
            self.ap.logger.info(f"创建表情包索引: {len(self.emoji_index)} 个情感类别")
        except Exception as e:
            self.ap.logger.error(f"保存表情包索引失败: {e}")

    def _extract_emotion_from_filename(self, filename):
        """从文件名中提取情感标签"""
        # 移除扩展名
        name_without_ext = os.path.splitext(filename)[0]
        
        # 检查文件名中是否包含情感关键词
        for emotion, keywords in self.emotion_keywords.items():
            for keyword in keywords:
                if keyword in name_without_ext:
                    return emotion
        
        # 如果没有匹配到情感关键词，返回默认情感
        return "默认"

    def get_emoji_for_emotion(self, text: str) -> typing.Optional[str]:
        """
        根据文本内容选择合适的表情包
        
        Args:
            text: 文本内容
            
        Returns:
            表情包文件路径或None
        """
        # 如果表情包功能关闭或没有表情包，返回None
        if not self.emoji_enabled or not self.emoji_index:
            return None
            
        # 分析文本情感
        emotion_scores = self._analyze_emotion(text)
        
        # 按情感得分排序
        sorted_emotions = sorted(emotion_scores.items(), key=lambda x: x[1], reverse=True)
        
        # 如果最高情感得分低于阈值，不发送表情包
        if sorted_emotions[0][1] < self.emoji_threshold:
            return None
            
        # 获取得分最高的情感
        top_emotion = sorted_emotions[0][0]
        
        # 如果该情感没有表情包，尝试使用默认表情包
        if top_emotion not in self.emoji_index or not self.emoji_index[top_emotion]:
            if "默认" in self.emoji_index and self.emoji_index["默认"]:
                emoji_filename = random.choice(self.emoji_index["默认"])
            else:
                # 如果没有默认表情包，随机选择一个情感类别
                available_emotions = [e for e in self.emoji_index if self.emoji_index[e]]
                if not available_emotions:
                    return None
                emoji_filename = random.choice(self.emoji_index[random.choice(available_emotions)])
        else:
            # 从该情感类别中随机选择一个表情包
            emoji_filename = random.choice(self.emoji_index[top_emotion])
            
        return os.path.join(self.emoji_dir, emoji_filename)
        
    def _analyze_emotion(self, text: str) -> dict:
        """
        分析文本情感，返回各情感类别的得分
        
        Args:
            text: 文本内容
            
        Returns:
            情感得分字典，如 {"开心": 0.8, "悲伤": 0.1, ...}
        """
        emotion_scores = {emotion: 0.0 for emotion in self.emotion_keywords}
        
        # 简单的关键词匹配方法
        for emotion, keywords in self.emotion_keywords.items():
            if not keywords:  # 跳过默认情感
                continue
                
            # 计算文本中包含该情感关键词的数量
            keyword_count = sum(1 for keyword in keywords if keyword in text)
            
            # 计算情感得分，最高为1.0
            if keywords:
                emotion_scores[emotion] = min(1.0, keyword_count / len(keywords) * 2)
        
        # 如果没有明显情感，设置默认情感得分为0.3
        if all(score < 0.3 for score in emotion_scores.values()):
            emotion_scores["默认"] = 0.3
            
        return emotion_scores
    
    def toggle_emoji(self):
        """切换表情包功能开关"""
        self.emoji_enabled = not self.emoji_enabled
        return self.emoji_enabled