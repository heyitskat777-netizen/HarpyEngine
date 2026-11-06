"""Actual held award restores a real destroyed Base, enabling actual empty-Frame storage."""

import asyncio
from uuid import uuid4

import pytest
import test_handler_advancements
from test_budget_storage import native as storage_native
from test_enforcer_requisitions import approved
from test_handler_advancements import source
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate, call, finish_routine, movement, recover_both
from test_strain import facts
from test_world import gorgon, initial

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_location_rebuild import open_rebuild
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_location_rebuild as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_access import Access
from girlframe.services.m3_budget_ruin import RuinService
from girlframe.services.m3_budget_storage import StorageService
from girlframe.services.m3_location_rebuild import LocationRebuildService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def setup(store, tmp_path, monkeypatch):
    def prepare_both(svc, game, high):
        svc.configure(
            ADMIN,
            str(uuid4()),
            state(game).revision,
            "barely_hanging_on",
            frozenset({"void", "budget"}),
        )
        period = svc.periods.begin(ADMIN, str(uuid4()))
        actual = state(game)
        count = sum(any(a.void for a in sheet.assets) for sheet in actual.sheets.values())
        return svc.prepare(
            ADMIN,
            str(uuid4()),
            period["id"],
            1,
            actual.revision,
            facts(at_least_half_have_void=2 * count >= len(actual.order), no_girl_void=count == 0),
        )["id"]

    monkeypatch.setattr(test_handler_advancements, "prepared", prepare_both)
    strain, game, advancement, award = source(store, tmp_path, monkeypatch, 6)
    approved(store, game, tmp_path, monkeypatch, extra=(*awards.RULES, rules.RULE))
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    strain.missions.access = Access(store)
    data = advancement.view(ADMIN, award)
    advancement.claim_void(
        ADMIN,
        str(uuid4()),
        award,
        data["revision"],
        data["work_revision"],
        "Actual held award for rebuilding",
    )
    world = initial()
    world_service = WorldService(strain.missions)
    world_service.initialize(
        ADMIN, str(uuid4()), state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    world_service.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="rebuild-superior",
            name="Actual regional superior",
            jobs=("handler",),
            controller=1,
            cell=(0, 0),
            revealed=True,
            detail="The real higher-up ordering Frame storage",
        ),
    )
    physical = PhysicalService(store)
    for viewer in (PLAYER, OTHER):
        data = physical.preview(viewer)
        proposed = physical.propose(
            viewer,
            str(uuid4()),
            data["game_revision"],
            InitialPlacement(
                actor=ActorRef.model_validate(data["actor"]),
                frame_instance=data["frame_instance"],
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                mode="outside_frame",
                account="Actual original body and empty Frame at the ruined Base site",
                facts_confirmed=True,
            ),
        )
        physical.decide(
            ADMIN, str(uuid4()), proposed["id"], 1, "accept", "Actual owned physical source"
        )
    effects = EffectService(strain)
    storage = None
    for request in tuple(state(game).strain.requests):
        if request.track == "void":
            face, column = 1, 1
            choice = Choice(
                rule_id="strain.void.low.1.1",
                account="Actual arrival",
                gorgon=gorgon("directed", str(uuid4()), (10, 0)),
            )
        elif request.track == "rebellion":
            face, column = 1, 2
            choice = Choice(rule_id="strain.rebellion.low.1.2", account="Actual control slip")
        else:
            face, column = 6, 1
            choice = Choice(
                rule_id="strain.budget.high.6.1",
                account="Actual superior's persistent storage demand",
                target="base0",
                victim="rebuild-superior",
                storage_owner=2,
            )
            storage = request.id + ":effect:storage"
        strain.dice.face = face
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, column)
        effects.apply(ADMIN, str(uuid4()), request.id + ":effect", 1, state(game).revision, choice)
    assert storage
    period = strain.periods.current(ADMIN)["id"]
    cycle = CycleService(strain.periods)
    activate(cycle, game, period)
    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    call(cycle, game, ADMIN, period, "finish", movement(game))
    period = strain.periods.begin(ADMIN, str(uuid4()))
    actual = state(game)
    count = sum(any(x.void for x in sheet.assets) for sheet in actual.sheets.values())
    strain.prepare(
        ADMIN,
        str(uuid4()),
        period["id"],
        1,
        actual.revision,
        facts(at_least_half_have_void=2 * count >= len(actual.order), no_girl_void=count == 0),
    )
    strain.dice.face = 6
    while True:
        request = next(
            x
            for x in state(game).strain.requests
            if x.track == "budget" and (x.kind == "endgame" or x.severity == "high")
        )
        if request.kind == "endgame":
            break
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, 2)
    strain.choose(ADMIN, str(uuid4()), request.id, 1, state(game).revision, 3, endgame=True)
    ruin = RuinService(store)
    source_id = request.id + ":effect"
    data = ruin.view(ADMIN, source_id)
    ruin.apply(
        ADMIN,
        str(uuid4()),
        source_id,
        data["revision"],
        data["game_revision"],
        ("base0", "city0"),
        "The genuine Budget Endgame ruins these actual locations",
    )
    return game, world_service, LocationRebuildService(store), StorageService(store), award, storage


