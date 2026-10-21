"""模型初始化：聊天模型与嵌入模型，全项目唯一的模型出口。"""
from langchain.chat_models import init_chat_model
from langchain_openai import OpenAIEmbeddings

from core.config import settings


def get_chat_model(temperature: float = 0.2):
    """聊天模型：与厨房项目相同写法，OpenAI 兼容接口接 Qwen。"""
    return init_chat_model(
        model=settings.CHAT_MODEL,
        model_provider="openai",
        api_key=settings.API_KEY,
        base_url=settings.BASE_URL,
        temperature=temperature,
    )


def get_embeddings() -> OpenAIEmbeddings:
    """嵌入模型。

    check_embedding_ctx_length=False 是对接非 OpenAI 官方端点的关键参数：
    关闭后跳过本地 tiktoken 计数，直接把整段文本发给服务端，避免
    兼容接口因 tokenizer 不一致而报错。
    """
    return OpenAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        api_key=settings.API_KEY,
        base_url=settings.BASE_URL,
        check_embedding_ctx_length=False,
    )
