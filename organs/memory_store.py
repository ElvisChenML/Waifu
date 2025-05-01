from datetime import datetime
from typing import Any, Dict, List, Optional, Iterator
from plugins.Waifu.organs.memory_item import MemoryItem

class MemoryStore:
    """用于管理记忆的存储器。"""

    def __init__(self,tag_count:int = 30):
        """初始化一个空的记忆存储器。"""
        self.memories: List[MemoryItem] = []
        self._tag_count = tag_count

    def insert_memory(self, content: str, tags:list[str]) -> int:
        """在存储器中插入一个新的记忆。

        参数:
            content: 要记住的内容
            tags: 记忆的标签

        返回:
            插入记忆的索引
        """
        memory = MemoryItem(content, tags)
        self.memories.append(memory)
        return len(self.memories) - 1

    def get_memory(self, index: int) -> Optional[MemoryItem]:
        """通过索引获取记忆。"""
        if 0 <= index < len(self.memories):
            return self.memories[index]
        return None

    def delete_memory(self, index: int) -> bool:
        """通过索引删除记忆。

        返回:
            如果删除成功则返回True，否则返回False
        """
        if 0 <= index < len(self.memories):
            self.memories.pop(index)
            return True
        return False

    def clear_memories(self) -> None:
        """清除所有存储的记忆。"""
        self.memories = []

    def __iter__(self) -> Iterator[MemoryItem]:
        """使记忆存储器可迭代。"""
        return iter(self.memories)

    def __len__(self) -> int:
        """返回存储的记忆数量。"""
        return len(self.memories)