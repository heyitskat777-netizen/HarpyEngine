"""Actual Beneath counter preserves private effects, independent responses and parent timing."""

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
from girlframe.services.m3_alpha_beneath import counter
from girlframe.services.onboarding import WorkflowError


def begin_counter(game, worker, gateway, parent, choice, faces):
    game.store.policy = game.store.policy.model_copy(
        update={
            "owner_m3_rulings": game.store.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            )
        }
    )
    before, calls = state(game), game.dice.calls
    actor, attacker = current_ref(before, 3), current_ref(before, 2)
    prepared = PlayInput(
        play="put_someone_beneath_you",
        parent=parent,
        target=2,
        heat=1,
        context="PRIVATE_BENEATH_COUNTER I turn the original Alpha's insult against her",
        trigger_confirmed=True,
    )
    with game.store.engine.connect() as c:
        snapshot = before.model_copy(deep=True)
        assert "put_someone_beneath_you" in counter_plays(
            game, c, before, game.action(c, parent), actor
        )
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
        assert "put_someone_beneath_you" in dict(
            next(x for x in form.fields if x.key == "play").options
        )
        assert not await form.interaction_check(interaction(2))
        form.values.update(play=("put_someone_beneath_you",), heat=("1",), context=prepared.context)
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
    assert "PRIVATE_BENEATH" not in json.dumps(gateway.messages)


def test_native_beneath_counter_high_waits_for_original_alpha_pin_response(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, parent, receipt, choice = opportunity(ledger, tmp_path, monkeypatch)
    child = begin_counter(game, worker, gateway, parent, choice, (5, 5))
    pending = next(x for x in game.choices(OTHER) if x["kind"] == "beneath_select")
    before = state(game)
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            pending["id"],
            pending["revision"],
            ChoiceAnswer(options=("tag", "pin"), fields={"tag": "Forged"}, text="Forged"),
        )
    assert state(game) == before
    answer(
        game,
        OTHER,
        "beneath_select",
        options=("tag", "pin"),
        fields={"tag": "PRIVATE_BENEATH_PINNED"},
        text="PRIVATE_BENEATH actual reversal and pin",
    )
    actual = state(game)
    tags = [x for x in actual.sheets["2"].tags if x.id.startswith(child + ":tag:")]
    assert len(tags) == 1 and tags[0].giver == 3 and tags[0].label == "PRIVATE_BENEATH_PINNED"
    assert any(x.get("kind") == "physical_pin" and x.get("action") == child for x in actual.facts)
    assert game.inspect(OTHER, child)["state"] == "awaiting_choices"
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    assert not conditions(actual, current_ref(actual, 2), current_ref(actual, 3))
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "beneath_pin_response")
    assert any(x.identity == row["id"] for x in InboxService(ledger).items(PLAYER))
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER, str(uuid4()), row["id"], row["revision"], ChoiceAnswer(text="Forged answer")
        )
    assert state(game) == actual
    from girlframe.services.m2_game import GameService

    reopened = GameService(ledger, dice=game.dice)
    assert reopened.decision(PLAYER, row["id"])["kind"] == "beneath_pin_response"
    key = str(uuid4())
    owned = ChoiceAnswer(text="PRIVATE_BENEATH I concede this moment, in my own words")
    result = reopened.respond(PLAYER, key, row["id"], row["revision"], owned)
    after = state(game)
    assert reopened.respond(PLAYER, key, row["id"], row["revision"], owned) == result
    assert state(game) == after
    assert game.inspect(OTHER, child)["result"]["pinned_response"] == owned.text
    finish_counter(game, worker, gateway, parent, receipt, child, broken=True)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_native_beneath_counter_mid_preserves_affected_private_bond_choice(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, parent, receipt, choice = opportunity(ledger, tmp_path, monkeypatch)
    child = begin_counter(game, worker, gateway, parent, choice, (3, 4))
    row = next(x for x in game.choices(OTHER) if x["kind"] == "beneath_select")
    assert "bonds" not in game.decision(OTHER, row["id"])["beneath"]
    answer(
        game,
        OTHER,
        "beneath_select",
        options=("tag", "bond"),
        fields={"tag": "PRIVATE_BENEATH_SHAMED"},
        text="PRIVATE_BENEATH actual confrontation",
    )
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "beneath_details")
    own = game.decision(PLAYER, row["id"])
    peer = own["beneath"]["bonds"][0]
    from girlframe.engine.m3_actor_bonds import depth
    from girlframe.engine.m3_actor_state import ActorRef

    victim = current_ref(state(game), 2)
    counterpart = ActorRef.model_validate(peer["ref"])
    before = depth(state(game), victim, counterpart)
    answer(game, PLAYER, "beneath_details", fields={"bond": peer["token"]})
    assert depth(state(game), victim, counterpart) == before - 1
    finish_counter(game, worker, gateway, parent, receipt, child, broken=True)


def test_native_beneath_counter_low_keeps_original_alpha_choice_and_actual_asset(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, parent, receipt, choice = opportunity(
        ledger, tmp_path, monkeypatch, retaliate=False
    )
    child = begin_counter(game, worker, gateway, parent, choice, (1, 1))
    assert not any(x["kind"] == "beneath_select" for x in game.choices(OTHER))
    answer(
        game, PLAYER, "beneath_select", options=("damage",), text="PRIVATE_BENEATH I strike back"
    )
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    row = next(x for x in game.choices(OTHER) if x["kind"] == "beneath_details")
    assert any(x.identity == row["id"] for x in InboxService(ledger).items(OTHER))
    before = state(game)
    asset = next(x for x in before.sheets["3"].assets if x.family == "girl" and not x.damaged)
    answer(game, OTHER, "beneath_details", denied=(asset.id,))
    assert next(x for x in state(game).sheets["3"].assets if x.id == asset.id).damaged
    finish_counter(game, worker, gateway, parent, receipt, child, broken=False)
