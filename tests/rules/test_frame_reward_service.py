from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_off_duty_cycle import activate, prepared, roll_for

from girlframe.database import tables as t
from girlframe.engine.m3_frame_rewards import Claim
from girlframe.engine.m3_frame_state import FrameRuntime
from girlframe.services.m3_frame_rewards import RewardService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def setup(store):
    cycle, game, period = prepared(store)
    activate(cycle, game, period)
    return RewardService(cycle.periods), cycle, game, period


def own(svc, actor, period):
    return next(
        x for x in svc.periods.get(actor, period)["work"] if x["kind"] == "frame_off_duty_reward"
    )


def submit(svc, actor, work, choice, key=None):
    data = svc.get(actor, work)
    return svc.apply(
        actor, key or str(uuid4()), work, data["revision"], data["game_revision"], choice
    )


def test_janus_bonus_is_owned_post_roll_exactly_once_private_and_replay_safe(ledger):
    svc, cycle, game, period = setup(ledger)
    identity = own(svc, PLAYER, period)["id"]
    choice = Claim(fulfilled=True, official="handler:1", account="PRIVATE_DEMONSTRATION_ACCOUNT")
    with pytest.raises(WorkflowError, match="actual Off-Duty Play"):
        submit(svc, PLAYER, identity, choice)
    roll_for(cycle, game, period, PLAYER, (2, 2), review_reward=False)
    with pytest.raises(WorkflowError):
        submit(svc, OTHER, identity, choice)
    with pytest.raises(WorkflowError):
        submit(svc, ADMIN, identity, choice)
    data = svc.get(PLAYER, identity)
    assert data["ready"] and data["frame"] == "JANUS"
    initial = state(game).sheets["2"].permissions
    result = svc.apply(
        PLAYER, "frame-bonus", identity, data["revision"], data["game_revision"], choice
    )
    assert (
        svc.apply(PLAYER, "frame-bonus", identity, data["revision"], data["game_revision"], choice)
        == result
    )
    assert state(game).sheets["2"].permissions == initial + 1
    with pytest.raises(WorkflowError):
        submit(svc, PLAYER, identity, choice)
    with ledger.engine.connect() as c:
        metadata = str(list(c.scalars(sa.select(t.events.c.payload_json))))
        outcomes = str(list(c.scalars(sa.select(t.commands.c.outcome_json))))
        assert "PRIVATE_DEMONSTRATION_ACCOUNT" not in metadata + outcomes


def test_no_trigger_cannot_be_forged_for_another_owner_and_has_no_reward(ledger):
    svc, cycle, game, period = setup(ledger)
    roll_for(cycle, game, period, PLAYER, review_reward=False)
    identity = own(svc, PLAYER, period)["id"]
    choice = Claim(fulfilled=False, account="The owner explicitly records no qualifying event")
    initial = state(game).sheets["2"].permissions
    assert not submit(svc, PLAYER, identity, choice)["reward_granted"]
    assert state(game).sheets["2"].permissions == initial


def test_frozen_frame_context_does_not_restore_old_resources_or_grant_new_frames_bonus(ledger):
    svc, cycle, game, period = setup(ledger)
    roll_for(cycle, game, period, PLAYER, review_reward=False)
    identity = own(svc, PLAYER, period)["id"]
    with ledger.transaction() as c:
        current = state(game)
        current.sheets["2"].frame = "CONSUME"
        current.sheets["2"].frame_runtime = FrameRuntime(
            id="new-frame", generation=1, source_work="synthetic-swap", consume_hunger="Quiet"
        )
        current.sheets["2"].heat = 12
        current.sheets["2"].revision += 1
        game.event(c, 1, "after-roll-frame", "synthetic.frame_change", current)
    assert svc.get(PLAYER, identity)["frame"] == "JANUS"
    submit(
        svc,
        PLAYER,
        identity,
        Claim(
            fulfilled=True, official="handler:1", account="The prior Frame's actual demonstration"
        ),
    )
    final = state(game)
    assert (
        final.sheets["2"].frame == "CONSUME" and final.sheets["2"].frame_runtime.id == "new-frame"
    )
    assert final.sheets["2"].heat == 12 and final.sheets["2"].permissions == 1
    assert not [
        x for x in svc.periods.get(PLAYER, period)["work"] if x["kind"] == "frame_off_duty_reward"
    ]


