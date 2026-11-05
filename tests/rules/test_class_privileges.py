"""Native paid Class privilege suspension, blocked bypass and actual owned restoration."""

import asyncio
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_service import service
from test_mission_ui import current
from test_punishment_service import submit

from girlframe.discord_adapter.m3_privileges import open_privilege
from girlframe.discord_adapter.m3_punishments import open_details
from girlframe.engine import m3_untouchable as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_privileges import KIND, suspended
from girlframe.engine.m3_punishments import Details
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_privileges import PrivilegeService
from girlframe.services.m3_punishments import PunishmentService
from girlframe.services.m3_untouchable import UntouchableService, entitlement
from girlframe.services.onboarding import WorkflowError


def test_native_class_receipt_real_revocation_blocks_rebuy_then_restores_original_without_cost(
    ledger, tmp_path, monkeypatch
):
    missions, game = service(ledger, girl="ALPHA", frame="THE ENFORCER")
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"missions", "discipline"}}
            ),
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"privilege_restoration": "inflictor_condition_owner_restores"}
            ),
        }
    )
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].permissions = 4
        game.event(c, 1, str(uuid4()), "synthetic.existing_class_funds", actual)
    buyer = UntouchableService(game)
    missions = MissionService(ledger)
    menu = buyer.menu(PLAYER)
    buyer.buy(
        PLAYER,
        str(uuid4()),
        menu["revision"],
        ActorRef.model_validate(menu["actor"]),
        menu["frame"],
        "An actual native Class acquisition",
    )
    receipt = rules.held(state(game), current_ref(state(game), 2))
    assert receipt
    mission = missions.offer(ADMIN, str(uuid4()), "An actual source mission", (2,))
    missions.respond(PLAYER, str(uuid4()), mission["id"], 1, "accept")
    missions.start(ADMIN, str(uuid4()), mission["id"], 2)
    ended = missions.end(ADMIN, str(uuid4()), mission["id"], 3, False)
    discipline = PunishmentService(ledger)
    source = next(x for x in missions.get(ADMIN, mission["id"])["work"] if x["subject"] == 2)
    data = discipline.get(ADMIN, source["id"])
    assert {"id": receipt.id, "name": "Untouchable Frame"} in data["choices"]["requisitions"]

    async def revoke():
        interaction = current(1, 28900)
        await interaction.response.defer(ephemeral=True)
        await open_details(interaction, discipline, source["id"], "revoked_privileges")
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            requisition=(receipt.id,), restoration="The original agreed corrective action"
        )
        await form.confirm.callback(current(1, 28901))
        assert form.completed

    asyncio.run(revoke())
    while pending := missions.get(ADMIN, mission["id"])["work"]:
        submit(
            discipline, ADMIN, pending[0]["id"], Details(kind="stimulant_injection"), str(uuid4())
        )
    missions.complete(ADMIN, str(uuid4()), mission["id"], ended["revision"])
    actual = state(game)
    gate = next(x for x in actual.obligations if x.kind == KIND)
    assert suspended(actual, receipt.id)
    with ledger.engine.connect() as c:
        assert entitlement(game, c, actual, current_ref(actual, 2)) is None
    before = actual.model_dump_json()
    menu = buyer.menu(PLAYER)
    assert menu["permissions"] >= 2 and not menu["owned"]
    with pytest.raises(WorkflowError, match="Restore the original paid entitlement"):
        buyer.buy(
            PLAYER,
            str(uuid4()),
            menu["revision"],
            ActorRef.model_validate(menu["actor"]),
            menu["frame"],
            "Cannot bypass the actual temporary suspension",
        )
    assert state(game).model_dump_json() == before
    privileges = PrivilegeService(ledger)

    async def restore(viewer, number, evidence):
        interaction = current(viewer.user_id, number)
        await interaction.response.defer(ephemeral=True)
        await open_privilege(interaction, privileges, gate.id)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(evidence=evidence, confirm=("yes",))
        await form.confirm.callback(current(viewer.user_id, number + 1))
        assert form.completed

    asyncio.run(restore(ADMIN, 28902, "I observed that the original restoration condition was met"))
    assert suspended(state(game), receipt.id)
    asyncio.run(
        restore(PLAYER, 28904, "I restore my original Class privilege after that permission")
    )
    restored = state(game)
    assert not suspended(restored, receipt.id)
    assert restored.sheets["2"].permissions == actual.sheets["2"].permissions
    assert restored.requisitions == actual.requisitions
    with ledger.engine.connect() as c:
        assert entitlement(game, c, restored, current_ref(restored, 2)) == receipt
    assert buyer.menu(PLAYER)["receipt"] == receipt.id
