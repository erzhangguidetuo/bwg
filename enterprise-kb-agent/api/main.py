"""FastAPI 服务层：把 LangGraph 问答能力包装成 HTTP 接口。

端点一览：
    POST   /chat                非流式问答，返回答案 + 轨迹 + 引用来源
    POST   /chat/stream         SSE 流式问答，先推送节点执行轨迹，最后推答案
    POST   /upload              上传文档并增量索引（同名文档幂等覆盖）
    GET    /documents           已索引文档列表
    DELETE /documents/{source}  删除指定文档及其全部向量块

设计要点：
1. 图对象在应用启动时构建一次（lifespan），所有请求共享；
2. 检索到的 documents 一并返回，前端才能展示"参考来源"；
3. SSE（Server-Sent Events）实现流程可见性——企业产品里
   "正在检索...正在自检..."的进度条就来自这种节点级事件流。
"""
import json
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.config import settings
from core.llm import get_embeddings
from graph.builder import build_graph_with_sqlite
from ingestion.indexer import index_single_file
from ingestion.loader import _LOADERS
from retrieval.hybrid import get_shared_retriever
from retrieval.vector_store import VectorStore

# 支持上传的扩展名集合（复用 loader 的注册表）
ALLOWED_EXTS = set(_LOADERS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时构建图与共享对象，关闭时随进程释放。"""
    app.state.graph = build_graph_with_sqlite()
    app.state.embedder = get_embeddings()
    yield


app = FastAPI(title="Enterprise KB Agent", version="0.4.0", lifespan=lifespan)

# 允许本机 Streamlit 跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    question: str
    thread_id: str = "web-1"


def run_graph_collect(graph, question: str, thread_id: str) -> dict:
    """跑完整轮问答，收集轨迹与检索结果（/chat 与 /chat/stream 共用）。"""
    trace: list[str] = []
    documents: list[dict] = []
    answer = ""
    route = ""
    source = ""

    for event in graph.stream(
        {
            "messages": [{"role": "user", "content": question}],
            "question": question,
            "retry_count": 0,
        },
        {"configurable": {"thread_id": thread_id}},
        stream_mode="updates",
    ):
        for node_name, update in event.items():
            trace.append(node_name)
            if isinstance(update, dict):
                if "documents" in update and update["documents"]:
                    documents = update["documents"]
                if "route" in update:
                    route = update["route"]
                if "source" in update:
                    source = update["source"]
                if "answer" in update:
                    answer = update["answer"]

    return {"answer": answer, "route": route, "source": source,
            "trace": trace, "documents": documents}


@app.post("/chat")
def chat(req: ChatRequest) -> dict:
    result = run_graph_collect(app.state.graph, req.question, req.thread_id)
    return result


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """SSE 流式接口：逐个推送节点事件，最后推送完整结果。"""

    def event_stream():
        for payload in run_graph_streaming(app.state.graph, req.question, req.thread_id):
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def run_graph_streaming(graph, question: str, thread_id: str):
    """以生成器形式产出事件：每个节点一个 payload，最后一个 payload
    携带完整结果。逻辑与 run_graph_collect 相同，只是边跑边吐。"""
    trace: list[str] = []
    documents: list[dict] = []
    answer = ""
    route = ""
    source = ""

    for event in graph.stream(
        {
            "messages": [{"role": "user", "content": question}],
            "question": question,
            "retry_count": 0,
        },
        {"configurable": {"thread_id": thread_id}},
        stream_mode="updates",
    ):
        for node_name, update in event.items():
            trace.append(node_name)
            if isinstance(update, dict):
                if "documents" in update and update["documents"]:
                    documents = update["documents"]
                if "route" in update:
                    route = update["route"]
                if "source" in update:
                    source = update["source"]
                if "answer" in update:
                    answer = update["answer"]
            yield {"type": "node", "node": node_name, "trace": trace}

    yield {"type": "final", "answer": answer, "route": route, "source": source,
           "trace": trace, "documents": documents}


# ---------------- 文档管理 ----------------

def _list_documents() -> list[dict]:
    conn = sqlite3.connect(str(settings.META_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT source, chunks, updated_at FROM documents ORDER BY source"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@app.get("/documents")
def list_documents() -> list[dict]:
    return _list_documents()


@app.post("/upload")
def upload(file: UploadFile = File(...)) -> dict:
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(400, f"不支持的格式 {ext}，支持: {sorted(ALLOWED_EXTS)}")

    # 只保留文件名本身，防路径穿越；保存到语料目录
    safe_name = Path(file.filename).name
    dest = settings.DOCS_DIR / safe_name
    dest.write_bytes(file.file.read())

    try:
        n_chunks = index_single_file(dest, app.state.embedder)
    except Exception as e:
        dest.unlink(missing_ok=True)  # 索引失败则不留半成品文件
        raise HTTPException(500, f"索引失败: {e}") from e

    # 关键：通知共享检索器重建语料缓存，否则新文档检索不到
    get_shared_retriever().refresh()

    return {"source": safe_name, "chunks": n_chunks}


@app.delete("/documents/{source}")
def delete_document(source: str) -> dict:
    VectorStore().delete_by_source(source)
    conn = sqlite3.connect(str(settings.META_DB))
    conn.execute("DELETE FROM documents WHERE source = ?", (source,))
    conn.commit()
    conn.close()
    doc_file = settings.DOCS_DIR / Path(source).name
    doc_file.unlink(missing_ok=True)
    get_shared_retriever().refresh()
    return {"deleted": source}
