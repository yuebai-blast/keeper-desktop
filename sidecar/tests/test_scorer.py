"""层② 打分输出解析的测试——纯解析，不联网。"""

import pytest

from keeper_engine.scorer import parse_response


def test_parse_plain_json():
    assert parse_response('{"score": 88, "reason": "构图好"}') == (88.0, "构图好")


def test_parse_with_markdown_fence():
    assert parse_response('```json\n{"score": 70, "reason": "表情自然"}\n```') == (70.0, "表情自然")


def test_parse_with_extra_text():
    assert parse_response('好的，结果是：{"score": 61, "reason": "瞬间不错"} 以上。') == (61.0, "瞬间不错")


def test_parse_clamps_range():
    assert parse_response('{"score": 150, "reason": ""}')[0] == 100.0
    assert parse_response('{"score": -5, "reason": ""}')[0] == 0.0


def test_parse_truncates_reason():
    out = parse_response('{"score": 50, "reason": "' + "好" * 50 + '"}')
    assert len(out[1]) == 30


def test_parse_malformed_raises():
    with pytest.raises(ValueError):
        parse_response("这里没有 JSON")
