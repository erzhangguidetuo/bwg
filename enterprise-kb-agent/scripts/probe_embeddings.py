"""探测 OpenAI 兼容端点支持哪些嵌入模型。

依次尝试常见模型名，只打印成功/失败状态，不打印密钥。
把成功的模型名写进 .env 的 embedding_model 即可。

用法：
    uv run scripts/probe_embeddings.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import settings
from core.llm import get_embeddings
from langchain_openai import OpenAIEmbeddings

CANDIDATES = [
    "text-embedding-v4",
    "text-embedding-v3",
    "text-embedding-ada-002",
    "text-embedding-3-small",
    "bge-large-zh",
    "bge-m3",
]


def probe():
    print(f"端点: {settings.BASE_URL}")
    print(f"当前配置的 embedding_model: {settings.EMBEDDING_MODEL}\n")
    ok = []
    for name in CANDIDATES:
        try:
            embedder = OpenAIEmbeddings(
                model=name,
                api_key=settings.API_KEY,
                base_url=settings.BASE_URL,
                check_embedding_ctx_length=False,
            )
            dim = len(embedder.embed_query("测试"))
            print(f"  [可用] {name}  (维度 {dim})")
            ok.append((name, dim))
        except Exception as e:
            reason = str(e).splitlines()[0][:80]
            print(f"  [不可用] {name}  ({reason})")
    if ok:
        print(f"\n建议在 .env 中设置: embedding_model={ok[0][0]}")


if __name__ == "__main__":
    probe()
