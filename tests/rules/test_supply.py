import pytest
from pydantic import ValidationError

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_supply import consume, modifiers
from girlframe.engine.m3_supply_state import SupplyLoss
from girlframe.engine.rolls import OsIndex


def loss(**kwargs):
    values = dict(
        id="source",
        period="period",
        source_event="event",
        population=(
            ActorRef(kind="pilot", entity="2", incarnation="original"),
            ActorRef(kind="pilot", entity="3", incarnation="other"),
        ),
        index=0,
        resource="Synthetic missing resource",
        rng_source="test_injected",
    )
    values.update(kwargs)
    return SupplyLoss(**values)


@pytest.mark.parametrize("index", (-1, 2, True))
def test_invalid_random_index_cannot_assign_a_supply_loss(index):
    with pytest.raises(ValidationError):
        loss(index=index)


def test_os_index_uses_uniform_primitive_for_the_actual_population_size(monkeypatch):
    calls = []

    def draw(size):
        calls.append(size)
        return size - 1

    monkeypatch.setattr("girlframe.engine.rolls.secrets.randbelow", draw)
    assert OsIndex().choose(7) == 6 and calls == [7]
    with pytest.raises(ValueError):
        OsIndex().choose(0)


def test_supply_modifier_binds_actual_character_and_consumes_once_for_the_original_action():
    item = loss()
    canon = GameState(supply_losses=[item])
    assert (
        modifiers(canon, "period", ActorRef(kind="pilot", entity="2", incarnation="new-body")) == []
    )
    assert modifiers(canon, "other-period", item.owner) == []
    actual = modifiers(canon, "period", item.owner)
    assert actual == [{"id": "source", "source": "missed_supply", "amount": -2}]
    with pytest.raises(ValueError, match="STALE_SUPPLY"):
        consume(canon, "period", item.owner, [], "action")
    assert canon.supply_losses[0].action is None
    consume(canon, "period", item.owner, actual, "actual-roll")
    assert not modifiers(canon, "period", item.owner) and item.action is None
    assert canon.supply_losses[0].action == "actual-roll"
    with pytest.raises(ValueError):
        consume(canon, "period", item.owner, actual, "another-roll")


def test_receipt_expression_exposes_the_base_and_separate_supply_penalty():
    from girlframe.discord_adapter.m2_receipt_text import expression

    assert (
        expression(
            {
                "faces": [3, 3],
                "heat": 0,
                "base_modifier": 4,
                "modifier_source": "Status",
                "pre_modifiers": [{"source": "missed_supply", "amount": -2}],
            }
        )
        == "3 + 3 + 4 Status + (-2) missed supply"
    )
