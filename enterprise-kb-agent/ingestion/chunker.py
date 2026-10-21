"""分块：把长文本切成适合检索的小块。

为什么必须分块：
1. 嵌入模型对长文本的表征能力下降，"一段一个主题"检索精度最高；
2. 返回给大模型的上下文有限，块越小能带的候选片段越多。

这里用 RecursiveCharacterTextSplitter：按段落 -> 句子 -> 字符的优先级
递归切分，尽量保持语义完整。chunk_size / overlap 做成可配置参数，
是阶段五"分块策略对比实验"的基础。
"""
from langchain_text_splitters import RecursiveCharacterTextSplitter

from core.config import settings


def split_documents(docs: list[dict], chunk_size: int | None = None,
                    overlap: int | None = None) -> list[dict]:
    chunk_size = chunk_size or settings.CHUNK_SIZE
    overlap = overlap or settings.CHUNK_OVERLAP

    # 参数防御：重叠必须小于块大小，否则 splitter 会抛异常
    overlap = min(overlap, chunk_size - 1)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        # 中文友好：优先按换行和标点切
        separators=["\n\n", "\n", "。", "；", "，", " ", ""],
        length_function=len,
    )

    chunks = []
    for doc in docs:
        pieces = splitter.split_text(doc["text"])
        for idx, piece in enumerate(pieces):
            metadata = dict(doc["metadata"])
            metadata["chunk_index"] = idx
            chunks.append({"text": piece, "metadata": metadata})
    return chunks
