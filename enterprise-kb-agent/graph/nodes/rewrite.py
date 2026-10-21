"""查询改写节点：复用 core.rewrite，首轮直接透传。"""
from core.rewrite import rewrite_query


def rewrite_node(state) -> dict:
    # 首轮提问（历史里只有当前这一条用户消息）无需改写
    history = [m for m in state["messages"][:-1]]
    if not history:
        return {"rewritten_query": state["question"]}
    rewritten = rewrite_query(history, state["question"])
    return {"rewritten_query": rewritten}
