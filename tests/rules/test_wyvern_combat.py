"""Four real Wyvern combat normals authored for final P1; deliberately NOT RUN here."""

import asyncio
import copy
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from test_enforcement_initiative import cast_target
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import answer, pass_tags, state, tick
from test_world import gorgon
from test_wyvern import buy, free_chat, ready, roll

from girlframe.engine import m3_battle as battle
from girlframe.engine import m3_vehicles as vehicles
from girlframe.engine import m3_wyvern as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_world import introduce_gorgon
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_movement import MovementService
from girlframe.services.m3_sprite import SpriteService
from girlframe.services.m3_vehicles import VehicleService
from girlframe.services.m3_wyvern_combat import WyvernCombatService, records
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def interaction(viewer, identity):
    return SimpleNamespace(user=SimpleNamespace(id=viewer.user_id), channel_id=900, id=identity)


def native_controls(monkeypatch):
    import girlframe.discord_adapter.m3_wyvern_combat as native

    captured = dict(pickers=[], forms=[], plays=[])
    people = {x.user_id: x for x in (PLAYER, OTHER, ADMIN)}
    monkeypatch.setattr(native, "viewer_from_interaction", lambda current: people[current.user.id])

    class Picker:
        def __init__(self, owner, title, options, choose):
            self.owner, self.title, self.options, self.choose = owner, title, options, choose

        async def show(self, current):
            captured["pickers"].append(self)

    class Form:
        def __init__(self, owner, title, instructions, fields, submit):
            self.owner, self.fields, self.submit = owner, fields, submit

        async def present(self, current):
            captured["forms"].append(self)

    async def play(current, game, *, parent=None):
        captured["plays"].append(dict(owner=current.user.id, parent=parent))

    monkeypatch.setattr(native, "Picker", Picker)
    monkeypatch.setattr(native, "NativeForm", Form)
    monkeypatch.setattr("girlframe.discord_adapter.m2_ui.open_play", play)
    return native, captured


def actual_asset(game, actor):
    with game.store.engine.connect() as c:
        return next(
            item.id
            for item in resolve(state(game), actor, profiles(c, game.store.campaign_id)).assets
            if not item.damaged
        )


