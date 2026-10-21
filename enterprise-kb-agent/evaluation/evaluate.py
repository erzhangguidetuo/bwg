r"""评测脚本：量化 RAG 系统效果，并支持分块参数对比实验。

三个评测维度：
1. 检索命中率 hit@k：期望文档是否出现在 Top-K 检索结果中。
   分别测"纯向量"与"混合检索"，量化阶段二带来的提升。
2. 回答准确率：生成答案是否包含评测集要求的关键词
   （确定性判定，等价于事实核查的宽松下界）。
3. 分块实验：chunk_size 取 300/500/800 重建索引分别测命中率，
   观察分块粒度对检索质量的影响，实验后恢复默认配置。

用法（项目根目录下）：
    uv run -m evaluation.evaluate --retrieval        # 只测检索
    uv run -m evaluation.evaluate --answers          # 只测回答
    uv run -m evaluation.evaluate --chunk-experiment # 分块实验
    uv run -m evaluation.evaluate --all              # 全部
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import settings
from core.llm import get_chat_model, get_embeddings
from evaluation.data_loader import load_qa_dataset
from ingestion.indexer import build_index
from retrieval.hybrid import HybridRetriever
from retrieval.vector_store import VectorStore

# 与 scripts/ask.py 相同的生成提示词，保证评测对象与线上行为一致
from scripts.ask import SYSTEM_PROMPT, format_context

CHUNK_SIZES = [300, 500, 800]


def _norm(text: str) -> str:
    """归一化：去空格、转小写，让关键词匹配对排版不敏感。"""
    return text.replace(" ", "").replace("\n", "").lower()


def eval_retrieval(top_k: int = 4) -> dict:
    """对比纯向量与混合检索的 hit@k 与 hit@1。

    小语料下 hit@4 容易饱和（Top-4 已覆盖大半语料），补测 hit@1
    才有区分度——要求期望文档必须排在第一名。
    """
    items = load_qa_dataset()
    embedder = get_embeddings()
    vector_store = VectorStore()
    hybrid = HybridRetriever()

    stats = {"vec_hit_k": 0, "vec_hit_1": 0, "hyb_hit_k": 0, "hyb_hit_1": 0}
    failures = []
    for item in items:
        expected = item["expected_source"]

        vec = vector_store.search(embedder.embed_query(item["question"]), k=top_k)
        hyb = hybrid.search(item["question"], top_k=top_k)
        vec_sources = {h["metadata"]["source"] for h in vec}
        hyb_sources = {h["metadata"]["source"] for h in hyb}

        stats["vec_hit_k"] += expected in vec_sources
        stats["vec_hit_1"] += bool(vec) and vec[0]["metadata"]["source"] == expected
        stats["hyb_hit_k"] += expected in hyb_sources
        stats["hyb_hit_1"] += bool(hyb) and hyb[0]["metadata"]["source"] == expected

        if expected not in hyb_sources:
            failures.append({"id": item["id"], "question": item["question"]})

    n = len(items)
    return {
        "n": n, "top_k": top_k,
        "vector_hit_rate": stats["vec_hit_k"] / n,
        "vector_hit1_rate": stats["vec_hit_1"] / n,
        "hybrid_hit_rate": stats["hyb_hit_k"] / n,
        "hybrid_hit1_rate": stats["hyb_hit_1"] / n,
        "hybrid_misses": failures,
    }


def eval_answers(top_k: int = 4) -> dict:
    """完整问答链路的准确率：检索 + 带引用生成 + 关键词判定。"""
    items = load_qa_dataset()
    model = get_chat_model(temperature=0.2)
    hybrid = HybridRetriever()

    correct, results = 0, []
    for item in items:
        hits = hybrid.search(item["question"], top_k=top_k)
        prompt = SYSTEM_PROMPT.format(context=format_context(hits))
        response = model.invoke([
            {"role": "system", "content": prompt},
            {"role": "user", "content": item["question"]},
        ])
        answer_norm = _norm(response.content)
        ok = any(_norm(kw) in answer_norm for kw in item["must_contain"])
        correct += ok
        results.append({"id": item["id"], "pass": ok, "answer": response.content[:80]})

    return {"n": len(items), "accuracy": correct / len(items), "results": results}


def eval_chunk_experiment(top_k: int = 4) -> list[dict]:
    """分块粒度实验：不同 chunk_size 下重建索引并测命中率，最后恢复默认。"""
    embedder = get_embeddings()
    report = []
    for size in CHUNK_SIZES:
        print(f"  -- chunk_size={size}: 重建索引中...")
        build_index(settings.DOCS_DIR, embedder, reset=True, chunk_size=size)
        time.sleep(1)
        metrics = eval_retrieval(top_k=top_k)
        print(f"     混合检索 hit@{top_k} = {metrics['hybrid_hit_rate']:.0%}")
        report.append({"chunk_size": size, "hit_rate": metrics["hybrid_hit_rate"]})

    print(f"  -- 恢复默认 chunk_size={settings.CHUNK_SIZE}")
    build_index(settings.DOCS_DIR, embedder, reset=True)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--retrieval", action="store_true")
    parser.add_argument("--answers", action="store_true")
    parser.add_argument("--chunk-experiment", action="store_true")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    if not any([args.retrieval, args.answers, args.chunk_experiment, args.all]):
        args.all = True

    report = {}
    if args.all or args.retrieval:
        print("[1/3] 检索命中率（纯向量 vs 混合）")
        report["retrieval"] = eval_retrieval()
        print(f"  纯向量 hit@4 = {report['retrieval']['vector_hit_rate']:.0%}, "
              f"hit@1 = {report['retrieval']['vector_hit1_rate']:.0%}")
        print(f"  混合检索 hit@4 = {report['retrieval']['hybrid_hit_rate']:.0%}, "
              f"hit@1 = {report['retrieval']['hybrid_hit1_rate']:.0%}")
        for m in report["retrieval"]["hybrid_misses"]:
            print(f"  未命中: #{m['id']} {m['question']}")

    if args.all or args.chunk_experiment:
        print("[2/3] 分块粒度实验")
        report["chunk_experiment"] = eval_chunk_experiment()

    if args.all or args.answers:
        print("[3/3] 回答准确率（含生成，较慢）")
        report["answers"] = eval_answers()
        print(f"  回答准确率 = {report['answers']['accuracy']:.0%}")
        for r in report["answers"]["results"]:
            if not r["pass"]:
                print(f"  未通过: #{r['id']}  答案片段: {r['answer']}")

    out = Path(__file__).parent / "report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已保存: {out}")


if __name__ == "__main__":
    main()
