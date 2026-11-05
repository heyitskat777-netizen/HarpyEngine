"""Actual flesh-layer Play → real Asset blows → original guards/weakness → Core strike."""

import asyncio
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_battle_pipeline import table
from test_battle_service import prepared
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick
from test_mission_ui import current
from test_world import gorgon

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.engine import m3_leviathan as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle import core_available
from girlframe.engine.m3_battle_state import Declaration
from girlframe.engine.m3_gorgon_combat import Contest, Exposure
from girlframe.engine.m3_world import expose_gorgon, update
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_battle import BattleService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_gorgon import GorgonService
from girlframe.services.m3_leviathan import RULE, LeviathanService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


@pytest.fixture(autouse=True)
def candidate(monkeypatch):
    from girlframe.engine.rules_registry import Registry

    actual = Registry.require_available

    def source_gate(registry, identity):
        if identity == RULE:
            return next(x for x in registry.entries if x.id == identity)
        return actual(registry, identity)

    monkeypatch.setattr(Registry, "require_available", source_gate)


def source(store, *, gorgon_class="erratic", exposed=False):
    game, worker, gateway, *_ = prepared(store)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(update=dict(subsystems=approval.subsystems | {"world"}))
        )
    )
    with store.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            gorgons=canon.world.gorgons
            + (
                gorgon(
                    gorgon_class,
                    "actual-leviathan",
                    types=("leviathan",),
                    revealed=True,
                    exposed=exposed,
                ),
                gorgon("erratic", "actual-layer-hunter", revealed=True),
            ),
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_leviathan_body", canon)
    cast = CastService(ActorService(MissionService(store)))
    change(cast, ADMIN, "join", ActorRef(kind="gorgon", entity="actual-leviathan"))
    service = LeviathanService(store, game)
    with store.engine.connect() as c:
        task = next(
            x for x in service._tasks(c, ADMIN) if x["actor"]["entity"] == "actual-leviathan"
        )
    return game, worker, gateway, service, task


def raise_layers(service, task, *, key=None):
    key = key or str(uuid4())
    return key, service.protect(
        ADMIN,
        key,
        task["id"],
        task["revision"],
        task["source_sha256"],
        ("Actual outer living flesh", "Actual inner living flesh"),
        "The source Leviathan wraps its Core in two physical layers",
    )


def body(game):
    return next(x for x in state(game).world.gorgons if x.id == "actual-leviathan")


def battle(game, worker, gateway, monkeypatch, asset=None, *, after_roll=None):
    import girlframe.services.m2_game as shared

    monkeypatch.setattr(
        shared, "M3_HEAT_IDS", (*shared.M3_HEAT_IDS, "all_out_assault", "go_for_the_core")
    )
    svc = BattleService(game.store)
    data = svc.preview(PLAYER, 900)
    own = next(x for x in data["actors"] if x["ref"]["kind"] == "pilot" and x["owned"])
    target = next(x for x in data["actors"] if x["ref"]["entity"] == "actual-leviathan")
    declared = Declaration(
        play="all_out_assault" if asset else "go_for_the_core",
        actor=ActorRef.model_validate(own["ref"]),
        target=ActorRef.model_validate(target["ref"]),
        attacking_asset=own["assets"][0]["id"],
        target_asset=asset,
        actor_sha256=own["sha256"],
        target_sha256=target["sha256"],
        account="The actual own resource reaches this original opposing flesh/Core",
    )
    context = svc.propose(PLAYER, str(uuid4()), data["revision"], 900, declared)["id"]
    svc.confirm(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        context,
        opening=True,
        reach=True,
        outside_permission=False,
        indirect=False,
        evidence="Actual opening and reach",
    )
    game.dice.faces = (4, 5) if asset else (6, 6)
    root = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play=declared.play,
            heat=0,
            piloting=True,
            target_actor=declared.target,
            attacking_asset=declared.attacking_asset,
            target_asset=asset,
            battle_context=context,
            context=declared.account,
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    if after_roll is not None:
        after_roll()
    pass_tags(game)
    if asset:
        table(game)
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, root)["state"] == "complete"
    return root


