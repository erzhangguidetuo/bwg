"""评测脚本共用的轻量工具：分词与 BM25。

刻意只用标准库，并且与 ``gpt_researcher`` 包解耦——
这样评测脚本在没装项目依赖（langchain、openai 等）的环境里也能跑，
方便在 CI 里当成一个轻量门禁。
"""

from __future__ import annotations

import math
import re

__all__ = ["tokenize", "BM25", "rank_desc"]

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    """中英混排轻量分词：英文/数字整体保留，中文按单字切分。

    单字切分在 BM25 上对付短查询最稳，也省掉了 jieba 这类额外依赖。
    """
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def rank_desc(scores: list[float]) -> list[int]:
    """按分数降序返回下标；同分保持原顺序，保证结果可复现。"""
    return sorted(range(len(scores)), key=lambda i: (-scores[i], i))


class BM25:
    """Okapi BM25，参数 k1=1.5 / b=0.75（检索领域常规默认值）。"""

    def __init__(self, corpus_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs = corpus_tokens
        self.n_docs = len(corpus_tokens)
        self.avg_len = (sum(len(d) for d in corpus_tokens) / self.n_docs) if self.n_docs else 0.0

        self.tf: list[dict[str, int]] = []
        df: dict[str, int] = {}
        for tokens in corpus_tokens:
            counts: dict[str, int] = {}
            for tok in tokens:
                counts[tok] = counts.get(tok, 0) + 1
            self.tf.append(counts)
            for tok in counts:
                df[tok] = df.get(tok, 0) + 1
        self.idf = {tok: math.log(1 + (self.n_docs - f + 0.5) / (f + 0.5)) for tok, f in df.items()}

    def scores(self, query_tokens: list[str]) -> list[float]:
        out = [0.0] * self.n_docs
        for i in range(self.n_docs):
            length = len(self.docs[i])
            counts = self.tf[i]
            score = 0.0
            for tok in query_tokens:
                freq = counts.get(tok)
                if not freq:
                    continue
                denom = freq + self.k1 * (1 - self.b + self.b * length / (self.avg_len or 1))
                score += self.idf.get(tok, 0.0) * freq * (self.k1 + 1) / denom
            out[i] = score
        return out
