"""Genuine held insurance, actual deaths, Budget effect and real storage release."""

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
from test_punishment_service import submit
from test_strain import facts
from test_supply_drop import ready as ready_low
from test_world import gorgon, initial

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_girl_insurance import open_insurance
from girlframe.discord_adapter.m3_strain import open_work
from girlframe.engine import m3_girl_insurance as rules
from girlframe.engine import m3_handler_advancements as advancement
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_strain_effects import Choice
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_access import Access
from girlframe.services.m3_budget_storage import StorageService
from girlframe.services.m3_girl_insurance import GirlInsuranceService, verify_exclusion
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def buy(service, award):
    async def native():
        own = current(1, 33000)
        await own.response.defer(ephemeral=True)
        await open_insurance(own, service)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(award=(award,), account="PRIVATE_GENUINE_INSURANCE_SOURCE")
        await form.confirm.callback(current(1, 33001))
        assert form.completed

    asyncio.run(native())
    return rules.acquisitions(state(service.game))[-1].id


def high_ready(store, tmp_path, monkeypatch):
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
    strain, game, awards, award = source(store, tmp_path, monkeypatch, 6)
    approved(store, game, tmp_path, monkeypatch, extra=(*advancement.RULES, rules.RULE))
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    strain.missions.access = Access(store)
    data = awards.view(ADMIN, award)
    awards.claim_void(
        ADMIN,
        str(uuid4()),
        award,
        data["revision"],
        data["work_revision"],
        "Actual held insurance advancement",
    )
    insurance = GirlInsuranceService(store)
    receipt = buy(insurance, award)
    world = initial()
    WorldService(strain.missions).initialize(
        ADMIN, str(uuid4()), state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    WorldService(strain.missions).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="insurance-superior",
            name="Actual regional superior",
            controller=1,
            jobs=("handler",),
            cell=(0, 0),
            revealed=True,
            detail="Actual higher-up requiring ordinary Frame storage",
        ),
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
                mode="outside_frame",
                account="Actual original Girl outside assigned Frame",
                facts_confirmed=True,
            ),
        )
        physical.decide(
            ADMIN, str(uuid4()), result["id"], 1, "accept", "Actual source-proved placement"
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
                account="Actual higher-up stores empty Frame",
                target="base0",
                victim="insurance-superior",
                storage_owner=2,
            )
            storage = request.id + ":effect:storage"
        strain.dice.face = face
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, column)
        effects.apply(ADMIN, str(uuid4()), request.id + ":effect", 1, state(game).revision, choice)
    assert storage
    storage_native(StorageService(store), 2, storage, "store")
    period = strain.periods.current(ADMIN)["id"]
    cycle = CycleService(strain.periods)
    activate(cycle, game, period)
    recover_both(cycle, game, period)
    finish_routine(cycle, game, period)
    call(cycle, game, ADMIN, period, "finish", movement(game))
    return insurance, strain, game, receipt, storage


def actual_death(game, missions):
    mission = missions.offer(ADMIN, str(uuid4()), "Actual failed mission by unstored Girl", (3,))
    mission = missions.respond(OTHER, str(uuid4()), mission["id"], mission["revision"], "accept")
    mission = missions.start(ADMIN, str(uuid4()), mission["id"], mission["revision"])
    mission = missions.end(ADMIN, str(uuid4()), mission["id"], mission["revision"], False)
    work = next(
        x["id"]
        for x in missions.get(ADMIN, mission["id"])["work"]
        if x["kind"] == "punishment" and x["subject"] == 3
    )
    discipline = PunishmentService(game.store)
    data = discipline.get(ADMIN, work)
    args = (
        ADMIN,
        "actual-insured-execution",
        work,
        data["revision"],
        data["game_revision"],
        Details(kind="execution"),
    )
    result = discipline.apply(*args)
    assert discipline.apply(*args) == result
    for remaining in missions.get(ADMIN, mission["id"])["work"]:
        if remaining["kind"] == "punishment":
            submit(
                discipline,
                ADMIN,
                remaining["id"],
                Details(kind="stimulant_injection"),
                str(uuid4()),
            )
    mission = missions.get(ADMIN, mission["id"])
    missions.complete(ADMIN, str(uuid4()), mission["mission"]["id"], mission["mission"]["revision"])
    return next(x for x in state(game).career_archives if x.actor.entity == "3")


