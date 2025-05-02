from plugins.Waifu.organs.memory_item import MemoryItem
import networkx as nx
import heapq
from itertools import combinations
import math
from pkg.core import app
import numpy as np

class MemoryGraph:
    def __init__(self,app:app.Application):
        # 使用NetworkX图表示记忆连接
        self._graph = nx.Graph()
        self._base_decay = 0.6
        self._noise_threshold = 0.2
        self._max_edges_per_node = 30
        self._app = app
        self._need_update_noise = True
        self._add_cnt = 0
        self._add_cnt_limit = 1000

    def add_memory(self, memory: MemoryItem):
        tags = set(memory.tags())
        # 添加节点（关键词）
        current_node = self._graph.number_of_nodes()
        self._graph.add_nodes_from(tags)
        after_node = self._graph.number_of_nodes()

        # 更新所有标签对之间的边
        self._update_edges(tags)

        # 每一千个节点，进行一次裁剪
        self._add_cnt += after_node - current_node
        if self._add_cnt >= self._add_cnt_limit:
            self._prune_graph()
            self._add_cnt = 0

    def get_avg_degree(self) -> float:
        """
        计算图的平均度数
        """
        if self._graph.number_of_nodes() == 0:
            return 0.0
        return sum(dict(self._graph.degree()).values()) / self._graph.number_of_nodes()

    def get_avg_degree_of_tags(self, tags: set[str]) -> float:
        """
        计算指定标签的平均度数
        """
        node_cnt = 0
        degree_sum = 0.0
        for tag in tags:
            if self._graph.has_node(tag):
                node_cnt += 1
                degree_sum += self._graph.degree(tag)
        if node_cnt == 0:
            return 0.0
        return degree_sum/ node_cnt

    def print_graph(self):
        node_cnt = self._graph.number_of_nodes()
        edge_cnt = self._graph.number_of_edges()
        avg_degree = self.get_avg_degree()
        self._app.logger.info(f"图节点数：{node_cnt}，边数：{edge_cnt} 平均度数：{avg_degree:.4f}")
        return

    def _update_noise_threshold(self):
        """
        动态调整噪声阈值，根据图的当前状态
        """

        if not self._need_update_noise:
            return
        self._need_update_noise = False

        if self._graph.number_of_edges() == 0:
            self._noise_threshold = 0.2
            return

        self._adjust_max_edges_per_node()

        # 计算全图权重分布
        weights = [data['weight'] for _, _, data in self._graph.edges(data=True)]
        if not weights:
            return

        # 使用分位数计算阈值
        lower_quartile = np.percentile(weights, 25)
        avg_degree = self.get_avg_degree()

        # 动态调整阈值范围
        max_threshold = 0.4 + 0.1 * math.log2(avg_degree)
        self._noise_threshold = max(0.1, min(max_threshold, lower_quartile))
        self._app.logger.info(f"动态噪声阈值已更新为: {self._noise_threshold:.4f}")

    def _remove_isolated_nodes(self):
        """
        移除孤立节点
        """
        isolated_nodes = [node for node, degree in self._graph.degree() if degree == 0]
        self._graph.remove_nodes_from(isolated_nodes)

    def _limit_node_edges(self):
        """
        限制每个节点的最大边数
        """
        self._adjust_max_edges_per_node()
        for node in self._graph.nodes():
            edges = list(self._graph.edges(node, data=True))
            if len(edges) > self._max_edges_per_node:
                # 按权重排序，保留权重最高的边
                edges = sorted(edges, key=lambda x: -x[2]['weight'])
                for edge in edges[self._max_edges_per_node:]:
                    self._graph.remove_edge(edge[0], edge[1])

    def _adjust_max_edges_per_node(self):
        """
        根据图的平均度数动态调整每个节点的最大边数
        """
        avg_degree = self.get_avg_degree()
        if avg_degree < 30:
            self._max_edges_per_node = 40
        elif avg_degree < 50:
            self._max_edges_per_node = 30
        else:
            self._max_edges_per_node = 20

    def _prune_graph(self):
        """
        定期清理低权重边
        """
        self._update_noise_threshold()

        for u, v, data in list(self._graph.edges(data=True)):
            if data['weight'] < self._noise_threshold:
                self._graph.remove_edge(u, v)

        self._limit_node_edges()

        self._remove_isolated_nodes()

        self._need_update_noise = True

        self.print_graph()

    def _update_edges(self, keywords: set[str]):
        """
        更新图的边权重并稀疏化，优化算法：
        1. 基于PMI的权重计算：更准确地衡量关联性
        2. 引入全局归一化：平衡整体权重分布
        3. 动态平滑：防止低频节点权重过高
        """
        keywords = list(keywords)
        edges_to_update = []

        # 统计共现次数
        for i, j in combinations(keywords, 2):
            if self._graph.has_edge(i, j):
                self._graph[i][j]['cooccurrence'] += 1
            else:
                self._graph.add_edge(i, j, cooccurrence=1)
            edges_to_update.append((i, j))

        # 改进的PMI权重计算
        total_edges = max(1, self._graph.number_of_edges())
        for i, j in edges_to_update:
            degree_i = max(1, self._graph.degree[i])  # 避免除零
            degree_j = max(1, self._graph.degree[j])
            cooccurrence = self._graph[i][j]['cooccurrence']

            # PMI计算：log(P(x,y) / (P(x) * P(y)))
            pmi = math.log2((cooccurrence * total_edges) / (degree_i * degree_j))

            # 添加平滑和归一化
            smoothing = 0.2  # 平滑因子，防止极值
            norm_factor = math.log2(total_edges) + smoothing

            # 权重计算综合考虑PMI和共现频率
            freq_factor = math.log2(1 + cooccurrence) / math.log2(total_edges)
            pmi_factor = (pmi + smoothing) / norm_factor

            # 混合权重，可以调整alpha来控制PMI和频率的影响
            alpha = 0.7  # PMI权重占比
            weight = alpha * pmi_factor + (1-alpha) * freq_factor

            # 确保权重在合理范围内
            weight = max(0.01, min(1.0, weight))
            self._graph[i][j]['weight'] = weight

        self._need_update_noise = True

    def _get_valid_neighbors(self,keyword:str) -> list[str]:
        """
        获取与关键词相关的有效边
        """
        if not self._graph.has_node(keyword):
            return []
        edges = self._graph.edges(keyword, data=True)
        sorted_edges = sorted(edges, key=lambda x: -x[2]['weight'])[:self._max_edges_per_node]
        # 过滤掉权重小于阈值的边
        sorted_edges = [edge for edge in sorted_edges if edge[2]['weight'] > self._noise_threshold]
        return [edge[1] for edge in sorted_edges]

    def get_connection_strength(self, key1, key2) -> float:
        """
        获取两个关键词之间的连接强度。
        """
        if self._graph.has_edge(key1, key2):
            return self._graph[key1][key2]['weight']
        return 0

    def get_connection_cooccurrence(self, key1, key2) -> float:
        if self._graph.has_edge(key1, key2):
            return self._graph[key1][key2]['cooccurrence']
        return 0

    def get_related_keywords(self, keywords: set[str]) -> list[str]:
        """
        基于海马体特性的记忆扩散算法
        特性模拟：
        1. 短链优先（CA3模式完成）
        2. 动态衰减（DG区抑制调控）
        3. 噪声过滤（抑制性中间神经元）
        """
        valid_keywords = {k for k in keywords if self._graph.has_node(k)}
        if not valid_keywords:
            self._app.logger.info("无效关键词，无法联想")
            return []

        self._update_noise_threshold()

        query_avg_degree = self.get_avg_degree_of_tags(valid_keywords)
        global_avg_degree = self.get_avg_degree()

        adjustment = 0.0
        if query_avg_degree > 0:
            ratio = query_avg_degree / global_avg_degree
            if ratio < 0.5:  # 查询区域明显稀疏
                adjustment = -0.05  # 降低阈值，允许更多联想
            elif ratio > 2.0:  # 查询区域明显密集
                adjustment = 0.05  # 提高阈值，减少联想噪音

        # 最终阈值
        final_threshold = max(0.05, min(0.5, self._noise_threshold + adjustment))

        self._app.logger.info(f"当前全局噪声阈值：{self._noise_threshold:.4f} 当前联想噪声阈值：{final_threshold:.4f}")
        self._app.logger.info(f"联想有效关键词：{valid_keywords}")

        # 初始化优先队列和强度记录
        need_search = []
        for k in valid_keywords:
            heapq.heappush(need_search, (-1.0, k, 0,k))

        self._app.logger.info(f"初始优先队列大小：{len(need_search)}")

        related:dict[str,float] = {}
        # 充当accessed_nodes
        max_strength = {}

        while len(need_search) > 0:
            neg_strength, curr, depth,from_node = heapq.heappop(need_search)

            curr_strength = -neg_strength

            if curr_strength <= self._noise_threshold:
                break

            if curr_strength <= max_strength.get(curr, 0):
                continue

            max_strength[curr] = curr_strength

            self._app.logger.info(f"当前关键词：{curr}，强度：{curr_strength:.4f}")

            related[curr] = curr_strength

            # 动态衰减计算（神经可塑性补偿）
            neighbors = self._get_valid_neighbors(curr)
            avg_weight = sum(self.get_connection_strength(curr, n) for n in neighbors) / max(1, len(neighbors))

            for neighbor in neighbors:
                edge_weight = self.get_connection_strength(curr, neighbor)

                # 改进的动态衰减：高权重边减缓衰减
                weight_ratio = edge_weight / max(0.01, avg_weight)
                dynamic_decay = self._base_decay + 0.2 * min(1.0, weight_ratio)
                dynamic_decay = min(dynamic_decay, 0.8)

                # 路径质量评估：考虑整条路径而非仅当前边
                path_quality = 1.0
                if depth > 0:
                    path_quality = min(1.0, edge_weight / self.get_connection_strength(from_node, curr))

                # 结合路径质量的衰减计算
                adjusted_decay = dynamic_decay * (0.8 + 0.2 * path_quality)
                decay_rate = adjusted_decay ** depth
                new_strength = curr_strength * decay_rate * edge_weight

                # 过滤噪音
                if new_strength > 0:
                    heapq.heappush(need_search, (-new_strength, neighbor, depth + 1,curr))


        # 前额叶皮层归一化处理
        max_value = max(related.values(), default=1e-5)
        normalized = {k: v/max_value for k, v in related.items()}
        sorted_related = sorted(normalized.items(), key=lambda x: -x[1])

        for k,w in sorted_related[:20]:
            self._app.logger.info(f"扩散关键词：{k}，强度：{w:.4f}")

        # 排除输入标签并返回
        return [k for k, v in sorted_related
                if k not in valid_keywords]

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
