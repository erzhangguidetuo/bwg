"""BM25 关键词检索通道。

BM25 解决的问题：向量检索擅长语义相似，但对"精确字面"弱——
比如查"第十一条"、"RRF"这类专有名词或编号，语义向量容易漂移到
意思相近但字面不同的段落；BM25 基于词频统计，字面命中即高分。

中文必须先分词（英文按空格天然切分，中文不行），这里用 jieba。
索引在进程内重建（语料来自 Chroma 全量文档），语料量大时可改为
持久化 pickle 或换 Elasticsearch。
"""
import jieba
from rank_bm25 import BM25Okapi

from retrieval.fusion import make_key
from retrieval.vector_store import VectorStore


def tokenize(text: str) -> list[str]:
    """中文分词：jieba 精确模式，过滤空白。"""
    return [t for t in jieba.lcut(text) if t.strip()]


class BM25Store:
    """基于语料块构建的 BM25 检索器。"""

    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        self.keys = [make_key(c["metadata"]) for c in chunks]
        corpus = [tokenize(c["text"]) for c in chunks]
        # 语料为空时 rank_bm25 会报错，这里给一个空索引兜底
        self.bm25 = BM25Okapi(corpus) if corpus else None

    @classmethod
    def from_vector_store(cls, store: VectorStore) -> "BM25Store":
        """从 Chroma 全量文档重建索引，保证与向量库内容一致。"""
        return cls(store.get_all())

    def search(self, query: str, k: int = 8) -> list[tuple[str, float]]:
        """返回 [(key, bm25_score)]，按分数降序，最多 k 个。"""
        if self.bm25 is None:
            return []
        scores = self.bm25.get_scores(tokenize(query))
        ranked = sorted(zip(self.keys, scores), key=lambda x: x[1], reverse=True)
        return [(key, score) for key, score in ranked[:k] if score > 0]
