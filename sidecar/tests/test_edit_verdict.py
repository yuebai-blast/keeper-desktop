"""层② 修图判定四态枚举与兜底逻辑测试。"""

from keeper_engine.enumeration.edit_verdict import EditVerdict


def test_four_values():
    assert {v.value for v in EditVerdict} == {
        "READY", "WORTH_EDITING", "NOT_WORTH", "UNFIXABLE",
    }


def test_coerce_keeps_legal_value():
    assert EditVerdict.coerce("WORTH_EDITING") == "WORTH_EDITING"
    assert EditVerdict.coerce(" UNFIXABLE ") == "UNFIXABLE"  # 去空白后合法


def test_coerce_falls_back_to_ready():
    assert EditVerdict.coerce("") == "READY"
    assert EditVerdict.coerce("乱写的") == "READY"
    assert EditVerdict.coerce(None) == "READY"  # None 也兜底
