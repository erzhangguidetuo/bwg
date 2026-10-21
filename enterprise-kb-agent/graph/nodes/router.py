"""意图路由节点：判断本轮问题该走哪条分支。

三条分支：
- chitchat：打招呼、闲聊，与知识库无关 -> 直接对话，不检索
- knowledge：公司制度、内部信息 -> 知识库问答主链路
- web：外部实时信息（新闻、天气、股价）-> 直接联网搜索

路由是 Agentic RAG 省钱的第一道闸：大部分闲聊请求被挡在
检索与评分环节之前，token 消耗和延迟都显著下降。
"""
from core.llm import get_chat_model

ROUTER_PROMPT = """你是对话意图分类器。根据对话历史与最新问题，输出且只输出
以下三个词之一（不要任何其他内容）：

chitchat - 打招呼、寒暄、闲聊，或与任何具体事务无关的问题
knowledge - 询问公司内部制度、文档、流程等知识库应能回答的问题
web - 询问需要实时或外部信息的问题（如今天的新闻、天气、股价）

对分类拿不准时，一律输出 knowledge。"""

ROUTE_SET = {"chitchat", "knowledge", "web"}


def parse_route(raw: str) -> str:
    """容错解析路由输出（纯函数，可单测）。"""
    text = raw.strip().lower()
    for route in ROUTE_SET:
        if route in text:
            return route
    return "knowledge"  # 默认走知识库


def router_node(state) -> dict:
    model = get_chat_model(temperature=0)
    messages = [{"role": "system", "content": ROUTER_PROMPT}]
    messages.extend(state["messages"][-6:])
    response = model.invoke(messages)

    # 关键：router 是每轮必然执行的第一个节点，在这里重置所有
    # 瞬时字段。否则检查点会把上一轮的 rewritten_query / documents
    # / grade 等残留值带进本轮，造成"拿旧问题去搜索"的状态污染。
    return {
        "route": parse_route(response.content),
        "rewritten_query": "",
        "documents": [],
        "grade": {},
        "retry_count": 0,
        "web_results": "",
        "source": "knowledge",
    }
