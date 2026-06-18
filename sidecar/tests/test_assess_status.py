"""AssessStatus 枚举与 ProjectPhoto 新字段默认值。"""

from keeper_engine.entity.project_photo import ProjectPhoto
from keeper_engine.enumeration.assess_status import AssessStatus


def test_assess_status_values_are_screaming_snake():
    assert AssessStatus.NOT_ASSESSED.value == "NOT_ASSESSED"
    assert AssessStatus.SUCCESS.value == "SUCCESS"
    assert AssessStatus.LAYER1_FAILED.value == "LAYER1_FAILED"
    assert AssessStatus.LAYER2_FAILED.value == "LAYER2_FAILED"


def test_project_photo_defaults():
    p = ProjectPhoto(
        project_id=1, workspace_path="/w/a.jpg", original_path="/s/a.jpg",
        original_rel_path="a.jpg", filename="a.jpg",
    )
    assert p.assess_status == AssessStatus.NOT_ASSESSED.value
    assert p.assess_error_ignored is False
