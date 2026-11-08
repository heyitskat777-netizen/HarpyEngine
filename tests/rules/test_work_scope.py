import pytest
from pydantic import ValidationError

from girlframe.engine.m3_work_scope import WorkScope


@pytest.mark.parametrize(
    "fields,kind",
    [
        ({"mission_id": "actual-mission"}, "mission"),
        ({"off_duty_id": "actual-period"}, "off_duty"),
        ({"scene_id": "actual-scene"}, "scene"),
        ({"campaign_context": True}, "campaign"),
    ],
)
def test_work_has_exactly_one_explicit_context(fields, kind):
    assert WorkScope(**fields).kind == kind


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"mission_id": ""},
        {"scene_id": ""},
        {"mission_id": "m", "off_duty_id": "p"},
        {"mission_id": "m", "scene_id": "s"},
        {"off_duty_id": "p", "scene_id": "s"},
        {"scene_id": "s", "campaign_context": True},
        {"campaign_context": 1},
        {"campaign_context": "true"},
        {"campaign_context": True, "force": True},
    ],
)
def test_empty_ambiguous_or_invented_work_contexts_are_not_inferred(fields):
    with pytest.raises(ValidationError):
        WorkScope(**fields)
