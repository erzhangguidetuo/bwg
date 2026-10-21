"""查询改写：把多轮对话中的指代性追问改写为独立完整的检索 query。

为什么需要改写：
用户在对话中经常说"那病假呢？"、"第二种方案呢？"——这类 query
单独拿去检索几乎必然失败，因为指代信息（"那"、"它"）只存在于
对话历史里。改写节点把历史与追问合成一句自包含的检索语句，
是 RAG 多轮场景的标配前置步骤。

阶段三会把本函数接入 LangGraph 的 rewrite 节点。
"""
from core.llm import get_chat_model

REWRITE_PROMPT = """你是一个检索查询改写器。根据对话历史，把用户的最新问题
改写成一句"不依赖上下文也能看懂"的独立检索查询。

要求：
1. 消解所有指代（他/它/这个/那个/第二种），替换为具体对象；
2. 补全省略的主语和谓语；
3. 只输出改写后的查询本身，不要任何解释、引号或前缀；
4. 如果最新问题本身就是完整的独立查询，原样输出。
"""


def rewrite_query(history: list[dict], question: str) -> str:
    """history 为 [{"role", "content"}] 形式的对话历史（可含图片轮需先转文字）。"""
    model = get_chat_model(temperature=0)
    messages = [{"role": "system", "content": REWRITE_PROMPT}]
    messages.extend(history[-6:])  # 只带最近几轮，控制 token 与噪声
    messages.append({"role": "user",
                     "content": f"对话历史如上。请改写这个最新问题：{question}"})
    response = model.invoke(messages)
    return response.content.strip()
