"""Reviewed Rift presence must replace cached map coordinates in views and actions."""

import asyncio
from uuid import uuid4

import pytest
from test_actors import canon as canon
from test_actors import ledger as ledger
from test_cast_service import change
from test_harpy_defeat import choose, rolled
from test_ledger import ADMIN, PLAYER
from test_m2_game import state, tick
from test_mission_ui import current
from test_world import gorgon

from girlframe.discord_adapter.m3_off_duty_cycle import open_end
from girlframe.discord_adapter.m3_world import MapPages
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_gorgon_combat import Exposure, expose
from girlframe.engine.m3_harpy_defeat_state import Travel
from girlframe.engine.m3_world import update
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_gorgon import GorgonService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_world import (
    WorldService,
    _world_projection,
    require_world_advancement,
)
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize(
    "key,kind,entity",
    [
        ("npcs", "npc", "2"),
        ("gorgons", "gorgon", "secret"),
        ("pilots", "external_pilot", "external"),
    ],
)
def test_private_world_projection_masks_each_actual_offstage_body_without_rewriting_cache(
    canon, key, kind, entity
):
    actor = ActorRef.model_validate(dict(kind=kind, entity=entity))
    original = resolve(canon, actor, ())
    canon.harpy_travels.append(
        Travel(
            id="reviewed-route",
            actor=actor,
            controller=original.controller,
            source_event="owned-route",
            source_sha256=original.source_sha256,
            rift="actual-rift",
            travels_frame=False,
            destination=None,
            account="Actual route",
            navigation="Actual equipment and source route",
            judge=1,
            appointment="actual-appointment",
            state="offstage",
            response_event="actual-review",
        )
    )
    before = canon.model_dump_json()
    view = _world_projection(canon)
    assert next(x for x in view[key] if x["id"] == entity)["cell"] is None
    assert canon.model_dump_json() == before
    assert next(x for x in getattr(canon.world, key) if x.id == entity).cell == (0, 0)


def test_actual_gorgon_crossing_masks_map_and_blocks_cached_actions_until_real_return(
    ledger,
):
    travel, game, worker, gateway, opener, _, _, _ = rolled(ledger)
    choose(
        travel,
        game,
        PLAYER,
        "harpy_defeat_select",
        options=("rift",),
        text="I open this actual Rift and escape",
    )
    tick(worker, gateway, 5)
    missions = MissionService(ledger)
    world, cast = WorldService(missions), CastService(ActorService(missions))
    actor = ActorRef(kind="gorgon", entity="actual-traveler")
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            gorgons=(*canon.world.gorgons, gorgon("erratic", actor.entity, revealed=True)),
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_gorgon_setup", canon)
    change(cast, ADMIN, "join", actor)
    portal = state(game).void_rifts[-1]
    assert (
        next(
            x for x in world.get(ADMIN, private=True)["world"]["pilots"] if x["id"] == opener.entity
        )["cell"]
        is None
    )
    proposal = travel.propose_route(
        ADMIN,
        "actual-world-follow",
        state(game).revision,
        actor,
        rift=portal.id,
        account="The original Gorgon crosses this real Rift",
        navigation="Actual recorded navigation equipment and route",
    )
    travel.review_route(
        ADMIN,
        "actual-world-crossing-review",
        proposal["id"],
        state(game).revision,
        allow=True,
        account="The actual source route permits this crossing",
    )
    before = state(game)
    cached = next(x for x in before.world.gorgons if x.id == actor.entity)
    assert cached.cell == (0, 0)
    assert (
        next(
            x for x in world.get(ADMIN, private=True)["world"]["gorgons"] if x["id"] == actor.entity
        )["cell"]
        is None
    )
    assert (
        next(x for x in world.get(PLAYER)["world"]["gorgons"] if x["id"] == actor.entity)["cell"]
        is None
    )
    with pytest.raises(WorkflowError, match="OFFSTAGE_RIFT"):
        world.locate_gorgon(
            ADMIN,
            "cannot-teleport-return",
            before.revision,
            actor.entity,
            (1, 1),
            "A new position cannot fabricate a return",
        )
    with pytest.raises(WorkflowError, match="OFFSTAGE_RIFT"):
        require_world_advancement(before)
    assert actor.entity not in str(GorgonService(world).preview(ADMIN)["attackers"])
    with pytest.raises(ValueError, match="OFFSTAGE_RIFT"):
        expose(
            before,
            Exposure(
                actor=actor,
                source_sha256=resolve(before, actor, ()).source_sha256,
                account="A cached square is not real exposure",
                weakness_confirmed=True,
            ),
            "not-real-map-exposure",
        )

    async def show():
        interaction = current(2)
        await interaction.response.defer(ephemeral=True)
        pages = MapPages(world, 2)
        pages.page = 1
        await pages.show(interaction)
        content = interaction.edit_original_response.call_args.kwargs["content"]
        assert "position unknown or offstage" in content
        end_view = current(1)
        await end_view.response.defer(ephemeral=True)
        await open_end(
            end_view, CycleService(OffDutyService(missions)), dict(game_revision=before.revision)
        )
        assert end_view.edit_original_response.call_args.kwargs["view"] is not None

    asyncio.run(show())
    assert state(game) == before
    returned = travel.propose_route(
        ADMIN,
        "actual-world-return",
        before.revision,
        actor,
        return_of=proposal["id"],
        destination=(1, 1),
        account="The original Gorgon actually returns",
        navigation="Actual return route and source equipment",
    )
    travel.review_route(
        ADMIN,
        "actual-world-return-review",
        returned["id"],
        state(game).revision,
        allow=True,
        account="Actual known return square confirmed",
    )
    assert next(x for x in world.get(PLAYER)["world"]["gorgons"] if x["id"] == actor.entity)[
        "cell"
    ] == [1, 1]
    with pytest.raises(WorkflowError, match="OFFSTAGE_RIFT"):
        require_world_advancement(state(game))
    escaped = next(x for x in state(game).harpy_defeats if x.actor == opener and x.escaped)
    original_return = travel.propose_route(
        PLAYER,
        "actual-opener-return",
        state(game).revision,
        opener,
        escape_effect=escaped.id,
        destination=(0, 0),
        account="The actual original Rift opener returns",
        navigation="Actual route home",
    )
    travel.review_route(
        ADMIN,
        "actual-opener-return-review",
        original_return["id"],
        state(game).revision,
        allow=True,
        account="The real original Harpy's return route is established",
    )
    require_world_advancement(state(game))
