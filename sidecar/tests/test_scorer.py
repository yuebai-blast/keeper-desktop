"""层② 打分输出解析的测试——纯解析，不联网。"""

import pytest

from keeper_engine.client.scorer import _layer2_prompt, parse_response


def test_parse_plain_json():
    assert parse_response('{"score": 88, "flaws": "无", "reason": "构图好"}') == (88.0, "构图好", "无")


def test_parse_with_markdown_fence():
    out = parse_response('```json\n{"score": 70, "flaws": "碎发", "reason": "表情自然"}\n```')
    assert out == (70.0, "表情自然", "碎发")


def test_parse_with_extra_text():
    out = parse_response('结果：{"score": 61, "flaws": "无", "reason": "瞬间不错"} 完')
    assert out == (61.0, "瞬间不错", "无")


def test_parse_clamps_range():
    assert parse_response('{"score": 150, "reason": ""}')[0] == 100.0
    assert parse_response('{"score": -5, "reason": ""}')[0] == 0.0


def test_parse_missing_flaws_defaults_empty():
    assert parse_response('{"score": 50, "reason": "一般"}')[2] == ""


def test_parse_malformed_raises():
    with pytest.raises(ValueError):
        parse_response("这里没有 JSON")


def test_layer2_prompt_loads_from_file():
    p = _layer2_prompt()
    assert "0–100" in p and "骨架" in p and "flaws" in p  # 提示词文件读得到、含关键结构
