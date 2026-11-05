"""Actual Sprite human choices protect the physical target without rewriting its receipt."""

import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_battle_pipeline import table
from test_battle_service import confirm, prepared
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick
from test_world import gorgon

from girlframe.database import tables as t
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle_state import Declaration
from girlframe.engine.m3_world import update
from girlframe.services.m3_sprite import SpriteService
from girlframe.services.onboarding import WorkflowError


def sprite_roll(store, monkeypatch):
    import girlframe.services.m2_game as shared

    monkeypatch.setattr(shared, "M3_HEAT_IDS", (*shared.M3_HEAT_IDS, "all_out_assault"))
    game, worker, gateway, svc, _, _ = prepared(store)
    with store.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            gorgons=canon.world.gorgons
            + (
                gorgon("sprite", "shield-one", revealed=True),
                gorgon("sprite", "shield-two", revealed=True),
            ),
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_sprites_present", canon)
    data = svc.preview(PLAYER, 900)
    actor = next(x for x in data["actors"] if x["ref"]["entity"] == "2")
    target = next(x for x in data["actors"] if x["ref"]["entity"] == "3")
    declaration = Declaration(
        play="all_out_assault",
        actor=ActorRef.model_validate(actor["ref"]),
        target=ActorRef.model_validate(target["ref"]),
        attacking_asset=actor["assets"][0]["id"],
        target_asset=target["assets"][0]["id"],
        actor_sha256=actor["sha256"],
        target_sha256=target["sha256"],
        account="Actual incoming physical blow",
    )
    context = confirm(svc, game, data, declaration)
    game.dice.faces = (4, 5)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="all_out_assault",
            heat=0,
            piloting=True,
            target_actor=declaration.target,
            attacking_asset=declaration.attacking_asset,
            target_asset=declaration.target_asset,
            battle_context=context,
            context=declaration.account,
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    table(game)
    with store.engine.connect() as c:
        rows = game.pending(c, action)
    requests = [x for x in rows if x["kind"] == "battle_sprite_intercept"]
    assert len(requests) == 1 and requests[0]["actor_id"] == "1"
    return game, worker, gateway, action, declaration, requests[0]


@pytest.mark.parametrize("intercept", [True, False])
def test_two_actual_sprites_one_human_one_optional_window_and_original_receipt(
    ledger, monkeypatch, intercept
):
    game, worker, gateway, action, declared, request = sprite_roll(ledger, monkeypatch)
    svc = SpriteService(ledger)
    identity = json.loads(request["body_json"])["work_id"]
    with pytest.raises(WorkflowError, match="controller"):
        svc.get(OTHER, identity)
    data = svc.get(ADMIN, identity)
    assert len(data["options"]) == 2
    assert game.decision(ADMIN, request["id"])["sprite_intercept"]
    with pytest.raises(WorkflowError, match="actual Sprite|dedicated|source"):
        game.respond(
            ADMIN,
            str(uuid4()),
            request["id"],
            request["revision"],
            __import__("girlframe.engine.m2", fromlist=["ChoiceAnswer"]).ChoiceAnswer(),
        )
    option = data["options"][0]
    key = str(uuid4())
    result = svc.respond(
        ADMIN,
        key,
        identity,
        data["revision"],
        data["game_revision"],
        ActorRef.model_validate(option["actor"]) if intercept else None,
        option["asset"] if intercept else None,
        "Actual owned leap" if intercept else "I decline",
    )
    assert (
        svc.respond(
            ADMIN,
            key,
            identity,
            data["revision"],
            data["game_revision"],
            ActorRef.model_validate(option["actor"]) if intercept else None,
            option["asset"] if intercept else None,
            "Actual owned leap" if intercept else "I decline",
        )
        == result
    )
    after = state(game)
    assert next(x for x in after.sheets["3"].assets if x.id == declared.target_asset).damaged is (
        not intercept
    )
    sprite = next(x for x in after.world.gorgons if x.id == "shield-one")
    assert sprite.assets[0].damaged is intercept
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.dice.calls == 1
    with ledger.engine.connect() as c:
        assert not c.scalar(
            sa.select(t.m2["m2_responses"].c.choice_id).where(
                t.m2["m2_responses"].c.campaign_id == ledger.campaign_id,
                t.m2["m2_responses"].c.choice_id == request["id"],
            )
        )
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_owned_sprite_native_controls_pause_and_stale_do_not_change_blow(ledger, monkeypatch):
    import asyncio

    from test_mission_ui import current

    from girlframe.discord_adapter.m2_forms import NativeForm
    from girlframe.discord_adapter.m3_sprite import open_sprite

    game, _, _, _, _, request = sprite_roll(ledger, monkeypatch)
    svc = SpriteService(ledger)
    identity = json.loads(request["body_json"])["work_id"]
    data = svc.get(ADMIN, identity)
    ledger.safety(PLAYER, str(uuid4()), ledger.status(PLAYER)["revision"], pause=True)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="PAUSED|paused"):
        svc.respond(
            ADMIN,
            str(uuid4()),
            identity,
            data["revision"],
            data["game_revision"],
            None,
            None,
            "Actual optional decline",
        )
    assert state(game).model_dump_json() == before
    ledger.safety(PLAYER, str(uuid4()), ledger.status(PLAYER)["revision"], pause=False)
    with pytest.raises(WorkflowError, match="STALE"):
        svc.respond(
            ADMIN,
            str(uuid4()),
            identity,
            data["revision"] - 1,
            data["game_revision"],
            None,
            None,
            "Actual optional decline",
        )

    async def run():
        caller = current(1)
        await caller.response.defer(ephemeral=True)
        await open_sprite(caller, svc, identity)
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert not await form.interaction_check(current(3))
        form.values.update(option=("0",), account="The actual original Sprite leaps in")
        await form.confirm.callback(current(1, 992201))
        assert form.completed

    asyncio.run(run())
    assert next(x for x in state(game).world.gorgons if x.id == "shield-one").assets[0].damaged


@pytest.mark.parametrize("intercept", [True, False])
def test_real_fatal_core_sprite_shields_original_without_exposing_sprite_core(
    ledger, monkeypatch, intercept
):
    from test_battle_pipeline import core

    game, _, _, action, target = core(ledger, monkeypatch, (6, 6), sprites=True)
    with ledger.engine.connect() as c:
        request = next(x for x in game.pending(c, action) if x["kind"] == "battle_sprite_intercept")
    svc = SpriteService(ledger)
    identity = json.loads(request["body_json"])["work_id"]
    data = svc.get(ADMIN, identity)
    option = data["options"][0]
    with ledger.engine.connect() as c:
        receipt = game.action(c, action)["data"]["receipt"]
    svc.respond(
        ADMIN,
        str(uuid4()),
        identity,
        data["revision"],
        data["game_revision"],
        ActorRef.model_validate(option["actor"]) if intercept else None,
        option["asset"] if intercept else None,
        "Actually shield the original Core" if intercept else "Decline this interception",
    )
    after = state(game)
    assert ("3" in after.sheets) is intercept
    assert any(x.actor == target for x in after.career_archives) is (not intercept)
    sprite = next(x for x in after.world.gorgons if x.id == "actual-core-shield")
    assert sprite.alive and not sprite.exposed and sprite.assets[0].damaged is intercept
    with ledger.engine.connect() as c:
        saved = game.action(c, action)
        assert saved["state"] == "complete" and saved["data"]["receipt"] == receipt
    assert game.dice.calls == 1