def test_pre_roll_frame_change_supersedes_only_untriggered_candidate_and_uses_new_rule(ledger):
    svc, cycle, game, period = setup(ledger)
    old = own(svc, PLAYER, period)["id"]
    with ledger.transaction() as c:
        current = state(game)
        current.sheets["2"].frame = "PROJECT ANKOU"
        current.sheets["2"].frame_runtime = FrameRuntime(
            id="new-frame", generation=1, source_work="synthetic-swap"
        )
        current.sheets["2"].revision += 1
        game.event(c, 1, "before-roll-frame", "synthetic.frame_change", current)
    assert svc.get(PLAYER, old)["state"] == "resolved"
    current_work = own(svc, PLAYER, period)["id"]
    assert current_work != old
    roll_for(cycle, game, period, PLAYER, review_reward=False)
    assert svc.get(PLAYER, current_work)["frame"] == "PROJECT ANKOU"
    submit(
        svc,
        PLAYER,
        current_work,
        Claim(fulfilled=True, account="The actual actor minimized casualties"),
    )
    assert state(game).sheets["2"].permissions == 1


def test_failure_after_canonical_event_rolls_back_permission_and_work_and_retry_is_safe(
    ledger, monkeypatch
):
    svc, cycle, game, period = setup(ledger)
    roll_for(cycle, game, period, PLAYER, review_reward=False)
    identity = own(svc, PLAYER, period)["id"]
    before = state(game)
    original = svc.game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic post-event failure")

    monkeypatch.setattr(svc.game, "event", fail)
    choice = Claim(fulfilled=True, official="handler:1", account="An actual demonstration")
    with pytest.raises(RuntimeError):
        submit(svc, PLAYER, identity, choice, "retry")
    assert state(game) == before and svc.get(PLAYER, identity)["state"] == "pending"
    monkeypatch.setattr(svc.game, "event", original)
    submit(svc, PLAYER, identity, choice, "retry")
    assert state(game).sheets["2"].permissions == before.sheets["2"].permissions + 1


def test_concurrent_reviews_pause_and_changed_policy_cannot_grant_twice(ledger):
    svc, cycle, game, period = setup(ledger)
    roll_for(cycle, game, period, PLAYER, review_reward=False)
    identity = own(svc, PLAYER, period)["id"]
    choice = Claim(fulfilled=True, official="handler:1", account="An actual demonstration")
    data = svc.get(PLAYER, identity)
    ledger.safety(OTHER, "pause", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        submit(svc, PLAYER, identity, choice)
    ledger.safety(OTHER, "resume", ledger.status(OTHER)["revision"], pause=False)

    def attempt(key):
        try:
            return svc.apply(PLAYER, key, identity, data["revision"], data["game_revision"], choice)
        except WorkflowError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(attempt, ("one", "two")))
    assert sum(x is not None for x in result) == 1
    assert state(game).sheets["2"].permissions == 1


def test_queen_choice_stays_with_actual_holder_at_roll_after_later_court_transfer(ledger):
    svc, cycle, game, period = setup(ledger)
    with ledger.transaction() as c:
        current = state(game)
        current.sheets["2"].frame = "THE RED QUEEN"
        current.sheets["2"].frame_runtime = FrameRuntime(
            id="queen-frame",
            generation=1,
            source_work="synthetic-replacement",
            court={"The Queen": 3},
        )
        current.sheets["2"].revision += 1
        game.event(c, 1, "queen-before-roll", "synthetic.frame_change", current)
    roll_for(cycle, game, period, PLAYER, review_reward=False)
    work = next(
        x
        for x in svc.periods.get(OTHER, period)["work"]
        if x["kind"] == "frame_off_duty_reward"
        and svc.get(OTHER, x["id"])["frame"] == "THE RED QUEEN"
    )
    identity = work["id"]
    with ledger.transaction() as c:
        current = state(game)
        current.sheets["2"].frame_runtime = current.sheets["2"].frame_runtime.model_copy(
            update={"court": {"The Queen": 2}}
        )
        current.sheets["2"].revision += 1
        game.event(c, 1, "queen-after-roll", "synthetic.court_transfer", current)
    data = svc.get(OTHER, identity)
    assert data["owner_id"] == "3" and data["pilots"] == (("2", "SYNTH"),)
    with pytest.raises(WorkflowError, match="source decision owner"):
        svc.apply(
            PLAYER,
            "new-holder-cannot-retake-past-choice",
            identity,
            data["revision"],
            data["game_revision"],
            recipient=2,
            account="Not my original choice",
        )
    result = svc.apply(
        OTHER,
        "original-holder-chooses",
        identity,
        data["revision"],
        data["game_revision"],
        recipient=2,
        account="The actual original holder makes its choice",
    )
    assert result["reward_granted"] and state(game).sheets["2"].permissions == 1
    assert state(game).sheets["2"].frame_runtime.court["The Queen"] == 2


