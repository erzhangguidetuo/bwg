"""全局配置：集中加载 .env，统一管理路径与模型参数。"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 项目根目录（core/config.py 的上一级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 加载根目录下的 .env（API 密钥等敏感信息不入库）
load_dotenv(PROJECT_ROOT / ".env")


def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default)


class Settings:
    """集中配置项，避免各模块散落硬编码。"""

    # ---- 模型配置（OpenAI 兼容接口）----
    API_KEY: str = _get("api_key")
    BASE_URL: str = _get("base_url")
    CHAT_MODEL: str = _get("chat_model", "qwen3.8-flash")
    # 嵌入模型：可用 scripts/probe_embeddings.py 探测服务端支持哪些
    EMBEDDING_MODEL: str = _get("embedding_model", "text-embedding-v4")
    # 联网降级搜索
    TAVILY_API_KEY: str = _get("Tavily_api_key")

    # ---- Agent 行为参数 ----
    MAX_RETRIES: int = 2          # 检索不充分时的最大重试次数
    CHECKPOINT_DB: Path = PROJECT_ROOT / "data" / "chat_memory.sqlite"

    # ---- 路径配置 ----
    DOCS_DIR: Path = PROJECT_ROOT / "data" / "docs"
    CHROMA_DIR: Path = PROJECT_ROOT / "data" / "chroma"
    META_DB: Path = PROJECT_ROOT / "data" / "kb_meta.sqlite"
    COLLECTION_NAME: str = "kb_docs"

    # ---- 分块参数（阶段五调优的重点实验对象）----
    CHUNK_SIZE: int = 500      # 每块目标字符数
    CHUNK_OVERLAP: int = 80    # 相邻块重叠字符数，防止语义被切断
    RETRIEVAL_TOP_K: int = 4   # 检索返回的片段数


settings = Settings()
