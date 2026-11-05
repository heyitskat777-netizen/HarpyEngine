"""A converted but unlocated Frame never gains an invented map square."""

import pytest
from test_actors import canon as canon
from test_actors import ledger as ledger
from test_ledger import ADMIN, PLAYER
from test_m2_game import state
from test_world import gorgon
from test_world_service import ready

from girlframe.engine import m3_gorgon, m3_gorgon_combat
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_world import directed_steps, locate_gorgon, update
from girlframe.engine.m3_world_state import Goal
from girlframe.services.onboarding import WorkflowError


def test_two_unlocated_gorgons_have_no_shared_square_and_cannot_attack(canon):
    canon.world = update(
        canon.world, gorgons=(gorgon("erratic", "a", cell=None), gorgon("erratic", "b", cell=None))
    )
    first, second = (ActorRef(kind="gorgon", entity=x) for x in ("a", "b"))
    assert resolve(canon, first, ()).cell is None
    with pytest.raises(ValueError, match="co-located"):
        m3_gorgon_combat.eligible(canon, first, second)
    with pytest.raises(ValueError, match="co-located"):
        m3_gorgon.eligible(canon, first, ActorRef(kind="npc", entity="2"))


def test_unknown_directed_position_cannot_move_toward_a_goal_until_actual_facts(canon):
    actual = gorgon(
        "directed", "unlocated", cell=None, goal=Goal(kind="location", entity_id="city0")
    )
    world = update(canon.world, gorgons=(actual,))
    with pytest.raises(ValueError, match="UNKNOWN_POSITION"):
        directed_steps(world, actual)
    placed = locate_gorgon(world, actual.id, (1, 1), "actual-observed-position")
    assert placed.gorgons[0].cell == (1, 1) and world.gorgons[0].cell is None
    assert placed.gorgons[0].assets == actual.assets
    assert placed.gorgons[0].position_event == "actual-observed-position"
    with pytest.raises(ValueError, match="missing initial"):
        locate_gorgon(placed, actual.id, (0, 0), "cannot-reset")


def test_real_handler_records_missing_position_once_with_stale_and_pause_guards(ledger):
    service, game = ready(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            gorgons=canon.world.gorgons
            + (gorgon("erratic", "converted", cell=None, revealed=True),),
        )
        game.event(c, 1, "synthetic-converted-frame", "synthetic.state", canon)
    assert (
        next(x for x in service.get(PLAYER)["world"]["gorgons"] if x["id"] == "converted")["cell"]
        is None
    )
    revision = state(game).revision
    with pytest.raises(WorkflowError):
        service.locate_gorgon(
            PLAYER, "cannot-set-handler-facts", revision, "converted", (1, 1), "No authority"
        )
    ledger.safety(PLAYER, "pause-actual-world", ledger.status(PLAYER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.locate_gorgon(
            ADMIN, "paused-position", revision, "converted", (1, 1), "Actual observed position"
        )
    ledger.safety(PLAYER, "resume-actual-world", ledger.status(PLAYER)["revision"], pause=False)
    result = service.locate_gorgon(
        ADMIN, "actual-position", revision, "converted", (1, 1), "Actual observed position"
    )
    assert (
        service.locate_gorgon(
            ADMIN, "actual-position", revision, "converted", (1, 1), "Actual observed position"
        )
        == result
    )
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        service.locate_gorgon(
            ADMIN, "stale-position", revision, "converted", (2, 2), "Cannot move known actor"
        )
