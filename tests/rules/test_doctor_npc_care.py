"""Printed p70 Cute Nurse: actual NPC care, confirmed by its original controller."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_doctor_runtime import acquire, doctor
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_world import initial

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_doctor import open_care, open_procedure
from girlframe.engine import m3_doctor as rules
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_doctor_care import CareService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def npc_patient(ledger, tmp_path, monkeypatch):
    source, game = doctor(ledger, tmp_path, monkeypatch)
    acquire(game, rules.NURSE)
    missions = MissionService(ledger)
    world = WorldService(missions)
    initial_world = initial()
    world.initialize(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        initial_world.board,
        initial_world.locations,
        initial_world.gorgons[0],
    )
    roles = NpcRoleService(world)
    offer = roles.offer(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id="care-patient",
            name="Introduced patient",
            jobs=("civilian",),
            detail="An actual ordinary patient",
            controller=3,
            cell=(0, 0),
            revealed=True,
        ),
    )
    roles.respond(OTHER, str(uuid4()), offer["id"], state(game).revision, "accept")
    patient = ActorRef(kind="npc", entity="care-patient")
    cast = CastService(ActorService(missions))
    data = cast.view(OTHER, 900)
    cast.change(
        OTHER, str(uuid4()), 900, data["game_revision"], data["cast_revision"], "join", patient
    )
    return source, game, patient


def test_native_cute_nurse_npc_patient_controller_confirms_actual_care(
    ledger, tmp_path, monkeypatch
):
    source, game, patient = npc_patient(ledger, tmp_path, monkeypatch)
    doctor_ref = current_ref(state(game), 2)
    original = depth(state(game), doctor_ref, patient)
    controller_bond = depth(state(game), doctor_ref, current_ref(state(game), 3))
    calls = game.dice.calls
    menu = source.menu(PLAYER, 900)
    assert patient.token in {x["token"] for x in menu["nurse_targets"]}
    assert patient.token not in {x["token"] for x in menu["targets"]}

    async def episode():
        interaction = current(2, 998801)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_procedure(interaction, source, menu, "nurse")
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            target=(patient.token,), account="PRIVATE_CARE I provide actual medical care"
        )
        submit = current(2, 998802)
        await form.confirm.callback(submit)
        assert form.completed
        await form.confirm.callback(submit)
        care = rules.values(state(game), "doctor_care", rules.Care)
        assert len(care) == 1
        identity = care[0].id
        assert care[0].patient == patient and care[0].patient_controller == 3
        assert care[0].phase == "proposal" and not care[0].angel
        assert depth(state(game), doctor_ref, patient) == original
        reopened = CareService(game)
        assert reopened.get(OTHER, identity)["can_confirm"]
        assert not reopened.get(PLAYER, identity)["can_confirm"]
        with pytest.raises(WorkflowError):
            reopened.get(ADMIN, identity)
        with pytest.raises(WorkflowError):
            reopened.confirm(
                PLAYER, str(uuid4()), identity, state(game).revision, "Cannot speak for patient"
            )
        own = current(3, 998803)
        await own.response.defer(ephemeral=True)
        await open_care(own, source, identity)
        confirmation = own.edit_original_response.call_args.kwargs["view"]
        confirmation.values.update(
            account="PRIVATE_PATIENT I confirm receiving the actual medical care"
        )
        submit = current(3, 998804)
        await confirmation.confirm.callback(submit)
        assert confirmation.completed
        await confirmation.confirm.callback(submit)
        actual = state(game)
        assert depth(actual, doctor_ref, patient) == original + 1
        assert depth(actual, doctor_ref, current_ref(actual, 3)) == controller_bond
        saved = reopened.get(OTHER, identity)["care"]
        assert saved["phase"] == "complete" and saved["care_event"]
        assert len([x for x in actual.facts if x.get("kind") == "doctor_nurse_bond"]) == 1
        assert game.dice.calls == calls
        with ledger.engine.connect() as c:
            assert "PRIVATE_CARE" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))
            assert "PRIVATE_PATIENT" not in str(list(c.scalars(sa.select(t.events.c.payload_json))))

    asyncio.run(episode())


def test_npc_nurse_menu_preserves_hidden_and_stale_cast_boundaries(ledger, tmp_path, monkeypatch):
    source, game, patient = npc_patient(ledger, tmp_path, monkeypatch)
    original = next(x for x in state(game).world.npcs if x.id == patient.entity)
    pilot_targets = source.menu(PLAYER, 900)["targets"]
    for changes in (
        dict(revealed=False, name="PRIVATE_HIDDEN_PATIENT"),
        dict(alive=False),
        dict(controller=1),
    ):
        with ledger.transaction() as c:
            actual = state(game)
            actual.world = actual.world.model_copy(
                update={
                    "npcs": tuple(
                        original.model_copy(update=changes) if x.id == patient.entity else x
                        for x in actual.world.npcs
                    )
                }
            )
            game.event(c, 1, str(uuid4()), "synthetic.patient_visibility_or_lifetime", actual)
        menu = source.menu(PLAYER, 900)
        assert menu["targets"] == pilot_targets
        assert patient.token not in {x["token"] for x in menu["nurse_targets"]}
        assert "PRIVATE_HIDDEN_PATIENT" not in str(menu)
        with pytest.raises(WorkflowError, match="visible current NPC"):
            CareService(game).propose(
                PLAYER,
                str(uuid4()),
                state(game).revision,
                900,
                patient,
                "A guessed token cannot authorize care",
            )
        assert not rules.values(state(game), "doctor_care", rules.Care)
