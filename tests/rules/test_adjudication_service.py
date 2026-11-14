"""Source surgery never deadlocks mandatory outcomes or restores a forbidden roll."""

from uuid import uuid4

import pytest
from test_defeat_service import required
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick

from girlframe.engine import m3_lobotomy as surgery_rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_lobotomy_state import Plan, Surgery
from girlframe.services.m3_adjudication import AdjudicationService
from girlframe.services.onboarding import WorkflowError


def forbid(game, owner, play):
    # Synthetic source surgery: all actual-choice phases are separately service-tested.
    with game.store.transaction() as c:
        canon = state(game)
        source, identity = str(uuid4()), str(uuid4())
        canon.lobotomies.append(
            Surgery(
                id=identity,
                subject=current_ref(canon, owner),
                inflictor=current_ref(canon, 1),
                work_ids=("synthetic-source-severe-work",),
                source_event="synthetic-severe-source",
            )
        )
        selected = Plan(
            options=("play",),
            room="Synthetic room",
            restraints="Synthetic restraints",
            tools="Synthetic tools",
            forbidden_play=play,
        )
        canon = surgery_rules.prepare(canon, identity, selected, "synthetic-inflictor-plan")
        canon = surgery_rules.respond(
            canon,
            identity,
            {"play": "Synthetic original patient response"},
            "synthetic-patient-source",
        )
        canon = surgery_rules.apply(canon, identity, source, allow_duplicate_labels=False)
        game.event(
            c,
            1,
            str(uuid4()),
            "m3.punishment_applied",
            canon,
            event_id=source,
            punishment="lobotomization",
        )


def test_forbidden_required_defeat_uses_actual_handler_manual_total_then_real_owned_outcome(ledger):
    game, worker, gateway, parent = required(ledger)
    forbid(game, 2, "defeat")
    before, calls = state(game).sheets["2"].heat, game.dice.calls
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="defeat",
            parent=parent,
            heat=0,
            context="Actual mandatory consequence",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    assert game.inspect(PLAYER, identity)["state"] == "awaiting_adjudication"
    assert game.dice.calls == calls and state(game).sheets["2"].heat == before
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "manual_adjudication")
    service = AdjudicationService(ledger)
    data = service.get(ADMIN, row["id"])
    with pytest.raises(WorkflowError):
        service.submit(
            PLAYER,
            str(uuid4()),
            row["id"],
            data["revision"],
            11,
            "The patient cannot assign her own favorable result",
        )
    result = service.submit(
        ADMIN,
        "actual-handler-adjudication",
        row["id"],
        data["revision"],
        8,
        "The source circumstances permit this defined consequence tier without a roll",
    )
    assert result["receipt"]["faces"] is None
    assert game.dice.calls == calls and state(game).sheets["2"].heat == before
    assert (
        service.submit(
            ADMIN,
            "actual-handler-adjudication",
            row["id"],
            data["revision"],
            8,
            "The source circumstances permit this defined consequence tier without a roll",
        )
        == result
    )
    assert not service.get(ADMIN, row["id"])["can_act"]
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("escape_cockpit_choose_location",),
        text="Actual original Girl escapes the damaged cockpit",
    )
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert surgery_rules.blocked_play(state(game).sheets["2"], "defeat") is not None
    assert game.dice.calls == calls


def test_voluntary_forbidden_play_is_blocked_without_a_manual_override_or_rng(ledger):
    from test_beneath_service import ready

    game, _, _ = ready(ledger)
    forbid(game, 2, "keep_your_head")
    with pytest.raises(WorkflowError, match="cannot roll"):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="keep_your_head",
                heat=0,
                context="A voluntary source trigger",
                trigger_confirmed=True,
            ),
        )
    assert game.dice.calls == 0 and not game.choices(ADMIN)


