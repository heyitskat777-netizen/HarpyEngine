"""Source p70: a non-Doctor caller initiates the actual Running Ragged workflow."""

import asyncio
from uuid import uuid4

import pytest
from test_doctor_runtime import acquire, doctor
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.m3_doctor import open_doctor, open_request
from girlframe.engine import m3_doctor as rules
from girlframe.engine.m2 import TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.services.m3_doctor_procedures import ProcedureService
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
