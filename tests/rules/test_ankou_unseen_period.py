"""An entire genuine Off-Duty without a sighting owes five real Feedback results."""

import asyncio
from uuid import uuid4

import pytest
import test_strain_effect_service
from test_ankou import buy
from test_cast_service import change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, state
from test_off_duty_cycle import activate, call, finish_routine, movement, prepared, recover_both
from test_physical_operations import place
from test_strain_service import ready as strain_ready

from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.engine import m3_ankou as rules
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services import m3_ankou_feedback_sequences as sequences
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_ankou import AnkouService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


def test_actual_unseen_off_duty_requires_owned_fact_and_five_feedback_results(
    ledger, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        test_strain_effect_service,
        "ready",
        lambda store, face: strain_ready(store, face=face, frame=rules.FRAME),
    )
    cycle, game, period = prepared(ledger)
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RELAY, *rules.REQUISITIONS))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    with ledger.transaction() as c:
        canon = place(place(state(game), 2, mode="outside_frame"), 3, mode="outside_frame")
        canon.sheets["2"].permissions = 10
        game.event(c, 1, str(uuid4()), "synthetic.prior_obsession_resources_positions", canon)
    cycle.missions.access = Access(ledger)
    controls = AnkouService(game)
    gateway = Gateway()
    buy(controls, rules.OBSESSIVE)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    cast = CastService(ActorService(MissionService(ledger)))
    change(cast, PLAYER, "withdraw", actor)
    change(cast, PLAYER, "join", actor)
    assert any(
        any(role.actor == actor for role in venue.roles) for venue in state(game).scene_casts
    )
    obsession = controls.choose_obsession(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        target,
        "My actual one-sided Obsession before this Off-Duty",
    )["id"]
    activate(cycle, game, period)
    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    result = call(cycle, game, ADMIN, period, "finish", movement(game))
    assert result["phase"] == "complete"
    ended_period = state(game)
    task = next(x for x in rules.records(ended_period, rules.Task) if x.kind == "missed_obsession")
    assert task.actor == actor and task.target == target and task.source == obsession
    assert task.options == (period,) and task.controller == PLAYER.user_id
    assert not rules.get(ended_period, rules.Obsession, obsession).ended_event
    for viewer, choice in ((ADMIN, "not_seen"), (PLAYER, "seen")):
        with pytest.raises(WorkflowError):
            controls.choose_task(
                viewer,
                str(uuid4()),
                ended_period.revision,
                task.id,
                choice,
                "Cannot invent another person's answer or a sighting",
            )
        assert state(game) == ended_period
    controls.choose_task(
        PLAYER,
        str(uuid4()),
        ended_period.revision,
        task.id,
        "not_seen",
        "I endured this entire actual Off-Duty without seeing my Obsession",
    )
    after_fact = state(game)
    ended = rules.get(after_fact, rules.Obsession, obsession)
    sequence = rules.get(after_fact, rules.FeedbackSequence, ended.sequence)
    assert sequence.count == 5 and sequence.reason == "obsession" and sequence.source == obsession
    assert ended.ended_event and rules.get(after_fact, rules.Task, task.id).completed_event
    assert not sequence.steps and sequence.venue is None
    with pytest.raises(WorkflowError, match="all5"):
        controls.choose_obsession(PLAYER, str(uuid4()), after_fact.revision, target, "Too early")
    assert state(game) == after_fact
    rolls_before_feedback = game.dice.calls
    sequences.activate(
        game,
        PLAYER,
        str(uuid4()),
        sequence.id,
        900,
        state(game).revision,
        "I face the actual loss in my genuinely joined scene",
    )
    asyncio.run(SourcePauseWorker(game).tick(gateway))
    step_ids = []
    for ordinal in range(1, 6):
        current = rules.get(state(game), rules.FeedbackSequence, sequence.id)
        assert len(current.steps) == ordinal and not current.completed_event
        step = rules.get(state(game), rules.FeedbackStep, current.steps[-1])
        assert step.ordinal == ordinal and step.phase == "choice"
        step_ids.append(step.id)
        sequences.choose(
            game,
            PLAYER,
            str(uuid4()),
            step.id,
            state(game).revision,
            "purpose",
            target,
            f"I make my actual purpose request for result {ordinal}",
        )
        awaiting = state(game)
        with pytest.raises(WorkflowError):
            sequences.answer_purpose(
                game,
                ADMIN,
                str(uuid4()),
                step.id,
                awaiting.revision,
                False,
                "Not the actual requested person",
            )
        assert state(game) == awaiting
        sequences.answer_purpose(
            game,
            OTHER,
            str(uuid4()),
            step.id,
            state(game).revision,
            False,
            f"My actual original character declines request {ordinal}",
        )
        done = state(game)
        assert rules.get(done, rules.FeedbackStep, step.id).completed_event
        if ordinal < 5:
            with pytest.raises(WorkflowError, match="all5"):
                controls.choose_obsession(
                    PLAYER,
                    str(uuid4()),
                    done.revision,
                    target,
                    "Still too early",
                )
            assert state(game) == done
    final = state(game)
    assert len(set(step_ids)) == 5
    assert rules.get(final, rules.FeedbackSequence, sequence.id).completed_event
    assert is_helpless(final, actor, target)
    with pytest.raises(WorkflowError, match="someone else"):
        controls.choose_obsession(
            PLAYER, str(uuid4()), final.revision, target, "The old person is not someone else"
        )
    assert state(game) == final
    replacement = active_handler(final)
    assert replacement is not None and replacement != target
    next_obsession = controls.choose_obsession(
        PLAYER,
        str(uuid4()),
        final.revision,
        replacement,
        "My actual new Obsession after all five",
    )["id"]
    after = state(game)
    assert rules.get(after, rules.Obsession, obsession).replacement_event
    assert rules.get(after, rules.Obsession, next_obsession).target == replacement
    assert game.dice.calls == rolls_before_feedback