def test_native_owned_layers_real_battle_piercing_original_weakness_then_actual_core_death(
    ledger, monkeypatch
):
    game, worker, gateway, service, task = source(ledger)
    before = state(game)
    inbox = InboxService(ledger)
    item = next(x for x in inbox.items(ADMIN) if x.task == "leviathan_layers")
    assert not any(x.task == "leviathan_layers" for x in inbox.items(PLAYER))

    async def native():
        caller = current(1, 998001)
        await caller.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(caller, item)
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and not await form.interaction_check(current(2))
        assert {x.key for x in form.fields} == {"layer_one", "layer_two", "account"}
        form.values.update(
            layer_one="Actual outer flesh",
            layer_two="Actual inner flesh",
            account="The actual source creature raises its protective layers",
        )
        await form.confirm.callback(current(1, 998002))
        assert form.completed

    asyncio.run(native())
    actual = body(game)
    layers = actual.flesh_layers
    assert layers and len(actual.assets) == len(before.world.gorgons[-2].assets) + 2
    assert actual.core_plan == before.world.gorgons[-2].core_plan
    assert state(game).sheets == before.sheets and game.dice.calls == 0
    assert not any(x.task == "leviathan_layers" for x in inbox.items(ADMIN))
    core = GorgonService(WorldService(MissionService(ledger)))
    for asset in layers:
        battle(game, worker, gateway, monkeypatch, asset)
        assert next(x for x in body(game).assets if x.id == asset).damaged
        assert not any(x["ref"]["entity"] == actual.id for x in core.cores(ADMIN)["gorgons"])
    assert rules.layers_clear(body(game)) and not body(game).exposed
    battle(game, worker, gateway, monkeypatch, actual.core_plan.assets[0])
    available = next(x for x in core.cores(ADMIN)["gorgons"] if x["ref"]["entity"] == actual.id)
    core.expose(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Exposure(
            actor=ActorRef.model_validate(available["ref"]),
            source_sha256=available["source_sha256"],
            account="The actual original conversational weakness is now present",
            weakness_confirmed=True,
        ),
    )
    strike = battle(game, worker, gateway, monkeypatch)
    assert not body(game).alive and game.dice.calls == 4
    assert game.inspect(PLAYER, strike)["receipt"]["pre_total"] == 9
    assert body(game).flesh_layers == layers


