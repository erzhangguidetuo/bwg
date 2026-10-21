"""分块模块单元测试。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ingestion.chunker import split_documents


def test_split_respects_size():
    long_text = "这是一段很长的制度说明。" * 200
    docs = [{"text": long_text, "metadata": {"source": "test.md", "page": None}}]
    chunks = split_documents(docs, chunk_size=100, overlap=20)
    assert len(chunks) > 1
    assert all(len(c["text"]) <= 150 for c in chunks)  # 留出重叠余量


def test_metadata_preserved():
    docs = [{"text": "内容甲。\n\n内容乙。", "metadata": {"source": "a.md", "page": 3}}]
    chunks = split_documents(docs, chunk_size=10, overlap=0)
    assert all(c["metadata"]["source"] == "a.md" for c in chunks)
    assert all(c["metadata"]["page"] == 3 for c in chunks)
    assert [c["metadata"]["chunk_index"] for c in chunks] == list(range(len(chunks)))
