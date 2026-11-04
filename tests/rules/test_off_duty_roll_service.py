"""Synthetic active period isolates the shared Play bridge; no live approval is implied."""

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Gateway, answer, pass_tags, start, state, tick
from test_mission_service import service

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import TagState
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_play_support import cancel_unrolled, resume
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def active(store, faces=(4, 5)):
    missions, game = service(store)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"plays"}}
            )
        }
    )
    from test_m2_game import Dice

    game.dice = Dice(faces)
    periods = OffDutyService(missions)
    period = periods.begin(ADMIN, "begin")
    with store.transaction() as c:
        saved = periods._get(c, period["id"])
        saved.phase = "active"
        saved.revision += 1
        event = game.event(c, 1, "fixture-active", "synthetic.active")
        periods._save(c, saved, event)
    return periods, game, GameWorker(game), Gateway(), period["id"]


def saved(periods, identity):
    with periods.store.engine.connect() as c:
        return periods._get(c, identity)


def test_status_roll_uses_confirmed_chat_lock_tag_window_and_one_saved_receipt(ledger):
    periods, game, worker, gateway, identity = active(ledger, (1, 2))
    before = state(game).sheets["2"].heat
    action = start(game, play="go_off_duty", off_duty_id=identity)
    assert game.dice.calls == 0
    with pytest.raises(WorkflowError, match="LOCK_NOT_ACKNOWLEDGED"):
        game.roll(PLAYER, "too-early", action)
    tick(worker, gateway)
    raw = saved(periods, identity).progress["2"].roll
    assert raw.faces == (1, 2) and raw.modifier == 4 and raw.total == 7
    assert raw.stage == "tag_window"
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["ruleset"] == "girlframe-m3-core-1"
    assert receipt["modifier_source"] == "Status"
    assert state(game).sheets["2"].heat == before
    with pytest.raises(WorkflowError, match="second time"):
        start(game, play="go_off_duty", off_duty_id=identity)
    pass_tags(game)
    assert saved(periods, identity).progress["2"].roll.stage == "choices"
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 8)
    assert game.dice.calls == 1
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    assert {k[0] + k[1]: v for k, v in gateway.values.items()} == gateway.original


def test_bond_tag_modifier_changes_actual_period_tier_without_changing_raw_dice(ledger):
    periods, game, worker, gateway, identity = active(ledger, (1, 1))
    with ledger.transaction() as c:
        current = state(game)
        current.sheets["2"].tags.append(
            TagState(id="known", label="Known", giver=3, observers=(3,))
        )
        game.event(c, 1, "tag-fixture", "synthetic.tag", current)
    action = start(game, play="go_off_duty", off_duty_id=identity)
    tick(worker, gateway)
    answer(game, PLAYER, "tag_window", options=("pass",))
    answer(
        game, OTHER, "tag_window", options=("tag",), denied=("known",), number=1, text="Relevant"
    )
    answer(game, ADMIN, "tag_window", options=("pass",))
    result = saved(periods, identity).progress["2"].roll
    assert result.faces == (1, 1) and result.total == 8
    assert result.adjustments[0].amount == 2
    assert game.inspect(PLAYER, action)["result"]["tier"] == "mid"
    assert state(game).sheets["2"].tags[0].marked


def test_abort_resume_retains_receipt_answered_humans_and_invalidates_old_pending_form(ledger):
    periods, game, worker, gateway, identity = active(ledger)
    action = start(game, play="go_off_duty", off_duty_id=identity)
    tick(worker, gateway)
    answer(game, PLAYER, "tag_window", options=("pass",))
    old = game.choices(OTHER)[0]
    game.abort(ADMIN, "abort", action)
    with pytest.raises(WorkflowError, match="permissions"):
        resume(game, PLAYER, "too-soon", action, game.inspect(PLAYER, action)["revision"])
    tick(worker, gateway, 5)
    revision = game.inspect(PLAYER, action)["revision"]
    with pytest.raises(WorkflowError, match="acting Pilot"):
        resume(game, OTHER, "wrong", action, revision)
    result = resume(game, PLAYER, "resume", action, revision)
    assert result["receipt_preserved"]
    assert resume(game, PLAYER, "resume", action, revision) == result
    assert game.choices(PLAYER) == []
    assert game.choices(OTHER)[0]["revision"] == old["revision"] + 1
    tick(GameWorker(game), gateway, 3)
    assert game.dice.calls == 1
    answer(game, OTHER, "tag_window", options=("pass",))
    answer(game, ADMIN, "tag_window", options=("pass",))
    assert saved(periods, identity).progress["2"].roll.stage == "choices"
    assert game.dice.calls == 1


