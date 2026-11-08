"""Genuine award purchase, real Mission repair/delivery and source expiry consequences."""

import asyncio
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_engage_actual import pass_tags
from test_handler_advancements import source
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate, call, finish_routine, movement, recover_both
from test_punishment_service import submit
from test_void_keep import keep as resist
from test_world import gorgon, initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_supply_drop import open_supply_drop
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_modular
from girlframe.engine import m3_supply_drop as rules
from girlframe.engine.m2 import AssetState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_modular import Replacement
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Faction
from girlframe.services.inbox import InboxService
from girlframe.services.m3_access import Access
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_modular import ModularService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_supply_drop import SupplyDropService
from girlframe.services.m3_void import VoidService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    strain, game, advancement, award = source(store, tmp_path, monkeypatch, 6)
    approved(store, game, tmp_path, monkeypatch, extra=(*awards.RULES, rules.RULE, m3_modular.RULE))
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    strain.missions.access = Access(store)
    world = initial()
    WorldService(strain.missions).initialize(
        ADMIN, str(uuid4()), state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    physical = PhysicalService(store)
    for viewer in (PLAYER, OTHER):
        data = physical.preview(viewer)
        result = physical.propose(
            viewer,
            str(uuid4()),
            data["game_revision"],
            InitialPlacement(
                actor=ActorRef.model_validate(data["actor"]),
                frame_instance=data["frame_instance"],
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                mode="piloting",
                account="Actual original Girl and assigned Frame",
                facts_confirmed=True,
            ),
        )
        physical.decide(
            ADMIN, str(uuid4()), result["id"], 1, "accept", "Actual source-proved placement"
        )
    data = advancement.view(ADMIN, award)
    advancement.claim_void(
        ADMIN,
        str(uuid4()),
        award,
        data["revision"],
        data["work_revision"],
        "Actual held Handler advancement",
    )
    # Finish the actual original preparation and Off-Duty lifecycle; no source work is waived.
    effects = EffectService(strain)
    for request in tuple(state(game).strain.requests):
        if request.track == "void":
            face, column = 1, 1
            choice = Choice(
                rule_id="strain.void.low.1.1",
                account="Actual source arrival",
                gorgon=gorgon("directed", str(uuid4()), (10, 0)),
            )
        elif request.track == "rebellion":
            face, column = 1, 1
            choice = Choice(
                rule_id="strain.rebellion.low.1.1",
                account="Actual group appears",
                target="city0",
                faction=Faction(
                    id="actual-group",
                    name="Actual group",
                    kind="rebel",
                    cells=((0, 4),),
                    description="Actual dissent",
                ),
            )
        else:
            face, column = 5, 2
            choice = Choice(
                rule_id="strain.budget.low.5.2", account="Actual reassigned rooms", rooms=((2, 3),)
            )
        strain.dice.face = face
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, column)
        effects.apply(ADMIN, str(uuid4()), request.id + ":effect", 1, state(game).revision, choice)
    period = strain.periods.current(ADMIN)["id"]
    cycle = CycleService(strain.periods)
    activate(cycle, game, period)
    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    call(cycle, game, ADMIN, period, "finish", movement(game))
    return game, SupplyDropService(store), MissionService(store), award


def acquire(service, award):
    data = service.menu(ADMIN)
    args = (
        ADMIN,
        "actual-supply-acquisition",
        award,
        data["revision"],
        "Actual Supply Drop acquisition",
    )
    result = service.buy(*args)
    assert service.buy(*args) == result
    return result["id"]


def launch(missions):
    offered = missions.offer(ADMIN, str(uuid4()), "Actual Supply Drop Mission", (2, 3))
    missions.respond(PLAYER, str(uuid4()), offered["id"], 1, "accept")
    missions.respond(OTHER, str(uuid4()), offered["id"], 2, "accept")
    missions.start(ADMIN, str(uuid4()), offered["id"], 3)
    return offered["id"]


