"""管理面模型客户端解析测试——纯解析，不联网。

回归：do_call 已把 Result 拆包，列表数据直接在顶层（TotalCount/Items），
早期 _parse 误读 resp["Result"]["Items"] → 永远空（见调试记录）。
"""

from keeper_engine.client.foundation_model_client import FoundationModelClient

parse = FoundationModelClient._parse


def _item(name, version, task_types, display=None, access="Public"):
    return {
        "Name": name,
        "PrimaryVersion": version,
        "DisplayName": display or name,
        "AccessType": access,
        "FoundationModelTag": {"TaskTypes": task_types},
    }


def test_parse_unwrapped_top_level_items():
    # 真实形态：顶层直接是 TotalCount/Items，无 Result 包裹
    resp = {"TotalCount": 1, "PageNumber": 1, "PageSize": 100,
            "Items": [_item("doubao-seed-2-0-pro", "260215", ["Chat", "VisualQuestionAnswering"])]}
    models = parse(resp)
    assert [m.model_id for m in models] == ["doubao-seed-2-0-pro-260215"]
    assert models[0].name == "doubao-seed-2-0-pro"
    assert models[0].version == "260215"


def test_parse_wrapped_result_still_works():
    # 防御：万一某版本仍带 Result 包裹也能解析
    resp = {"Result": {"Items": [_item("m", "v1", ["VisualQuestionAnswering"])]}}
    assert [m.model_id for m in parse(resp)] == ["m-v1"]


def test_parse_skips_items_without_vqa():
    resp = {"Items": [
        _item("vqa-model", "1", ["Chat", "VisualQuestionAnswering"]),
        _item("text-only", "1", ["TextGeneration"]),  # 无 VQA 应被剔除
    ]}
    assert [m.name for m in parse(resp)] == ["vqa-model"]


def test_parse_skips_non_public():
    resp = {"Items": [
        _item("pub", "1", ["VisualQuestionAnswering"], access="Public"),
        _item("priv", "1", ["VisualQuestionAnswering"], access="Private"),  # 自建私有模型应被剔除
    ]}
    assert [m.name for m in parse(resp)] == ["pub"]


def test_parse_model_id_without_version():
    resp = {"Items": [_item("only-name", "", ["VisualQuestionAnswering"])]}
    assert parse(resp)[0].model_id == "only-name"


def test_parse_empty():
    assert parse({}) == []
    assert parse({"Items": []}) == []
