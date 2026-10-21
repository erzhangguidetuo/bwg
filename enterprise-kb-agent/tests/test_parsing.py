"""路由与自检解析函数的单元测试（纯函数，无需模型与网络）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graph.nodes.grade import parse_grade
from graph.nodes.router import parse_route


def test_parse_route():
    assert parse_route("knowledge") == "knowledge"
    assert parse_route("  CHITCHAT\n") == "chitchat"
    assert parse_route("我认为是 web") == "web"
    # 异常输出默认走知识库
    assert parse_route("随便什么模糊回答") == "knowledge"


def test_parse_grade_normal():
    result = parse_grade('{"sufficient": true, "missing": null}')
    assert result == {"sufficient": True, "missing": None}


def test_parse_grade_in_code_fence():
    raw = '```json\n{"sufficient": false, "missing": "缺少病假工资标准"}\n```'
    result = parse_grade(raw)
    assert result["sufficient"] is False
    assert "病假" in result["missing"]


def test_parse_grade_broken_output_is_fail_safe():
    # 模型输出异常时按"不充分"处理，驱动重试或降级
    result = parse_grade("我觉得应该可以吧")
    assert result["sufficient"] is False
