"""Source-specific next-refusal modifiers, including actual actor consumption."""

import pytest
from pydantic import ValidationError

from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_refusal import consume, modifiers
from girlframe.engine.m3_refusal_state import RefusalBonus


def bonus(identity="actual-source", **values):
    return RefusalBonus(
        id=identity, period="actual-period", handler=1, source_event="event:" + identity, **values
    )


def test_distinct_occurrences_stack_once_on_actual_next_refusal_and_preserve_originals():
    sources = [bonus("first"), bonus("second")]
    before = [x.model_dump_json() for x in sources]
    selected = modifiers(sources, 1)
    assert [x["amount"] for x in selected] == [2, 2]
    ref = ActorRef(kind="pilot", entity="2", incarnation="original-character")
    after = consume(sources, 1, selected, ref, "real-roll")
    assert not modifiers(after, 1)
    assert all(x.actor == ref and x.action == "real-roll" for x in after)
    assert [x.model_dump_json() for x in sources] == before
    with pytest.raises(ValueError, match="STALE_CONTROL"):
        consume(after, 1, selected, ref, "different-roll")


def test_changed_handler_unrelated_role_and_stale_modifier_list_do_not_consume():
    sources = [bonus()]
    ref = ActorRef(kind="pilot", entity="2", incarnation="original")
    with pytest.raises(ValueError, match="original control-slip Handler"):
        modifiers(sources, 3)
    with pytest.raises(ValueError):
        consume(sources, 1, [], ref, "actual")
    with pytest.raises(ValueError):
        consume(sources, 1, modifiers(sources, 1), ActorRef(kind="npc", entity="npc"), "actual")
    assert sources[0].action is None


@pytest.mark.parametrize(
    "values",
    (
        {"amount": 3},
        {"amount": True},
        {"action": "roll"},
        {"actor": ActorRef(kind="pilot", entity="2", incarnation="original")},
    ),
)
def test_source_cannot_change_printed_amount_or_invent_half_a_consumption(values):
    with pytest.raises(ValidationError):
        bonus(**values)