def test_actual_pin_restricts_real_movement_then_original_owner_native_release(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, source = ready(ledger, tmp_path, monkeypatch)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    roll(game, worker, gateway)
    free_chat(worker, gateway)
    used = source.use_roused(PLAYER, "actual-pin-use", 900, state(game).revision, target, "pin")
    pin = next(x for x in rules.records(state(game), rules.Pin) if x.use == used["id"])
    controls = WyvernCombatService(game)
    assert controls.view(OTHER, pin.id)["can_counter"]
    assert controls.view(PLAYER, pin.id)["can_release"]
    with pytest.raises(WorkflowError, match="original actual people"):
        controls.view(ADMIN, pin.id)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        MovementService(game).move(
            OTHER,
            str(uuid4()),
            state(game).revision,
            900,
            target,
            (1, 0),
            account="I try to leave the real pin",
        )
    assert state(game).model_dump_json() == before
    native, ui = native_controls(monkeypatch)
    asyncio.run(native.open_combat(interaction(PLAYER, 401), game, pin.id))
    picker = ui["pickers"][-1]
    assert picker.owner == PLAYER.user_id and "release" in dict(picker.options)
    assert "counter" not in dict(picker.options)
    asyncio.run(picker.choose(interaction(PLAYER, 402), "release"))
    form = ui["forms"][-1]
    assert form.owner == PLAYER.user_id
    asyncio.run(
        form.submit(
            interaction(PLAYER, 403),
            dict(account="I physically lift my original Frame away and release her"),
        )
    )
    assert not rules.pinned(state(game), target)
    assert not rules.roused(state(game), actor)
    assert not controls.view(OTHER, pin.id)["can_counter"]
    assert controls.view(PLAYER, pin.id)["counter"] is None
    MovementService(game).move(
        OTHER,
        str(uuid4()),
        state(game).revision,
        900,
        target,
        (1, 0),
        account="I actually leave after the real release",
    )
    with ledger.engine.connect() as c:
        assert resolve(state(game), target, profiles(c, ledger.campaign_id)).cell == (1, 0)
    assert game.dice.calls == 1


def test_known_incoming_receipt_and_heat_survive_too_big_then_real_different_native_play(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, source = ready(ledger, tmp_path, monkeypatch)
    actor, opponent = current_ref(state(game), 2), current_ref(state(game), 3)
    roll(game, worker, gateway)
    free_chat(worker, gateway)
    marked = next(
        x.id for x in state(game).sheets["3"].identities if not x.marked and not x.protected
    )
    game.dice.faces = (3, 4)
    incoming = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="flirt",
            target=2,
            heat=1,
            identity=marked,
            gain=1,
            context="I actually Flirt with her over the open cockpit channel",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(OTHER, incoming)["state"] != "tag_window":
        game.roll(OTHER, str(uuid4()), incoming)
    with ledger.engine.connect() as c:
        old_receipt = copy.deepcopy(game.action(c, incoming)["data"]["receipt"])
    paid_heat = state(game).sheets["3"].heat
    assert (
        old_receipt and next(x for x in state(game).sheets["3"].identities if x.id == marked).marked
    )
    used = source.use_roused(
        PLAYER, str(uuid4()), 900, state(game).revision, opponent, "too_big", incoming=incoming
    )
    effect = next(x for x in records(state(game), battle.WyvernDeflection) if x.use == used["id"])
    controls = WyvernCombatService(game)
    data = controls.view(OTHER, effect.id)
    assert data["can_counter"] and data["counter"]["body"]["source_work"] == effect.id
    assert data["counter"]["parent"] == incoming
    native, ui = native_controls(monkeypatch)
    asyncio.run(native.open_combat(interaction(OTHER, 501), game, effect.id))
    picker = ui["pickers"][-1]
    assert picker.owner == OTHER.user_id and "counter" in dict(picker.options)
    asyncio.run(picker.choose(interaction(OTHER, 502), "counter"))
    assert ui["plays"][-1] == dict(owner=OTHER.user_id, parent=data["counter"])
    game.dice.faces = (3, 4)
    child = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            parent=incoming,
            source_work=effect.id,
            context="Instead I keep my head while navigating the real hazardous withdrawal",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if game.inspect(OTHER, child)["state"] != "tag_window":
        game.roll(OTHER, str(uuid4()), child)
    pass_tags(game)
    if any(x["kind"] == "mockingbird_risk" for x in game.choices(OTHER)):
        answer(game, OTHER, "mockingbird_risk")
    answer(game, OTHER, "actor_keep", options=("tough",))
    answer(
        game,
        ADMIN,
        "handler_keep",
        flag=True,
        text="The genuinely different course resolves its actual danger",
    )
    assert game.inspect(OTHER, child)["state"] == "complete"
    assert game.inspect(OTHER, incoming)["state"] == "complete"
    with ledger.engine.connect() as c:
        assert game.action(c, incoming)["data"]["receipt"] == old_receipt
    assert state(game).sheets["3"].heat == paid_heat
    assert next(x for x in state(game).sheets["3"].identities if x.id == marked).marked
    assert controls.view(OTHER, effect.id)["counter"] is None
    assert game.dice.calls == 3 and not rules.roused(state(game), actor)
    free_chat(worker, gateway)
    assert {key[0] + key[1]: value for key, value in gateway.values.items()} == gateway.original


def test_actual_sprite_crush_waits_for_real_optional_interception_then_destroys_original_body(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, source = ready(ledger, tmp_path, monkeypatch)
    buy(source, rules.CRUSH)
    with ledger.transaction() as c:
        canon = state(game)
        for entity in (
            gorgon("sprite", "actual-small", revealed=True),
            gorgon("sprite", "actual-shield", revealed=True, follows="actual-small"),
        ):
            canon.world = introduce_gorgon(canon.world, entity).world
        game.event(
            c,
            ADMIN.user_id,
            str(uuid4()),
            "synthetic.actual_existing_sprite_bodies_and_core_plans",
            canon,
        )
    target = ActorRef(kind="gorgon", entity="actual-small")
    cast_target(game, target)
    used = actual_asset(game, current_ref(state(game), 2))
    before = next(x for x in state(game).world.gorgons if x.id == target.entity)
    action = roll(game, worker, gateway, play="engage", target=target, faces=(1, 1))
    answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=("crush_small",),
        fields={"crush_small": used},
        denied=(used,),
        text="My original Frame crushes this actual small Gorgon body",
    )
    assert game.inspect(PLAYER, action)["state"] != "complete"
    with ledger.engine.connect() as c:
        row = next(x for x in game.pending(c, action) if x["kind"] == "battle_sprite_intercept")
    sprite = SpriteService(ledger)
    work = json.loads(row["body_json"])["work_id"]
    data = sprite.get(ADMIN, work)
    assert any(x["actor"]["entity"] == "actual-shield" for x in data["options"])
    assert next(x for x in state(game).world.gorgons if x.id == target.entity).alive
    sprite.respond(
        ADMIN,
        "actual-sprite-declines",
        work,
        data["revision"],
        data["game_revision"],
        None,
        None,
        "The actual Sprite's human declines to intercept this blow",
    )
    canon = state(game)
    destroyed = next(x for x in canon.world.gorgons if x.id == target.entity)
    assert not destroyed.alive and not destroyed.assets
    assert {x.id for x in before.assets} <= {x.id for x in destroyed.destroyed_assets}
    assert next(x for x in canon.world.gorgons if x.id == "actual-shield").alive
    assert next(x for x in canon.sheets["2"].assets if x.id == used).damaged
    effect = next(x for x in records(canon, battle.WyvernCrush) if x.action == action)
    assert effect.completed_event and effect.outcome == "crushed"
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
    assert not any(role.actor == target for scene in canon.scene_casts for role in scene.roles)


def test_actual_handler_assessed_empty_vehicle_is_crushed_by_real_engage_with_cost_and_encirclement(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, source = ready(ledger, tmp_path, monkeypatch)
    buy(source, rules.CRUSH)
    assessed = VehicleService(game).assess(
        ADMIN,
        "actual-empty-truck",
        state(game).revision,
        900,
        "Empty Foundation truck",
        "The actual regular vehicle in the open source scene",
        (0, 0),
        "empty",
    )
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    with ledger.engine.connect() as c:
        used = [
            x.id
            for x in resolve(state(game), actor, profiles(c, ledger.campaign_id)).assets
            if not x.damaged
        ]
    assert len(used) >= 3
    action = roll(game, worker, gateway, play="engage", target=target, faces=(6, 6))
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "engage_maneuvers")
    projection = game.decision(PLAYER, row["id"])["engage"]
    assert "crush_small" in projection["maneuvers"] and "encircle" in projection["maneuvers"]
    assert any(x["id"] == assessed["id"] for x in projection["wyvern_vehicles"])
    answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=("crush_small", "encircle", "cover"),
        fields={
            "crush_small": used[0],
            "encircle": used[1],
            "cover": used[2],
            "wyvern_vehicle": assessed["id"],
        },
        denied=(used[0],),
        text="I crush the actual empty truck, surround the actual foe, and cover the approach",
    )
    canon = state(game)
    vehicle = next(x for x in vehicles.vehicles(canon) if x.id == assessed["id"])
    assert (
        vehicle.destroyed_event and vehicle.source_action == action and vehicle.occupancy == "empty"
    )
    assert next(x for x in canon.sheets["2"].assets if x.id == used[0]).damaged
    assert not next(x for x in canon.sheets["2"].assets if x.id == used[1]).damaged
    assert any(
        x.actor == actor and x.target == target and x.action == action and x.asset == used[1]
        for x in records(canon, battle.WyvernEncirclement)
    )
    crush = next(x for x in records(canon, battle.WyvernCrush) if x.action == action)
    assert crush.vehicle == vehicle.id and crush.outcome == "crushed" and crush.completed_event
    assert game.inspect(PLAYER, action)["state"] == "complete" and game.dice.calls == 1
