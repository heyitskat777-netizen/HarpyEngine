"""Actual ordinary NPC use, then the original Newgirl's optional Bond choice."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_easy_target import _npc_protection_native, ready, source
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.database import tables as t
from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_easy_target import EasyTargetService, prove_npc_use
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("deepen", [True, False], ids=["deepen", "decline"])
def test_native_actual_npc_use_then_owned_bond(ledger, tmp_path, monkeypatch, deepen):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, mixed=True)
    npc = ActorRef(kind="npc", entity="bystander")
    identity = source(game, worker, gateway, selected=npc)
    work = rules.identity(identity, npc)
    calls = game.dice.calls
    receipt = game.inspect(PLAYER, identity)["receipt"]

    def submit(viewer, kind, values, interaction_id):
        row = next(x for x in game.choices(viewer) if x["kind"] == kind + ":" + npc.token)
        asyncio.run(_npc_protection_native(game, viewer.user_id, row, values, interaction_id))

    submit(
        OTHER,
        "easy_target_react",
        dict(
            urge=("use",),
            context="I use her as the audience for an ordinary rehearsal, triggering no Play",
            account="PRIVATE_NPC_USE I choose to use her as my audience",
        ),
        99800,
    )
    reaction = rules.get(state(game), rules.Reaction, work)
    assert reaction.performer == npc and reaction.play is None and reaction.child is None
    assert not any(x["kind"].startswith("easy_target_bond") for x in game.choices(PLAYER))
    submit(
        ADMIN,
        "easy_target_validate",
        dict(
            yes=("yes",),
            account="This ordinary rehearsal has no separate Play or mechanical effect",
        ),
        99810,
    )
    perform = next(x for x in game.choices(OTHER) if x["kind"] == "easy_target_child:" + npc.token)
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            perform["id"],
            perform["revision"],
            ChoiceAnswer(text="I cannot perform as the other controller's NPC"),
        )
    before = state(game)
    original_depth = depth(before, current_ref(before, 2), npc)
    submit(
        OTHER,
        "easy_target_child",
        dict(account="PRIVATE_USE_PERFORMED I finished rehearsing my ordinary speech to her"),
        99820,
    )
    actual = state(game)
    performance = rules.records(actual, rules.NpcUse)[-1]
    assert performance.actor == npc and performance.controller == OTHER.user_id
    assert performance.target == current_ref(actual, 2) and performance.session == identity
    assert actual.sheets == before.sheets and actual.world == before.world
    assert depth(actual, current_ref(actual, 2), npc) == original_depth
    assert not rules.get(actual, rules.Reaction, work).completed_event
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    with game.store.engine.connect() as c:
        assert prove_npc_use(game, c, actual, performance.id) == performance
        forged = actual.model_copy(deep=True)
        rules.put(forged, performance.model_copy(update={"account": "Invented performance"}))
        with pytest.raises(WorkflowError, match="canonical original"):
            prove_npc_use(game, c, forged, performance.id)
    # Durable private readback works through a fresh service before choosing the Bond.
    assert EasyTargetService(game).view(PLAYER, work)["npc_use"][0]["id"] == performance.id
    submit(
        PLAYER,
        "easy_target_bond",
        dict(
            yes=("yes" if deepen else "no",), account="My own choice after the actual completed use"
        ),
        99830,
    )
    final = state(game)
    reaction = rules.get(final, rules.Reaction, work)
    assert reaction.completed_event and reaction.consequence == (
        "bond" if deepen else "bond-declined"
    )
    assert depth(final, current_ref(final, 2), npc) == original_depth + int(deepen)
    assert len(rules.records(final, rules.NpcUse)) == 1
    assert not reaction.child and not reaction.protection_event and not reaction.harm
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert game.dice.calls == calls and game.inspect(PLAYER, identity)["receipt"] == receipt
    assert controls.view(OTHER, work)["npc_use"][0]["account"] == performance.account
    with game.store.engine.connect() as c:
        assert "PRIVATE_USE_PERFORMED" not in str(
            list(c.scalars(sa.select(t.events.c.payload_json)))
        )
