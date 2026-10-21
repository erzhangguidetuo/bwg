"""演示查询改写效果：模拟一段多轮对话中的追问。

用法：
    uv run scripts/demo_rewrite.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.rewrite import rewrite_query

history = [
    {"role": "user", "content": "员工入职满十年年假有几天？"},
    {"role": "assistant", "content": "入职满十年不满二十年的，年假为 10 个工作日 [1]。"},
]

cases = [
    "那病假的工资怎么算？",
    "超过十年的呢？",
    "考勤打卡漏了几次会被扣钱？",
]

for q in cases:
    rewritten = rewrite_query(history, q)
    print(f"原始问题: {q}")
    print(f"改写结果: {rewritten}")
    print("-" * 50)
    # 把回答追加进历史，模拟真实多轮
    history.append({"role": "user", "content": q})
    history.append({"role": "assistant", "content": "（略）"})
