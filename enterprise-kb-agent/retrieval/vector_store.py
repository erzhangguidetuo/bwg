"""向量库封装：基于 Chroma 的持久化存储与相似度检索。

设计要点：
- 向量本身由 core.llm.get_embeddings() 生成，本模块只管存取；
- chunk_id 用"文件名 + chunk_index"的哈希，重建索引时同文档同块号
  会覆盖旧记录，天然支持文档更新的幂等写入；
- 元数据直接随向量存入 Chroma，检索结果自带来源信息（引用溯源的
  基础）。
"""
import hashlib

import chromadb

from core.config import settings


def make_chunk_id(source: str, chunk_index: int) -> str:
    """由来源与块号生成稳定 ID。"""
    raw = f"{source}::{chunk_index}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


class VectorStore:
    def __init__(self):
        client = chromadb.PersistentClient(path=str(settings.CHROMA_DIR))
        self.collection = client.get_or_create_collection(
            name=settings.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    # ---------- 写入 ----------
    def add_chunks(self, chunks: list[dict], embeddings: list[list[float]]):
        """chunks 与 embeddings 一一对应，批量入库。"""
        self.collection.upsert(
            ids=[make_chunk_id(c["metadata"]["source"], c["metadata"]["chunk_index"])
                 for c in chunks],
            documents=[c["text"] for c in chunks],
            metadatas=[c["metadata"] for c in chunks],
            embeddings=embeddings,
        )

    def count(self) -> int:
        return self.collection.count()

    def delete_by_source(self, source: str):
        """按文档来源删除全部块（上传同名新版本前调用，实现幂等更新）。"""
        self.collection.delete(where={"source": source})

    def get_all(self) -> list[dict]:
        """全量读取（BM25 建索引用）：返回与 add_chunks 相同结构的 chunks。"""
        if self.count() == 0:
            return []
        result = self.collection.get(include=["documents", "metadatas"])
        return [
            {"text": text, "metadata": meta}
            for text, meta in zip(result["documents"], result["metadatas"])
        ]

    # ---------- 检索 ----------
    def search(self, query_embedding: list[float], k: int | None = None) -> list[dict]:
        """返回 [{"text", "metadata", "distance"}]，按相似度降序。"""
        k = k or settings.RETRIEVAL_TOP_K
        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(k, max(self.count(), 1)),
            include=["documents", "metadatas", "distances"],
        )
        hits = []
        for text, meta, dist in zip(
            result["documents"][0], result["metadatas"][0], result["distances"][0]
        ):
            hits.append({"text": text, "metadata": meta, "distance": dist})
        return hits

    # ---------- 管理 ----------
    def reset(self):
        """清空集合（重建索引前调用）。"""
        client = chromadb.PersistentClient(path=str(settings.CHROMA_DIR))
        client.delete_collection(settings.COLLECTION_NAME)
        self.collection = client.get_or_create_collection(
            name=settings.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
