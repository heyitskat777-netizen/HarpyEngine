"""Real selected group, optional leader opportunity, genuine death and destruction."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_service import prepared, ready
from test_world import initial

from girlframe.database import tables as t
from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_strain import open_work
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_rebel_leader import opportunities
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Faction, Npc, NpcRecruitment
from girlframe.services.inbox import InboxService
from girlframe.services.m3_battle_npc import NpcDamageService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_rebel_leader import LeaderService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("outcome", ["destroy", "forgo"])
def test_actual_leader_opportunity_requires_death_for_real_group_destruction(ledger, outcome):
    strain, game = ready(ledger, face=6)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "plays"}}
            )
        }
    )
    worlds = WorldService(strain.missions)
    world = initial()
    worlds.initialize(
        ADMIN, "map", state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    worlds.npc(
        ADMIN,
        "real-leader",
        state(game).revision,
        Npc(
            id="leader",
            name="Actual rebel leader",
            controller=1,
            jobs=("intelligence_agent",),
            cell=(0, 4),
            detail="The actual living leader",
            revealed=True,
        ),
    )
    worlds.faction(
        ADMIN,
        "real-group",
        state(game).revision,
        Faction(
            id="rebel-group",
            name="Actual Rebel Group",
            kind="rebel",
            cells=((0, 4),),
            leader="leader",
        ),
    )
    with ledger.transaction() as c:
        baseline = state(game)
        baseline.world = update(
            baseline.world,
            npc_recruitment=(
                NpcRecruitment(
                    id="pending-recruitment",
                    source_work="prior-source",
                    city="city0",
                    faction="rebel-group",
                ),
            ),
        )
        game.event(c, 1, "synthetic-prior-recruitment", "synthetic.baseline", baseline)
    prepared(strain, game, high=frozenset({"rebellion"}))
    while True:
        request = next(
            x
            for x in state(game).strain.requests
            if x.track == "rebellion" and (x.kind == "endgame" or x.severity == "high")
        )
        if request.kind == "endgame":
            break
        strain.roll(ADMIN, str(uuid4()), request.id, 1, state(game).revision)
        strain.choose(ADMIN, str(uuid4()), request.id, 2, state(game).revision, 2)

    async def select_source():
        interaction = current(1, 30100)
        await interaction.response.defer(ephemeral=True)
        await open_work(interaction, strain, request.id)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(option=("1",), faction=("rebel-group",))
        await form.confirm.callback(current(1, 30101))
        assert form.completed

    asyncio.run(select_source())
    identity = request.id + ":effect"
    service = LeaderService(ledger)
    original = state(game)
    with pytest.raises(WorkflowError):
        service.view(PLAYER, identity)

    async def native(number, values):
        inbox = InboxService(ledger)
        item = next(x for x in inbox.items(ADMIN) if x.identity == identity)
        assert item.task == "m3_rebel_leader"
        interaction = current(1, number)
        interaction.channel_id = 999
        await interaction.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(interaction, item)
        assert interaction.channel_id == 999
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        await form.confirm.callback(current(1, number + 1))
        assert form.completed

    asyncio.run(
        native(
            30110,
            dict(leader=("leader",), account="A real opportunity targets this existing leader"),
        )
    )
    actual = state(game)
    value = opportunities(actual)[0]
    assert value.phase == "available" and value.leader == ActorRef(kind="npc", entity="leader")
    assert actual.world == original.world and actual.sheets == original.sheets
    with ledger.engine.connect() as c:
        work = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(work)
                .where(work.c.campaign_id == ledger.campaign_id, work.c.id == identity)
                .order_by(work.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        assert (
            row["state"] == "resolved"
        )  # An actual opportunity was granted, not a forced mission.
    with pytest.raises(WorkflowError, match="still alive"):
        service.act(
            ADMIN, "no-fake-kill", identity, actual.revision, "destroy", "Leader is still alive"
        )
    assert state(game) == actual
    if outcome == "destroy":
        moves = HandlerPlayService(ledger)
        leader = ActorRef(kind="npc", entity="leader")
        grant = moves.start(ADMIN, str(uuid4()), state(game).revision, (leader,))["id"]
        moves.submit(
            ADMIN,
            str(uuid4()),
            grant,
            state(game).revision,
            "mess",
            Effect(kind="damage", target=leader, account="The actual leader takes a real hit"),
        )
        with ledger.engine.connect() as c:
            work = t.m3["m3_required_work"]
            damage = (
                c.execute(
                    sa.select(work)
                    .where(work.c.campaign_id == ledger.campaign_id, work.c.kind == "npc_damage")
                    .order_by(work.c.revision.desc())
                    .limit(1)
                )
                .mappings()
                .one()
            )
        NpcDamageService(ledger).respond(
            ADMIN,
            str(uuid4()),
            damage["id"],
            damage["revision"],
            "kill",
            "The real leader dies from the actual hit",
        )
        assert not next(x for x in state(game).world.npcs if x.id == "leader").alive
    before = state(game)
    response = (
        "The actual group is dismantled after its leader's death"
        if outcome == "destroy"
        else "I forgo this optional opportunity"
    )
    asyncio.run(native(30120, dict(action=(outcome,), account=response)))
    final = state(game)
    assert opportunities(final)[0].phase == ("destroyed" if outcome == "destroy" else "forgone")
    assert opportunities(final)[0].response == response
    assert (
        service.act(ADMIN, "30121", identity, before.revision, outcome, response)["phase"]
        == opportunities(final)[0].phase
    )
    assert state(game) == final
    if outcome == "destroy":
        assert not final.world.factions[0].active and not final.world.npc_recruitment
        assert final.sheets == before.sheets  # No personal kill credit/resource grant inferred.
        assert opportunities(final)[0].death_event
    else:
        assert final.world == before.world and final.sheets == before.sheets
        assert opportunities(final)[0].death_event is None
