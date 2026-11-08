"""Paid source retention and actual independently owned Enforcer trigger rewards."""

from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved, buy
from test_frame_reward_service import submit
from test_frame_swap import selection
from test_frame_swap_service import configured, pay, setup
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_off_duty_cycle import activate, prepared, roll_for

from girlframe.engine import m3_enforcer_requisitions as acquired
from girlframe.engine import m3_privileges as privilege
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_frame_rewards import Claim
from girlframe.services.m3_enforcer_requisitions import owned
from girlframe.services.m3_frame_rewards import RewardService
from girlframe.services.onboarding import WorkflowError


def test_actual_paid_swap_retains_original_rule_source_and_temporary_loss_not_historical_swap(
    ledger, tmp_path, monkeypatch
):
    swap, game = setup(ledger, tmp_path, monkeypatch)
    acquisition = approved(ledger, game, tmp_path, monkeypatch, extra=acquired.BASE)
    swap.registry = acquisition.registry
    purchase = buy(acquisition, acquired.SNOOP, "frame_grafting")
    original = state(game)
    actor = current_ref(original, 2)
    grant = acquired.held(original, actor, acquired.SNOOP)
    plan = swap.create(PLAYER, str(uuid4()), "THE ENFORCER")["id"]
    chosen = selection(original).model_copy(update=dict(retained_rule=acquired.SNOOP))
    swap.change(PLAYER, str(uuid4()), plan, 1, selection=chosen)
    pay(swap, plan)
    actual = state(game)
    assert acquired.held(actual, actor, acquired.SNOOP) == grant
    assert acquired.frame(actual, actor) != grant.frame
    with ledger.engine.connect() as c:
        assert owned(c, game, actual, actor, acquired.SNOOP) == grant
    receipt = actual.requisitions[-1]
    assert receipt.kind == "frame_swap"
    chars = {int(k): s.character_id for k, s in actual.sheets.items()}
    removed = privilege.revoke(
        actual,
        2,
        1,
        receipt.id,
        "Actual original restoration condition",
        str(uuid4()),
        "actual-source",
        chars,
    )
    assert acquired.held(removed, actor, acquired.SNOOP) is None
    assert removed.sheets["2"].frame == actual.sheets["2"].frame
    assert removed.sheets["2"].assets == actual.sheets["2"].assets
    assert removed.sheets["2"].permissions == actual.sheets["2"].permissions
    gate = removed.obligations[-1]
    gate.details["restoration_allowed"] = "true"
    restored = privilege.restore(removed, gate.id, actor.incarnation, None)
    assert acquired.held(restored, actor, acquired.SNOOP) == grant
    assert (
        restored.requisitions == actual.requisitions
        and restored.parked_frames == actual.parked_frames
    )
    assert purchase["id"] == grant.purchase


def trigger_source(store, tmp_path, monkeypatch):
    cycle, game, period = prepared(store)
    acquisition = approved(store, game, tmp_path, monkeypatch, extra=acquired.BASE)
    cycle.missions.access.registry = acquisition.registry
    with store.transaction() as c:
        canon = state(game)
        canon.sheets["2"].permissions = 3
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_permissions", canon)
    return cycle, game, period, acquisition


def test_actual_grafted_trigger_at_real_off_duty_source_grants_once_alongside_native_rule(
    ledger, tmp_path, monkeypatch
):
    cycle, game, period, acquisition = trigger_source(ledger, tmp_path, monkeypatch)
    buy(acquisition, acquired.PERMISSION, "frame_grafting")
    rewards = RewardService(cycle.periods)
    data = cycle.periods.get(ADMIN, period)
    rewards.refresh(ADMIN, str(uuid4()), period, data["revision"], state(game).revision)
    activate(cycle, game, period)
    roll_for(cycle, game, period, PLAYER, review_reward=False)
    works = [
        x for x in cycle.periods.get(PLAYER, period)["work"] if x["kind"] == "frame_off_duty_reward"
    ]
    retained = next(x for x in works if rewards.get(PLAYER, x["id"])["frame"] == "THE ENFORCER")
    native = next(x for x in works if rewards.get(PLAYER, x["id"])["frame"] == "JANUS")
    before = state(game).sheets["2"].permissions
    submit(
        rewards,
        PLAYER,
        retained["id"],
        Claim(
            fulfilled=True,
            evidence="Actual evidence of cadremate disobedience brought to original Handler",
            account="Actual original source trigger",
        ),
    )
    assert state(game).sheets["2"].permissions == before + 1
    with pytest.raises(WorkflowError):
        submit(
            rewards,
            PLAYER,
            retained["id"],
            Claim(fulfilled=True, evidence="Repeat", account="No duplicate"),
        )
    submit(
        rewards,
        PLAYER,
        native["id"],
        Claim(
            fulfilled=True,
            official="handler:1",
            account="Actual separate native JANUS demonstration",
        ),
    )
    assert state(game).sheets["2"].permissions == before + 2


def test_trigger_acquired_after_known_off_duty_roll_cannot_retroactively_qualify(
    ledger, tmp_path, monkeypatch
):
    cycle, game, period, acquisition = trigger_source(ledger, tmp_path, monkeypatch)
    activate(cycle, game, period)
    roll_for(cycle, game, period, PLAYER, review_reward=False)
    buy(acquisition, acquired.PERMISSION, "frame_grafting")
    rewards = RewardService(cycle.periods)
    data = cycle.periods.get(ADMIN, period)
    rewards.refresh(ADMIN, str(uuid4()), period, data["revision"], state(game).revision)
    assert all(
        rewards.get(PLAYER, x["id"])["frame"] != "THE ENFORCER"
        for x in cycle.periods.get(PLAYER, period)["work"]
        if x["kind"] == "frame_off_duty_reward"
    )


@pytest.mark.parametrize("rule", acquired.BASE)
def test_native_enforcer_rule_retention_has_actual_paid_source_and_stops_unselected_rules(
    ledger, tmp_path, monkeypatch, rule
):
    from girlframe.engine import m3_enforcer as enforcer
    from girlframe.engine.m3_personal_firearm import held as firearms

    swap, game = setup(ledger, tmp_path, monkeypatch)
    first = configured(swap, game)
    pay(swap, first)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].permissions = 4
        game.event(c, 1, str(uuid4()), "synthetic.actual_next_exchange_funds", canon)
    actor = current_ref(state(game), 2)
    source = state(game)
    plan = swap.create(PLAYER, str(uuid4()), "JANUS-B")["id"]
    selected = selection(source, "JANUS-B").model_copy(update=dict(retained_rule=rule))
    swap.change(PLAYER, str(uuid4()), plan, 1, selection=selected)
    pay(swap, plan)
    actual = state(game)
    grant = acquired.held(actual, actor, rule)
    assert grant and grant.source_kind == "frame_swap"
    with ledger.engine.connect() as c:
        assert owned(c, game, actual, actor, rule) == grant
    assert actual.sheets["2"].permissions == 0
    assert actual.sheets["2"].frame == "JANUS-B"
    assert not firearms(actual, actor, acquired.frame(actual, actor))
    assert enforcer.initiative(actual, actor) == (rule == acquired.INITIATIVE)
    assert enforcer.conditioning(actual, actor) == (rule == acquired.OBEDIENCE)
    assert actual.personal_firearms[0].issues == source.personal_firearms[0].issues
