"""Actual Budget meeting uses a separately played Director and the Handler's own pool."""

import asyncio

import sqlalchemy as sa
from test_cast_service import change
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_strain_service import prepared, ready
from test_world import initial

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_budget_director import open_meeting
from girlframe.discord_adapter.m3_strain_effects import open_effect
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_budget_director import get
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_world_state import Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_budget_director import MeetingService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_world import WorldService


def test_actual_budget_director_meeting_native_presence_heat_and_departure(ledger):
    strain, game = ready(ledger, face=1)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "plays"}}
            )
        }
    )
    world = initial()
    worlds = WorldService(strain.missions)
    worlds.initialize(
        ADMIN,
        "performance-world",
        state(game).revision,
        world.board,
        world.locations,
        world.gorgons[0],
    )
    roles = NpcRoleService(worlds)
    proposal = roles.offer(
        ADMIN,
        "real-director-invitation",
        state(game).revision,
        Npc(
            id="performance-director",
            name="Performance Director",
            jobs=("director",),
            detail="The separately played actual Director",
            controller=2,
            cell=(0, 0),
            revealed=True,
        ),
    )
    roles.respond(PLAYER, "real-director-accept", proposal["id"], state(game).revision, "accept")
    prepared(strain, game, high=frozenset({"budget"}))
    request = next(x for x in state(game).strain.requests if x.track == "budget")
    strain.roll(ADMIN, "performance-die", request.id, 1, state(game).revision)
    strain.choose(ADMIN, "performance-column", request.id, 2, state(game).revision, 1)
    effects = EffectService(strain)
    work = request.id + ":effect"
    identity = work + ":meeting"
    service = MeetingService(ledger)
    old_body = active_handler(state(game))
    player = state(game).sheets["2"].model_copy(deep=True)

    async def select():
        interaction = current(1, 28400)
        await interaction.response.defer(ephemeral=True)
        await open_effect(interaction, effects, work)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values = {
            "director": ("performance-director",),
            "account": "This actual Director calls a performance meeting",
        }
        await form.confirm.callback(current(1, 28401))
        assert form.completed

    asyncio.run(select())
    assert (
        next(x for x in InboxService(ledger).items(PLAYER) if x.identity == identity).task
        == "m3_budget_director"
    )

    async def respond(user, number, values):
        interaction = current(user, number)
        await interaction.response.defer(ephemeral=True)
        await open_meeting(interaction, service, identity)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values = values
        await form.confirm.callback(current(user, number + 1))
        assert form.completed

    asyncio.run(
        respond(
            2,
            28402,
            {"appearance": ("appear",), "account": "My Director actually appears for the meeting"},
        )
    )
    asyncio.run(
        respond(
            1,
            28404,
            {
                "first": "Eager to please",
                "second": "Disposable",
                "account": "My actual Handler is present in this meeting",
            },
        )
    )
    meeting = get(state(game), identity)
    assert meeting.phase == "active" and meeting.heat == 4
    actor = ActorRef(kind="handler", entity="1", incarnation=meeting.context)
    actual = resolve(state(game), actor, ())
    assert actual.rules == "handler_girl" and actual.heat == 4 and len(actual.identities) == 2
    assert "1" not in state(game).sheets and state(game).sheets["2"] == player
    cast = CastService(ActorService(strain.missions))
    change(cast, ADMIN, "join", actor)
    change(cast, PLAYER, "join", ActorRef(kind="npc", entity="performance-director"))
    asyncio.run(
        respond(
            2,
            28406,
            {
                "departure": ("end",),
                "account": "The actual performance meeting ends and my Director leaves",
            },
        )
    )
    final = state(game)
    assert get(final, identity).phase == "complete"
    assert not next(x for x in final.director_contexts if x.id == meeting.context).active
    assert next(x for x in final.world.npcs if x.id == "performance-director").alive
    assert any(role.actor == old_body for scene in final.scene_casts for role in scene.roles)
    assert not any(
        role.actor == ActorRef(kind="npc", entity="performance-director")
        for scene in final.scene_casts
        for role in scene.roles
    )
    with ledger.engine.connect() as c:
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table)
                .where(table.c.campaign_id == ledger.campaign_id, table.c.id == identity)
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        assert row["state"] == "resolved"
