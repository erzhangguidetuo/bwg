"""企业知识库问答：混合检索（向量 + BM25 + RRF）-> 带引用生成。

用法（项目根目录下）：
    uv run scripts/ask.py "公司的年假有几天？"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import settings
from core.llm import get_chat_model
from retrieval.hybrid import HybridRetriever

# 系统提示词：约束"只依据给定材料回答、必须带引用编号、找不到就明说"。
# 这三条约束对应企业 RAG 的核心诉求：可控、可溯源、不幻觉。
SYSTEM_PROMPT = """你是一名严谨的企业知识库问答助手。

规则：
1. 只依据下面提供的【参考资料】回答问题，禁止使用资料之外的知识。
2. 回答中引用资料的地方，用 [1] [2] 这样的编号标注，编号对应资料序号。
3. 如果资料不足以回答问题，直接回答"知识库中未找到相关信息"，不要编造。

参考资料：
{context}
"""


def format_context(hits: list[dict]) -> str:
    """把检索结果拼成带编号的参考资料段落。"""
    parts = []
    for i, hit in enumerate(hits, 1):
        source = hit["metadata"]["source"]
        page = hit["metadata"].get("page")
        loc = f"第{page}页" if page else ""
        parts.append(f"[{i}] （来源: {source} {loc}）\n{hit['text']}")
    return "\n\n".join(parts)


def answer(question: str) -> str:
    # 1. 混合检索：两路并行 + RRF 融合
    retriever = HybridRetriever()
    if retriever.is_empty:
        raise RuntimeError("向量库为空，请先运行: uv run scripts/build_index.py")
    hits = retriever.search(question, top_k=settings.RETRIEVAL_TOP_K)

    # 2. 生成：带引用的受限回答
    model = get_chat_model()
    prompt = SYSTEM_PROMPT.format(context=format_context(hits))
    response = model.invoke(
        [{"role": "system", "content": prompt},
         {"role": "user", "content": question}]
    )

    # 3. 展示：回答 + 来源明细（含通道命中信息）
    print("=" * 60)
    print(response.content)
    print("=" * 60)
    print("引用来源:")
    for i, hit in enumerate(hits, 1):
        meta = hit["metadata"]
        ch = hit["channels"]
        channel_str = "、".join(f"{name} 第{rank}名" for name, rank in ch.items())
        print(f"  [{i}] {meta['source']} (chunk {meta['chunk_index']}, "
              f"RRF {hit['rrf_score']})")
        print(f"      命中通道: {channel_str}")
    return response.content


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('用法: uv run scripts/ask.py "你的问题"')
        sys.exit(1)
    answer(sys.argv[1])
