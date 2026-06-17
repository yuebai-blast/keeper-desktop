"""层② 打分输出解析的测试——纯解析，不联网。"""

from types import SimpleNamespace

import pytest

from keeper_engine.client.scorer import _layer2_prompt, extract_output_text, parse_response


def _msg(*texts):
    """构造一个 Responses API 的 message 输出项（含若干 output_text 内容块）。"""
    content = [SimpleNamespace(type="output_text", text=t) for t in texts]
    return SimpleNamespace(type="message", content=content)


def test_extract_output_text_joins_message_parts():
    resp = SimpleNamespace(output=[_msg("前", "后")])
    assert extract_output_text(resp) == "前后"


def test_extract_output_text_skips_reasoning_blocks():
    # reasoning 等非 message 项要跳过，只取 message 里的 output_text
    resp = SimpleNamespace(output=[
        SimpleNamespace(type="reasoning", content=None),
        _msg('{"score": 80, "reason": "好"}'),
    ])
    assert extract_output_text(resp) == '{"score": 80, "reason": "好"}'


def test_extract_output_text_empty_output():
    assert extract_output_text(SimpleNamespace(output=[])) == ""


def test_parse_plain_json():
    assert parse_response('{"score": 88, "flaws": "无", "reason": "构图好"}') == (88.0, "构图好", "无", "ready", "")


def test_parse_with_markdown_fence():
    out = parse_response('```json\n{"score": 70, "flaws": "碎发", "reason": "表情自然"}\n```')
    assert out == (70.0, "表情自然", "碎发", "ready", "")


def test_parse_with_extra_text():
    out = parse_response('结果：{"score": 61, "flaws": "无", "reason": "瞬间不错"} 完')
    assert out == (61.0, "瞬间不错", "无", "ready", "")


def test_parse_clamps_range():
    assert parse_response('{"score": 150, "reason": ""}')[0] == 100.0
    assert parse_response('{"score": -5, "reason": ""}')[0] == 0.0


def test_parse_missing_flaws_defaults_empty():
    assert parse_response('{"score": 50, "reason": "一般"}')[2] == ""


def test_parse_malformed_raises():
    with pytest.raises(ValueError):
        parse_response("这里没有 JSON")


def test_parse_edit_fields_present():
    out = parse_response(
        '{"score": 82, "reason": "好", "flaws": "碎发",'
        ' "editable": "worth_editing", "edit_advice": "磨皮去碎发即可"}'
    )
    assert out == (82.0, "好", "碎发", "worth_editing", "磨皮去碎发即可")


def test_parse_editable_illegal_falls_back_ready():
    # 非法 editable 兜底为 ready
    assert parse_response('{"score": 50, "reason": "", "editable": "胡来"}')[3] == "ready"


def test_parse_editable_missing_defaults_ready():
    assert parse_response('{"score": 50, "reason": ""}')[3] == "ready"


def test_parse_edit_advice_truncated_to_40():
    long = "修" * 60
    out = parse_response('{"score": 50, "reason": "", "edit_advice": "%s"}' % long)
    assert len(out[4]) == 40


def test_layer2_prompt_loads_from_file():
    p = _layer2_prompt()
    assert "0–100" in p and "骨架" in p and "flaws" in p  # 提示词文件读得到、含关键结构
