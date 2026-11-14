"""Actual Oldgen advice turns the tables after failed Brutalize; no invented response."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_enforcer_requisitions import approved
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_oldgen import native_choice
from test_oldgen_sleep_counter import PEOPLE, interaction, ready

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_alpha import open_alpha_choice
from girlframe.engine import m3_alpha as alpha
from girlframe.engine import m3_oldgen as oldgen
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_alpha import advice_counter, counter_plays
from girlframe.services.m3_oldgen import OldgenService, prove_advice
from girlframe.services.onboarding import WorkflowError


def test_native_oldgen_brutalize_counter_waits_for_owned_advice_then_applies_broken(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway = ready(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(alpha.RULE, oldgen.RULE, oldgen.ADVICE))
    original = state(game)
    attacker, adviser = (current_ref(original, owner) for owner in (2, 3))
    parent = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        original.sheets["2"].revision,
        PlayInput(
            play="brutalize",
            target_actor=adviser,
            heat=0,
            context="I actually tear into the Oldgen with words, fists and teeth",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 4)
    for viewer in PEOPLE:
        answer(game, viewer, "tag_window", options=("pass",))
    parent_receipt = game.inspect(PLAYER, parent)["receipt"]
    answer(game, OTHER, "alpha_low", options=("counter_broken",))
    choice = next(x for x in game.choices(OTHER) if x["kind"] == "alpha_counter_play")
    prepared = PlayInput(
        play=oldgen.PLAY,
        parent=parent,
        target=2,
        heat=1,
        context="PRIVATE_BRUTALIZE_ADVICE I advise the Alpha how to keep herself alive",
        trigger_confirmed=True,
    )
    before, calls = state(game), game.dice.calls
    with ledger.engine.connect() as c:
        assert oldgen.PLAY in counter_plays(game, c, before, game.action(c, parent), adviser)
        with pytest.raises(WorkflowError):
            advice_counter(game, c, before, adviser, prepared.model_copy(update={"target": 4}), 900)
        with pytest.raises(WorkflowError):
            advice_counter(game, c, before, attacker, prepared, 900)
    assert state(game) == before and game.dice.calls == calls
    assert not alpha.conditions(before, attacker, adviser)

    async def native():
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_alpha_choice(opened, game, choice["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert oldgen.PLAY in dict(next(x for x in form.fields if x.key == "play").options)
        assert not await form.interaction_check(interaction(2))
        form.values.update(play=(oldgen.PLAY,), heat=("1",), context=prepared.context)
        submitted = interaction()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(native())
    with ledger.engine.connect() as c:
        actions = t.m2["m2_actions"]
        child = game.action(
            c,
            c.scalar(
                sa.select(actions.c.id).where(
                    actions.c.campaign_id == ledger.campaign_id,
                    actions.c.parent_id == parent,
                    actions.c.actor_id == "3",
                )
            ),
        )
    identity = child["id"]
    assert child["data"]["alpha_counter_source"]["choice"] == choice["id"]
    assert child["data"]["oldgen"]["target"] == attacker.model_dump(mode="json")
    assert child["data"]["prepared"]["source_work"] is None
    assert state(game).sheets["3"].heat == before.sheets["3"].heat and game.dice.calls == calls
    game.dice.faces = (3, 4)
    tick(worker, gateway, 4)
    for viewer in PEOPLE:
        answer(game, viewer, "tag_window", options=("pass",))
    assert state(game).sheets["3"].heat == before.sheets["3"].heat - 1
    native_choice(game, OTHER, "oldgen_write_maxim", "PRIVATE_BRUTALIZE_MAXIM Keep yourself alive")
    owed = next(x for x in game.choices(PLAYER) if x["kind"] == "oldgen_listen")
    with pytest.raises(WorkflowError):
        game.decision(OTHER, owed["id"])
    assert game.inspect(OTHER, identity)["state"] != "complete"
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    assert not alpha.conditions(state(game), attacker, adviser)
    native_choice(game, PLAYER, "oldgen_listen", "I actually sit and listen to her advice")
    actual = state(game)
    assert game.inspect(OTHER, identity)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert alpha.conditions(actual, attacker, adviser)
    assert game.inspect(PLAYER, parent)["receipt"] == parent_receipt
    with ledger.engine.connect() as c:
        proof = prove_advice(game, c, actual, identity)
        assert proof.actor == adviser and proof.target == attacker and proof.total == 8
        assert proof.heat == 1 and proof.caster == 3 and proof.counterpart == 2
        assert game.action(c, identity)["data"]["alpha_counter_completed"]
        assert (
            c.scalar(sa.select(t.events.c.actor_id).where(t.events.c.id == proof.roll_event)) == "3"
        )
        assert "PRIVATE_BRUTALIZE" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
    maxim = next(x for x in oldgen.records(actual, oldgen.Maxim) if x.advice == identity)
    assert maxim.owner == adviser and maxim.subject == attacker
    with pytest.raises(WorkflowError):
        OldgenService(game).view(PLAYER, maxim.id)
    receipt = game.inspect(OTHER, identity)["receipt"]
    assert game.roll(OTHER, str(uuid4()), identity)["receipt"] == receipt
    assert game.dice.calls == calls + 1
    tick(worker, gateway, 4)
