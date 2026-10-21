"""混合检索器：向量 + BM25 两路并行，RRF 融合出最终排名。

这是阶段二的核心交付。企业生产系统的检索层基本都是这个形态：
"语义一路、字面一路、融合兜底"。
"""
from core.config import settings
from core.llm import get_embeddings
from retrieval.bm25_store import BM25Store
from retrieval.fusion import make_key, rrf_fuse
from retrieval.vector_store import VectorStore


class HybridRetriever:
    def __init__(self):
        self.store = VectorStore()
        self._build_cache()

    def _build_cache(self):
        """从 Chroma 加载全量语料并重建 BM25 索引。"""
        self.embedder = get_embeddings()
        all_chunks = self.store.get_all()
        self.chunk_map = {make_key(c["metadata"]): c for c in all_chunks}
        self.bm25 = BM25Store(all_chunks)

    def refresh(self):
        """索引更新后由外部调用（如 /upload 上传新文档），重建语料缓存。

        这是"服务内存缓存 vs 磁盘索引"一致性问题的解法：检索器
        不感知文件系统变化，必须由写入口显式通知。
        """
        self._build_cache()

    @property
    def is_empty(self) -> bool:
        return len(self.chunk_map) == 0

    def search(self, query: str, top_k: int | None = None) -> list[dict]:
        """混合检索。

        返回 [{"text", "metadata", "rrf_score", "channels"}]，channels 记录
        该片段是被哪些通道命中的（如 {"vector": 2, "bm25": 5}），
        便于观察两路检索各自的贡献。
        """
        top_k = top_k or settings.RETRIEVAL_TOP_K
        if self.is_empty:
            return []

        # 两路各取候选（候选池大于最终 top_k，给融合留出空间）
        pool = max(top_k * 2, 8)

        query_vec = self.embedder.embed_query(query)
        vector_hits = self.store.search(query_vec, k=pool)
        bm25_hits = self.bm25.search(query, k=pool)

        # 整理成 RRF 需要的排名列表
        vector_ranking = [(h["metadata"]["source"], h["metadata"]["chunk_index"])
                          for h in vector_hits]
        bm25_ranking = [key.split("::") for key, _ in bm25_hits]
        rankings: list[list[str]] = [
            [make_key({"source": s, "chunk_index": i}) for s, i in vector_ranking],
            ["::".join(parts) for parts in bm25_ranking],
        ]

        fused = rrf_fuse(rankings)

        # 记录每个片段被各通道命中的排名，用于展示与调试
        channels: dict[str, dict] = {}
        for channel_name, ranking in (("vector", rankings[0]), ("bm25", rankings[1])):
            for rank, key in enumerate(ranking, start=1):
                channels.setdefault(key, {})[channel_name] = rank

        results = []
        for key, score in fused[:top_k]:
            chunk = self.chunk_map.get(key)
            if chunk is None:
                continue  # 理论上不发生，防御性跳过
            results.append({
                **chunk,
                "rrf_score": round(score, 5),
                "channels": channels.get(key, {}),
            })
        return results


# ---------- 共享单例：供 LangGraph 节点与 FastAPI 服务共用 ----------

_shared: HybridRetriever | None = None


def get_shared_retriever() -> HybridRetriever:
    """全局唯一检索器实例。写入口（/upload）调 refresh() 后，
    所有持有该实例的节点立即检索到新文档。"""
    global _shared
    if _shared is None:
        _shared = HybridRetriever()
    return _shared
