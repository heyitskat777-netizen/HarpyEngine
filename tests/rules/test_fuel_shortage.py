"""One genuine selected shortage -> native battle confirmation -> unavoidable real loss.

Authored for the final P1 candidate; no worker pytest/collection run.
"""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_cast_service import change as change_cast
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_ui import current
from test_physical_operations import place
from test_strain_service import prepared, ready
from test_world import initial

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_battle import open_context
from girlframe.discord_adapter.m3_fuel_shortage import battle_losses, open_fuel_shortage
from girlframe.engine import m3_fuel_shortage as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle_state import Context, Declaration
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_battle import BattleService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_fuel_shortage import FuelService, prove
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def test_actual_armed_shortage_first_battle_native_unavoidable_loss_and_private_reopen(ledger):
    strain, game = ready(ledger, face=1)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(
                    subsystems=approval.subsystems | {"world", "plays"},
                )
            ),
        )
    )
    world = initial()
    worlds = WorldService(strain.missions)
    worlds.initialize(
        ADMIN, "fuel-map", state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    npc = Npc(
        id="actual-late-relief-doctor",
        name="Actual relief doctor",
        jobs=("doctor",),
        controller=1,
        cell=(0, 0),
        detail="Actual preexisting person at the battle site",
    )
    worlds.npc(ADMIN, "fuel-existing-doctor", state(game).revision, npc)
    with ledger.transaction() as c:
        actual = place(place(state(game), 2), 3)
        game.event(c, 1, str(uuid4()), "synthetic.actual_fuel_battle_positions", actual)
    casts = CastService(ActorService(strain.missions))
    victim = ActorRef(kind="npc", entity=npc.id)
    change_cast(casts, ADMIN, "join", victim)
    period = prepared(strain, game, high=frozenset({"budget"}))
    request = next(x for x in state(game).strain.requests if x.track == "budget")
    strain.roll(ADMIN, "fuel-actual-high-die", request.id, 1, state(game).revision)
    strain.choose(ADMIN, "fuel-actual-column", request.id, 2, state(game).revision, 2)
    identity = request.id + ":effect"
    service = FuelService(game)
    assert service.view(ADMIN, identity)["can_arm"]
    with pytest.raises(WorkflowError):
        service.view(PLAYER, identity)
    arm_revision = state(game).revision

    async def arm_native():
        own = current(1, 991001)
        await own.response.defer(ephemeral=True)
        await open_fuel_shortage(own, service, identity)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(2))
        form.values.update(operation=("arm",))
        confirmation = current(1, 991002)
        await form.confirm.callback(confirmation)
        assert form.completed, str(confirmation.edit_original_response.call_args)

    asyncio.run(arm_native())
    (armed,) = rules.records(state(game))
    assert armed.phase == "armed" and armed.period == period
    assert service.arm(ADMIN, "991002", identity, arm_revision)["phase"] == "armed"
    calls = game.dice.calls
    assert calls == 0 and strain.dice.calls == 1
    # Resolving actual scheduling permits OffDuty work to proceed; no fictional battle is made.
    with ledger.engine.connect() as c:
        work = t.m3["m3_required_work"]
        latest = (
            c.execute(
                sa.select(work)
                .where(
                    work.c.campaign_id == ledger.campaign_id,
                    work.c.id == identity,
                )
                .order_by(work.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        assert latest["state"] == "resolved"
        assert prove(game, c, state(game), identity) == armed
    assert not any(x.get("kind") == "battle_context" for x in state(game).facts)

    battle = BattleService(ledger)
    preview = battle.preview(PLAYER, 900)
    actor = next(
        x for x in preview["actors"] if x["ref"]["kind"] == "pilot" and x["ref"]["entity"] == "2"
    )
    target = next(
        x for x in preview["actors"] if x["ref"]["kind"] == "pilot" and x["ref"]["entity"] == "3"
    )
    declaration = Declaration.model_validate_json(
        __import__("json").dumps(
            dict(
                play="all_out_assault",
                actor=actor["ref"],
                target=target["ref"],
                attacking_asset=actor["assets"][0]["id"],
                target_asset=target["assets"][0]["id"],
                actor_sha256=actor["sha256"],
                target_sha256=target["sha256"],
                account="Actual Cadre battle at the existing relief base",
            )
        )
    )
    offered = battle.propose(
        PLAYER, "fuel-first-real-battle", preview["revision"], 900, declaration
    )
    projection = service.for_context(ADMIN, offered["id"])
    assert projection["required"] and len(projection["arms"]) == 1
    source = projection["arms"][0]
    assert victim.model_dump(mode="json") in [x["ref"] for x in source["npcs"]]
    assert "base0" in {x["id"] for x in source["locations"]}
    before = state(game)
    evidence = "Actual opening and range; the Cadre arrived too late to prevent these losses"
    with pytest.raises(WorkflowError, match="unavoidable loss"):
        battle.confirm(
            ADMIN,
            "fuel-missing-selection",
            before.revision,
            offered["id"],
            opening=True,
            reach=True,
            outside_permission=False,
            indirect=False,
            evidence=evidence,
        )
    assert state(game).model_dump_json() == before.model_dump_json()
    values = {
        "fuel:" + identity + ":npc": (npc.id,),
        "fuel:" + identity + ":site": ("base0",),
        "fuel:" + identity + ":account": (
            "The actual doctor is killed and this actual base is destroyed before relief arrives"
        ),
    }
    selections = battle_losses(projection, values)

    async def actual_review():
        own = current(1, 991003)
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_context(own, battle, offered["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(2))
        assert "fuel:" + identity + ":account" in {x.key for x in form.fields}
        form.values.update(
            values
            | dict(
                opening=("yes",),
                reach=("yes",),
                outside=("no",),
                indirect=("no",),
                evidence=evidence,
            )
        )
        confirmation = current(1, 991004)
        await form.confirm.callback(confirmation)
        assert form.completed, str(confirmation.edit_original_response.call_args)

    asyncio.run(actual_review())
    final = state(game)
    (saved,) = rules.records(final)
    assert saved.phase == "complete" and saved.battle == offered["id"]
    assert saved.loss == selections[0] and saved.original_npc == npc
    assert not next(x for x in final.world.npcs if x.id == npc.id).alive
    assert next(x for x in final.world.locations if x.id == "base0").condition == "destroyed"
    assert not any(victim == x.actor for cast in final.scene_casts for x in cast.roles)
    assert game.dice.calls == calls and strain.dice.calls == 1
    actual_cast = next(x for x in final.scene_casts if x.channel == 900)
    with ledger.engine.connect() as c:
        canonical = prove(game, c, final, identity)
        assert canonical == saved
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.event_id == saved.battle_event,
            )
        )
        snapshot = type(final).model_validate_json(raw)
        context = next(
            Context.model_validate_json(x["body"])
            for x in reversed(snapshot.facts)
            if x.get("kind") == "battle_context" and x.get("id") == saved.battle
        )
        assert context.cast_revision == actual_cast.revision
        assert not next(x for x in snapshot.world.npcs if x.id == npc.id).alive
    assert (
        battle.confirm(
            ADMIN,
            "991004",
            before.revision,
            offered["id"],
            opening=True,
            reach=True,
            outside_permission=False,
            indirect=False,
            evidence=evidence,
            fuel_losses=selections,
        )["state"]
        == "confirmed"
    )
    assert service.view(ADMIN, identity)["record"]["battle_event"] == saved.battle_event
    with pytest.raises(WorkflowError):
        service.view(PLAYER, identity)
    assert len(rules.records(state(game))) == 1


def _actual_alternative(ledger, npc_outcome, site_outcome):
    from test_world import gorgon

    from girlframe.discord_adapter.m3_fuel_shortage import open_manifestation
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_mockingbird_sex import corruption_options
    from girlframe.engine.m3_strain_effects import Choice
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_fuel_shortage import prove_npc_void_tag
    from girlframe.services.m3_strain_effects import EffectService

    strain, game = ready(ledger, face=1)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update=dict(
            m3_approval=approval.model_copy(
                update=dict(subsystems=approval.subsystems | {"world", "plays"}),
            )
        )
    )
    worlds = WorldService(strain.missions)
    world = initial()
    worlds.initialize(
        ADMIN,
        "alternative-map",
        state(game).revision,
        world.board,
        world.locations,
        world.gorgons[0],
    )
    npc = Npc(
        id="actual-threatened-person",
        name="Actual threatened doctor",
        jobs=("doctor",),
        controller=1,
        cell=(0, 0),
        detail="An actual existing person at the battle site",
    )
    worlds.npc(ADMIN, "alternative-npc", state(game).revision, npc)
    sprite_victim = Npc(
        id="actual-sprite-captive",
        name="Actual initial Sprite captive",
        jobs=("civilian",),
        controller=1,
        cell=(0, 0),
        detail="Another actual person captured by the separate printed Sprite introduction",
    )
    worlds.npc(ADMIN, "alternative-sprite-victim", state(game).revision, sprite_victim)
    with ledger.transaction() as c:
        actual = place(place(state(game), 2), 3)
        # Known initial synthetic fixture conditions, before any selected Strain source.
        for sheet in actual.sheets.values():
            for asset in sheet.assets:
                asset.void = False
        game.event(c, 1, str(uuid4()), "synthetic.actual_alternative_baseline", actual)
    victim = ActorRef(kind="npc", entity=npc.id)
    change_cast(CastService(ActorService(strain.missions)), ADMIN, "join", victim)
    prepared(strain, game, high=frozenset({"budget"}))
    request = next(x for x in state(game).strain.requests if x.track == "budget")
    strain.roll(ADMIN, "alternative-budget-die", request.id, 1, state(game).revision)
    strain.choose(ADMIN, "alternative-budget-column", request.id, 2, state(game).revision, 2)
    identity = request.id + ":effect"
    service = FuelService(game)
    service.arm(ADMIN, "alternative-arm", identity, state(game).revision)
    # Actual separate Strain introduction supplies the real Gorgon, not a fabricated captor.
    spawn = next(x for x in state(game).strain.requests if x.track == "void")
    assert spawn.severity == "low"
    strain.dice.face = 5
    strain.roll(ADMIN, "actual-threat-die", spawn.id, 1, state(game).revision)
    strain.choose(ADMIN, "actual-threat-column", spawn.id, 2, state(game).revision, 1)
    incoming = gorgon("sprite", "actual-fuel-threat", (0, 0))
    EffectService(strain).apply(
        ADMIN,
        "actual-threat-introduction",
        spawn.id + ":effect",
        1,
        state(game).revision,
        Choice(
            rule_id="strain.void.low.5.1",
            victim=sprite_victim.id,
            account="The actual Sprite enters this base while following the original Gorgon",
            gorgon=incoming,
        ),
    )
    assert rules.records(state(game))[0].phase == "armed"
    threat = ActorRef(kind="gorgon", entity=incoming.id)
    battle = BattleService(ledger)
    preview = battle.preview(PLAYER, 900)
    actor = next(
        x for x in preview["actors"] if x["ref"]["kind"] == "pilot" and x["ref"]["entity"] == "2"
    )
    target = next(
        x for x in preview["actors"] if x["ref"]["kind"] == "pilot" and x["ref"]["entity"] == "3"
    )
    declaration = Declaration.model_validate_json(
        __import__("json").dumps(
            dict(
                play="all_out_assault",
                actor=actor["ref"],
                target=target["ref"],
                attacking_asset=actor["assets"][0]["id"],
                target_asset=target["assets"][0]["id"],
                actor_sha256=actor["sha256"],
                target_sha256=target["sha256"],
                account="The actual Cadre arrives at this real battle after the fuel delay",
            )
        )
    )
    offered = battle.propose(PLAYER, "alternative-battle", preview["revision"], 900, declaration)
    manifestation_id = None
    if npc_outcome == "corrupt":

        async def actual_handler_choice():
            own = current(1, 992001)
            await own.response.defer(ephemeral=True)
            await open_manifestation(own, service, identity)
            form = own.edit_original_response.call_args.kwargs["view"]
            assert not await form.interaction_check(current(2))
            form.values.update(context=(offered["id"],))
            select = current(1, 992002)
            await form.confirm.callback(select)
            actual = select.edit_original_response.call_args.kwargs["view"]
            actual.values.update(npc=(npc.id,), threat=(incoming.id,), manifestation=("brain",))
            confirmation = current(1, 992003)
            await actual.confirm.callback(confirmation)
            assert actual.completed, str(confirmation.edit_original_response.call_args)

        asyncio.run(actual_handler_choice())
        manifestation_id = rules.manifestations(state(game))[0].id
        assert next(x for x in state(game).world.npcs if x.id == npc.id) == npc
    prefix = "fuel:" + identity + ":"
    values = {
        prefix + "npc": (npc.id,),
        prefix + "site": ("base0",),
        prefix + "npc_outcome": (npc_outcome,),
        prefix + "site_outcome": (site_outcome,),
        prefix + "threat": (incoming.id,),
        prefix + "account": "Actual Gorgon loss before relief; no opportunity to prevent it",
    }
    if manifestation_id:
        values[prefix + "manifestation_source"] = (manifestation_id,)
    before = state(game)
    base = next(x for x in before.world.locations if x.id == "base0")

    async def actual_loss():
        own = current(1, 992004)
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_context(own, battle, offered["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            values
            | dict(
                opening=("yes",),
                reach=("yes",),
                outside=("no",),
                indirect=("no",),
                evidence="Actual source battle and unavoidable loss",
            )
        )
        confirmation = current(1, 992005)
        await form.confirm.callback(confirmation)
        assert form.completed, str(confirmation.edit_original_response.call_args)

    asyncio.run(actual_loss())
    final = state(game)
    (saved,) = rules.records(final)
    assert saved.phase == "complete" and saved.loss.threat == threat
    changed_npc = next(x for x in final.world.npcs if x.id == npc.id)
    site = next(x for x in final.world.locations if x.id == base.id)
    assert changed_npc.alive and changed_npc.controller == npc.controller
    assert changed_npc.bonds == npc.bonds and changed_npc.jobs == npc.jobs
    assert changed_npc.revealed == npc.revealed and changed_npc.employment == npc.employment
    assert site.condition == base.condition and site.allegiance == base.allegiance
    assert not site.operational and not site.foundation_operational
    assert site.control_loss.kind == ("captured" if site_outcome == "capture" else "corrupted")
    assert site.control_loss.threat == threat and site.control_loss.source == identity
    assert not any(
        x.get("kind") in ("quadrant_loss", "structure_destroyed_source") for x in final.facts
    )
    public = worlds.get(PLAYER)
    assert '"control_loss"' not in __import__("json").dumps(public)
    with ledger.engine.connect() as c:
        assert prove(game, c, final, identity) == saved
        actual = resolve(final, victim, profiles(c, ledger.campaign_id))
        if npc_outcome == "capture":
            assert (
                changed_npc.captive_of == incoming.id
                and changed_npc.custody_event == saved.battle_event
            )
            assert actual.custody == "gorgon_captive"
            assert not any(r.actor == victim for cast in final.scene_casts for r in cast.roles)
        else:
            assert changed_npc.captive_of == npc.captive_of and actual.custody is None
            (tag_id,) = rules.npc_void_tags(final, victim)
            tag = prove_npc_void_tag(game, c, final, victim, tag_id)
            assert tag.label == "Void of the brain" and tag.giver_entity == threat.model_dump_json()
            assert ("tag:" + tag.id, tag.label) in corruption_options(final, victim)
            removed = final.model_copy(deep=True)
            removed.world = removed.world.model_copy(
                update=dict(
                    npcs=tuple(
                        x.model_copy(update=dict(tags=tuple(t for t in x.tags if t.id != tag_id)))
                        if x.id == npc.id
                        else x
                        for x in removed.world.npcs
                    )
                )
            )
            assert not any(key == "tag:" + tag_id for key, _ in corruption_options(removed, victim))
            # Pure removal suppresses the option; immutable birth proof does not require a live Tag.
            assert prove(game, c, removed, identity) == saved
    assert game.dice.calls == 0 and strain.dice.calls == 2
    assert service.view(ADMIN, identity)["phase"] == "complete"
    with pytest.raises(WorkflowError):
        service.view(PLAYER, identity)


def test_actual_fuel_capture_and_corrupted_site_preserve_bodies_and_operational_control(ledger):
    _actual_alternative(ledger, "capture", "corrupt")


def test_actual_fuel_npc_void_and_captured_site_keep_handler_choice_and_tag_provenance(ledger):
    _actual_alternative(ledger, "corrupt", "capture")
