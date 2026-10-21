"""检索节点：调用阶段二的混合检索器。

使用共享单例检索器：与 FastAPI 服务共用同一个实例，
上传新文档后调用方执行 retriever.refresh() 即可全局生效。
"""
from retrieval.hybrid import get_shared_retriever


def make_retrieve_node():
    def retrieve_node(state) -> dict:
        query = state.get("rewritten_query") or state["question"]
        documents = get_shared_retriever().search(query, top_k=4)
        return {"documents": documents}
    return retrieve_node
