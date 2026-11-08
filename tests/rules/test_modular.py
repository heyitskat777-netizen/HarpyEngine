"""Native paid slot/Asset, real temporary revocation and actual repair substitutions."""

import asyncio
import copy
from uuid import uuid4

import pytest
import test_strain_effect_service
import test_strain_service
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_service import service as mission_service
from test_mission_ui import current
from test_off_duty_cycle import activate, call, prepared, roll_for
from test_strain_service import ready as strain_ready

from girlframe.discord_adapter.m3_modular import open_purchase
from girlframe.discord_adapter.m3_off_duty_cycle import open_action
from girlframe.discord_adapter.m3_privileges import open_privilege
from girlframe.discord_adapter.m3_punishments import open_details
from girlframe.engine import m3_modular as rules
from girlframe.engine.m2 import AssetState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_assets import counts_toward_limit, frame_capacity
from girlframe.engine.m3_core import install
from girlframe.engine.m3_privileges import KIND, suspended
from girlframe.services.m3_access import Access
from girlframe.services.m3_modular import ModularService
from girlframe.services.m3_privileges import PrivilegeService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize(
    "old_void", (False, True), ids=("ordinary-replacement", "void-replacement")
)
def test_native_modular_capacity_source_suspension_and_actual_repair_replacement(
    ledger, tmp_path, monkeypatch, old_void
):
    monkeypatch.setattr(
        test_strain_service,
        "service",
        lambda store, frame: mission_service(store, girl="ALPHA", frame=frame),
    )
    monkeypatch.setattr(
        test_strain_effect_service,
        "ready",
        lambda store, face: strain_ready(store, face=face, frame="WYVERN 0.4"),
    )
    cycle, game, period = prepared(ledger)
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    cycle.missions.access = Access(ledger)
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"privilege_restoration": "inflictor_condition_owner_restores"}
            )
        }
    )
    with ledger.transaction() as c:
        actual = state(game)
        sheet = actual.sheets["2"]
        sheet.permissions = 4
        frames = [x for x in sheet.assets if x.family == "frame" and counts_toward_limit(sheet, x)]
        original, ordinary = frames[:2]
        original.damaged = True
        original.void = old_void
        ordinary.damaged = True
        ordinary_id = ordinary.id
        old = copy.deepcopy(original)
        for number in range(5 - len(frames)):
            sheet.assets.append(
                AssetState(
                    id="actual-existing-frame:" + str(number),
                    family="frame",
                    name="Actual existing hardware " + str(number),
                    description="Previously owned actual hardware",
                )
            )
        game.event(c, 1, str(uuid4()), "synthetic.actual_previous_modular_resources", actual)
    service = ModularService(game)

    async def acquire():
        own = current(2, 999801)
        await own.response.defer(ephemeral=True)
        await open_purchase(own, service)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            name="Actual additional modular tool",
            description="The authored additional Frame Asset",
            account="Actual Modular Build acquisition",
        )
        await form.confirm.callback(current(2, 999802))
        assert form.completed

    asyncio.run(acquire())
    acquired = state(game)
    actor = current_ref(acquired, 2)
    paid = rules.held(acquired, actor)
    assert paid and acquired.sheets["2"].permissions == 2
    assert frame_capacity(acquired.sheets["2"], acquired) == 6
    assert (
        sum(
            x.family == "frame" and counts_toward_limit(acquired.sheets["2"], x)
            for x in acquired.sheets["2"].assets
        )
        == 6
    )
    assert len([x for x in acquired.sheets["2"].assets if x.family == "frame"]) == 7
    activate(cycle, game, period)
    call(
        cycle,
        game,
        ADMIN,
        period,
        "handler_scene",
        "punish",
        (1, 2),
        "Actual Handler scene requiring a temporary privilege consequence",
        2,
    )
    discipline = PunishmentService(ledger)
    work = period + ":handler-punishment"
    scene = discipline.get(ADMIN, work)
    discipline.propose_scene(
        ADMIN,
        str(uuid4()),
        work,
        scene["revision"],
        scene["game_revision"],
        "Actual source Punishment scene for temporary Modular Build suspension",
    )
    for participant in (ADMIN, PLAYER):
        scene = discipline.get(participant, work)
        if participant.user_id not in scene["context_scene"]["acknowledgements"]:
            discipline.attest_scene(
                participant, str(uuid4()), work, scene["revision"], scene["game_revision"]
            )

    async def revoke():
        own = current(1, 999803)
        await own.response.defer(ephemeral=True)
        await open_details(own, discipline, work, "revoked_privileges")
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            requisition=(paid.id,), restoration="The actual corrective condition is met"
        )
        confirmed = current(1, 999804)
        await form.confirm.callback(confirmed)
        assert form.completed, str(confirmed.edit_original_response.call_args)

    physical = copy.deepcopy(state(game).sheets["2"].assets)
    asyncio.run(revoke())
    current_state = state(game)
    assert suspended(current_state, paid.id)
    assert current_state.sheets["2"].assets == physical
    assert frame_capacity(current_state.sheets["2"], current_state) == 5
    with pytest.raises(ValueError, match="extra-slot source"):
        install(
            current_state.sheets["2"],
            AssetState(
                id="blocked-extra",
                family="frame",
                name="Unavailable extra hardware",
                description="No source capacity",
            ),
            state=current_state,
        )
    data = service.menu(PLAYER)
    with pytest.raises(WorkflowError, match="Restore the original entitlement"):
        service.buy(
            PLAYER,
            str(uuid4()),
            data["revision"],
            ActorRef.model_validate(data["actor"]),
            data["frame"],
            "No repurchase bypass",
            "Another tool",
            "No duplicated entitlement",
        )
    gate = next(x for x in current_state.obligations if x.kind == KIND)
    privileges = PrivilegeService(ledger)

    async def restore(viewer, number):
        own = current(viewer.user_id, number)
        await own.response.defer(ephemeral=True)
        await open_privilege(own, privileges, gate.id)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            evidence="The original condition and actual restoration are confirmed", confirm=("yes",)
        )
        await form.confirm.callback(current(viewer.user_id, number + 1))
        assert form.completed

    asyncio.run(restore(ADMIN, 999805))
    asyncio.run(restore(PLAYER, 999807))
    restored = state(game)
    assert (
        restored.sheets["2"].assets == physical
        and restored.requisitions == current_state.requisitions
    )
    assert (
        frame_capacity(restored.sheets["2"], restored) == 6
        and restored.sheets["2"].permissions == 2
    )
    action = roll_for(cycle, game, period, PLAYER, (2, 2))
    raw = copy.deepcopy(game.inspect(PLAYER, action)["receipt"])
    call(cycle, game, PLAYER, period, "scene", None, (), "")

    async def recover():
        own = current(2, 999809)
        await own.response.defer(ephemeral=True)
        await open_action(own, cycle, period, "recover")
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(repairs=("yes",), modular_assets=(old.id,))
        form.values["modular_name:" + old.id] = "Actual new replacement hardware"
        form.values["modular_description:" + old.id] = (
            "New functional modular hardware replacing the damaged part"
        )
        await form.confirm.callback(current(2, 999810))
        assert form.completed

    asyncio.run(recover())
    final = state(game)
    assert old.id not in {x.id for x in final.sheets["2"].assets}
    replacement = next(
        x for x in final.sheets["2"].assets if x.name == "Actual new replacement hardware"
    )
    assert not replacement.damaged and not replacement.void
    ordinary = next(x for x in final.sheets["2"].assets if x.id == ordinary_id)
    assert not ordinary.damaged  # Normal repairs still happen without selecting replacement.
    assert len(final.sheets["2"].assets) == len(physical)
    assert cycle.review(PLAYER, period)["own"]["recovered"]
    assert game.inspect(PLAYER, action)["receipt"] == raw and game.dice.calls == 1
