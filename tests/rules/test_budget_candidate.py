"""Actual source Candidate, shared process, original assignment and assessment."""

import asyncio

import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_service import prepared, ready
from test_world import initial

from girlframe.database import tables as t
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m3_budget_candidate import get
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_budget_candidate import CandidateService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService


def test_candidate_source_native_table_process_assignment_and_actual_assessment(ledger):
    strain, game = ready(ledger, face=4)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}},
            )
        }
    )
    world = initial()
    worlds = WorldService(strain.missions)
    worlds.initialize(
        ADMIN,
        "candidate-world",
        state(game).revision,
        world.board,
        world.locations,
        world.gorgons[0],
    )
    worlds.npc(
        ADMIN,
        "candidate-actual-npc",
        state(game).revision,
        Npc(
            id="trainee",
            name="Actual trainee",
            jobs=("civilian",),
            detail="An existing person whose body and controller will be preserved",
            cell=(0, 0),
            controller=1,
            revealed=True,
        ),
    )
    prepared(strain, game, high=frozenset({"budget"}))
    request = next(x for x in state(game).strain.requests if x.track == "budget")
    strain.roll(ADMIN, "candidate-die", request.id, 1, state(game).revision)
    strain.choose(ADMIN, "candidate-column", request.id, 2, state(game).revision, 2)
    effects = EffectService(strain)
    identity = request.id + ":effect:candidate"
    original = state(game).sheets["2"].model_copy(deep=True)

    async def select():
        interaction = current(1, 28500)
        await interaction.response.defer(ephemeral=True)
        await open_effect(interaction, effects, request.id + ":effect")
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values = dict(
            candidate=("trainee",),
            assessor=("2",),
            account="Assign the actual trainee and original Girl assessor",
        )
        await form.confirm.callback(current(1, 28501))
        assert form.completed

    asyncio.run(select())
    npc = next(x for x in state(game).world.npcs if x.id == "trainee")
    assert npc.controller == 1 and npc.jobs == ("civilian", "pilot_candidate")
    assert get(state(game), identity).assessor.incarnation == original.character_id
    inbox = InboxService(ledger)

    async def respond(viewer, number, action, account):
        item = next(x for x in inbox.items(viewer) if x.identity == identity)
        assert item.task == "m3_budget_candidate"
        interaction = current(viewer.user_id, number)
        await interaction.response.defer(ephemeral=True)
        await InboxView(inbox, viewer.user_id).route(interaction, item)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values = dict(action=(action,), account=account)
        await form.confirm.callback(current(viewer.user_id, number + 1))
        assert form.completed

    asyncio.run(
        respond(ADMIN, 28502, "propose", "The table will observe a supervised simulator test")
    )
    asyncio.run(
        respond(PLAYER, 28504, "propose", "The table will observe a simulator test and debrief")
    )
    process = get(state(game), identity)
    assert process.approvals == (2,)
    asyncio.run(respond(ADMIN, 28506, "agree", "I agree to that revised exact process"))
    asyncio.run(respond(OTHER, 28508, "agree", "I agree to that same exact process"))
    assert get(state(game), identity).phase == "assessing"
    assert CandidateService(ledger).view(PLAYER, identity)["assessor"]
    asyncio.run(
        respond(PLAYER, 28510, "assess", "I observed the simulator test and gave my debrief")
    )
    final = get(state(game), identity)
    assert final.phase == "complete" and final.report and final.process.endswith("and debrief")
    assert state(game).sheets["2"] == original
    assert not state(game).world.pilots
    with ledger.engine.connect() as c:
        work = t.m3["m3_required_work"]
        assert (
            c.scalar(
                sa.select(work.c.state)
                .where(
                    work.c.campaign_id == ledger.campaign_id,
                    work.c.id == identity,
                )
                .order_by(work.c.revision.desc())
                .limit(1)
            )
            == "resolved"
        )
