"""RRF 融合逻辑单元测试（纯函数，无需模型与网络）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retrieval.fusion import make_key, rrf_fuse


def test_rrf_prefers_documents_hit_by_both_channels():
    # 文档 A 同时被两路召回且都靠前，应排在单路第一名之前
    rankings = [
        ["A", "B", "C"],   # 向量通道排名
        ["A", "D", "E"],   # BM25 通道排名
    ]
    fused = rrf_fuse(rankings)
    assert fused[0][0] == "A"
    # A 得分为两路之和，应严格大于任何单路第一名
    top_score = fused[0][1]
    single_channel_max = 1 / (60 + 1)
    assert top_score > single_channel_max


def test_rrf_ordering():
    fused = rrf_fuse([["A", "B", "C"], ["C", "B", "A"]])
    keys = [k for k, _ in fused]
    # A 和 C 对称并列第一，B 两路都是第 2，综合分最低
    assert set(keys[:2]) == {"A", "C"}
    assert keys[2] == "B"


def test_make_key():
    assert make_key({"source": "a.md", "chunk_index": 3}) == "a.md::3"
