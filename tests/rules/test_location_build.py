"""One genuine award creates an actual Base and enables original-owner Frame storage."""

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
from test_strain import facts
from test_world import initial

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_location_build import open_build
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_location_build as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_access import Access
from girlframe.services.m3_budget_storage import StorageService
from girlframe.services.m3_location_build import LocationBuildService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError

SITE = (3, 2)


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
        count = sum(any(x.void for x in sheet.assets) for sheet in actual.sheets.values())
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
        "Actual held award for a new location",
    )
    initial_world = initial()
    world = WorldService(strain.missions)
    world.initialize(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        initial_world.board,
        initial_world.locations,
        initial_world.gorgons[0],
    )
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="build-superior",
            name="Actual regional superior",
            jobs=("handler",),
            controller=1,
            cell=(0, 0),
            revealed=True,
            detail="Real higher-up requiring an actual Base",
        ),
    )
    physical = PhysicalService(store)
    for viewer in (PLAYER, OTHER):
        data = physical.preview(viewer)
        cell = SITE if viewer == PLAYER else (0, 0)
        proposed = physical.propose(
            viewer,
            str(uuid4()),
            data["game_revision"],
            InitialPlacement(
                actor=ActorRef.model_validate(data["actor"]),
                frame_instance=data["frame_instance"],
                girl_cell=cell,
                frame_cell=cell,
                mode="outside_frame",
                account="Actual original Girl and empty assigned Frame at this real map square",
                facts_confirmed=True,
            ),
        )
        physical.decide(
            ADMIN, str(uuid4()), proposed["id"], 1, "accept", "Actual original physical source"
        )
    request = next(x for x in state(game).strain.requests if x.track == "budget")
    strain.dice.face = 6
    strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
    strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, 1)
    return (
        game,
        world,
        LocationBuildService(store),
        EffectService(strain),
        award,
        request.id + ":effect",
    )


def test_genuine_native_new_base_real_owner_storage_history_and_single_spend(
    ledger, tmp_path, monkeypatch
):
    game, world, build, effects, award, storage_source = setup(ledger, tmp_path, monkeypatch)
    before = state(game)
    assert not any(x.cell == SITE for x in before.world.locations)
    with pytest.raises((ValueError, WorkflowError)):
        effects.apply(
            ADMIN,
            str(uuid4()),
            storage_source,
            1,
            before.revision,
            Choice(
                rule_id="strain.budget.high.6.1",
                target="unbuilt-site",
                victim="build-superior",
                storage_owner=2,
                account="There is no actual Base at the intended site yet",
            ),
        )
    quote = build.menu(ADMIN)
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="actual-intervening-arrival",
            name="Actual arrival",
            jobs=("mechanic",),
            controller=1,
            cell=(1, 0),
            revealed=True,
            detail="Actual source change before confirmation",
        ),
    )
    with pytest.raises(WorkflowError, match="Reopen"):
        build.build(
            ADMIN,
            str(uuid4()),
            award,
            quote["revision"],
            "base",
            "Actual new Base",
            SITE,
            "Stale construction quote",
        )
    assert awards.awards(state(game))[0].phase == "held"
    prior = state(game)
    args = []

    async def native_build():
        own = current(1, 35000)
        await own.response.defer(ephemeral=True)
        await open_build(own, build)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            award=(award,),
            kind=("base",),
            name="Actual new Base",
            x="3",
            y="2",
            account="PRIVATE_ACTUAL_LOCATION_BUILD",
        )
        args.extend(
            (
                ADMIN,
                "35001",
                award,
                prior.revision,
                "base",
                "Actual new Base",
                SITE,
                "PRIVATE_ACTUAL_LOCATION_BUILD",
            )
        )
        await form.confirm.callback(current(1, 35001))
        assert form.completed

    asyncio.run(native_build())
    after = state(game)
    effect = awards.awards(after)[0].location_build
    assert (
        effect
        and effect.location.kind == "base"
        and effect.location.cell == SITE
        and effect.location.operational
    )
    assert len(after.world.locations) == len(prior.world.locations) + 1
    assert after.world == prior.world.model_copy(
        update=dict(locations=prior.world.locations + (effect.location,))
    )
    assert (
        after.sheets == prior.sheets
        and after.placements == prior.placements
        and after.strain == prior.strain
    )
    result = build.build(*args)
    assert result["location"] == effect.location.id and state(game) == after
    effects.apply(
        ADMIN,
        str(uuid4()),
        storage_source,
        1,
        after.revision,
        Choice(
            rule_id="strain.budget.high.6.1",
            target=effect.location.id,
            victim="build-superior",
            storage_owner=2,
            account="The actual new Base receives the original empty Frame",
        ),
    )
    storage = storage_source + ":storage"
    storage_native(StorageService(ledger), 2, storage, "store")
    assert StorageService(ledger).view(PLAYER, storage)["entries"][-1]["action"] == "store"

    async def history():
        inbox = InboxService(ledger)
        item = next(
            x for x in inbox.items(ADMIN) if x.task == "m3_location_build" and x.identity == award
        )
        assert not item.incoming
        own = current(1, 35010)
        own.channel_id = 999
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(own, item)
        content = own.edit_original_response.call_args.kwargs["content"]
        assert "Actual new Base" in content and "PRIVATE_ACTUAL_LOCATION_BUILD" not in content

    asyncio.run(history())
