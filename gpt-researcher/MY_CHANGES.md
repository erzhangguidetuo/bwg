# MY_CHANGES —— 本仓库相对上游的改动说明

> 本仓库是 **GPT Researcher** 的 fork，上游地址：
> <https://github.com/assafelovic/gpt-researcher>
>
> 按 Apache-2.0 第 4(b) 条要求，本文件声明相对上游所做的修改。
> 上游代码的著作权归 Assaf Elovic 及贡献者所有，`LICENSE` 原样保留、未做改动。

- **Fork 维护者**：【你的名字 / GitHub ID】
- **Fork 基点**：`master` @ `5cdad9c`（2026-06-23，共 2956 个提交）
- **改动范围**：新增一个 token 预算模块 + 默认关闭的接入点 + 一套离线评测台
- **行为兼容性**：默认配置下与上游**逐字节等价**——新逻辑只有在显式设置环境变量后才生效

---

## 1. 新增模块：`gpt_researcher/context/budget.py`

把「能塞多少 evidence 进 prompt」从隐式变成显式。

**动机**：`ContextCompressor` 解决了「选哪些分块」，但没解决「选完之后还剩多少预算」。
上游控制上下文的两把旋钮都不是 token 量：

- `COMPRESSION_THRESHOLD`（默认 8000 **字符**）：低于阈值直接跳过过滤，按原顺序取前 `max_results` 条；
- `max_results`（默认 10 **条**）。

多智能体模式下每个 Executor 各自拼一份上下文，分块一多就会撞上模型上下文上限；
而同样 10 条分块在不同长度的页面上可能差 3 倍 token，靠条数控不住成本。

提供的能力：

| 接口 | 作用 |
|---|---|
| `estimate_tokens(text)` | tiktoken 精确计数；不可用时按中英文字符加权估算（CJK 字数 + 英文词数） |
| `ContextBudget(limit, overflow=...)` | 按优先级装填分块，超预算即按策略处理；`overflow` 可选 `drop` / `truncate` / `keep` |
| `ContextBudget.from_chunks(...)` | 一次性装填，返回 `(保留分块, BudgetReport)` |
| `truncate_to_tokens(text, limit)` | 单个超长分块的兜底截断 |
| `BudgetReport` | 记录保留/丢弃条数与 token、利用率，可直接写日志 |

**约束**：只用标准库，tiktoken 是**可选**依赖——没装不能 ImportError。

## 2. 修改：`gpt_researcher/context/compression.py`（唯一的逻辑接入点）

给 `ContextCompressor` 加了一个**可选**的 token 预算阶段，在两个返回路径上都生效：

- 快路径（`total_chars < COMPRESSION_THRESHOLD`）返回前过滤一次；
- 常规路径（splitter + `EmbeddingsFilter`）拿到 `relevant_docs` 后过滤一次。

新增两个环境变量，**默认都是关闭 / 与上游一致**：

| 变量 | 默认 | 说明 |
|---|---|---|
| `CONTEXT_TOKEN_BUDGET` | `0`（关闭） | 单次上下文的 token 上限；`0` 表示完全不介入 |
| `CONTEXT_TOKEN_OVERFLOW` | `drop` | 超预算分块的处理策略：`drop` / `truncate` / `keep` |

实现细节：

- 保序装填，传入顺序即优先级（`ContextCompressor` 的输出天然已按相关性排序）；
- 只有在真的丢弃了分块时才打日志（`logger.info`），不污染正常路径的输出；
- `token_budget <= 0` 时 `_apply_token_budget` 直接原样返回，不产生任何额外计算。

`.env.example` 里补了这两个变量的注释说明。

## 3. 修改：`gpt_researcher/context/__init__.py`

在包导出里加上 `ContextBudget` / `estimate_tokens` / `truncate_to_tokens`，
方便 `from gpt_researcher.context import ContextBudget` 直接使用。纯追加，未改动原有导出。

## 4. 修改：`evals/README.md`

加了一节 `Context Budget Evaluation`，把新评测台挂进上游已有的 evals 索引。

## 5. 新增：离线评测台 `evals/context_budget_eval/`

沿用上游 `evals/` 下既有的「一个评测一个子目录」约定，与 `hallucination_eval`、
`simple_evals` 并列。

| 文件 | 作用 |
|---|---|
| `run_bench.py` | 对比 `none` / `embeddings` / `keyword` / `keyword_budget` 的 token 消耗、压缩率与**证据召回率** |
| `_common.py` | 分词 + BM25（纯标准库，与主包解耦） |
| `data/sample_docs.jsonl` | 30 条候选分块（含干扰项） |
| `data/sample_queries.jsonl` | 13 条查询，带 `gold_chunk_ids` 证据标注 |
| `results/` | 三份跑出来的报告（见下） |

**为什么加**：上游没有可复现的对照表说明「哪种过滤策略省了多少 token、代价是什么」。
这个评测台把结论变成可验证的数字，并顺带验证预算层的收益与代价。

评测脚本不 import `gpt_researcher` 包（避免拉起 langchain 等重依赖），
按文件路径加载所需的 `budget.py`，因此**在只有标准库的环境里也能跑**，可放进 CI 当轻量门禁。

### 实测结果（`--embedder hashing` 占位向量，仅验证流程）

预算 150 tokens、`overflow=drop`：

| strategy | 平均上下文 tokens | 相对全量压缩率 | 证据召回率 |
|---|---|---|---|
| none | 2190.0 | 0.00% | 100.0% |
| keyword | 229.2 | 89.53% | 100.0% |
| embeddings | 78.0 | 96.44% | 84.62% |
| keyword_budget | 103.4 | 95.28% | 84.62% |

预算 150 tokens、`overflow=truncate`：`keyword_budget` = 146.1 tokens / 93.33% / **92.31%**。

预算 4000 tokens（宽松）：`keyword_budget` 与 `keyword` 完全一致（229.2 / 89.53% / 100%）
——**预算宽松时新逻辑不产生任何副作用**，这是这个开关能安全上线的前提。

## 6. 没有做的事（避免误读）

- 没有改动上游任何**默认行为**：不开 `CONTEXT_TOKEN_BUDGET` 时，返回的上下文与上游一致。
- 没有动 `agent.py` / `skills/` / `retriever` / `vector_store` 的既有实现。
- 没有新增运行时依赖（`budget.py` 与评测脚本所需的一切都在标准库里）。
- 评测脚本默认的 `--embedder hashing` 是**占位实现，没有语义能力**，
  只用于验证流程；真实结论需 `--embedder st`（依赖 `sentence-transformers`）。
- 没有改动 `evals/` 下上游已有的评测资产。

## 7. 复现

```bash
# 流程验证（无需任何 API Key 与模型）
python evals/context_budget_eval/run_bench.py --embedder hashing

# 真实评测
pip install sentence-transformers
python evals/context_budget_eval/run_bench.py --embedder st \
    --out evals/context_budget_eval/results/context_filter.md

# 对比不同预算下的取舍
python evals/context_budget_eval/run_bench.py --budget 150  --overflow drop
python evals/context_budget_eval/run_bench.py --budget 150  --overflow truncate
python evals/context_budget_eval/run_bench.py --budget 4000
```

## 8. 许可与归属

- 上游许可证：Apache License 2.0（见 `LICENSE`，未修改）
- 本次新增/修改文件的著作权归 fork 维护者所有，同样以 Apache-2.0 提供
- 上游项目主页：<https://github.com/assafelovic/gpt-researcher>
- 上游文档：<https://docs.gptr.dev/>