def manual_period(game, period, play):
    from test_m2_game import Gateway

    from girlframe.delivery.m2_worker import GameWorker

    before = state(game).order
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=play,
            off_duty_id=period,
            heat=0,
            context="Actual mandatory period Play",
            trigger_confirmed=True,
        ),
    )["action_id"]
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    assert game.dice.calls == 0 and state(game).order == before
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "manual_adjudication")
    service = AdjudicationService(game.store)
    current = service.get(ADMIN, row["id"])
    service.submit(
        ADMIN,
        str(uuid4()),
        row["id"],
        current["revision"],
        2 if play == "void_observation" else 8,
        "The Handler explicitly assigns this total from the actual circumstances, without dice",
    )
    pass_tags(game)
    tick(worker, gateway, 8)
    return identity


def no_frame_trigger(cycle, game, period):
    from girlframe.engine.m3_frame_rewards import Claim
    from girlframe.services.m3_frame_rewards import RewardService

    service = RewardService(cycle.periods)
    for row in cycle.periods.get(PLAYER, period)["work"]:
        if row["kind"] != "frame_off_duty_reward":
            continue
        data = service.get(PLAYER, row["id"])
        if data["owner_id"] == "2" and data["mode"] == "conditional":
            service.apply(
                PLAYER,
                str(uuid4()),
                row["id"],
                data["revision"],
                data["game_revision"],
                Claim(fulfilled=False, account="No actual Frame trigger"),
            )


def test_forbidden_go_off_duty_manual_source_reaches_actual_optional_scene_and_recovery(ledger):
    from test_m2_game import Dice
    from test_off_duty_cycle import activate, call, prepared

    from girlframe.engine.m3_off_duty import RecoveryChoice

    cycle, game, period = prepared(ledger)
    forbid(game, 2, "go_off_duty")
    activate(cycle, game, period)
    game.dice = Dice((6, 6))
    identity = manual_period(game, period, "go_off_duty")
    with ledger.engine.connect() as c:
        actual = cycle.periods._get(c, period).progress["2"].roll
    assert actual.faces is None and actual.adjudication.total == 8 and actual.total == 8
    from girlframe.services.m3_dose_up import _roll_source

    with ledger.engine.connect() as c:
        action = game.action(c, identity)
        source, total = _roll_source(game, c, action)
        assert source == action["data"]["receipt"]["adjudication"]["source_event"]
        assert total == 8 and action["data"]["receipt"]["rng_source"] == "manual_adjudication"
    no_frame_trigger(cycle, game, period)
    call(cycle, game, PLAYER, period, "scene", None, (), "")
    call(cycle, game, PLAYER, period, "recover", RecoveryChoice())
    assert cycle.review(PLAYER, period)["own"]["recovered"] and game.dice.calls == 0
    assert game.inspect(PLAYER, identity)["receipt"]["faces"] is None


def test_forbidden_observation_manual_total_keeps_actual_demotion_and_owned_outcome_attendance(
    ledger,
):
    from test_observation_service import apply, pending, select, setup
    from test_off_duty_cycle import call

    from girlframe.engine.m3_observation_state import Details
    from girlframe.engine.m3_off_duty import RecoveryChoice

    observation, cycle, game, period = setup(ledger)
    forbid(game, 2, "void_observation")
    assert state(game).order == (2, 3)
    manual_period(game, period, "void_observation")
    assert state(game).order == (3, 2) and game.dice.calls == 0
    select(observation, PLAYER, period, ("harpy_candidate_tag",))
    effect = pending(observation, PLAYER, period)
    apply(
        observation, PLAYER, effect, Details(account="The original Girl receives the printed Tag")
    )
    call(
        cycle,
        game,
        PLAYER,
        period,
        "scene",
        "observation:harpy_candidate_tag",
        (2, 1),
        "Actual shared original-Girl and Handler scene",
    )
    call(cycle, game, PLAYER, period, "acknowledge", 2)
    call(cycle, game, ADMIN, period, "acknowledge", 2)
    no_frame_trigger(cycle, game, period)
    call(cycle, game, PLAYER, period, "recover", RecoveryChoice())
    assert cycle.review(PLAYER, period)["own"]["recovered"] and game.dice.calls == 0
    assert not any(
        x.kind == "void_observation" and x.state == "pending" for x in state(game).obligations
    )
