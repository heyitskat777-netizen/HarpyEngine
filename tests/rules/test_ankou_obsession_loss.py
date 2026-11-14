"""A genuine NPC death causes all five original Feedback results before replacement."""

import asyncio
from uuid import uuid4

import pytest
from test_ankou import buy, ready
from test_gorgon_service import apply as attack
from test_gorgon_service import selection
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_world import gorgon
from test_world_service import transfer_npc

from girlframe.delivery.p1_source_pause_worker import SourcePauseWorker
from girlframe.engine import m3_ankou as rules
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Npc
from girlframe.services import m3_ankou_feedback_sequences as sequences
from girlframe.services.m3_gorgon import GorgonService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_npc_obsession_death_requires_five_feedback_results_before_replacement(
    ledger, tmp_path, monkeypatch
):
    game, _, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    world = WorldService(MissionService(ledger))
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="original-obsession",
            name="Original living person",
            jobs=("guard",),
            controller=1,
            detail="Actual original NPC",
            cell=(0, 0),
            revealed=True,
        ),
    )
    transfer_npc(world, ADMIN, OTHER, "original-obsession")
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            gorgons=(*canon.world.gorgons, gorgon("erratic", "hunter", name="Actual hunter")),
        )
        game.event(c, 1, str(uuid4()), "synthetic.original_gorgon_position", canon)
    buy(controls, rules.OBSESSIVE)
    target = ActorRef(kind="npc", entity="original-obsession")
    actor, replacement = current_ref(state(game), 2), current_ref(state(game), 3)
    obsession = controls.choose_obsession(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        target,
        "My actual one-sided Obsession",
    )["id"]
    gorgons = GorgonService(world)
    data, chosen = selection(gorgons)
    assert chosen.target == target
    death = attack(gorgons, data=data, attack=chosen)
    after_death = state(game)
    assert not next(x for x in after_death.world.npcs if x.id == target.entity).alive
    ended = rules.get(after_death, rules.Obsession, obsession)
    assert ended.ended_event == death["id"] and ended.sequence
    sequence = rules.get(after_death, rules.FeedbackSequence, ended.sequence)
    assert sequence.count == 5 and sequence.reason == "obsession" and sequence.source == obsession
    assert not sequence.steps and sequence.venue is None
    with pytest.raises(WorkflowError, match="all5"):
        controls.choose_obsession(
            PLAYER,
            str(uuid4()),
            after_death.revision,
            replacement,
            "Too early",
        )
    assert state(game) == after_death
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
            replacement,
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
                    replacement,
                    "Still too early",
                )
            assert state(game) == done
    final = state(game)
    assert len(set(step_ids)) == 5
    assert rules.get(final, rules.FeedbackSequence, sequence.id).completed_event
    assert is_helpless(final, actor, replacement)
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
    assert not next(x for x in after.world.npcs if x.id == target.entity).alive
    assert game.dice.calls == 0