def test_frame_reward_private_projection_never_lists_hidden_officials(ledger):
    from girlframe.engine.m3_world_state import Npc
    from girlframe.services.m3_world import WorldService

    svc, cycle, game, period = setup(ledger)
    WorldService(cycle.missions).npc(
        ADMIN,
        "secret-npc",
        state(game).revision,
        Npc(
            id="secret-official",
            name="PRIVATE_SECRET_NAME",
            jobs=("scientist",),
            detail="Private role",
            controller=1,
            cell=(0, 0),
        ),
    )
    roll_for(cycle, game, period, PLAYER, review_reward=False)
    identity = own(svc, PLAYER, period)["id"]
    assert "PRIVATE_SECRET_NAME" not in str(svc.get(PLAYER, identity))
    with pytest.raises(WorkflowError, match="known official"):
        submit(
            svc,
            PLAYER,
            identity,
            Claim(fulfilled=True, official="npc:secret-official", account="A guessed private ID"),
        )
    with pytest.raises(WorkflowError, match="other participants"):
        svc.get(OTHER, identity)


@pytest.mark.parametrize("interested", (True, False))
def test_wyvern_offering_waits_for_actual_handlers_owned_opinion(ledger, interested):
    svc, cycle, game, period = setup(ledger)
    with ledger.transaction() as c:
        current = state(game)
        current.sheets["2"].frame = "WYVERN 0.4"
        current.sheets["2"].frame_runtime = FrameRuntime(
            id="wyvern", generation=1, source_work="synthetic-frame"
        )
        current.sheets["2"].revision += 1
        game.event(c, 1, "wyvern-frame", "synthetic.frame", current)
    roll_for(cycle, game, period, PLAYER, review_reward=False)
    identity = own(svc, PLAYER, period)["id"]
    result = submit(
        svc,
        PLAYER,
        identity,
        Claim(
            fulfilled=True, offering="PRIVATE_OFFERING", account="An actual offer for the Handler"
        ),
    )
    assert result["state"] == "awaiting_interest" and state(game).sheets["2"].permissions == 0
    child = next(
        x for x in svc.periods.get(ADMIN, period)["work"] if x["kind"] == "frame_reward_interest"
    )
    data = svc.get(ADMIN, child["id"])
    assert data["offering"] == "PRIVATE_OFFERING"
    assert "PRIVATE_OFFERING" not in str(svc.get(PLAYER, child["id"]))
    with pytest.raises(WorkflowError, match="recorded Handler"):
        svc.answer_interest(
            PLAYER,
            "cannot-choose-for-handler",
            child["id"],
            data["revision"],
            data["game_revision"],
            True,
        )
    with pytest.raises(WorkflowError):
        submit(
            svc,
            PLAYER,
            identity,
            Claim(fulfilled=False, account="Cannot erase the pending question"),
        )
    result = svc.answer_interest(
        ADMIN, "handler-answer", child["id"], data["revision"], data["game_revision"], interested
    )
    assert (
        svc.answer_interest(
            ADMIN,
            "handler-answer",
            child["id"],
            data["revision"],
            data["game_revision"],
            interested,
        )
        == result
    )
    assert state(game).sheets["2"].permissions == int(interested)
    assert svc.get(PLAYER, identity)["state"] == "resolved"
    with ledger.engine.connect() as c:
        assert "PRIVATE_OFFERING" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
