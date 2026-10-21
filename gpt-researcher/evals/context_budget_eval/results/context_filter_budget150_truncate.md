# 上下文过滤 / 预算策略离线评测

Embedding: `hashing-degraded`（**降级，结果仅用于流程验证**）

候选分块 30 条 · 查询 13 条 · 全量基线 2190 tokens · 预算上限 150 tokens（overflow=truncate）

参数：`SIMILARITY_THRESHOLD=0.35`、`KEYWORD_RELATIVE_THRESHOLD=0.5`、`KEYWORD_MAX_RESULTS=25`

### 策略对比（按查询取平均）

| strategy | 说明 | 平均上下文 tokens | 相对全量压缩率 | 平均保留块数 | 证据召回率 |
|---|---|---|---|---|---|
| none | 不过滤（全量拼接） | 2190.0000 | 0.0000 | 30.0000 | 1.0000 |
| keyword | BM25 相对阈值过滤 | 229.2000 | 0.8953 | 3.0800 | 1.0000 |
| embeddings | Embedding 余弦阈值过滤 | 78.0000 | 0.9644 | 1.0000 | 0.8462 |
| keyword_budget | BM25 过滤 + token 预算 | 146.1000 | 0.9333 | 1.9200 | 0.9231 |
