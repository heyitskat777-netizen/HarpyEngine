"""Draft narrow model/domain boundaries; actual purge SQL chain owned by Virus tests."""

import pytest
from pydantic import ValidationError

from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_role_punishment_state import RolePunishment


def case(**changes):
    actor = ActorRef(kind="pilot", entity="2", incarnation="original")
    values = dict(
        id="case",
        source_kind="compliance_virus",
        source_work="real-purge-required-work",
        source_event="actual-purge-event",
        chooser=None,
        chooser_controller=1,
        executor=actor,
        executor_controller=2,
        executor_frame="original-frame",
        subject=actor,
        subject_controller=2,
    )
    return RolePunishment(**(values | changes))


def test_self_case_requires_exact_virus_kind_work_and_no_synthetic_roll():
    assert case().executor == case().subject
    for invalid in (
        dict(source_kind="enforcement_initiative"),
        dict(source_kind="handler_play"),
        dict(source_work=None),
        dict(action="fake-roll"),
    ):
        with pytest.raises(ValidationError):
            case(**invalid)


def test_actual_harpy_executor_retains_frame_without_proxy_pilot():
    actor = ActorRef(kind="external_pilot", entity="actual-harpy")
    result = case(executor=actor, subject=actor)
    assert result.executor.kind == "external_pilot"
    with pytest.raises(ValidationError):
        case(executor=actor, subject=actor, executor_frame=None)
