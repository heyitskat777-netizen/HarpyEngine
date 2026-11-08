"""One actual same-NPC control handover; broader lineage stays deferred to P1."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_body_facts import ready, record
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter import m3_changeling as native
from girlframe.engine import m3_changeling as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_changeling import ChangelingService
from girlframe.services.onboarding import WorkflowError


def test_real_npc_claim_hands_pending_question_to_current_role_without_rewriting_history(
    ledger, tmp_path, monkeypatch
):
    game, bodies, world, casts = ready(ledger, tmp_path, monkeypatch)
    owner = current_ref(state(game), 2)
    starting = state(game).sheets["2"].review.creation.npc_bonds[0]
    npc = Npc(
        id="original-question-subject",
        name=starting.name or "Original starting person",
        jobs=("civilian",),
        controller=1,
        cell=(0, 0),
        revealed=True,
        detail="Actual original starting counterpart",
    )
    world.npc(ADMIN, str(uuid4()), state(game).revision, npc)
    world.claim_npc(OTHER, str(uuid4()), state(game).revision, npc.id)
    world.import_starting_npc(PLAYER, str(uuid4()), state(game).revision, starting.slot, npc.id)
    target = ActorRef(kind="npc", entity=npc.id)
    shown = casts.view(OTHER, 900)
    casts.change(
        OTHER, str(uuid4()), 900, shown["game_revision"], shown["cast_revision"], "join", target
    )
    bodies.record(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        target,
        "human_npc",
        "Witnessed original human brain in this actual NPC body",
    )
    record(game, bodies, PLAYER)
    bodies.establish_npc_original(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        owner,
        starting.slot,
        "This is the genuine original person from the saved starting relationship",
    )
    offered = bodies.menu(PLAYER, 900)["imports"][0]
    bodies.import_starting(
        PLAYER, str(uuid4()), state(game).revision, owner, offered["source_event"]
    )
    node = next(x for x in rules.records(state(game), rules.String) if x.subject.actor == target)
    controls = ChangelingService(game)
    used = controls.fingers(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        node.id,
        "question",
        "Consume the actual original String",
        question="What do you need from us?",
    )
    use = rules.get(state(game), used["id"])
    assert use.question and not rules.reciprocal(use.subject)
    original = rules.record(state(game), rules.Question, use.question)
    with pytest.raises(WorkflowError):
        controls.view(ADMIN, original.id)  # Handler privilege does not disclose it.
    world.claim_npc(ADMIN, str(uuid4()), state(game).revision, npc.id)
    with pytest.raises(WorkflowError):
        controls.answer(OTHER, str(uuid4()), state(game).revision, original.id, "Old controller")
    with pytest.raises(WorkflowError, match="Join"):
        controls.answer(ADMIN, str(uuid4()), state(game).revision, original.id, "Before joining")
    prior_cast = casts.view(OTHER, 900)
    casts.change(
        OTHER,
        str(uuid4()),
        900,
        prior_cast["game_revision"],
        prior_cast["cast_revision"],
        "withdraw",
        target,
    )
    shown = casts.view(ADMIN, 900)
    casts.change(
        ADMIN, str(uuid4()), 900, shown["game_revision"], shown["cast_revision"], "join", target
    )
    with ledger.engine.connect() as c:
        assert any(x["id"] == original.id and x["pending"] for x in controls._tasks(c, ADMIN))
        assert not any(x["id"] == original.id for x in controls._tasks(c, OTHER))
    monkeypatch.setattr(native, "viewer_from_interaction", lambda interaction: ADMIN)

    async def answer_native():
        opened = current(1, 813001)
        opened.channel_id = 999
        await opened.response.defer(ephemeral=True)
        await native.open_changeling(opened, controls, original.id)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values["answer"] = "A genuine plan.\n  PRIVATE_CURRENT_NPC_ANSWER"
        submitted = current(1, 813002)
        await form.confirm.callback(submitted)
        assert form.completed
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(answer_native())
    answered = rules.record(state(game), rules.Question, original.id)
    assert answered.model_copy(update={"answer": None, "answer_event": None}) == original
    assert answered.answerer.controller == OTHER.user_id
    assert rules.get(state(game), use.id).completed_event
    assert controls.view(ADMIN, original.id)["body"]["answer"] == answered.answer
    assert controls.view(PLAYER, original.id)["body"]["answer"] == answered.answer
    with pytest.raises(WorkflowError):
        controls.view(OTHER, original.id)
    with ledger.engine.connect() as c:
        assert (
            c.scalar(sa.select(t.events.c.actor_id).where(t.events.c.id == answered.answer_event))
            == "1"
        )
    assert rules.record(state(game), rules.String, node.id).spent_by == use.id
