"""RRF（Reciprocal Rank Fusion，倒数排名融合）。

为什么用 RRF 而不是直接加权分数：
1. 向量检索返回的是余弦距离，BM25 返回的是无上限的相关性分数，
   两者量纲完全不同，直接加权没有意义；
2. RRF 只看"排名"，与分数尺度无关，是生产系统融合多路检索的
   标准做法（Elasticsearch、Milvus 均内置此策略）。

公式：score(d) = Σ 1 / (k + rank_i(d))，k 通常取 60，
作用是平滑头部排名的差异，避免某一路的"第一名"垄断结果。
"""
from collections import defaultdict

RRF_K = 60


def rrf_fuse(rankings: list[list[str]]) -> list[tuple[str, float]]:
    """融合多路检索的排名列表。

    参数:
        rankings: 每一路的文档 key 列表，按相关性从高到低排列。
                  key 需在各路之间可互相比较（本项目用 source::chunk_index）。
    返回:
        [(key, rrf_score)] 按 rrf_score 降序。
    """
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] += 1.0 / (RRF_K + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


def make_key(metadata: dict) -> str:
    """用元数据构造跨通道一致的文档唯一 key。"""
    return f"{metadata['source']}::{metadata['chunk_index']}"
