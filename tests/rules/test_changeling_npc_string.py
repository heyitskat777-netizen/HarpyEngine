"""Actual NPC followthrough Bond produces one consumable controller-owned Psych String."""

from uuid import uuid4

import pytest
from test_cast_service import change as cast_change
from test_changeling import ready
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, state, tick
from test_npc_flirt import finish_roll

from girlframe.engine import m3_changeling as rules
from girlframe.engine import m3_npc_flirt as npc_rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_changeling import prove_fingers, prove_node
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_flirt import NpcFlirtService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_npc_followthrough_string_is_consumed_for_owned_question(
    ledger, tmp_path, monkeypatch
):
    # Prior physical/world/resources are explicit synthetic setup in ready.
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(
            rules.BLANK,
            rules.STRINGS,
            rules.FINGERS,
            *rules.REQUISITIONS,
            npc_rules.RULE,
            "core.core.npcs",
            "core.core.npc-assets",
            "core.core.npc-tags",
            "npc.npc.public-relations",
        ),
    )
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world", "playbooks"}}
            )
        }
    )
    mission = MissionService(ledger)
    npc = ActorRef(kind="npc", entity="actual-psychic-counterpart")
    WorldService(mission).npc(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Pat",
            jobs=("public_relations",),
            controller=1,
            detail="PRIVATE_NPC_BODY",
            revealed=True,
            cell=(0, 0),
        ),
    )
    cast_change(CastService(ActorService(mission)), ADMIN, "join", npc)
    controls.body_fact(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        npc,
        "human_npc",
        "I witness this actual ordinary human brain in its original body",
    )
    actor = current_ref(state(game), 2)
    assert depth(state(game), actor, npc) == 0
    game.dice = Dice((4, 4))
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="flirt",
            target_actor=npc,
            heat=0,
            context="I ask what this actual person wants",
            trigger_confirmed=True,
        ),
    )["action_id"]
    finish_roll(game, worker, gateway, action)
    answer(game, PLAYER, "npc_flirt_actor", options=("name",))
    answer(game, ADMIN, "npc_flirt_target", text="Call me Agent Seven", flag=True)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    tick(worker, gateway, 6)
    assert depth(state(game), actor, npc) == 0
    assert not [x for x in rules.records(state(game), rules.String) if x.subject.actor == npc]
    service = NpcFlirtService(game)
    done = service.record_followthrough(
        PLAYER,
        str(uuid4()),
        action,
        state(game).revision,
        900,
        "I actually address Pat as Agent Seven",
    )["id"]
    service.confirm_followthrough(
        ADMIN,
        str(uuid4()),
        done,
        state(game).revision,
        True,
        "She addressed me as Agent Seven as I requested",
    )
    assert depth(state(game), actor, npc) == 1
    nodes = [x for x in rules.records(state(game), rules.String) if x.subject.actor == npc]
    assert len(nodes) == 1 and nodes[0].origin == "deepen"
    with ledger.engine.connect() as c:
        prove_node(game, c, state(game), nodes[0].id)
    use_id = controls.fingers(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        nodes[0].id,
        "question",
        "I consume this actual earned String",
        question="What are you worried about?",
    )["id"]
    use = rules.record(state(game), rules.Fingers, use_id)
    assert not rules.reciprocal(use.subject)
    question = next(x for x in rules.records(state(game), rules.Question) if x.source == use_id)
    with pytest.raises(WorkflowError):
        controls.answer(OTHER, str(uuid4()), state(game).revision, question.id, "Wrong owner")
    controls.answer(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        question.id,
        "I am worried about the actual next patrol",
    )
    final = state(game)
    with ledger.engine.connect() as c:
        proved = prove_fingers(game, c, final, use_id)
        assert proved.completed_event
    assert rules.record(final, rules.Question, question.id).answer == (
        "I am worried about the actual next patrol"
    )
    with pytest.raises(WorkflowError):
        controls.fingers(
            PLAYER,
            str(uuid4()),
            state(game).revision,
            900,
            nodes[0].id,
            "question",
            "Cannot spend twice",
            question="Again?",
        )
    assert state(game).model_dump_json() == final.model_dump_json()
