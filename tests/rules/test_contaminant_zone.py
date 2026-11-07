"""Actual quarantines feed Strain, Gorgon/Harpy rules, site protection and source Warp."""

import asyncio
from uuid import uuid4

import pytest
from handler_award_scenario import ordinary_pr_award
from test_battle_pipeline import table
from test_cast_service import change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current
from test_strain import facts
from test_strain_service import D6
from test_world import gorgon

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_contaminant_zone import open_zone
from girlframe.discord_adapter.m3_handler_advancements import (
    AcquireContaminantZone,
    open_advancement,
)
from girlframe.engine import m3_contaminant_zone as rules
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle_state import Declaration
from girlframe.engine.m3_gorgon import NpcAttack
from girlframe.engine.m3_strain import effective_levels
from girlframe.engine.m3_world import destroy, end_off_duty, update
from girlframe.engine.m3_world_state import Faction, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actor_plays import ActorPlayService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_battle import BattleService
from girlframe.services.m3_battle_dormant import DormantService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_contaminant_zone import (
    ContaminantZoneService,
    paid,
    prove_harpy,
    zone_proof,
)
from girlframe.services.m3_gorgon import GorgonService
from girlframe.services.m3_handler_advancements import HandlerAdvancementService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_harpy_defeat import HarpyDefeatService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def setup(store, tmp_path, monkeypatch):
    game, worker, gateway = ordinary_pr_award(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    store.policy = store.policy.model_copy(
        update=dict(
            m3_approval=store.policy.m3_approval.model_copy(
                update=dict(
                    subsystems=store.policy.m3_approval.subsystems | {"strain", "world", "plays"}
                )
            )
        )
    )
    game.dice = Dice((4, 4))
    return game, ContaminantZoneService(store), worker, gateway


async def step(interaction, **values):
    form = interaction.edit_original_response.call_args.kwargs["view"]
    form.values.update(values)
    response = current(1, int(uuid4().int % 1000000000))
    response.channel_id = 900
    await form.confirm.callback(response)
    assert form.completed, response.edit_original_response.call_args
    return response


def acquire(service, game):
    award = next(x for x in awards.awards(state(game)) if x.phase == "held")

    async def run():
        own = current(1, int(uuid4().int % 1000000000))
        await own.response.defer(ephemeral=True)
        await open_advancement(own, HandlerAdvancementService(service.store), award.id)
        form = own.edit_original_response.call_args.kwargs["view"]
        button = next(x for x in form.children if isinstance(x, AcquireContaminantZone))
        selected = current(1, int(uuid4().int % 1000000000))
        await selected.response.defer(ephemeral=True)
        await button.callback(selected)
        await step(selected, account="My actual held award buys Contaminant Zone")

    asyncio.run(run())
    receipt = rules.acquisitions(state(game))[0]
    assert awards.awards(state(game))[0].acquisition == receipt.id
    return receipt


def quarantine_native(service, identity, *, study=False):
    async def run():
        own = current(1, int(uuid4().int % 1000000000))
        await own.response.defer(ephemeral=True)
        await open_zone(own, service, identity)
        selected = await step(own, operation=("quarantine",))
        form = await step(
            selected,
            cells="2,0\n2,1" if study else "0,0\n0,1",
            effects=("rebel_replacement", "field_study") if study else ("void_relief", "dormancy"),
            perimeter="Actual fenced research boundary"
            if study
            else "Actual sealed two-square cordon",
            account="My actual source-owned quarantine is physically established",
        )
        if study:
            form = await step(
                form,
                name="Actual replacement Harpy",
                cell="2,1",
                body=("linked",),
                heat="0",
                girl_assets="Void skin:An actual protective Girl capability",
                frame_assets="Harpy claws:Actual Void Frame claws",
                identities="Curious",
                account="My actual new world Harpy, linked capable body and owned resources",
            )
            await step(form, name="Actual protected study", manager=("private-study-manager",))

    asyncio.run(run())
    return rules.zones(state(service.game))[-1]


def test_actual_relief_dormancy_awakening_strain_consumer_and_real_breach(
    ledger, tmp_path, monkeypatch
):
    from girlframe.services import m2_game as shared

    monkeypatch.setattr(shared, "M3_HEAT_IDS", (*shared.M3_HEAT_IDS, "all_out_assault"))
    game, service, worker, gateway = setup(ledger, tmp_path, monkeypatch)
    original = gorgon("erratic", "actual-existing-gorgon", revealed=True)
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = update(canon.world, gorgons=(original,))
        game.event(c, 1, "actual-initial-gorgon", "synthetic.preexisting_world", canon)
    strain = StrainService(OffDutyService(MissionService(ledger)), dice=D6(1))
    strain.configure(ADMIN, str(uuid4()), state(game).revision, "business_as_usual", frozenset())
    receipt = acquire(service, game)
    zone = quarantine_native(service, receipt.id)
    result = state(game)
    actual = result.world.gorgons[0]
    assert actual.gorgon_class == "dormant" and actual.assets == original.assets
    assert actual.core_plan == original.core_plan and len(actual.assets) == 4
    assert (
        set(zone.cells) <= result.world.territory
        and effective_levels(result.strain)["void"] == "low"
    )
    casting = CastService(ActorService(MissionService(ledger)))
    foe = ActorRef(kind="gorgon", entity=actual.id)
    change(casting, ADMIN, "join", foe)
    battle = BattleService(ledger)
    preview = battle.preview(PLAYER, 900)
    actor = next(x for x in preview["actors"] if x["ref"]["entity"] == "2")
    target = next(x for x in preview["actors"] if x["ref"]["kind"] == "gorgon")
    declaration = Declaration(
        play="all_out_assault",
        actor=ActorRef.model_validate(actor["ref"]),
        target=foe,
        attacking_asset=actor["assets"][0]["id"],
        target_asset=target["assets"][0]["id"],
        actor_sha256=actor["sha256"],
        target_sha256=target["sha256"],
        account="Actual attack forces this real quarantined Gorgon awake",
    )
    opening = battle.propose(PLAYER, str(uuid4()), preview["revision"], 900, declaration)
    battle.confirm(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        opening["id"],
        opening=True,
        reach=True,
        outside_permission=True,
        indirect=False,
        evidence="The actual original Girl reaches the still Gorgon",
        dormant_awakened=True,
        dormant_close=False,
    )
    root = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="all_out_assault",
            heat=0,
            target_actor=foe,
            attacking_asset=declaration.attacking_asset,
            target_asset=declaration.target_asset,
            battle_context=opening["id"],
            context=declaration.account,
            trigger_confirmed=True,
            piloting=False,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    dormant = DormantService(ledger, game)
    work = next(x.identity for x in InboxService(ledger).items(PLAYER) if x.task == "m3_dormant")
    current_work = dormant.get(PLAYER, work)
    dormant.alter(
        PLAYER,
        str(uuid4()),
        work,
        current_work["revision"],
        current_work["game_revision"],
        current_work["assets"][0]["id"],
        "The actual original Girl capability gains real Void",
        piloting=False,
    )
    table(game)
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, root)["state"] == "complete"
    assert any(a.void for a in state(game).sheets["2"].assets)
    period = strain.periods.begin(ADMIN, str(uuid4()))
    strain.prepare(
        ADMIN,
        str(uuid4()),
        period["id"],
        1,
        state(game).revision,
        facts(at_least_half_have_void=True, no_girl_void=False),
    )
    current_state = state(game)
    request = next(x for x in current_state.strain.requests if x.track == "void")
    assert current_state.strain.levels["void"] == "high" and request.severity == "low"
    strain.roll(ADMIN, str(uuid4()), request.id, 1, current_state.revision)
    assert next(x for x in state(game).strain.events if x.id == request.id).severity == "low"
    source = state(game)
    service.break_quarantine(
        ADMIN,
        "contaminant-real-breach",
        zone.id,
        source.revision,
        foe,
        (0, 0),
        "The awakened original Gorgon physically ruptures the actual cordon",
    )
    final = state(game)
    assert (
        final.strain.levels["void"] == "high" and effective_levels(final.strain)["void"] == "high"
    )
    assert (
        final.strain.events == source.strain.events
        and final.world.territory == source.world.territory
    )
    assert final.world.gorgons == source.world.gorgons and not final.strain.void_relief_sources
    with pytest.raises(WorkflowError, match="still-intact"):
        service.break_quarantine(
            ADMIN, str(uuid4()), zone.id, final.revision, foe, (0, 0), "No second expiry"
        )
    with ledger.engine.connect() as c:
        assert zone_proof(game, c, final, zone.id).broken_event
        assert paid(game, c, final, receipt.id) == receipt
    assert game.dice.calls == 1


