r"""LangGraph 编排入口：把节点组装成带循环与分支的状态图。

图结构：

  START -> router --chitchat--> prepare_chat --> generate -> END
                \--web-------> web_search ---------------^
                 \-knowledge-> rewrite -> retrieve -> grade --sufficient--> prepare_kb -> generate
                                                    |
                                        (不足且未超重试上限)
                                                    v
                                                 retry --(回到 retrieve)

  grade --(不足且已超上限)--> web_search

三个编排层面的设计点：
1. 条件边（conditional edges）实现意图路由与自检分支；
2. retry 节点把"缺失信息"拼回查询，回到 retrieve 形成自检循环，
   上限由 settings.MAX_RETRIES 控制，防止无限循环；
3. SqliteSaver 检查点持久化整个 state，多轮会话只需要同一个
   thread_id，历史消息自动续接（与厨房项目的记忆用法同源）。
"""
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from core.config import settings
from graph.nodes.generate import generate_node
from graph.nodes.grade import grade_node
from graph.nodes.retrieval import make_retrieve_node
from graph.nodes.rewrite import rewrite_node
from graph.nodes.router import router_node
from graph.nodes.web_search import web_search_node
from graph.state import KBState


# ---------- 小型准备节点：给 generate 标注证据来源 ----------

def prepare_chat_node(state) -> dict:
    return {"source": "chitchat"}


def prepare_kb_node(state) -> dict:
    return {"source": "knowledge"}


def retry_node(state) -> dict:
    """重试节点：把自检发现的缺失信息拼回查询，驱动下一轮检索。"""
    missing = state.get("grade", {}).get("missing") or ""
    new_query = f"{state['rewritten_query']} {missing}".strip()
    return {
        "rewritten_query": new_query,
        "retry_count": state.get("retry_count", 0) + 1,
    }


# ---------- 条件边函数 ----------

def route_after_router(state) -> str:
    return state.get("route", "knowledge")


def route_after_grade(state) -> str:
    grade = state.get("grade", {})
    if grade.get("sufficient"):
        return "sufficient"
    if state.get("retry_count", 0) < settings.MAX_RETRIES:
        return "retry"
    return "fallback_web"


# ---------- 组装 ----------

def build_graph(checkpointer: SqliteSaver | None = None):
    graph = StateGraph(KBState)
    graph.add_node("router", router_node)
    graph.add_node("rewrite", rewrite_node)
    graph.add_node("retrieve", make_retrieve_node())
    graph.add_node("grade", grade_node)
    graph.add_node("retry", retry_node)
    graph.add_node("prepare_chat", prepare_chat_node)
    graph.add_node("prepare_kb", prepare_kb_node)
    graph.add_node("web_search", web_search_node)
    graph.add_node("generate", generate_node)

    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router", route_after_router,
        {"chitchat": "prepare_chat", "knowledge": "rewrite", "web": "web_search"},
    )
    graph.add_edge("prepare_chat", "generate")
    graph.add_edge("rewrite", "retrieve")
    graph.add_edge("retrieve", "grade")
    graph.add_conditional_edges(
        "grade", route_after_grade,
        {"sufficient": "prepare_kb", "retry": "retry", "fallback_web": "web_search"},
    )
    graph.add_edge("retry", "retrieve")
    graph.add_edge("prepare_kb", "generate")
    graph.add_edge("web_search", "generate")
    graph.add_edge("generate", END)

    return graph.compile(checkpointer=checkpointer)


def build_graph_with_sqlite():
    """带 SqliteSaver 会话记忆的入口，供 CLI / API 使用。"""
    conn = sqlite3.connect(str(settings.CHECKPOINT_DB), check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    return build_graph(checkpointer=checkpointer)
