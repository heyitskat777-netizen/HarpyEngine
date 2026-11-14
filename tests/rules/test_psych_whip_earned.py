"""Genuine paid Psych Whip consumes an earned String for Handler-selected Helpless."""

from uuid import uuid4

import pytest
from test_cast_service import change as cast_change
from test_changeling import ready
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, state, tick
from test_npc_flirt import finish_roll
from test_world_service import transfer_npc

from girlframe.engine import m3_changeling as rules
from girlframe.engine import m3_npc_flirt as npc_rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth, is_helpless
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_changeling import prove_fingers, prove_node
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_flirt import NpcFlirtService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def test_actual_paid_psych_whip_consumes_earned_npc_string_for_handler_helpless(
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
    transfer_npc(WorldService(mission), ADMIN, OTHER, npc.entity)
    cast_change(CastService(ActorService(mission)), OTHER, "join", npc)
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
    answer(game, OTHER, "npc_flirt_target", text="Call me Agent Seven", flag=True)
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
        OTHER,
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
    permissions = state(game).sheets["2"].permissions
    purchase = controls.purchase(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        rules.WHIP,
        "Actual paid Psych Whip in my original Changeling",
    )
    assert purchase["cost"] == 2
    assert state(game).sheets["2"].permissions == permissions - 2
    use_id = controls.fingers(
        PLAYER,
        str(uuid4()),
        state(game).revision,
        900,
        nodes[0].id,
        "fry",
        "I spend this exact earned String through my actual Psych Whip",
    )["id"]
    use = rules.record(state(game), rules.Fingers, use_id)
    assert use.handler_controller == 1 and use.subject.controller == 3
    assert not rules.reciprocal(use.subject)
    assert not is_helpless(state(game), npc, actor)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        controls.fry(OTHER, str(uuid4()), state(game).revision, use_id, "helpless")
    assert state(game).model_dump_json() == before
    controls.fry(ADMIN, str(uuid4()), state(game).revision, use_id, "helpless")
    final = state(game)
    assert is_helpless(final, npc, actor)
    assert next(x for x in final.world.npcs if x.id == npc.entity).alive
    outcome = rules.record(final, rules.FryOutcome, use_id)
    assert outcome.outcome == "helpless" and outcome.controller == 1
    with ledger.engine.connect() as c:
        assert prove_fingers(game, c, final, use_id).completed_event
    assert rules.record(final, rules.String, nodes[0].id).spent_by == use_id
    with pytest.raises(WorkflowError):
        controls.fingers(
            PLAYER,
            str(uuid4()),
            state(game).revision,
            900,
            nodes[0].id,
            "fry",
            "Cannot spend this String twice",
        )
    assert state(game).model_dump_json() == final.model_dump_json()
