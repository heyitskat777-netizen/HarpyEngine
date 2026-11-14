"""Actual Flirt counter episodes retain owned answers, consequences, costs and parent proof."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_alpha_brutalize_counter import interaction, opportunity
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_alpha import open_alpha_choice
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_alpha import conditions
from girlframe.services.inbox import InboxService
from girlframe.services.m3_alpha import counter_plays
from girlframe.services.m3_alpha_flirt import counter
from girlframe.services.onboarding import WorkflowError


def begin_counter(game, worker, gateway, parent, choice, faces):
    before, calls = state(game), game.dice.calls
    actor, attacker = current_ref(before, 3), current_ref(before, 2)
    prepared = PlayInput(
        play="flirt",
        parent=parent,
        target=2,
        heat=1,
        context="PRIVATE_FLIRT_COUNTER I flirt with the original Alpha under this pressure",
        trigger_confirmed=True,
    )
    with game.store.engine.connect() as c:
        snapshot = before.model_copy(deep=True)
        assert "flirt" in counter_plays(game, c, before, game.action(c, parent), actor)
        assert before == snapshot
        for person, attempt in (
            (attacker, prepared),
            (actor, prepared.model_copy(update={"target": 3})),
            (actor, prepared.model_copy(update={"source_work": "invented"})),
        ):
            with pytest.raises(WorkflowError):
                counter(game, c, before, person, attempt, 900)
    assert state(game) == before and game.dice.calls == calls

    async def native():
        opened = interaction()
        await opened.response.defer(ephemeral=True)
        await open_alpha_choice(opened, game, choice["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert "flirt" in dict(next(x for x in form.fields if x.key == "play").options)
        assert not await form.interaction_check(interaction(2))
        form.values.update(play=("flirt",), heat=("1",), context=prepared.context)
        submitted = interaction()
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(native())
    with game.store.engine.connect() as c:
        actions = t.m2["m2_actions"]
        identity = c.scalar(
            sa.select(actions.c.id).where(
                actions.c.campaign_id == game.store.campaign_id,
                actions.c.parent_id == parent,
                actions.c.actor_id == "3",
            )
        )
        child = game.action(c, identity)
        assert child["data"]["prepared"] == prepared.model_dump(mode="json")
        assert child["data"]["alpha_counter_source"]["choice"] == choice["id"]
    assert state(game).sheets["3"].heat == before.sheets["3"].heat
    assert game.dice.calls == calls
    game.dice.faces = faces
    tick(worker, gateway, 4)
    pass_tags(game)
    assert state(game).sheets["3"].heat == before.sheets["3"].heat - 1
    assert state(game).sheets["2"].heat == before.sheets["2"].heat
    assert game.dice.calls == calls + 1
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    assert not conditions(state(game), attacker, actor)
    return identity


def finish_counter(game, worker, gateway, parent, receipt, child, *, broken):
    assert game.inspect(OTHER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    actual = state(game)
    assert bool(conditions(actual, current_ref(actual, 2), current_ref(actual, 3))) == broken
    assert game.inspect(PLAYER, parent)["receipt"] == receipt
    saved = game.inspect(OTHER, child)["receipt"]
    calls = game.dice.calls
    assert game.roll(OTHER, str(uuid4()), child)["receipt"] == saved
    assert game.dice.calls == calls == 2
    with game.store.engine.connect() as c:
        rows = (
            c.execute(
                sa.select(t.events.c.payload_json).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.kind == "m3.alpha_counter_completed",
                )
            )
            .scalars()
            .all()
        )
        assert len([x for x in rows if json.loads(x).get("child") == child]) == 1
    tick(worker, gateway, 8)
    assert "PRIVATE_FLIRT" not in json.dumps(gateway.messages)


def test_native_flirt_counter_mid_waits_for_alpha_answer_and_keeps_owned_followthrough(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, parent, receipt, choice = opportunity(ledger, tmp_path, monkeypatch)
    child = begin_counter(game, worker, gateway, parent, choice, (3, 4))
    answer(game, OTHER, "actor_flirt", options=("name",))
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "target_flirt")
    assert any(x.identity == row["id"] for x in InboxService(ledger).items(PLAYER))
    before = state(game)
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(text="Forged reply")
        )
    assert state(game) == before
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    answer(game, PLAYER, "target_flirt", text="PRIVATE_FLIRT_WANTED Call me by my chosen name")
    finish_counter(game, worker, gateway, parent, receipt, child, broken=True)
    owed = next(
        x
        for x in game.own_obligations(OTHER)
        if x["kind"] == "flirt_followthrough" and x["action"] == child
    )
    bond = state(game).bonds["2:3"]
    follow = game.fulfill(
        OTHER, str(uuid4()), 900, owed["id"], "PRIVATE_FLIRT_FOLLOW I use the name she asked for"
    )["action_id"]
    tick(worker, gateway, 4)
    assert state(game).bonds["2:3"] == bond
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "followthrough_confirm")
    with pytest.raises(WorkflowError):
        game.respond(OTHER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(flag=True))
    answer(game, PLAYER, "followthrough_confirm", flag=True, text="PRIVATE_FLIRT_CONFIRM She did")
    assert game.inspect(OTHER, follow)["state"] == "complete"
    assert state(game).bonds["2:3"] == min(2, bond + 1)
    assert next(x for x in state(game).obligations if x.id == owed["id"]).state == "fulfilled"
    tick(worker, gateway, 6)
    assert "PRIVATE_FLIRT" not in json.dumps(gateway.messages)
    assert game.dice.calls == 2


def test_native_flirt_counter_low_waits_for_return_answer_without_optional_broken(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, parent, receipt, choice = opportunity(
        ledger, tmp_path, monkeypatch, retaliate=False
    )
    before = state(game).bonds["2:3"]
    child = begin_counter(game, worker, gateway, parent, choice, (1, 2))
    assert state(game).bonds["2:3"] == max(0, before - 1)
    answer(game, PLAYER, "target_flirt", options=("name",), text="PRIVATE_FLIRT_DISTANCE Pressure")
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    answer(game, OTHER, "actor_flirt_answer", text="PRIVATE_FLIRT_RETURN My own chosen name")
    finish_counter(game, worker, gateway, parent, receipt, child, broken=False)
    assert not any(
        x.action == child and x.kind == "flirt_followthrough" for x in state(game).obligations
    )


def test_native_flirt_counter_high_waits_for_original_alphas_actual_tag(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, parent, receipt, choice = opportunity(ledger, tmp_path, monkeypatch)
    child = begin_counter(game, worker, gateway, parent, choice, (6, 6))
    answer(
        game,
        OTHER,
        "actor_flirt",
        options=("name",),
        fields={"extra": "owe"},
        text="PRIVATE_FLIRT_TOO_FAR I offer her more than I intended",
    )
    answer(game, PLAYER, "target_flirt", text="PRIVATE_FLIRT_HIGH_WANTED A new name")
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    before = state(game)
    answer(game, PLAYER, "flirt_owe_tag", text="PRIVATE_FLIRT_TAG Owes the original Alpha")
    after = state(game)
    assert len(after.sheets["3"].tags) == len(before.sheets["3"].tags) + 1
    assert after.sheets["3"].tags[-1].label == "PRIVATE_FLIRT_TAG Owes the original Alpha"
    assert any(
        x.kind == "cannot_refuse_until_tag_resolved"
        and x.action == child
        and x.owner == 3
        and x.target == 2
        for x in after.obligations
    )
    finish_counter(game, worker, gateway, parent, receipt, child, broken=True)
