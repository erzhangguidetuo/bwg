"""摄取主流程：目录 -> 解析 -> 分块 -> 嵌入 -> Chroma 入库。

独立成函数而非脚本，方便测试复用与阶段三的 Agent 工具化。
"""
import sqlite3
from pathlib import Path

from core.config import settings
from ingestion.chunker import split_documents
from ingestion.loader import load_directory, load_file
from retrieval.vector_store import VectorStore


def _ensure_meta_db():
    """SQLite 元数据库：记录每份文档的分块数量，便于后续文档管理。"""
    conn = sqlite3.connect(settings.META_DB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            doc_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            source   TEXT UNIQUE NOT NULL,
            chunks   INTEGER NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()
    return conn


def build_index(docs_dir, embedder, reset: bool = True,
                chunk_size: int | None = None, overlap: int | None = None) -> dict:
    """完整摄取流水线，返回统计信息。

    chunk_size/overlap 供评测实验临时覆盖分块参数，默认取 settings。
    """
    print(f"[1/4] 解析目录: {docs_dir}")
    units = load_directory(docs_dir)
    if not units:
        raise RuntimeError(f"目录中没有可解析的文档: {docs_dir}")

    size = chunk_size or settings.CHUNK_SIZE
    ov = overlap or settings.CHUNK_OVERLAP
    print(f"[2/4] 分块中 (size={size}, overlap={ov})")
    chunks = split_documents(units, chunk_size=size, overlap=ov)
    print(f"      共得到 {len(chunks)} 个块")

    print("[3/4] 生成嵌入向量")
    texts = [c["text"] for c in chunks]
    embeddings = embedder.embed_documents(texts)

    print("[4/4] 写入 Chroma 与元数据库")
    store = VectorStore()
    if reset:
        store.reset()
    store.add_chunks(chunks, embeddings)

    conn = _ensure_meta_db()
    by_source: dict[str, int] = {}
    for c in chunks:
        by_source[c["metadata"]["source"]] = by_source.get(c["metadata"]["source"], 0) + 1
    for source, n in by_source.items():
        conn.execute(
            "INSERT INTO documents(source, chunks) VALUES(?, ?) "
            "ON CONFLICT(source) DO UPDATE SET chunks=excluded.chunks, "
            "updated_at=CURRENT_TIMESTAMP",
            (source, n),
        )
    conn.commit()
    conn.close()

    return {
        "units": len(units),
        "chunks": len(chunks),
        "stored": len(chunks),
        "total": store.count(),
    }


def index_single_file(path, embedder) -> int:
    """单文件增量索引：先删旧块再写入新块，保证同名文档幂等更新。

    与 build_index 的区别：不 reset 整个向量库，其他文档不受影响。
    供 API 的 /upload 接口调用。返回该文档的分块数。
    """
    path = Path(path)
    units = load_file(path)
    if not units:
        raise ValueError(f"文档解析结果为空: {path.name}")
    chunks = split_documents(units)
    embeddings = embedder.embed_documents([c["text"] for c in chunks])

    store = VectorStore()
    store.delete_by_source(path.name)
    store.add_chunks(chunks, embeddings)

    conn = _ensure_meta_db()
    conn.execute(
        "INSERT INTO documents(source, chunks) VALUES(?, ?) "
        "ON CONFLICT(source) DO UPDATE SET chunks=excluded.chunks, "
        "updated_at=CURRENT_TIMESTAMP",
        (path.name, len(chunks)),
    )
    conn.commit()
    conn.close()
    return len(chunks)