def settle(missions, game, mission):
    for work in missions.get(ADMIN, mission)["work"]:
        if work["kind"] == "punishment":
            submit(
                PunishmentService(game.store),
                ADMIN,
                work["id"],
                Details(kind="stimulant_injection"),
                str(uuid4()),
            )
    data = missions.get(ADMIN, mission)
    return missions.complete(ADMIN, str(uuid4()), mission, data["mission"]["revision"])


def propose(service, game, mission, kind="drop", asset=None):
    return service.act(
        ADMIN,
        str(uuid4()),
        mission,
        state(game).revision,
        kind,
        current_ref(state(game), 2),
        "Actual original Supply Drop use",
        asset=asset,
        name="Actual temporary cover",
        description="Custom temporary cover delivered to the original Frame",
    )["id"]


def native_receive(service, identity, viewer=PLAYER, *, replace=None, battle=None, number=31700):
    async def receive():
        inbox = InboxService(service.store)
        item = next(
            x for x in inbox.items(viewer) if x.task == "m3_supply_drop" and x.identity == identity
        )
        own = current(viewer.user_id, number)
        own.channel_id = 999
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, viewer.user_id).route(own, item)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(account="Actual owned receipt and installation")
        if battle is not None:
            form.values.update(battle=("yes" if battle else "no",))
        else:
            form.values.update(receive=("yes",))
            if replace:
                form.values.update(replace=(replace,))
        await form.confirm.callback(current(viewer.user_id, number + 1))
        assert form.completed

    asyncio.run(receive())


