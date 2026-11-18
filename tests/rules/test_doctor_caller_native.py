"""Source p70: a non-Doctor caller initiates the actual Running Ragged workflow."""

import asyncio
from uuid import uuid4

import pytest
from test_cast_service import change as cast_change
from test_doctor_npc_nanobot import setup as npc_setup
from test_doctor_runtime import acquire, doctor
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.m3_doctor import open_doctor, open_request
from girlframe.engine import m3_doctor as rules
from girlframe.engine.m2 import TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.engine.m3_world_state import WorldTag
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_doctor import DoctorService
from girlframe.services.m3_doctor_procedures import ProcedureService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.onboarding import WorkflowError


def test_native_caller_initiates_ragged_and_owns_tag_payment(ledger, tmp_path, monkeypatch):
    doctor_service, game = doctor(ledger, tmp_path, monkeypatch)
    acquire(game, rules.RAGGED)
    # Actual owner proposals and Handler reviews establish both current bodies.
    physical = PhysicalService(ledger)
    from test_world import initial

    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_world import WorldService

    world = initial()
    WorldService(MissionService(ledger)).initialize(
        ADMIN, str(uuid4()), state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    for viewer, cell in ((PLAYER, (0, 0)), (OTHER, (1, 0))):
        data = physical.preview(viewer)
        identity = physical.propose(
            viewer,
            str(uuid4()),
            data["game_revision"],
            InitialPlacement(
                actor=current_ref(state(game), viewer.user_id),
                frame_instance=data["frame_instance"],
                girl_cell=cell,
                frame_cell=cell,
                mode="piloting",
                account="Actual original body position",
                facts_confirmed=True,
            ),
        )["id"]
        physical.decide(ADMIN, str(uuid4()), identity, 1, "accept", "Actual source position review")
    with ledger.transaction() as c:
        value = state(game)
        value.sheets["3"].tags.append(TagState(id="caller-tag", label="Calls for help", giver=3))
        game.event(c, 1, str(uuid4()), "synthetic.actual_existing_tag", value)
    source = ProcedureService(game)
    before = state(game)
    assert before.sheets["3"].frame != rules.BOOK

    async def run():
        interaction = current(3, 998701)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_doctor(interaction, doctor_service)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert form.fields[0].key == "doctor"
        assert [x[0] for x in form.fields[0].options] == [current_ref(state(game), 2).token]
        form.values.update(
            doctor=(current_ref(state(game), 2).token,),
            account="I call the actual Doctor to my side",
        )
        submitted = current(3, 998702)
        await form.confirm.callback(submitted)
        requests = rules.values(state(game), "doctor_procedure", rules.Procedure)
        assert len(requests) == 1
        value = requests[0]
        assert value.doctor == current_ref(state(game), 2)
        assert value.counterpart == current_ref(state(game), 3)
        assert value.controller == 3 and value.phase == "proposal"
        assert not next(x for x in state(game).sheets["3"].tags if x.id == "caller-tag").marked
        assert next(x for x in state(game).placements if x.actor == value.doctor).girl_cell == (
            0,
            0,
        )
        # The original native submit can be retried without a second request.
        await form.confirm.callback(submitted)
        assert len(rules.values(state(game), "doctor_procedure", rules.Procedure)) == 1
        with pytest.raises(WorkflowError):
            source.get(ADMIN, value.id)
        reopened = current(3, 998703)
        await reopened.response.defer(ephemeral=True)
        await open_request(reopened, doctor_service, value.id)
        payment = reopened.edit_original_response.call_args.kwargs["view"]
        payment.values.update(tag=("caller-tag",), account="My call is answered; I mark my own Tag")
        paid = current(3, 998704)
        await payment.confirm.callback(paid)
        done = state(game)
        position = next(x for x in done.placements if x.actor == value.doctor)
        assert position.girl_cell == position.frame_cell == (1, 0)
        assert next(x for x in done.sheets["3"].tags if x.id == "caller-tag").marked
        assert done.sheets["2"].heat == before.sheets["2"].heat
        assert source.get(OTHER, value.id)["procedure"]["phase"] == "complete"
        assert source.get(PLAYER, value.id)["procedure"]["source_event"] == value.source_event
        revision = done.revision
        await payment.confirm.callback(paid)
        assert state(game).revision == revision

    asyncio.run(run())


@pytest.mark.parametrize("pay_as_npc", [True, False], ids=["npc-pays", "doctor-pays"])
def test_native_npc_call_and_owned_ragged_payment(ledger, tmp_path, monkeypatch, pay_as_npc):
    game, _, _, npc, _ = npc_setup(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.NANO, rules.TRACK, rules.RAGGED))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    casts = CastService(ActorService(MissionService(ledger)))
    assert ProcedureService(game).call_menu(ADMIN, 900)["npc_doctors"] == []
    acquire(game, rules.RAGGED)
    with ledger.transaction() as c:
        prepared = state(game)
        prepared.sheets["2"].tags.append(TagState(id="doctor-ready", label="Doctor ready", giver=3))
        prepared.world = prepared.world.model_copy(
            update=dict(
                npcs=tuple(
                    patient.model_copy(
                        update=dict(
                            tags=(WorldTag(id="npc-ready", label="Caller ready", giver_entity="2"),)
                        )
                    )
                    if patient.id == npc.entity
                    else patient
                    for patient in prepared.world.npcs
                )
            )
        )
        prepared.placements = [
            x.model_copy(update=dict(girl_cell=(1, 0), frame_cell=(1, 0)))
            if x.actor.entity == "2"
            else x
            for x in prepared.placements
        ]
        game.event(c, 1, str(uuid4()), "synthetic.actual_call_positions_and_tags", prepared)
    before = state(game)
    provider = current_ref(before, PLAYER.user_id)
    procedure = ProcedureService(game)
    payment_owner = ADMIN if pay_as_npc else PLAYER
    payer = npc if pay_as_npc else provider
    tag = "npc-ready" if pay_as_npc else "doctor-ready"
    with pytest.raises(WorkflowError, match="original NPC, Doctor and call scene"):
        procedure.propose(
            OTHER,
            str(uuid4()),
            before.revision,
            900,
            npc,
            "ragged",
            "Not my NPC",
            called_doctor=provider,
        )

    async def run():
        interaction = current(ADMIN.user_id, 998801)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_doctor(interaction, DoctorService(game))
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert form.fields[0].options == ((npc.token, "Pat"),)
        form.values.update(
            caller=(npc.token,),
            doctor=(provider.token,),
            account="I call the Doctor to my side",
        )
        submit = current(ADMIN.user_id, 998802)
        await form.confirm.callback(submit)
        assert form.completed, submit.edit_original_response.call_args_list
        await form.confirm.callback(submit)
        proposed = state(game)
        (request,) = rules.values(proposed, "doctor_procedure", rules.Procedure)
        assert request.counterpart == npc and request.controller == ADMIN.user_id
        assert request.npc_call_scene
        assert proposed.placements == before.placements
        assert not actor_tags(proposed, npc)[0].marked
        with pytest.raises(WorkflowError, match="Reopen your existing call"):
            procedure.propose(
                ADMIN,
                str(uuid4()),
                proposed.revision,
                900,
                npc,
                "ragged",
                "Duplicate call",
                called_doctor=provider,
            )

        reopened_game = GameService(ledger, dice=game.dice)
        reopened = ProcedureService(reopened_game)
        inbox = InboxService(ledger)
        for viewer in (ADMIN, PLAYER):
            assert any(item.identity == request.id for item in inbox.items(viewer))
        assert not any(item.identity == request.id for item in inbox.items(OTHER))
        with pytest.raises(WorkflowError, match="actual original Doctor procedure"):
            reopened.get(OTHER, request.id)
        with pytest.raises(WorkflowError, match="Tag holder you control"):
            reopened.confirm(
                PLAYER,
                str(uuid4()),
                request.id,
                proposed.revision,
                "Someone else's NPC Tag",
                "npc-ready",
                payer=npc,
            )
        with pytest.raises(WorkflowError, match="original pending procedure"):
            reopened.confirm(
                payment_owner,
                str(uuid4()),
                request.id,
                proposed.revision - 1,
                "Stale Tag offer",
                tag,
                payer=payer,
            )
        cast_change(casts, ADMIN, "withdraw", npc)
        with pytest.raises(WorkflowError, match="original NPC, Doctor and call scene"):
            reopened.confirm(
                payment_owner,
                str(uuid4()),
                request.id,
                state(game).revision,
                "Caller has left",
                tag,
                payer=payer,
            )
        cast_change(casts, ADMIN, "join", npc)
        ledger.safety(OTHER, "pause-ragged", ledger.status(OTHER)["revision"], pause=True)
        paused = state(game)
        with pytest.raises(WorkflowError, match="paused"):
            reopened.confirm(
                payment_owner,
                str(uuid4()),
                request.id,
                paused.revision,
                "Wait for the safety pause",
                tag,
                payer=payer,
            )
        assert state(game) == paused
        ledger.safety(OTHER, "resume-ragged", ledger.status(OTHER)["revision"], pause=False)

        response = current(payment_owner.user_id, 998803)
        await response.response.defer(ephemeral=True)
        await open_request(response, DoctorService(reopened_game), request.id)
        payment = response.edit_original_response.call_args.kwargs["view"]
        assert payment.fields[0].options == (
            ("0", "Caller ready" if pay_as_npc else "Doctor ready"),
        )
        payment.values.update(tag=("0",), account="I mark my own Tag for the actual arrival")
        confirmed = current(payment_owner.user_id, 998804)
        await payment.confirm.callback(confirmed)
        assert payment.completed, confirmed.edit_original_response.call_args_list
        done = state(game)
        await payment.confirm.callback(confirmed)
        assert state(game).revision == done.revision
        with pytest.raises(WorkflowError, match="original pending procedure"):
            reopened.confirm(
                payment_owner,
                str(uuid4()),
                request.id,
                done.revision,
                "Do not mark or move again",
                tag,
                payer=payer,
            )
        actual = next(x for x in done.placements if x.actor == provider)
        assert actual.girl_cell == (0, 0) and actual.frame_cell == (1, 0)
        assert actor_tags(done, npc)[0].marked is pay_as_npc
        assert actor_tags(done, provider)[-1].marked is not pay_as_npc
        assert done.sheets["2"].heat == before.sheets["2"].heat
        assert done.sheets["2"].permissions == before.sheets["2"].permissions
        assert done.sheets["3"] == before.sheets["3"]
        assert game.dice.calls == 0
        assert reopened.get(ADMIN, request.id)["procedure"]["phase"] == "complete"
        assert not any(item.identity == request.id for item in inbox.items(PLAYER))

    asyncio.run(run())
