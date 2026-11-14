from uuid import uuid4

import pytest
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_off_duty_cycle import activate, call, prepared
from test_world_service import transfer_npc

from girlframe.engine.m3_off_duty import HandlerContext
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import AdversaryPilot, Asset, Npc
from girlframe.services.inbox import InboxService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

ledger = ledger_fixture
ACTOR = GuildViewer(4, 200, True, False)


def npc_actor(store, cycle, game, job="base_personnel"):
    store.join(ACTOR, "join-npc-human")
    world = WorldService(cycle.missions)
    world.npc(
        ADMIN,
        "actual-npc",
        state(game).revision,
        Npc(
            id="person",
            name="PRIVATE_NPC",
            jobs=(job,),
            detail="A human's role",
            controller=1,
            cell=(0, 0),
            revealed=True,
        ),
    )
    transfer_npc(world, ADMIN, ACTOR, "person")


@pytest.mark.parametrize(
    "operation,expected",
    [
        ("hire", "foundation"),
        ("fire", "unemployed"),
        ("chastise", "unrecorded"),
        ("request", "unrecorded"),
    ],
)
def test_npc_scene_requires_actual_role_player_and_records_only_its_real_effect(
    ledger, operation, expected
):
    cycle, game, identity = prepared(ledger)
    npc_actor(ledger, cycle, game)
    activate(cycle, game, identity)
    call(
        cycle,
        game,
        ADMIN,
        identity,
        "handler_scene",
        "npc_employment",
        (1, 2),
        "PRIVATE_SCENE_ACCOUNT",
        None,
        HandlerContext(entity="npc:person", operation=operation),
    )
    assert cycle.review(ACTOR, identity)["handler_scene"]["participants"] == [1, 2, 4]
    assert any(x.task == "m3_off_duty" for x in InboxService(ledger).items(ACTOR))
    assert cycle.review(ACTOR, identity)["sheet"] is None
    for actor in (ADMIN, PLAYER):
        call(cycle, game, actor, identity, "acknowledge", None)
    assert state(game).world.npcs[0].employment == "unrecorded"
    data = cycle.review(ACTOR, identity)
    result = cycle.acknowledge(
        ACTOR, "actual-role-attestation", identity, data["revision"], data["game_revision"], None
    )
    assert (
        cycle.acknowledge(
            ACTOR,
            "actual-role-attestation",
            identity,
            data["revision"],
            data["game_revision"],
            None,
        )
        == result
    )
    assert state(game).world.npcs[0].employment == expected
    assert not [
        x
        for x in cycle.periods.get(ADMIN, identity)["work"]
        if x["kind"] == "off_duty_handler_scene"
    ]


def test_prisoner_npc_scene_uses_actual_role_and_does_not_convert_it_into_a_pc(ledger):
    cycle, game, identity = prepared(ledger)
    npc_actor(ledger, cycle, game, "prisoner")
    activate(cycle, game, identity)
    call(
        cycle,
        game,
        ADMIN,
        identity,
        "handler_scene",
        "prisoner",
        (1, 2),
        "A prison visit",
        None,
        HandlerContext(entity="npc:person"),
    )
    for actor in (ADMIN, PLAYER, ACTOR):
        call(cycle, game, actor, identity, "acknowledge", None)
    assert "4" not in state(game).sheets
    assert state(game).world.npcs[0].jobs == ("prisoner",)
    assert any(
        x["kind"] == "handler_off_duty_scene" and x["entity"] == "npc:person"
        for x in state(game).facts
    )


def test_free_harpy_cannot_be_used_as_prisoner_without_actual_custody_event(ledger):
    cycle, game, identity = prepared(ledger)
    activate(cycle, game, identity)
    harpy = AdversaryPilot(
        id="external",
        name="A Harpy",
        kind="harpy",
        girl="MOCKINGBIRD",
        frame="JANUS-B",
        controller=3,
        cell=(0, 0),
        assets=(
            Asset(id="a", name="Capability", description="An actual capability", family="girl"),
        ),
    )
    with ledger.transaction() as c:
        current = state(game)
        current.world = update(current.world, pilots=(harpy,))
        game.event(c, 1, "introduced-free-harpy", "synthetic.world", current)
    with pytest.raises(WorkflowError, match="actual current custody"):
        call(
            cycle,
            game,
            ADMIN,
            identity,
            "handler_scene",
            "prisoner",
            (1, 2),
            "Cannot invent a capture",
            None,
            HandlerContext(entity="pilot:external"),
        )
    event = str(uuid4())
    with ledger.transaction() as c:
        current = state(game)
        captured = harpy.model_copy(
            update={"custody": "captured", "custodian": 1, "custody_event": event}
        )
        current.world = update(current.world, pilots=(captured,))
        game.event(c, 1, "actual-capture", "synthetic.capture", current, event_id=event)
    call(
        cycle,
        game,
        ADMIN,
        identity,
        "handler_scene",
        "prisoner",
        (1, 2),
        "Actual prison scene",
        None,
        HandlerContext(entity="pilot:external"),
    )
    assert cycle.review(PLAYER, identity)["handler_scene"]["participants"] == [1, 2, 3]
    assert state(game).world.pilots[0].custody == "captured"


def test_exploit_scene_requires_affected_girls_own_participation_without_invented_rewards(ledger):
    cycle, game, identity = prepared(ledger)
    activate(cycle, game, identity)
    before = state(game).sheets["2"].model_dump()
    call(
        cycle,
        game,
        ADMIN,
        identity,
        "handler_scene",
        "exploit",
        (1, 2),
        "A human-authored scene",
        2,
    )
    call(cycle, game, ADMIN, identity, "acknowledge", None)
    assert any(
        x["kind"] == "off_duty_handler_scene" for x in cycle.periods.get(ADMIN, identity)["work"]
    )
    call(cycle, game, PLAYER, identity, "acknowledge", None)
    assert state(game).sheets["2"].model_dump() == before
    assert state(game).facts[-1]["scene_kind"] == "exploit"
