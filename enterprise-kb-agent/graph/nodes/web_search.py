"""联网降级节点：知识库两轮检索都不足时，用 Tavily 搜索兜底。

Tavily 是为 LLM 设计的搜索 API（返回已提炼的网页摘要而非链接列表），
在厨房助手里你已经用过同一工具，这里直接迁移。
"""
from langchain_tavily import TavilySearch

from core.config import settings

# 工具实例复用，避免重复初始化
_web_search = None


def _get_tool() -> TavilySearch:
    global _web_search
    if _web_search is None:
        _web_search = TavilySearch(
            api_key=settings.TAVILY_API_KEY,
            max_results=4,
            topic="general",
        )
    return _web_search


def format_search_results(raw: dict) -> str:
    """把 Tavily 返回结构拼成纯文本资料（纯函数，可单测）。"""
    results = raw.get("results", []) if isinstance(raw, dict) else []
    parts = []
    for i, item in enumerate(results, 1):
        title = item.get("title", "")
        content = item.get("content", "")
        url = item.get("url", "")
        parts.append(f"[{i}] {title}（{url}）\n{content}")
    return "\n\n".join(parts) if parts else "（联网搜索未返回有效结果）"


def web_search_node(state) -> dict:
    query = state.get("rewritten_query") or state["question"]
    raw = _get_tool().invoke({"query": query})
    return {
        "web_results": format_search_results(raw),
        "source": "web",
    }
