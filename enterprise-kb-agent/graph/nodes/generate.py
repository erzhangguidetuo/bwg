"""生成节点：根据路由与证据来源生成最终回答。

三种证据来源共用一个节点，提示词按 source 切换：
- knowledge：引用资料作答，带 [n] 引用编号
- web：基于联网搜索结果作答，明确告知信息来自互联网
- chitchat：正常对话，无检索环节
"""
from core.llm import get_chat_model
from graph.nodes.grade import format_docs

KB_PROMPT = """你是一名严谨的企业知识库问答助手。

规则：
1. 只依据下面提供的【参考资料】回答问题，禁止使用资料之外的知识。
2. 回答中引用资料的地方，用 [1] [2] 这样的编号标注。
3. 如果资料不足以回答问题，直接回答"知识库中未找到相关信息"，不要编造。

参考资料：
{context}"""

WEB_PROMPT = """你是一名问答助手。以下是通过联网搜索得到的【网络资料】：

{context}

请基于网络资料回答用户问题，并在回答开头注明"（以下信息来自联网搜索）"。
如果网络资料不足以回答，请如实说明。"""

CHAT_PROMPT = "你是一名友好的企业知识库助手，请自然地与用户对话。"


def generate_node(state) -> dict:
    model = get_chat_model(temperature=0.2)
    source = state.get("source", "knowledge")

    if source == "web":
        system = WEB_PROMPT.format(context=state.get("web_results", "（无结果）"))
    elif source == "chitchat":
        system = CHAT_PROMPT
    else:
        system = KB_PROMPT.format(context=format_docs(state.get("documents", [])))

    response = model.invoke([
        {"role": "system", "content": system},
        {"role": "user", "content": state["question"]},
    ])
    return {
        "answer": response.content,
        "messages": [{"role": "assistant", "content": response.content}],
    }
