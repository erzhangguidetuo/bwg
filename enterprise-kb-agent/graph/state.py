"""图的共享状态定义。

messages 使用 reducer（operator.add）：各节点返回的 messages 会**追加**
而非覆盖，这是多轮会话能与 SqliteSaver 检查点配合的关键——历史由
检查点持久化，每轮调用只传增量。
其余字段均为"最后写入者生效"，节点只返回自己负责的部分更新。
"""
import operator
from typing import Annotated, TypedDict


class KBState(TypedDict):
    # 多轮对话历史，追加式
    messages: Annotated[list[dict], operator.add]

    # 本轮输入
    question: str

    # 流转过程中的中间产物
    route: str                    # 路由结果: chitchat | knowledge | web
    rewritten_query: str          # 改写后的检索查询
    documents: list[dict]         # 检索到的片段（混合检索格式）
    grade: dict                   # 自检结果 {"sufficient": bool, "reason": str}
    retry_count: int              # 已重试次数
    web_results: str              # Tavily 降级搜索结果
    source: str                   # 最终回答依据: knowledge | web | chat

    # 输出
    answer: str
