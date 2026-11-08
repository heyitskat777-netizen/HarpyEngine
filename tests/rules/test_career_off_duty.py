"""An actual career ending closes original participation, without fake recovery."""

from uuid import uuid4

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, Gateway, answer, state, tick
from test_off_duty_cycle import activate, call, movement, prepared, roll_for
from test_off_duty_discipline import apply, task

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_off_duty import RecoveryChoice
from girlframe.engine.m3_punishments import Details
from girlframe.services.m3_careers import CareerService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.onboarding import WorkflowError


def roll_survivor(cycle, game, identity):
    game.dice = Dice((2, 2))
    game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="go_off_duty",
            off_duty_id=identity,
            heat=0,
            context="Actual surviving Girl goes Off-Duty",
            trigger_confirmed=True,
        ),
    )
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    for viewer in (ADMIN, OTHER, PLAYER):
        if any(row["kind"] == "tag_window" for row in game.choices(viewer)):
            answer(game, viewer, "tag_window", options=("pass",))
    tick(worker, gateway, 8)
    from girlframe.engine.m3_frame_rewards import Claim
    from girlframe.services.m3_frame_rewards import RewardService

    rewards = RewardService(cycle.periods)
    for row in cycle.periods.get(OTHER, identity)["work"]:
        if row["kind"] == "frame_off_duty_reward":
            data = rewards.get(OTHER, row["id"])
            rewards.apply(
                OTHER,
                str(uuid4()),
                row["id"],
                data["revision"],
                data["game_revision"],
                Claim(fulfilled=False, account="No actual printed trigger"),
            )


def executed_during_off_duty(store):
    cycle, game, identity = prepared(store)
    activate(cycle, game, identity)
    call(
        cycle,
        game,
        ADMIN,
        identity,
        "handler_scene",
        "punish",
        (1, 2),
        "An actual owned Handler scene",
        2,
    )
    work = task(cycle, identity)["id"]
    call(cycle, game, ADMIN, identity, "acknowledge", None)
    call(cycle, game, PLAYER, identity, "acknowledge", None)
    apply(PunishmentService(store), work, Details(kind="execution"))
    return cycle, game, identity


def test_survivor_finishes_real_off_duty_after_execution_without_healing_the_archived_girl(ledger):
    cycle, game, identity = executed_during_off_duty(ledger)
    archive = state(game).career_archives[-1]
    with ledger.engine.connect() as c:
        period = cycle.periods._get(c, identity)
    assert period.ended_characters == {"2": archive.actor.incarnation}
    assert period.progress["2"].career_ended == archive.id
    assert not period.progress["2"].recovered and period.progress["2"].roll is None
    before = archive.sheet_json
    roll_survivor(cycle, game, identity)
    call(cycle, game, OTHER, identity, "scene", None, (), "")
    call(cycle, game, OTHER, identity, "recover", RecoveryChoice())
    call(cycle, game, ADMIN, identity, "review_status", (3,), "Actual surviving roster")
    outcome = call(cycle, game, ADMIN, identity, "finish", movement(game))
    assert outcome["phase"] == "complete"
    assert state(game).career_archives[-1].sheet_json == before
    assert cycle.review(PLAYER, identity)["own"]["career_ended"] == archive.id
    assert cycle.review(PLAYER, identity)["sheet"] is None


def test_ended_original_cannot_claim_recovery_or_another_roll(ledger):
    cycle, game, identity = executed_during_off_duty(ledger)
    with pytest.raises(WorkflowError, match="original living Girl"):
        call(cycle, game, PLAYER, identity, "recover", RecoveryChoice())
    assert "2" not in state(game).sheets
    assert CareerService(ledger).archives(PLAYER)[0]["ending"] == "execution"


def test_incomplete_other_scene_is_reselected_without_forging_the_dead_participants_attendance(
    ledger,
):
    cycle, game, identity = prepared(ledger)
    activate(cycle, game, identity)
    roll_for(cycle, game, identity, OTHER, (4, 5))
    call(cycle, game, OTHER, identity, "scene", "barracks", (2, 3), "Planned actual scene")
    call(cycle, game, OTHER, identity, "acknowledge", 3)
    call(cycle, game, ADMIN, identity, "handler_scene", "punish", (1, 2), "Actual Handler scene", 2)
    work = task(cycle, identity)["id"]
    call(cycle, game, ADMIN, identity, "acknowledge", None)
    call(cycle, game, PLAYER, identity, "acknowledge", None)
    apply(PunishmentService(ledger), work, Details(kind="execution"))
    with ledger.engine.connect() as c:
        period = cycle.periods._get(c, identity)
    assert period.progress["3"].scene is None and not period.progress["3"].recovered
    call(cycle, game, OTHER, identity, "scene", None, (), "")
    call(cycle, game, OTHER, identity, "recover", RecoveryChoice())
