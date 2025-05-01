from plugins.Waifu.organs.memory_item import MemoryItem
import networkx as nx
import heapq

class MemoryGraph:
    def __init__(self):
        # 使用NetworkX图表示记忆连接
        self._graph = nx.Graph()

    def add_memory(self, memory: MemoryItem):
        tags = set(memory.tags())
        # 添加节点（关键词）
        self._graph.add_nodes_from(tags)

        # 更新所有标签对之间的边
        self._update_edges(tags)

    def _update_edges(self, keywords: set[str]):
        """
        在图中更新关键词之间的边。
        """
        keywords_list = list(keywords)
        for i in range(len(keywords_list)):
            for j in range(i + 1, len(keywords_list)):
                key1, key2 = keywords_list[i], keywords_list[j]
                if self._graph.has_edge(key1, key2):
                    self._graph[key1][key2]['weight'] += 1
                else:
                    self._graph.add_edge(key1, key2, weight=1.0)

    def get_connection_strength(self, key1, key2):
        """
        获取两个关键词之间的连接强度。
        """
        if self._graph.has_edge(key1, key2):
            return self._graph[key1][key2]['weight']
        return 0

    def get_related_keywords(self, keywords: set[str]) -> list[str]:
        """
        获取与给定关键词相关的关键词，由最大深度限制。
        同时考虑多个输入标签的综合连接强度。
        """

        valid_keywords = {k for k in keywords if self._graph.has_node(k)}
        if not valid_keywords:
            return []

        related = {}

        # 使用优先队列: (-strength, keyword, depth)
        # 负的强度值使得heapq优先处理强度最高的关键词
        need_search_keywords = []
        for k in valid_keywords:
            heapq.heappush(need_search_keywords, (-1.0, k, 0))

        # 记录已经访问过的(关键词, 源关键词)对，避免重复访问
        accessed_pairs = set()

        while need_search_keywords:
            neg_strength, keyword, depth = heapq.heappop(need_search_keywords)
            strength = -neg_strength  # 转回正值

            if keyword in accessed_pairs:
                continue
            accessed_pairs.add(keyword)

            total_connections = 0
            for src in related:
                if self._graph.has_edge(src, keyword):
                    total_connections += 1

            # 至少需要与2/3的关键词有连接
            most_part = len(related) * 2 // 3
            need_conn = max(1,most_part)
            if total_connections < need_conn and len(related) > 0:
                if keyword not in valid_keywords:
                    continue

            related[keyword] = strength

            for neighbor in self._graph.neighbors(keyword):
                if neighbor in related:
                    continue

                # 计算总连接长度
                total_weight = self._graph[keyword][neighbor]['weight']

                # 考虑所有相关关键词的连接
                for src in valid_keywords:
                    if self._graph.has_edge(src, neighbor) and src != keyword:
                        weight = self._graph[src][neighbor]['weight']
                        total_weight += weight

                # 计算新强度
                new_strength = strength - 1 / total_weight

                if new_strength > 0:
                    heapq.heappush(need_search_keywords, (-new_strength, neighbor, depth + 1))

        sorted_related = sorted(related.items(), key=lambda x: x[1], reverse=True)
        sorted_related = [k for k, v in sorted_related]
        return sorted_related

    def get_all_keywords(self):
        """
        获取图中的所有关键词。
        """
        return set(self._graph.nodes())

    def clear(self):
        """
        清除图中的所有数据。
        """
        self._graph.clear()
