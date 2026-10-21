"""评测集加载。"""
import json
from pathlib import Path


def load_qa_dataset() -> list[dict]:
    path = Path(__file__).parent / "qa_dataset.json"
    return json.loads(path.read_text(encoding="utf-8"))["items"]
