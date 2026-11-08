import pytest
from pydantic import ValidationError

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_repair_state import Shortage
from girlframe.engine.m3_repairs import (
    active,
    begin_period,
    close_period,
    dispatch,
    mission_ended,
    schedule,
)
from girlframe.engine.m3_strain import initial


def test_shortage_has_actual_mission_end_and_period_anchors_and_does_not_stack_free_quota():
    state = GameState(
        strain=initial("business_as_usual", frozenset()).model_copy(update={"periods": ("source",)})
    )
    first, second = schedule(state, "source-one", "source"), schedule(state, "source-two", "source")
    state.repair_shortages = [first, second]
    assert not active(state, "source")
    before_mission = begin_period(state, "unrelated-period")
    assert before_mission == state
    bound = dispatch(state, "actual-mission", "dispatch-event")
    assert all(x.mission == "actual-mission" and x.period is None for x in bound.repair_shortages)
    assert all(x.mission is None for x in state.repair_shortages)
    assert dispatch(bound, "another-mission", "other-dispatch") == bound
    assert begin_period(bound, "too-early") == bound
    ended = mission_ended(bound, "actual-mission", "end-event")
    period = begin_period(ended, "actual-recovery")
    assert active(period, "actual-recovery") == ("source-one", "source-two")
    assert not active(period, "source")
    assert begin_period(period, "later-recovery") == period
    assert not active(close_period(period, "actual-recovery"), "actual-recovery")


def test_unsourced_or_impossible_shortage_cannot_be_a_live_repair_restriction():
    with pytest.raises(ValueError):
        schedule(GameState(), "event", "invented-period")
    for fields in (
        {"mission_end_event": "event"},
        {"period": "period"},
        {"closed": True},
        {"mission": "mission"},
    ):
        with pytest.raises(ValidationError):
            Shortage(id="scope", source_period="source", **fields)