def test_actual_award_rule_repair_modular_then_next_mission_owner_capacity_delivery_use_and_expiry(
    ledger, tmp_path, monkeypatch
):
    game, supply, missions, award = ready(ledger, tmp_path, monkeypatch)
    before = state(game)

    async def buy_native():
        own = current(1, 31600)
        await own.response.defer(ephemeral=True)
        await open_supply_drop(own, supply)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(award=(award,), account="Actual source-backed Supply Drop")
        await form.confirm.callback(current(1, 31601))
        assert form.completed

    asyncio.run(buy_native())
    assert state(game).sheets == before.sheets
    assert awards.awards(state(game))[0].acquired_rule == rules.RULE
    with pytest.raises(WorkflowError, match="appointed campaign Handler"):
        supply.menu(PLAYER)
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].permissions = 6
        game.event(c, 1, str(uuid4()), "synthetic.actual_existing_permissions", actual)
    modular = ModularService(game)
    data = modular.menu(PLAYER)
    modular.buy(
        PLAYER,
        str(uuid4()),
        data["revision"],
        ActorRef.model_validate(data["actor"]),
        data["frame"],
        "Actual eligible Modular graft",
        "Actual extra hardware",
        "Actual extra Frame equipment",
        "WYVERN 0.4",
    )
    with ledger.transaction() as c:
        actual = state(game)
        sheet = actual.sheets["2"]
        damaged = next(x for x in sheet.assets if x.family == "frame")
        damaged.damaged = True
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_damage", actual)
    mission = launch(missions)
    repair = propose(supply, game, mission, "repair", damaged.id)
    data = supply.view_delivery(PLAYER, repair)
    assert (
        data["modular"]
        and next(x for x in state(game).sheets["2"].assets if x.id == damaged.id).damaged
    )
    supply.receive(
        PLAYER,
        str(uuid4()),
        repair,
        data["revision"],
        True,
        "My actual Modular replacement",
        modular=Replacement(
            asset=damaged.id, name="Actual repaired replacement", description="Actual replacement"
        ),
    )
    actual = state(game)
    assert all(x.id != damaged.id for x in actual.sheets["2"].assets)
    assert actual.facts[-1]["kind"] == "supply_drop_use"
    assert any(
        x.name == "Actual repaired replacement" and not x.damaged for x in actual.sheets["2"].assets
    )
    with pytest.raises(WorkflowError, match="unused"):
        propose(supply, game, mission)
    missions.end(
        ADMIN, str(uuid4()), mission, missions.get(ADMIN, mission)["mission"]["revision"], True
    )
    assert settle(missions, game, mission)["phase"] == "complete"
    # Real next Mission resets only the per-Mission use, not the paid rule/award.
    with ledger.transaction() as c:
        actual = state(game)
        sheet = actual.sheets["2"]
        while sum(x.family == "frame" for x in sheet.assets) < 6:
            sheet.assets.append(
                AssetState(
                    id="existing:" + str(len(sheet.assets)),
                    family="frame",
                    name="Actual prior hardware",
                )
            )
        game.event(c, 1, str(uuid4()), "synthetic.actual_existing_full_hardware", actual)
    mission = launch(missions)
    use = propose(supply, game, mission)
    proposed = state(game)
    assert not any(x.id == "supply-drop:" + use for x in proposed.sheets["2"].assets)
    data = supply.view_delivery(PLAYER, use)
    assert data["needs_replace"]
    # A genuine owned Play changes the quoted resources before receipt, without use/charge.
    game.dice.faces = (1, 1)
    worker, gateway = GameWorker(game), Gateway()
    prior = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=state(game).sheets["2"].heat,
            context="Actual danger before receiving the proposal",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The actual previous danger is resolved")
    assert game.inspect(PLAYER, prior)["state"] == "complete"
    tick(worker, gateway, 6)
    changed = state(game)
    stale = supply.view_delivery(PLAYER, use)
    with pytest.raises(WorkflowError, match="unchanged Girl"):
        supply.receive(
            PLAYER,
            str(uuid4()),
            use,
            stale["revision"],
            True,
            "Old quote cannot change resources",
            replace=data["replacements"][-1]["id"],
        )
    assert state(game) == changed and not rules.spent(
        changed, supply.menu(ADMIN, mission)["receipt"], mission
    )
    supply.receive(
        ADMIN, str(uuid4()), use, changed.revision, False, "Cancel the undelivered old quote"
    )
    use = propose(supply, game, mission)
    proposed = state(game)
    data = supply.view_delivery(PLAYER, use)
    with pytest.raises(WorkflowError, match="original recipient"):
        supply.receive(
            ADMIN, str(uuid4()), use, data["revision"], True, "Handler cannot choose my hardware"
        )
    replace = data["replacements"][-1]["id"]
    native_receive(supply, use, replace=replace)
    delivered = state(game)
    asset = next(x for x in delivered.sheets["2"].assets if x.id == "supply-drop:" + use)
    assert asset.family == "frame" and all(x.id != replace for x in delivered.sheets["2"].assets)
    args = (PLAYER, "31701", use, data["revision"], True, "Actual owned receipt and installation")
    assert supply.receive(*args, replace=replace) == dict(id=use, phase="delivered")
    assert state(game) == delivered and len(delivered.sheets["2"].assets) == len(
        proposed.sheets["2"].assets
    )
    with pytest.raises(ValueError, match="temporary|Supply Drop"):
        rules.require_temporary_clear(delivered, current_ref(delivered, 2))
    # The actual new canonical Asset participates in the ordinary Engage consumer.
    game.dice.faces = (4, 4)
    worker, gateway = GameWorker(game), Gateway()
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        delivered.sheets["2"].revision,
        PlayInput(
            play="engage",
            heat=delivered.sheets["2"].heat,
            target_actor=current_ref(delivered, 3),
            context="Actual cover using delivered equipment",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=("cover", "protect"),
        fields={"cover": asset.id, "protect": asset.id},
        text="Actual battlefield cover and protection",
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 6)
    before_end = state(game)
    missions.end(
        ADMIN, str(uuid4()), mission, missions.get(ADMIN, mission)["mission"]["revision"], True
    )
    expired = state(game)
    assert all(x.id != asset.id for x in expired.sheets["2"].assets)
    assert [x for x in before_end.sheets["2"].assets if x.id != asset.id] == expired.sheets[
        "2"
    ].assets
    assert next(x for x in rules.uses(expired) if x.id == use).phase == "expired"
    assert settle(missions, game, mission)["phase"] == "complete"
    assert len(awards.awards(state(game))) == 1 and len(rules.acquisitions(state(game))) == 1