def history(service, receipt):
    async def native():
        inbox = InboxService(service.store)
        item = next(
            x for x in inbox.items(ADMIN) if x.task == "m3_girl_insurance" and x.identity == receipt
        )
        assert not item.incoming
        own = current(1, 33020)
        own.channel_id = 999
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(own, item)
        assert "Consumed" in own.edit_original_response.call_args.kwargs["content"]

    asyncio.run(native())


def test_high_budget_real_insurance_death_and_actual_empty_frame_storage_release(
    ledger, tmp_path, monkeypatch
):
    insurance, strain, game, receipt, storage = high_ready(ledger, tmp_path, monkeypatch)
    before = state(game)
    assert before.strain.levels["budget"] == "high" and not rules.consumptions(before)
    with pytest.raises(WorkflowError):
        insurance.buy(
            ADMIN,
            str(uuid4()),
            rules.acquisitions(before)[0].award,
            before.revision,
            "No second award spend",
        )
    archive = actual_death(game, strain.missions)
    after = state(game)
    assert after.strain.levels["budget"] == "low" and len(rules.consumptions(after)) == 1
    consumed = rules.consumptions(after)[0]
    assert (
        consumed.archive == archive.id
        and consumed.actor == archive.actor
        and consumed.acquisition == receipt
    )
    with ledger.engine.connect() as c:
        assert verify_exclusion(game, c, after, archive.source_event, archive.id)
    history(insurance, receipt)
    storage_service = StorageService(ledger)
    assert any(x[0] == "release" for x in storage_service.view(PLAYER, storage)["actions"])
    storage_native(storage_service, 2, storage, "release")
    assert storage_service.view(PLAYER, storage)["phase"] == "released"
    assert state(game).sheets["2"] == after.sheets["2"]
    assert state(game).placements == after.placements


def test_low_budget_real_death_single_consumption_and_actual_next_strain_exemption(
    ledger, tmp_path, monkeypatch
):
    game, _, missions, award = ready_low(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(*advancement.RULES, rules.RULE))
    insurance = GirlInsuranceService(ledger)
    receipt = buy(insurance, award)
    before = state(game)
    archive = actual_death(game, missions)
    assert before.strain.levels["budget"] == state(game).strain.levels["budget"] == "low"
    assert len(rules.consumptions(state(game))) == 1
    history(insurance, receipt)
    from girlframe.services.m3_off_duty import OffDutyService

    strain = StrainService(OffDutyService(missions))
    period = strain.periods.begin(ADMIN, str(uuid4()))
    with ledger.engine.connect() as c:
        tasks = strain.periods._pending(c, period["id"])
        identity = next(x["id"] for x in tasks if x["kind"] == "off_duty_strain_start")
    data = strain.work(ADMIN, identity)
    assert any(
        x["id"] == archive.id and "Girl Insurance" in x["label"]
        for x in data["budget_death_exemptions"]
    )

    async def native_facts():
        own = current(1, 33030)
        await own.response.defer(ephemeral=True)
        await open_work(own, strain, identity)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert "Girl Insurance" in form.instructions

    asyncio.run(native_facts())
    actual = state(game)
    count = sum(any(x.void for x in sheet.assets) for sheet in actual.sheets.values())
    strain.prepare(
        ADMIN,
        str(uuid4()),
        period["id"],
        period["revision"],
        actual.revision,
        facts(at_least_half_have_void=2 * count >= len(actual.order), no_girl_void=count == 0),
    )
    assert state(game).strain.levels["budget"] == "low"
    assert next(x for x in state(game).strain.requests if x.track == "budget").severity == "low"
