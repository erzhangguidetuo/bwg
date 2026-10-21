#!/usr/bin/env python
"""上下文过滤 / 预算策略离线评测：none · embeddings · keyword · keyword+budget。

要回答的问题
------------
``gpt_researcher.context.ContextCompressor`` 目前用两把旋钮控制上下文大小：

- ``COMPRESSION_THRESHOLD``（默认 8000 **字符**）：低于阈值直接跳过过滤，按原顺序取前 ``max_results`` 条；
- ``max_results``：最终截断到多少 **条**。

字符数和条数都**不是 token 数**。同样 10 条分块，在不同长度的页面上可能差 3 倍 token。
多智能体调研里每个 Executor 各自拼一份上下文，很容易在不该爆的地方撞上模型窗口。

所以这里要量化的是：

1. 每种策略把多少 token 送进了模型，相对"全量拼接"省了多少；
2. 省下来的 token 里，**标注为必要证据的分块**有没有被一起丢掉；
3. 再加一层 token 预算（``gpt_researcher/context/budget.py``）之后，
   压缩率还能提升多少，证据召回率会掉多少 —— 也就是"要质量还是要成本"的显式权衡。

成本模型
--------
token 数按 ``gpt_researcher.context.budget.estimate_tokens`` 估算
（有 tiktoken 走精确计数，没有则按中英文字符加权估算）。
报告里同时给出 token 数和相对全量拼接的压缩率 —— 压缩率才是可迁移的结论，
绝对 token 数随语料变化。

用法
----
::

    # 离线冒烟（无模型依赖，纯标准库）
    python evals/context_budget_eval/run_bench.py --embedder hashing

    # 真实评测（pip install sentence-transformers）
    python evals/context_budget_eval/run_bench.py --embedder st \
        --out evals/context_budget_eval/results/context_filter.md
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from _common import BM25, rank_desc, tokenize  # noqa: E402

REPO_ROOT = HERE.parents[1]
BUDGET_PATH = REPO_ROOT / "gpt_researcher" / "context" / "budget.py"


# --------------------------------------------------------------- 预算模块加载
def _load_budget_module():
    """按文件路径加载，绕开 gpt_researcher 包的 __init__（它会拉起 langchain 等重依赖）。"""
    if BUDGET_PATH.exists():
        spec = importlib.util.spec_from_file_location("gpr_context_budget", BUDGET_PATH)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    from gpt_researcher.context import budget as module  # type: ignore

    return module


budget_mod = _load_budget_module()

# 与上游 gpt_researcher/context/compression.py 保持一致的默认参数，
# 评测结果才能直接对应当前线上行为。
SIMILARITY_THRESHOLD = float(os.environ.get("SIMILARITY_THRESHOLD", "0.35"))
KEYWORD_RELATIVE_THRESHOLD = float(os.environ.get("KEYWORD_RELATIVE_THRESHOLD", "0.5"))
KEYWORD_MAX_RESULTS = int(os.environ.get("KEYWORD_MAX_RESULTS", "25"))


# ------------------------------------------------------------------ 数据加载
def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{lineno} JSON 解析失败 -> {exc}") from exc
    return rows


# ------------------------------------------------------------------ Embedding
def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class HashingEmbedder:
    """确定性字符 n-gram 哈希向量——无模型环境下的降级实现，无语义能力。"""

    name = "hashing-degraded"
    degraded = True

    def __init__(self, dim: int = 1024):
        self.dim = dim

    def encode(self, texts: list[str]) -> list[list[float]]:
        import hashlib

        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self.dim
            tokens = tokenize(text)
            grams = tokens + ["".join(tokens[i : i + 2]) for i in range(len(tokens) - 1)]
            for gram in grams or [""]:
                digest = hashlib.md5(gram.encode("utf-8")).digest()
                vec[int.from_bytes(digest[:4], "big") % self.dim] += 1.0 if digest[4] % 2 == 0 else -1.0
            out.append(_l2_normalize(vec))
        return out


class SentenceTransformerEmbedder:
    degraded = False

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        from sentence_transformers import SentenceTransformer  # type: ignore

        self.model = SentenceTransformer(model_name)
        self.name = f"sentence-transformers:{model_name}"

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [
            list(map(float, v))
            for v in self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        ]


def build_embedder(choice: str):
    if choice == "hashing":
        return HashingEmbedder()
    if choice == "st":
        return SentenceTransformerEmbedder()
    try:
        return SentenceTransformerEmbedder()
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] sentence-transformers 不可用（{exc}），退化为哈希向量，结果仅供流程验证", file=sys.stderr)
        return HashingEmbedder()


# ------------------------------------------------------------------ 各策略实现
def strategy_none(query: str, docs: list[dict], ctx) -> list[int]:
    """不过滤：所有分块按原顺序全量拼接（对应上游快路径"跳过压缩直接返回"）。"""
    return list(range(len(docs)))


def strategy_keyword(query: str, docs: list[dict], ctx) -> list[int]:
    """BM25 相对阈值过滤。

    上游当前版本已移除关键词过滤路径（只剩 EmbeddingsFilter）。
    这里把它作为**零 embedding 成本的对照组**保留：不需要调用任何 embedding 接口，
    在中文短查询上往往比纯向量更稳。
    """
    scores = ctx["bm25"].scores(tokenize(query))
    ranked = rank_desc(scores)
    best = scores[ranked[0]] if ranked and scores[ranked[0]] > 0 else 0.0
    if best <= 0:
        return ranked[:1]  # 一个词都没匹配上时至少留一条，避免空上下文

    kept = [i for i in ranked if scores[i] >= best * KEYWORD_RELATIVE_THRESHOLD]
    return kept[:KEYWORD_MAX_RESULTS]


def strategy_embeddings(query: str, docs: list[dict], ctx) -> list[int]:
    """余弦相似度阈值过滤——对应上游 ContextCompressor 的 EmbeddingsFilter。"""
    qvec = ctx["embedder"].encode([query])[0]
    scores = [sum(a * b for a, b in zip(qvec, dvec)) for dvec in ctx["doc_vectors"]]
    ranked = rank_desc(scores)
    kept = [i for i in ranked if scores[i] >= SIMILARITY_THRESHOLD]
    return kept or ranked[:1]


def strategy_keyword_budget(query: str, docs: list[dict], ctx) -> list[int]:
    """本次新增：keyword 过滤后再套一层 token 预算。

    先用关键词策略选出候选，再按 ``ContextBudget`` 的 token 上限装填。
    顺序即优先级（BM25 已按相关性排序），超预算的按 overflow 策略处理。
    """
    ordered = strategy_keyword(query, docs, ctx)
    texts = [docs[i]["text"] for i in ordered]
    kept_texts, _report = budget_mod.ContextBudget.from_chunks(
        texts, ctx["budget"], mode="keyword+budget", overflow=ctx["overflow"]
    )
    # 按"文本被采纳的条数"回推索引：from_chunks 保序且不重复，取前 len(kept_texts) 个即可。
    return ordered[: len(kept_texts)]


STRATEGIES = {
    "none": ("不过滤（全量拼接）", strategy_none),
    "keyword": ("BM25 相对阈值过滤", strategy_keyword),
    "embeddings": ("Embedding 余弦阈值过滤", strategy_embeddings),
    "keyword_budget": ("BM25 过滤 + token 预算", strategy_keyword_budget),
}


# ---------------------------------------------------------------------- 主流程
def format_table(rows: list[dict], title: str) -> str:
    if not rows:
        return f"### {title}\n\n（无数据）\n"
    headers = list(rows[0].keys())
    lines = [f"### {title}", "", "| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        cells = [f"{row[h]:.4f}" if isinstance(row[h], float) else str(row[h]) for h in headers]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def run(args) -> int:
    docs = load_jsonl(Path(args.docs))
    queries = load_jsonl(Path(args.queries))
    if not docs or not queries:
        raise SystemExit("语料或查询集为空")

    doc_ids = [d["doc_id"] for d in docs]
    doc_index = {doc_id: i for i, doc_id in enumerate(doc_ids)}
    unknown = sorted({g for q in queries for g in q["gold_chunk_ids"] if g not in doc_index})
    if unknown:
        raise SystemExit(f"评测集里的 gold_chunk_id 不在语料中，例如：{unknown[:5]}")

    embedder = build_embedder(args.embedder)
    ctx = {
        "bm25": BM25([tokenize(d["text"]) for d in docs]),
        "embedder": embedder,
        "doc_vectors": embedder.encode([d["text"] for d in docs]),
        "budget": args.budget,
        "overflow": args.overflow,
    }

    names = [s.strip() for s in args.strategies.split(",") if s.strip()]
    for name in names:
        if name not in STRATEGIES:
            raise SystemExit(f"未知策略 {name!r}，可选：{', '.join(STRATEGIES)}")

    baseline_tokens = sum(budget_mod.estimate_tokens(d["text"]) for d in docs)
    summary: list[dict] = []
    per_query: list[dict] = []

    print(f"候选分块 {len(docs)} 条 / 查询 {len(queries)} 条 / Embedding: {embedder.name}")
    print(f"全量拼接基线：{baseline_tokens} tokens（估算）\n")

    for name in names:
        label, fn = STRATEGIES[name]
        totals = {"tokens": 0, "kept": 0, "gold_kept": 0, "gold_total": 0}
        for item in queries:
            kept_idx = fn(item["query"], docs, ctx)
            kept_tokens = sum(budget_mod.estimate_tokens(docs[i]["text"]) for i in kept_idx)
            kept_gold = len(set(doc_ids[i] for i in kept_idx) & set(item["gold_chunk_ids"]))

            totals["tokens"] += kept_tokens
            totals["kept"] += len(kept_idx)
            totals["gold_kept"] += kept_gold
            totals["gold_total"] += len(set(item["gold_chunk_ids"]))

            if args.per_query:
                per_query.append(
                    {
                        "strategy": name,
                        "query": item["query"][:24],
                        "kept": len(kept_idx),
                        "tokens": kept_tokens,
                        "evidence_recall": round(kept_gold / len(set(item["gold_chunk_ids"])), 4),
                    }
                )

        n = len(queries)
        avg_tokens = totals["tokens"] / n
        summary.append(
            {
                "strategy": name,
                "说明": label,
                "平均上下文 tokens": round(avg_tokens, 1),
                "相对全量压缩率": round(1 - avg_tokens / (baseline_tokens or 1), 4),
                "平均保留块数": round(totals["kept"] / n, 2),
                "证据召回率": round(totals["gold_kept"] / max(totals["gold_total"], 1), 4),
            }
        )

    header = (
        f"Embedding: `{embedder.name}`"
        + ("（**降级，结果仅用于流程验证**）" if getattr(embedder, "degraded", False) else "")
        + f"\n\n候选分块 {len(docs)} 条 · 查询 {len(queries)} 条 · "
        f"全量基线 {baseline_tokens} tokens · 预算上限 {args.budget} tokens（overflow={args.overflow}）\n\n"
        f"参数：`SIMILARITY_THRESHOLD={SIMILARITY_THRESHOLD}`、"
        f"`KEYWORD_RELATIVE_THRESHOLD={KEYWORD_RELATIVE_THRESHOLD}`、`KEYWORD_MAX_RESULTS={KEYWORD_MAX_RESULTS}`"
    )
    report = f"# 上下文过滤 / 预算策略离线评测\n\n{header}\n\n"
    report += format_table(summary, "策略对比（按查询取平均）")
    if per_query:
        report += "\n" + format_table(per_query, "逐条 query 明细")

    print(report)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"[ok] 报告已写入 {out}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="上下文过滤 / 预算策略离线评测")
    p.add_argument("--docs", default=str(HERE / "data" / "sample_docs.jsonl"), help="候选分块 jsonl")
    p.add_argument("--queries", default=str(HERE / "data" / "sample_queries.jsonl"), help="查询 jsonl")
    p.add_argument("--budget", type=int, default=150, help="token 预算上限（默认 150）")
    p.add_argument("--overflow", default="drop", choices=["drop", "truncate", "keep"],
                   help="超预算分块的处理策略（默认 drop）")
    p.add_argument("--strategies", default="none,keyword,embeddings,keyword_budget")
    p.add_argument("--embedder", default="auto", choices=["auto", "st", "hashing"])
    p.add_argument("--per-query", action="store_true", help="输出逐条 query 明细")
    p.add_argument("--out", default="", help="Markdown 报告输出路径")
    return p.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