def test_native_genuine_award_rebuild_actual_base_storage_consumer_private_history_and_replay(
    ledger, tmp_path, monkeypatch
):
    game, world, rebuild, storage_service, award, storage = setup(ledger, tmp_path, monkeypatch)
    before = state(game)
    with pytest.raises((ValueError, WorkflowError)):
        storage_service.act(
            PLAYER,
            str(uuid4()),
            storage,
            before.revision,
            "store",
            "Actually try storing the empty Frame at its destroyed Base",
        )
    assert state(game) == before and awards.awards(before)[0].phase == "held"
    old_quote = rebuild.menu(ADMIN)
    old_location = next(x for x in old_quote["locations"] if x["id"] == "base0")
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="real-intervening-npc",
            name="Actual new arrival",
            controller=1,
            jobs=("mechanic",),
            cell=(1, 0),
            revealed=True,
            detail="A real canonical intervening world event",
        ),
    )
    with pytest.raises(WorkflowError, match="Reopen"):
        rebuild.rebuild(
            ADMIN,
            str(uuid4()),
            award,
            old_quote["revision"],
            "base0",
            old_location["fingerprint"],
            "Stale quoted rebuilding",
        )
    assert awards.awards(state(game))[0].phase == "held"
    prior = state(game)
    args = []

    async def native():
        own = current(1, 34000)
        await own.response.defer(ephemeral=True)
        await open_rebuild(own, rebuild)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            award=(award,), location=("base0",), account="PRIVATE_ACTUAL_LOCATION_REBUILD"
        )
        location = next(x for x in rebuild.menu(ADMIN)["locations"] if x["id"] == "base0")
        args.extend(
            (
                ADMIN,
                "34001",
                award,
                prior.revision,
                "base0",
                location["fingerprint"],
                "PRIVATE_ACTUAL_LOCATION_REBUILD",
            )
        )
        await form.confirm.callback(current(1, 34001))
        assert form.completed

    asyncio.run(native())
    after = state(game)
    effect = awards.awards(after)[0].location_rebuild
    assert effect and effect.before.condition == "destroyed" and effect.after.condition == "intact"
    assert next(x for x in after.world.locations if x.id == "base0").operational
    assert after.world == prior.world.model_copy(
        update=dict(
            locations=tuple(effect.after if x.id == "base0" else x for x in prior.world.locations)
        )
    )
    assert (
        after.sheets == prior.sheets
        and after.placements == prior.placements
        and after.strain == prior.strain
    )
    result = rebuild.rebuild(*args)
    assert result["phase"] == "spent" and state(game) == after
    storage_native(StorageService(ledger), 2, storage, "store")
    assert StorageService(ledger).view(PLAYER, storage)["entries"][-1]["action"] == "store"

    async def history():
        inbox = InboxService(ledger)
        item = next(
            x for x in inbox.items(ADMIN) if x.task == "m3_location_rebuild" and x.identity == award
        )
        assert not item.incoming
        own = current(1, 34010)
        own.channel_id = 999
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(own, item)
        content = own.edit_original_response.call_args.kwargs["content"]
        assert (
            "destroyed" in content
            and "intact" in content
            and "PRIVATE_ACTUAL_LOCATION_REBUILD" not in content
        )

    asyncio.run(history())