def test_source_replay_stale_pause_foreign_role_and_no_damage_reset(ledger):
    game, _, _, service, task = source(ledger, exposed=True)
    original = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        service.get(OTHER, task["id"])
    with pytest.raises(WorkflowError, match="STALE_LEVIATHAN"):
        service.protect(
            ADMIN,
            str(uuid4()),
            task["id"],
            task["revision"] - 1,
            task["source_sha256"],
            ("Outer", "Inner"),
            "Actual source",
        )
    ledger.safety(PLAYER, str(uuid4()), ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        raise_layers(service, task)
    ledger.safety(PLAYER, str(uuid4()), ledger.status(PLAYER)["revision"], pause=False)
    assert state(game).model_dump_json() == original
    key, result = raise_layers(service, task)
    assert raise_layers(service, task, key=key)[1] == result
    assert not body(game).exposed and len(body(game).assets) == 6
    with pytest.raises(WorkflowError):
        raise_layers(service, task)
    assert len(body(game).assets) == 6 and game.dice.calls == 0


def test_raw_exposure_and_new_core_strike_cannot_bypass_actual_layers_or_original_plan(ledger):
    game, _, _, service, task = source(ledger)
    raise_layers(service, task)
    canon = state(game)
    actual = body(game)
    # Even if old exposed metadata survived elsewhere, intact real layers remain a gate.
    inconsistent = canon.model_copy(deep=True)
    inconsistent.world = update(
        inconsistent.world,
        gorgons=tuple(
            x.model_copy(update={"exposed": True}) if x.id == actual.id else x
            for x in inconsistent.world.gorgons
        ),
    )
    with pytest.raises(ValueError, match="flesh-layer"):
        core_available(
            inconsistent,
            ActorRef(kind="gorgon", entity=actual.id),
            ActorRef(kind="gorgon", entity="actual-layer-hunter"),
            (),
        )
    with pytest.raises(ValueError, match="Core-protecting"):
        expose_gorgon(canon.world, actual.id, "Weakness without actual original guards")
    dealt = actual.model_copy(
        update={
            "assets": tuple(
                x.model_copy(update={"damaged": True}) if x.id in actual.core_plan.assets else x
                for x in actual.assets
            )
        }
    )
    world = update(
        canon.world, gorgons=tuple(dealt if x.id == actual.id else x for x in canon.world.gorgons)
    )
    with pytest.raises(ValueError, match="flesh-layer"):
        expose_gorgon(world, actual.id, "Original weakness without both flesh layers")


def test_actual_contest_destroys_source_layer_without_shadow_pool_or_reset(ledger):
    game, _, _, service, task = source(ledger)
    raise_layers(service, task)
    core = GorgonService(WorldService(MissionService(ledger)))
    data = core.contests(ADMIN)
    attacker = next(x for x in data["attackers"] if x["ref"]["entity"] == "actual-layer-hunter")
    defender = next(x for x in attacker["targets"] if x["ref"]["entity"] == "actual-leviathan")
    layer = body(game).flesh_layers[0]
    core.contest(
        ADMIN,
        str(uuid4()),
        data["game_revision"],
        Contest(
            attacker=ActorRef.model_validate(attacker["ref"]),
            defender=ActorRef.model_validate(defender["ref"]),
            attacking_assets=(attacker["assets"][0]["id"],),
            defending_assets=(layer,),
            attacker_sha256=attacker["source_sha256"],
            defender_sha256=defender["source_sha256"],
            winner="attacker",
            losing_asset=layer,
            approach="direct",
            account="Actual pitted layer torn away",
            trigger_confirmed=True,
        ),
    )
    assert layer not in {x.id for x in body(game).assets}
    assert layer in {x.id for x in body(game).destroyed_assets}
    assert not rules.layers_clear(body(game))
    with pytest.raises(ValueError, match="already exist"):
        rules.protect(
            state(game),
            ActorRef(kind="gorgon", entity="actual-leviathan"),
            ("Replacement outer", "Replacement inner"),
            "Attempted reset",
            str(uuid4()),
        )
    assert game.dice.calls == 0


def test_pointer_validation_backwards_hash_shape_and_actual_dormant_type_awakening(ledger):
    game, _, _, service, task = source(ledger, gorgon_class="dormant")
    before = body(game)
    assert "flesh_layers" not in before.model_dump(mode="json")
    assert "flesh_layers_event" not in before.model_dump(mode="json")
    with pytest.raises(ValidationError):
        type(before).model_validate_json(
            before.model_copy(
                update={
                    "flesh_layers": (before.assets[0].id, before.assets[1].id),
                }
            ).model_dump_json()
        )
    raise_layers(service, task)
    from girlframe.services.m3_gorgon_dormant import awakened_source

    with ledger.engine.connect() as c:
        event = awakened_source(game, c, state(game), ActorRef(kind="gorgon", entity=before.id))
        assert event == body(game).flesh_layers_event
    assert body(game).gorgon_class == "dormant" and body(game).cell == before.cell
    assert len([x for x in state(game).facts if x.get("kind") == "dormant_awakening"]) == 1
    assert game.dice.calls == 0


def test_actual_layers_stale_unrolled_context_and_deny_new_core_before_lock(ledger):
    game, _, _, service, task = source(ledger, exposed=True)
    svc = BattleService(ledger)
    data = svc.preview(PLAYER, 900)
    own = next(x for x in data["actors"] if x["ref"]["kind"] == "pilot" and x["owned"])
    target = next(x for x in data["actors"] if x["ref"]["entity"] == "actual-leviathan")
    declared = Declaration(
        play="go_for_the_core",
        actor=ActorRef.model_validate(own["ref"]),
        target=ActorRef.model_validate(target["ref"]),
        attacking_asset=own["assets"][0]["id"],
        actor_sha256=own["sha256"],
        target_sha256=target["sha256"],
        account="The original exposed Core before this actual defensive action",
    )
    context = svc.propose(PLAYER, str(uuid4()), data["revision"], 900, declared)["id"]
    with ledger.engine.connect() as c:
        fresh = service.get(ADMIN, task["id"])
    raise_layers(service, fresh)
    with pytest.raises(WorkflowError, match="STALE_BATTLE"):
        svc.confirm(
            ADMIN,
            str(uuid4()),
            state(game).revision,
            context,
            opening=True,
            reach=True,
            outside_permission=False,
            indirect=False,
            evidence="The old opening",
        )
    current_data = svc.preview(PLAYER, 900)
    actor_now = next(x for x in current_data["actors"] if x["ref"] == own["ref"])
    target_now = next(x for x in current_data["actors"] if x["ref"] == target["ref"])
    with pytest.raises(WorkflowError, match="flesh-layer"):
        svc.propose(
            PLAYER,
            str(uuid4()),
            current_data["revision"],
            900,
            declared.model_copy(
                update={"actor_sha256": actor_now["sha256"], "target_sha256": target_now["sha256"]}
            ),
        )
    assert game.dice.calls == 0
    with ledger.engine.connect() as c:
        assert game.lock(c, 900) is None


def test_new_real_layers_do_not_recalculate_an_already_rolled_fatal_core_source(
    ledger, monkeypatch
):
    """Trusted effect composition, not a claim of an implemented Type counter menu."""
    game, worker, gateway, _, _ = source(ledger, exposed=True)

    def source_effect():
        with ledger.transaction() as c:
            event = str(uuid4())
            changed = rules.protect(
                state(game),
                ActorRef(kind="gorgon", entity="actual-leviathan"),
                ("Actual new outer layer", "Actual new inner layer"),
                "Recorded defensive source effect after the original strike roll",
                event,
            )
            game.event(
                c,
                1,
                str(uuid4()),
                "synthetic.actual_layer_effect_composition",
                changed,
                event_id=event,
            )
        assert not body(game).exposed and not rules.layers_clear(body(game))

    strike = battle(game, worker, gateway, monkeypatch, after_roll=source_effect)
    assert not body(game).alive
    # Initial four intact Assets: 12-4=8. The new two are not a retroactive roll modifier.
    assert game.inspect(PLAYER, strike)["receipt"]["pre_total"] == 8
    assert all(not x.damaged for x in body(game).assets if x.id in body(game).flesh_layers)
    assert game.dice.calls == 1


def test_ordinary_type_endpoint_cannot_interrupt_an_actual_unfinished_play(ledger, monkeypatch):
    game, worker, gateway, service, task = source(ledger)

    def attempt():
        current_task = service.get(ADMIN, task["id"])
        before = state(game).model_dump_json()
        with pytest.raises(WorkflowError, match="pending Plays"):
            raise_layers(service, current_task)
        assert state(game).model_dump_json() == before

    battle(game, worker, gateway, monkeypatch, body(game).assets[0].id, after_roll=attempt)
    assert body(game).flesh_layers is None and game.dice.calls == 1


def test_actual_unknown_position_stays_unknown_and_current_policy_still_gates_effect(ledger):
    game, _, _, service, task = source(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            gorgons=tuple(
                x.model_copy(update={"cell": None}) if x.id == "actual-leviathan" else x
                for x in canon.world.gorgons
            ),
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_unknown_body_position", canon)
    fresh = service.get(ADMIN, task["id"])
    old = ledger.policy
    ledger.policy = old.model_copy(
        update={"m3_approval": old.m3_approval.model_copy(update={"registry_sha256": "f" * 64})}
    )
    with pytest.raises(WorkflowError, match="M3_REVIEW_PENDING"):
        raise_layers(service, fresh)
    assert body(game).cell is None and body(game).flesh_layers is None
    ledger.policy = old
    raise_layers(service, fresh)
    assert body(game).cell is None and game.dice.calls == 0
