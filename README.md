# bwg

本仓库收录两个 AI Agent 方向的工程实践项目：

| 目录 | 方向 | 性质 |
|---|---|---|
| [`gpt-researcher/`](./gpt-researcher) | 多智能体深度研究（Deep Research）Agent | 基于开源二次开发（[assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher)，Apache-2.0） |
| [`enterprise-kb-agent/`](./enterprise-kb-agent) | 企业知识库智能问答 Agent（Agentic RAG） | **从 0 到 1 自研** |

---

## 1. gpt-researcher — 上下文预算与过滤策略评测

**我做了什么（详见 [`gpt-researcher/MY_CHANGES.md`](./gpt-researcher/MY_CHANGES.md)）**

- 新增 `gpt_researcher/context/budget.py`：token 估算 + 按优先级装填的上下文预算模块，
  支持 `drop` / `truncate` / `keep` 三种溢出策略，仅用标准库（`tiktoken` 可选）。
- 改造 `gpt_researcher/context/compression.py`：`ContextCompressor` 的两条返回路径
  都接入预算层，由环境变量 `CONTEXT_TOKEN_BUDGET` 控制，**默认 0 表示完全不影响上游原行为**。
- 新增 `evals/context_budget_eval/`：离线评测台，同时测量 **token 消耗 / 压缩率 / 证据召回率**。
- 新增 `MY_CHANGES.md`，按 Apache-2.0 第 4(b) 条声明修改内容。

**实测结论**（`--embedder hashing`，本地占位向量，可复现）

| 场景 | 平均 tokens | 压缩率 | 证据召回率 |
|---|---|---|---|
| 预算 4000（宽松），`keyword_budget` | 229.2 | 89.53% | 100% |
| 预算 150，`drop` | 103.4 | 95.28% | 84.62% |
| 预算 150，`truncate` | 146.1 | 93.33% | **92.31%** |

关键发现：**预算宽松时预算层零副作用**；预算紧张时 `truncate` 比 `drop` 多花约 28% token，
换回 7.7 个百分点的证据召回——把"质量与成本的取舍"从一个隐含行为变成了显式参数。

复现：

```bash
cd gpt-researcher
python evals/context_budget_eval/run_bench.py --embedder hashing --budget 150 --overflow truncate
```

---

## 2. enterprise-kb-agent — 企业知识库智能问答 Agent（自研）

从 0 到 1 独立实现的 Agentic RAG 问答系统，覆盖
**文档摄取 → 混合检索 → Agent 编排 → 引用溯源 → 效果评测** 完整链路，
不基于任何开源 RAG 框架二次开发。

**架构与核心技术**

- **混合检索**：Chroma 向量检索 + BM25 关键词检索（jieba 分词）双路并行，
  RRF 倒数排名融合结果；自带通道命中信息，可观测每路贡献。
- **Agent 编排**（LangGraph StateGraph）：意图路由（闲聊 / 知识库 / 联网三分支）
  → 查询改写（多轮指代消解）→ 混合检索 → 生成自检（证据不足时改写重试，上限 2 次）
  → 降级 Tavily 联网搜索，形成可控的循环与分支结构。
- **引用溯源**：回答逐句标注来源文档与分块编号，检索片段随 API 一并返回。
- **工程化**：FastAPI 提供 `/chat`（SSE 节点级流式）、`/upload`（增量索引）、
  `/documents`（文档管理）等接口；Streamlit 交付 Web 界面（执行轨迹、参考来源、文档管理）；
  SqliteSaver 检查点实现多轮会话记忆。
- **缓存一致性**：设计共享检索器单例 + 显式 `refresh()` 机制，
  解决「服务内存缓存 vs 磁盘索引」的一致性问题，上传文档即时可检索。

**实测结果**（自建 20 条 QA 评测集，评测脚本随仓库提供，见 `evaluation/`）

| 指标 | 纯向量 | 混合检索 |
|---|---|---|
| 检索 hit@4 | 100% | 100% |
| **检索 hit@1** | 95% | **100%** |
| 回答准确率（关键词判定） | — | **100%（20/20）** |

评测方法与边界（指标饱和、关键词判定的局限性、评测集自身的修正过程）
详见 [`enterprise-kb-agent/evaluation/report.md`](./enterprise-kb-agent/evaluation/report.md)。

快速开始：

```bash
cd enterprise-kb-agent
uv sync
uv run scripts/probe_embeddings.py   # 探测嵌入模型
uv run scripts/build_index.py        # 构建索引
uv run uvicorn api.main:app --port 8000 &   # API
uv run streamlit run app.py                  # Web 界面
```

---

## 许可证与来源声明

- `gpt-researcher/` 保留了上游的 `LICENSE`（Apache License 2.0），
  并附带 `MY_CHANGES.md` 说明相对上游的修改；原始项目著作权归其作者所有。
- `enterprise-kb-agent/` 为本仓库作者独立编写，无上游代码。
