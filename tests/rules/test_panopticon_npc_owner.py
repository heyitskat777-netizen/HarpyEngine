"""Real NPC Panopticon answers belong to the original, still-current controller."""

from uuid import uuid4

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, state, tick
from test_red_queen import buy, initialize, native_choice, ready, roll
from test_world_service import transfer_npc

from girlframe.engine import m3_red_queen as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_npc_panopticon_private_answer_requires_current_original_owner(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    initialize(controls)
    buy(controls, rules.PANOPTICON)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    world = WorldService(MissionService(ledger))
    target = ActorRef(kind="npc", entity="actual-observed-person")
    world.npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=target.entity,
            name="Actual observed person",
            jobs=("guard",),
            controller=1,
            cell=(1, 0),
            revealed=True,
            detail="Original person observed from a real distance",
        ),
    )
    transfer_npc(world, ADMIN, OTHER, target.entity)
    context = controls.record_context(
        PLAYER,
        str(uuid4()),
        900,
        state(game).revision,
        "distant",
        current_ref(state(game), 2),
        target,
        "I actually observe this person at a distance",
    )["id"]
    action = roll(
        game,
        worker,
        gateway,
        play="red_queen_panopticon",
        faces=(3, 4),
        target=target,
        source=context,
    )
    answer(game, PLAYER, "red_queen_questions", options=("where", "ashamed"))
    row = next(x for x in game.choices(OTHER) if x["kind"] == "red_queen_answers")
    with pytest.raises(WorkflowError):
        game.decision(PLAYER, row["id"])
    before = state(game)
    calls = game.dice.calls
    with pytest.raises(WorkflowError, match="finish pending Plays"):
        transfer_npc(world, OTHER, ADMIN, target.entity)
    assert state(game) == before and game.dice.calls == calls
    native_choice(
        game,
        OTHER,
        "red_queen_answers",
        **{
            "answer:where": "My actual present location",
            "answer:ashamed": "PRIVATE_ACTUAL_NPC_ANSWER",
        },
    )
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    source = rules.get(state(game), rules.Session, action)
    assert source.target == target and source.target_controller == OTHER.user_id
    assert source.replies["answer:ashamed"] == "PRIVATE_ACTUAL_NPC_ANSWER"
    # The original Handler is an explicit source participant, not an unauthorized viewer.
    assert controls.view(ADMIN, action)["source"]["handler_controller"] == ADMIN.user_id
    assert (
        controls.view(PLAYER, action)["source"]["replies"]["answer:where"]
        == "My actual present location"
    )
    calls = game.dice.calls
    transfer_npc(world, OTHER, ADMIN, target.entity)
    assert rules.get(state(game), rules.Session, action) == source
    assert (
        controls.view(OTHER, action)["source"]["replies"]["answer:ashamed"]
        == "PRIVATE_ACTUAL_NPC_ANSWER"
    )
    assert game.dice.calls == calls
