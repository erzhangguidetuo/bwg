"""多轮交互式问答入口：LangGraph 状态图 + SqliteSaver 会话记忆。

用法：
    uv run scripts/ask_agent.py            # 默认会话 thread-1
    uv run scripts/ask_agent.py my-thread  # 指定会话线程

运行后进入对话循环，输入 q 退出。历史按 thread 持久化到
data/chat_memory.sqlite，重启进程后同一 thread 可继续对话。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graph.builder import build_graph_with_sqlite


def main():
    thread_id = sys.argv[1] if len(sys.argv) > 1 else "thread-1"
    graph = build_graph_with_sqlite()
    config = {"configurable": {"thread_id": thread_id}}

    print(f"企业知识库助手已启动（会话: {thread_id}，输入 q 退出）")
    while True:
        try:
            question = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break
        if not question:
            continue
        if question.lower() == "q":
            print("再见。")
            break

        print("[流程]", end=" ")
        # stream_mode="updates" 可看到每个节点的执行轨迹，便于观察
        # 路由、自检、重试、降级是否按预期发生
        result = {"answer": ""}
        for event in graph.stream(
            {
                "messages": [{"role": "user", "content": question}],
                "question": question,
                "retry_count": 0,
            },
            config,
            stream_mode="updates",
        ):
            for node_name in event:
                print(f"-> {node_name}", end=" ")
            # 最后一个事件包含 generate 的 answer
            for update in event.values():
                if isinstance(update, dict) and "answer" in update:
                    result["answer"] = update["answer"]
        print()
        print("-" * 60)
        print(result["answer"])
        print("-" * 60)


if __name__ == "__main__":
    main()
