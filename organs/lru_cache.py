from typing import List, Optional
from collections import OrderedDict

class LRUCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache: OrderedDict[str, List[str]] = OrderedDict()

    def get(self, key: str) -> Optional[List[str]]:
        """获取缓存值，若存在则将其标记为最新使用"""
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)  # 移动到末尾表示最新访问
        return self.cache[key]

    def put(self, key: str, value: List[str]) -> None:
        """插入或更新缓存值"""
        if key in self.cache:
            self.cache.move_to_end(key)  # 已存在则更新并标记为最新
        self.cache[key] = value
        # 若超出容量，移除最久未使用的键（头部）
        if len(self.cache) > self.capacity:
            self.cache.popitem(last=False)