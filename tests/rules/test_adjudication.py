"""Mandatory exception receipts contain one honest method, never invented dice."""

import pytest
from pydantic import ValidationError

from girlframe.discord_adapter.m2_receipt_text import expression
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_adjudication import receipt
from girlframe.engine.m3_adjudication_state import Decision, Required
from girlframe.engine.m3_lobotomy_state import BlockedPlay
from girlframe.engine.m3_off_duty import Adjustment, Roll


def decision(play="go_off_duty"):
    required = Required(
        play=play,
        actor=ActorRef(kind="pilot", entity="2", incarnation="original"),
        handler=ActorRef(kind="handler", entity="1"),
        prohibition=BlockedPlay(
            play=play, surgery="source-surgery", source_event="source-surgery-event"
        ),
        source_kind="off_duty",
        source_id="actual-period",
        source_revision=1,
        registry="test-registry",
    )
    return Decision(
        id="actual-human-decision",
        action="actual-action",
        request="actual-request",
        required=required,
        total=8,
        reason="Actual Handler's explicit circumstances and ruling",
        source_event="actual-manual-source",
    )


def test_manual_period_receipt_keeps_actual_decision_and_only_actual_tag_adjustments():
    manual = decision()
    saved = Roll(
        faces=None,
        adjudication=manual,
        modifier=0,
        total=10,
        source="status",
        adjustments=(Adjustment(source="actual_tag", actor=3, amount=2, tag="actual-tag"),),
    )
    assert saved.total == 10 and saved.faces is None
    assert Roll.model_validate_json(saved.model_dump_json()) == saved
    shown = receipt(manual, "actual-receipt", "actual-time")
    assert shown["faces"] is None and shown["rng_source"] == "manual_adjudication"
    assert "MANUAL ADJUDICATION" in expression(shown) and "no RNG" in expression(shown)


@pytest.mark.parametrize(
    "changes",
    [
        {"faces": (4, 4)},
        {"modifier": 1},
        {"adjudication": None},
        {"total": 9},
    ],
)
def test_manual_receipt_rejects_fabricated_dice_or_hidden_modifiers(changes):
    values = dict(faces=None, adjudication=decision(), modifier=0, total=8, source="status")
    with pytest.raises(ValidationError):
        Roll(**(values | changes))


def test_legacy_actual_dice_receipt_remains_valid():
    actual = Roll(faces=(3, 4), modifier=2, total=9, source="status")
    assert actual.adjudication is None and actual.faces == (3, 4)