def test_stale_status_cancels_only_unrolled_and_new_confirmation_uses_current_status(ledger):
    periods, game, worker, gateway, identity = active(ledger)
    action = start(game, play="go_off_duty", off_duty_id=identity)
    with ledger.transaction() as c:
        current = state(game)
        current.order = (3, 2)
        game.event(c, 1, "off-duty-fixture-rank", "synthetic.rank", current)
    tick(worker, gateway)
    assert game.dice.calls == 0
    game.abort(ADMIN, "abort", action)
    tick(worker, gateway, 5)
    cancel_unrolled(game, PLAYER, "cancel", action, game.inspect(PLAYER, action)["revision"])
    new = start(game, play="go_off_duty", off_duty_id=identity)
    assert new != action
    tick(worker, gateway, 2)
    assert saved(periods, identity).progress["2"].roll.modifier == 0
    assert game.dice.calls == 1
    game.abort(ADMIN, "abort-rolled", new)
    tick(worker, gateway, 5)
    with pytest.raises(WorkflowError, match="unrolled"):
        cancel_unrolled(game, PLAYER, "reroll", new, game.inspect(PLAYER, new)["revision"])


def test_policy_revocation_and_safety_pause_prevent_roll_and_choices(ledger):
    periods, game, worker, gateway, identity = active(ledger)
    start(game, play="go_off_duty", off_duty_id=identity)
    policy = ledger.policy
    ledger.policy = policy.model_copy(update={"m3_approval": None})
    tick(worker, gateway)
    assert game.dice.calls == 0
    ledger.policy = policy
    tick(worker, gateway)
    assert game.dice.calls == 1
    ledger.safety(OTHER, "pause", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        answer(game, PLAYER, "tag_window", options=("pass",))
    ledger.safety(OTHER, "resume", ledger.status(OTHER)["revision"], pause=False)
    pass_tags(game)
    assert saved(periods, identity).progress["2"].roll.stage == "choices"


def test_period_write_failure_rolls_back_receipt_identity_spend_and_history(ledger, monkeypatch):
    import asyncio

    periods, game, worker, gateway, identity = active(ledger)
    before = state(game).sheets["2"]
    chosen = next(x.id for x in before.identities if not x.marked)
    action = start(game, play="go_off_duty", off_duty_id=identity, identity=chosen, gain=1)
    job = worker.claim("m2_locks", ("acquiring",))
    asyncio.run(worker.acquire(job, gateway))
    original = OffDutyService._save

    def fail(*args):
        raise RuntimeError("synthetic persistence failure")

    monkeypatch.setattr(OffDutyService, "_save", fail)
    with pytest.raises(RuntimeError, match="persistence"):
        game.roll(PLAYER, "roll", action)
    assert game.inspect(PLAYER, action)["receipt"] is None
    assert saved(periods, identity).progress["2"].roll is None
    assert state(game).sheets["2"] == before
    assert game.choices(PLAYER) == []
    monkeypatch.setattr(OffDutyService, "_save", original)
    result = game.roll(PLAYER, "roll", action)
    assert game.roll(PLAYER, "roll", action) == result
    assert state(game).sheets["2"].heat == before.heat + 1
    assert saved(periods, identity).progress["2"].roll.stage == "tag_window"


def test_m3_repeated_tag_embrace_keeps_same_named_cards_distinct_and_slot_bound(ledger):
    periods, game, worker, gateway, identity = active(ledger, (1, 1))
    before = state(game).sheets["2"]
    label = before.identities[0].name
    replaced = before.identities[1]
    with ledger.transaction() as c:
        current = state(game)
        current.sheets["2"].tags.append(
            TagState(id="repeat", label=label, giver=3, observers=(1, 2, 3), marked=True)
        )
        game.event(c, 1, "duplicate-label-source", "synthetic.tag", current)
    action = start(game, play="go_off_duty", off_duty_id=identity)
    tick(worker, gateway)
    answer(game, PLAYER, "tag_window", options=("pass",))
    answer(
        game,
        OTHER,
        "tag_window",
        options=("tag",),
        denied=("repeat",),
        number=1,
        text="A relevant known Tag",
    )
    answer(game, ADMIN, "tag_window", options=("pass",))
    game.abort(ADMIN, "interrupt-after-tag", action)
    tick(worker, gateway, 5)
    resume(game, PLAYER, "resume-after-tag", action, game.inspect(PLAYER, action)["revision"])
    tick(worker, gateway, 2)
    answer(game, PLAYER, "tag_resolution", options=("embrace",), denied=(replaced.id,))
    final = state(game).sheets["2"]
    cards = [x for x in final.identities if x.name == label]
    assert len(cards) == 2 and len({x.id for x in cards}) == 2
    assert any(x.slot == replaced.slot for x in cards)
    assert periods.get(PLAYER, identity)["revision"] > 1
    assert saved(periods, identity).progress["2"].roll.stage == "choices"
    assert game.dice.calls == 1
