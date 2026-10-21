"""自检节点：判断检索结果是否足以回答问题。

这是 Agentic RAG 区别于"一检索就生成"的关键节点：生成之前先让
模型审视证据，不足时给出改写建议与缺失点，驱动检索循环重试；
两次重试仍不足则降级联网搜索。这一步能显著压制幻觉——宁可
说"没找到"，不编造。

输出解析为纯函数 parse_grade，方便单测；模型输出异常时按
"不充分"处理（fail-safe：走重试/降级而不是硬答）。
"""
import json

from core.llm import get_chat_model

GRADE_PROMPT = """你是检索结果审查员。判断下面的参考资料是否足以回答用户问题。

参考资料：
{context}

用户问题：{question}

如果资料足以回答，输出 JSON：{{"sufficient": true, "missing": null}}
如果不足以回答，输出 JSON：{{"sufficient": false, "missing": "缺失的信息是什么、以及建议换个什么关键词再检索"}}
只输出 JSON，不要其他内容。"""


def parse_grade(raw: str) -> dict:
    """容错解析自检输出（纯函数，可单测）。"""
    text = raw.strip()
    # 剥掉可能的 markdown 代码块包裹
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
        return {
            "sufficient": bool(data.get("sufficient")),
            "missing": data.get("missing"),
        }
    except (json.JSONDecodeError, AttributeError):
        return {"sufficient": False, "missing": "自检输出解析失败"}


def format_docs(documents: list[dict]) -> str:
    return "\n\n".join(f"[{i}] {d['text']}" for i, d in enumerate(documents, 1))


def grade_node(state) -> dict:
    documents = state["documents"]
    if not documents:
        return {"grade": {"sufficient": False, "missing": "未检索到任何资料"}}

    model = get_chat_model(temperature=0)
    prompt = GRADE_PROMPT.format(
        context=format_docs(documents),
        question=state.get("rewritten_query") or state["question"],
    )
    response = model.invoke([{"role": "user", "content": prompt}])
    return {"grade": parse_grade(response.content)}