def test_actual_expiry_last_usable_frame_context_requires_real_defeat_before_mission_rewards(
    ledger, tmp_path, monkeypatch
):
    game, supply, missions, award = ready(ledger, tmp_path, monkeypatch)
    acquire(supply, award)
    mission = launch(missions)
    use = propose(supply, game, mission)
    native_receive(supply, use)
    with ledger.transaction() as c:
        actual = state(game)
        for asset in actual.sheets["2"].assets:
            if asset.family == "frame" and asset.id != "supply-drop:" + use:
                asset.damaged = True
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_frame_damage", actual)
    ended = missions.end(
        ADMIN, str(uuid4()), mission, missions.get(ADMIN, mission)["mission"]["revision"], True
    )
    assert ended["phase"] == "ending" and not ended["rewards_committed"]
    with pytest.raises(WorkflowError, match="pending"):
        missions.complete(ADMIN, str(uuid4()), mission, ended["revision"])
    native_receive(supply, use, ADMIN, battle=True, number=31800)
    work = next(x for x in missions.get(PLAYER, mission)["work"] if x["kind"] == "defeat")
    with pytest.raises(WorkflowError, match="pending"):
        missions.complete(ADMIN, str(uuid4()), mission, ended["revision"])
    game.dice.faces = (3, 3)
    worker, gateway = GameWorker(game), Gateway()
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="defeat",
            source_work=work["id"],
            heat=0,
            context="Actual source-owned Defeat after equipment expiry",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("escape_cockpit_choose_location",),
        text="I escape the actual damaged Frame",
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 6)
    result = missions.complete(ADMIN, str(uuid4()), mission, ended["revision"])
    assert result["rewards_committed"]
    assert settle(missions, game, mission)["phase"] == "complete"


def test_actual_expiry_exposes_full_void_family_and_owned_threshold_blocks_mission(
    ledger, tmp_path, monkeypatch
):
    game, supply, missions, award = ready(ledger, tmp_path, monkeypatch)
    acquire(supply, award)
    mission = launch(missions)
    use = propose(supply, game, mission)
    native_receive(supply, use)
    with ledger.transaction() as c:
        actual = state(game)
        for asset in actual.sheets["2"].assets:
            if asset.family == "frame" and asset.id != "supply-drop:" + use:
                asset.void = True
        game.event(c, 1, str(uuid4()), "synthetic.actual_prior_void_hardware", actual)
    ended = missions.end(
        ADMIN, str(uuid4()), mission, missions.get(ADMIN, mission)["mission"]["revision"], True
    )
    assert ended["phase"] == "ending"
    work = next(x for x in missions.get(PLAYER, mission)["work"] if x["kind"] == "void_threshold")
    view = VoidService(ledger).get(PLAYER, work["id"])
    assert view["threshold"]["family"] == "frame"
    with pytest.raises(WorkflowError, match="pending"):
        missions.complete(ADMIN, str(uuid4()), mission, ended["revision"])
    worker, gateway = GameWorker(game), Gateway()
    child = resist(game, worker, gateway, None, work["id"])
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert VoidService(ledger).get(PLAYER, work["id"])["stage"] == "prevented"
    tick(worker, gateway, 6)
    result = missions.complete(ADMIN, str(uuid4()), mission, ended["revision"])
    assert result["rewards_committed"]
    assert settle(missions, game, mission)["phase"] == "complete"
