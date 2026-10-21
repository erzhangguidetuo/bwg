# 上下文过滤 / 预算评测（context_budget_eval）

这个目录是我在 GPT Researcher 上加的**离线评测台**，用来回答一个上游没有量化回答的问题：

> 不同的上下文筛选策略各把多少 token 送进了模型？省下来的 token 里，
> **真正必要的证据**有没有被一起丢掉？再加一层 token 预算，代价是什么？

## 为什么需要它

上游 `gpt_researcher/context/compression.py` 里控制上下文大小的其实是两把旋钮：

| 旋钮 | 作用 | 问题 |
|---|---|---|
| `COMPRESSION_THRESHOLD`（默认 8000） | 内容**字符数**低于阈值就跳过压缩，按原顺序取前 `max_results` 条 | 字符数不是 token 数 |
| `max_results`（默认 10） | 最终截断到多少**条**分块 | 条数也不是 token 数 |

同样 10 条分块，在不同长度的页面上可能差 3 倍 token。多智能体调研时每个 Executor
各自拼一份上下文，很容易在不该爆的地方撞上模型窗口，只能靠报错后回头把这个旋钮调小
——而调小它又会连带砍掉本来该保留的证据。

所以这个评测台做两件事：**量化每种策略的 token / 证据权衡**，并验证我新加的
token 预算层（`gpt_researcher/context/budget.py`）是否真的能把这件事变成显式参数。

## 目录

```
evals/context_budget_eval/
├── run_bench.py                  # 主评测脚本
├── _common.py                    # 分词 + BM25（纯标准库，与主包解耦）
├── data/
│   ├── sample_docs.jsonl         # 30 条候选分块（模拟抓取到的网页片段，含干扰项）
│   └── sample_queries.jsonl      # 13 条查询，带 gold_chunk_ids
└── results/                      # 评测报告
```

## 快速开始

脚本**只依赖标准库**，不需要装 langchain / openai，也不需要任何 API Key：

```bash
# 流程验证（哈希向量的占位实现，无语义能力）
python evals/context_budget_eval/run_bench.py --embedder hashing

# 真实评测（需 pip install sentence-transformers）
python evals/context_budget_eval/run_bench.py --embedder st \
    --out evals/context_budget_eval/results/context_filter.md

# 只看某几种策略 / 收紧预算 / 输出逐条明细
python evals/context_budget_eval/run_bench.py \
    --strategies keyword,keyword_budget --budget 150 --per-query
```

### 数据格式

`sample_docs.jsonl`（候选分块，模拟 `page_content`）：

```json
{"doc_id": "c-05", "url": "https://...", "title": "工业协议对比", "text": "..."}
```

`sample_queries.jsonl`：

```json
{"query": "怎么判断一个网关的协议支持是不是真的好用", "gold_chunk_ids": ["c-05"], "topic": "协议"}
```

`gold_chunk_ids` 是**必要证据**的标注——评测的核心就是看过滤之后这些块还在不在。

## 四个被对比的策略

| 策略 | 实现 | 与上游的关系 |
|---|---|---|
| `none` | 全量拼接，不过滤 | 对应上游快路径「跳过压缩直接返回」的极端情况 |
| `embeddings` | 余弦相似度阈值过滤（`SIMILARITY_THRESHOLD=0.35`） | **复刻上游 `ContextCompressor` 当前的默认行为** |
| `keyword` | BM25 相对阈值过滤 | 上游已移除关键词过滤路径；这里作为**零 embedding 成本的对照组**保留 |
| `keyword_budget` | keyword 过滤后再套 token 预算 | **本次新增**，用 `gpt_researcher/context/budget.py` |

## 实测结果

`data/sample_docs.jsonl`（30 条，全量基线约 2190 tokens）+ `data/sample_queries.jsonl`（13 条）。

**预算 150 tokens · `overflow=drop`**

| strategy | 说明 | 平均上下文 tokens | 相对全量压缩率 | 平均保留块数 | 证据召回率 |
|---|---|---|---|---|---|
| none | 不过滤（全量拼接） | 2190.0 | 0.00% | 30.00 | 100.0% |
| keyword | BM25 相对阈值过滤 | 229.2 | 89.53% | 3.08 | **100.0%** |
| embeddings | Embedding 余弦阈值过滤 | 78.0 | 96.44% | 1.00 | 84.62% |
| keyword_budget | BM25 + token 预算（150） | 103.4 | 95.28% | 1.38 | 84.62% |

**预算 4000 tokens（宽松）**：`keyword_budget` 与 `keyword` 完全一致（229.2 tokens / 100% 召回）
——预算宽松时它**不产生任何副作用**，这是这个开关能安全上线的关键。

**预算 150 tokens · `overflow=truncate`**

| strategy | 平均上下文 tokens | 相对全量压缩率 | 平均保留块数 | 证据召回率 |
|---|---|---|---|---|
| keyword_budget (truncate) | 146.1 | 93.33% | 1.92 | **92.31%** |

### 怎么读这几张表

1. **`keyword` 是性价比最高的一档**：压掉近 90% 的 token，证据一条没丢。
   而且它不需要任何 embedding 调用——省的是 token，也省了 embedding 的钱和延迟。
2. **`embeddings` 压得更狠（96.4%），但证据召回掉了 15 个百分点**。
   它把语义相近的干扰块排上来，反而把真正含答案的块挤出局。
   在本次语料上，纯向量过滤是「省得更多但更危险」的一档。
   ——这也是为什么上游把 `COMPRESSION_THRESHOLD` 快路径留在那里：小文档干脆别过滤。
3. **`drop` vs `truncate` 是有意义的抉择**：同样 150 token 预算下，
   `truncate` 多花 42.7 个 token（约占预算 28%），把证据召回从 84.62% 拉回 **92.31%**。
   超长分块前面往往就是答案所在，一刀切掉整块代价过大。
   **这就是预算层的价值——「要质量还是要成本」变成了一个可以调的显式参数**，
   而不是靠改 `max_results` 这种和 token 不成比例的旋钮去猜。

> ⚠️ 以上是 `--embedder hashing`（占位实现）下的**流程验证结果**。
> 哈希向量没有语义能力，`embeddings` 那一行的绝对值不可外推。
> 换上真实模型（`--embedder st`）后请重新跑并把报告写回这里。

## 实现说明

- **token 计数**：走 `gpt_researcher.context.budget.estimate_tokens`，
  有 tiktoken 用精确计数，没有则按 CJK 字数 + 英文词数加权估算（中文语料实测偏差约 ±12%）。
- **模块加载方式**：评测脚本按文件路径直接加载 `budget.py` 和自身依赖，
  不 import `gpt_researcher` 包（它的 `__init__` 会拉起 langchain 等重依赖）。
  这样这个评测台可以在裸 Python 环境跑，方便放进 CI 当轻量门禁。
- **可复现性**：排序同分保持原索引顺序，不用随机数，同一输入每次结果一致。
- **不调用 LLM**：整个评测只做检索与过滤，不产生任何 API 费用。

## 怎么把评测结果用到线上

```bash
# 在 .env 里开启 token 预算约束（默认 0 = 关闭，行为与上游一致）
CONTEXT_TOKEN_BUDGET=4000
CONTEXT_TOKEN_OVERFLOW=truncate
```

开启后 `ContextCompressor` 会在返回上下文前按 token 装填一次，
超出预算的按 `drop` / `truncate` / `keep` 处理，并打一行日志：

```
[context_compressor] 预算 4000 tokens，实际使用 3871 (96.8%)，保留 7 条，丢弃 3 条 (1204 tokens)
```
