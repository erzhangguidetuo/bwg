# 企业知识库智能助手（Enterprise KB Agent）

基于 Agentic RAG 全链路的企业文档智能问答系统。从 0 到 1 实践
文档摄取、混合检索、LangGraph 编排、引用溯源与效果评估。

## 快速开始

```bash
# 1. 安装依赖（自动创建虚拟环境）
uv sync

# 2. 探测嵌入模型可用性，把可用模型写入 .env
uv run scripts/probe_embeddings.py

# 3. 构建知识库索引（解析 data/docs 下全部文档）
uv run scripts/build_index.py

# 4. 启动 API 与 Web 界面（两个终端分别执行）
uv run uvicorn api.main:app --port 8000   # API 服务
uv run streamlit run app.py               # Web 界面 http://localhost:8501

# 也可以用命令行对话（多轮，含会话记忆）
uv run scripts/ask_agent.py
```

## 项目结构

```
core/        配置与模型初始化
ingestion/   文档解析、分块、索引构建
retrieval/   向量库封装（Chroma）
graph/       LangGraph 编排（阶段三实现）
api/         FastAPI 服务（阶段四实现）
evaluation/  评测集与指标（阶段五实现）
data/docs/   企业文档语料
```

## 路线图

- [x] 阶段一：最小 RAG（解析 -> 分块 -> Chroma -> 带引用问答）
- [x] 阶段二：混合检索（BM25 + RRF 融合）与查询改写
- [x] 阶段三：LangGraph 编排（意图路由 / 生成自检 / 联网降级）
- [x] 阶段四：工程化（FastAPI + Streamlit + 会话记忆）
- [x] 阶段五：评测与调优（自建 QA 集、分块参数实验）

## 评测结果（evaluation/report.md）

| 指标 | 结果 |
|---|---|
| 混合检索 hit@1 | **100%**（纯向量 95%） |
| 混合检索 hit@4 | 100% |
| 回答准确率 | **100%**（20/20，关键词判定） |

复跑评测：`uv run -m evaluation.evaluate --all`
