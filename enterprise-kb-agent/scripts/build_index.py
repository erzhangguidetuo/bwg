"""索引构建入口：解析 -> 分块 -> 嵌入 -> 入库，一条命令完成摄取。

用法（项目根目录下）：
    uv run scripts/build_index.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import settings
from core.llm import get_embeddings
from ingestion.chunker import split_documents
from ingestion.indexer import build_index

if __name__ == "__main__":
    embedder = get_embeddings()
    stats = build_index(
        docs_dir=settings.DOCS_DIR,
        embedder=embedder,
    )
    print("\n==== 索引构建完成 ====")
    print(f"解析文档单元数: {stats['units']}")
    print(f"分块总数:       {stats['chunks']}")
    print(f"入库块数:       {stats['stored']}")
    print(f"向量库当前总量: {stats['total']}")
