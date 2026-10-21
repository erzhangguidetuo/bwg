"""Streamlit Web 界面：对话 + 流程可视化 + 文档管理。

启动方式（先启动 API，再另开终端）：
    uv run uvicorn api.main:app --port 8000
    uv run streamlit run app.py

界面结构：
- 侧边栏：会话线程切换、API 地址、文档管理（上传 / 列表 / 删除）
- 主区：聊天窗口，每轮回答上方显示执行轨迹（router -> retrieve -> ...），
  回答下方可展开"参考来源"查看命中的知识库片段
"""
import json

import requests
import streamlit as st

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="企业知识库助手", page_icon="📚", layout="wide")

# ---------------- 侧边栏：会话与文档管理 ----------------

with st.sidebar:
    st.title("设置")

    thread_id = st.text_input("会话线程 ID", value="web-1",
                              help="同一 ID 的多轮对话共享记忆")
    api_base = st.text_input("API 地址", value=API_BASE)

    st.divider()
    st.subheader("知识库文档")

    try:
        docs = requests.get(f"{api_base}/documents", timeout=10).json()
        for doc in docs:
            col1, col2 = st.columns([4, 1])
            col1.write(f"📄 {doc['source']}（{doc['chunks']} 块）")
            if col2.button("删", key=f"del-{doc['source']}"):
                requests.delete(f"{api_base}/documents/{doc['source']}", timeout=30)
                st.rerun()
        if not docs:
            st.caption("暂无文档")
    except requests.ConnectionError:
        st.error("无法连接 API，请先启动: uvicorn api.main:app --port 8000")

    st.divider()
    uploaded = st.file_uploader(
        "上传文档（PDF / DOCX / MD / TXT）", type=["pdf", "docx", "md", "txt"]
    )
    if uploaded is not None and st.button("上传并索引", type="primary"):
        with st.spinner("解析与索引中..."):
            resp = requests.post(
                f"{api_base}/upload",
                files={"file": (uploaded.name, uploaded.getvalue())},
                timeout=300,
            )
        if resp.ok:
            data = resp.json()
            st.success(f"{data['source']} 已索引（{data['chunks']} 块）")
            st.rerun()
        else:
            st.error(resp.json().get("detail", "上传失败"))

# ---------------- 主区：对话 ----------------

st.title("📚 企业知识库智能助手")
st.caption("Agentic RAG：意图路由 · 混合检索 · 生成自检 · 联网降级")

if "messages" not in st.session_state:
    st.session_state.messages = []

# 回放历史消息
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("trace"):
            st.caption("流程: " + " → ".join(msg["trace"]))
        if msg.get("documents"):
            with st.expander("参考来源"):
                for i, doc in enumerate(msg["documents"], 1):
                    meta = doc["metadata"]
                    st.markdown(
                        f"**[{i}] {meta['source']}**（chunk {meta['chunk_index']}）\n\n"
                        f"> {doc['text'][:200]}..."
                    )

# 输入新问题
if question := st.chat_input("输入你的问题..."):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        status = st.status("思考中...", expanded=True)
        node_log = []
        result = {}

        try:
            # SSE 流式接收节点事件，实时展示执行轨迹
            resp = requests.post(
                f"{api_base}/chat/stream",
                json={"question": question, "thread_id": thread_id},
                stream=True,
                timeout=300,
            )
            for line in resp.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data: "):
                    continue
                payload = line[len("data: "):]
                if payload == "[DONE]":
                    break
                event = json.loads(payload)
                if event["type"] == "node":
                    if event["node"] not in node_log:
                        node_log.append(event["node"])
                        status.update(label=" → ".join(node_log))
                elif event["type"] == "final":
                    result = event
            status.update(label=" → ".join(node_log), state="complete",
                          expanded=False)
        except requests.ConnectionError:
            status.update(label="API 未启动", state="error")
            result = {"answer": "无法连接 API 服务，请先启动 FastAPI。"}

        answer = result.get("answer", "（无回答）")
        st.markdown(answer)
        if node_log:
            st.caption("流程: " + " → ".join(node_log))
        if result.get("documents"):
            with st.expander("参考来源"):
                for i, doc in enumerate(result["documents"], 1):
                    meta = doc["metadata"]
                    st.markdown(
                        f"**[{i}] {meta['source']}**（chunk {meta['chunk_index']}）\n\n"
                        f"> {doc['text'][:200]}..."
                    )

    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "trace": node_log,
        "documents": result.get("documents", []),
    })
