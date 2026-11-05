"""Actual institutional departure preserves the living original without successor authority."""

import pytest
from test_actors import canon as canon
from test_actors import ledger as ledger

from girlframe.engine import m3_handler_consequences as rules
from girlframe.engine.m3_handler_state import Draft, HandlerPersona


@pytest.mark.parametrize("reason", ["fired", "retired", "imprisoned"])
def test_departure_archives_living_original_and_never_gives_new_persona_old_authority(
    canon, reason
):
    original = rules.active_handler(canon)
    before = canon.model_dump_json()
    result = rules.depart(
        canon,
        original,
        reason=reason,
        source_work="actual-last-base-loss-work",
        event="actual-institutional-decision",
        appointment="actual-appointment",
        account="The actual source judge specified this institutional consequence",
    )
    assert canon.model_dump_json() == before
    archive = result.handler_archives[-1]
    assert archive.actor == original and archive.ending == reason and archive.alive
    assert archive.custody == ("foundation_prison" if reason == "imprisoned" else "free")
    assert archive.source_event == "actual-institutional-decision"
    assert rules.active_handler(result) is None
    assert result.handler == canon.handler  # Human GM procedures are independent of fictional role.
    assert result.handler_departures[-1].source_work == "actual-last-base-loss-work"
    result.handler_persona = HandlerPersona(
        id="genuinely-new-handler-body",
        owner=1,
        appointment="actual-appointment",
        draft=Draft(name="New Handler"),
        source_event="actual-fresh-persona-source",
    )
    assert rules.active_handler(result) != original
    assert not rules.same_handler_body(result, original)
    assert rules.body_original(result, original) == archive.body