def test_actual_group_harpy_study_warp_protection_expiry_and_private_history(
    ledger, tmp_path, monkeypatch
):
    game, service, worker, gateway = setup(ledger, tmp_path, monkeypatch)
    world = WorldService(MissionService(ledger))
    group = Faction(
        id="actual-contained-rebels", name="Actual contained Rebels", kind="rebel", cells=((2, 1),)
    )
    world.faction(ADMIN, str(uuid4()), state(game).revision, group)
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="private-study-manager",
            name="PRIVATE_ACTUAL_MANAGER",
            jobs=("scientist",),
            detail="Actual field researcher",
            controller=1,
            cell=(2, 0),
        ),
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            gorgons=(gorgon("aggressive", "actual-site-threat", cell=(2, 0), revealed=True),),
        )
        game.event(c, 1, "actual-initial-site-threat", "synthetic.preexisting_world", canon)
    receipt = acquire(service, game)
    zone = quarantine_native(service, receipt.id, study=True)
    current_state = state(game)
    assert not next(x for x in current_state.world.factions if x.id == group.id).active
    ref = ActorRef(kind="external_pilot", entity=zone.harpies[0])
    with ledger.engine.connect() as c:
        body = prove_harpy(game, c, current_state, ref)
        assert HarpyDefeatService(ledger, game)._runtime(c, current_state, ref) == body
    assert body.frame_instance and len(resolve(current_state, ref, ()).assets) == 2
    casting = CastService(ActorService(MissionService(ledger)))
    change(casting, ADMIN, "join", ref)
    plays = ActorPlayService(game)
    preview = plays.preview(ADMIN, 900, ref)
    action = plays.begin(
        ADMIN,
        str(uuid4()),
        900,
        ref,
        preview["actor"]["source_sha256"],
        None,
        preview["cast_revision"],
        PlayInput(
            play="keep_your_head",
            heat=0,
            context="Actual new Harpy faces meaningful danger",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, ADMIN, "actor_keep", options=("beautiful", "in_control"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="My actual human source judgment")
    tick(worker, gateway, 5)
    assert game.inspect(ADMIN, action)["state"] == "complete" and game.dice.calls == 1
    threat = ActorRef(kind="gorgon", entity="actual-site-threat")
    manager = ActorRef(kind="npc", entity="private-study-manager")
    source = state(game)
    site = next(x for x in source.world.locations if zone.id in x.protection_sources)
    with pytest.raises(ValueError, match="quarantine"):
        destroy(source.world, site.id, gorgon_cause=True)
    advanced = end_off_duty(source.world, "actual-protected-site-end", (), ())
    assert next(x for x in advanced.world.locations if x.id == site.id).condition == "intact"
    gorgons = GorgonService(world)
    assert not gorgons.preview(ADMIN)["attackers"]

    replay = {}

    async def actual_warp():
        own = current(1, int(uuid4().int % 1000000000))
        await own.response.defer(ephemeral=True)
        await open_zone(own, service, zone.id)
        selected = await step(own, operation=("warp",))
        picker = selected.edit_original_response.call_args.kwargs["view"]
        next_step = current(1, int(uuid4().int % 1000000000))
        await next_step.response.defer(ephemeral=True)
        await picker.open_item(next_step, "contaminant_warp")
        replay["revision"] = state(game).revision
        confirmation = await step(
            next_step,
            cell="2,1",
            feature_label="The singing boundary",
            detail="Actual ground bends into a visible spiral around the source perimeter",
            account="My original Handler actually warps this part of the quarantined area",
        )
        replay["key"] = str(confirmation.id)

    asyncio.run(actual_warp())
    warped = state(game)
    feature = warped.world.features[0]
    assert feature.zone == zone.id and feature.cell == (2, 1)
    assert next(x for x in warped.handler_plays if x.id == feature.grant).state == "complete"
    grant = next(x for x in warped.handler_plays if x.id == feature.grant)
    handler_plays = HandlerPlayService(ledger)
    repeated = handler_plays.submit(
        ADMIN, replay["key"], grant.id, replay["revision"], "contaminant_warp", grant.effect
    )
    assert repeated["state"] == "complete" and state(game) == warped
    with pytest.raises(WorkflowError):
        handler_plays.submit(
            ADMIN, str(uuid4()), grant.id, warped.revision, "contaminant_warp", grant.effect
        )
    assert state(game).world.features == warped.world.features
    public, private = world.get(OTHER), world.get(ADMIN, private=True)
    assert "The singing boundary" in str(public) and "PRIVATE_ACTUAL_MANAGER" not in str(public)
    assert "source_event" not in str(public["world"]["features"])
    assert "private-study-manager" in str(private)
    service.break_quarantine(
        ADMIN,
        str(uuid4()),
        zone.id,
        warped.revision,
        threat,
        (2, 0),
        "The actual Gorgon breaks the real study perimeter",
    )
    final = state(game)
    assert handler_plays.get(ADMIN, grant.id)["grant"]["state"] == "complete"
    assert not final.world.field_studies[0].protected
    attacker, target = resolve(final, threat, ()), resolve(final, manager, ())
    gorgons.attack(
        ADMIN,
        str(uuid4()),
        final.revision,
        NpcAttack(
            attacker=threat,
            target=manager,
            assets=(attacker.assets[0].id,),
            attacker_sha256=attacker.source_sha256,
            target_sha256=target.source_sha256,
            account="The original Gorgon actually attacks after the breach",
            trigger_confirmed=True,
        ),
    )
    assert not next(x for x in state(game).world.npcs if x.id == manager.entity).alive
    assert state(game).world.features == warped.world.features

    async def history():
        inbox = InboxService(ledger)
        item = next(
            x
            for x in inbox.items(ADMIN)
            if x.task == "m3_contaminant_zone" and x.identity == zone.id
        )
        assert item.state == "established" and not item.incoming
        own = current(1, int(uuid4().int % 1000000000))
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(own, item)
        assert "broken" in str(own.edit_original_response.call_args)

    asyncio.run(history())
