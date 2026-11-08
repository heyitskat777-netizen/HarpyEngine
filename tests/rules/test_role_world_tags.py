"""Source social effects use actual world Tags/Bonds without invented Heat tracks."""

from uuid import uuid4

import pytest
from test_actors import bindings
from test_actors import canon as canon
from test_actors import ledger as ledger

from girlframe.engine import m3_role_punishments as rules
from girlframe.engine.m3_actor_bonds import current_ref, depth, set_depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_punishments import Details
from girlframe.engine.m3_role_punishment_state import Instruction


@pytest.mark.parametrize(
    "target",
    [ActorRef(kind="gorgon", entity="secret"), ActorRef(kind="external_pilot", entity="external")],
)
def test_actual_world_tags_and_intense_bond_use_only_real_heat_resources(canon, target):
    actor = current_ref(canon, 2)
    detail = Details(kind="quality_time", tag="Actual source world Tag")
    instruction = Instruction(kind=detail.kind, details_json=detail.model_dump_json())
    changed = rules.social(
        canon, target, actor, instruction, bindings(canon), "actual-source", str(uuid4())
    )
    assert depth(changed, target, actor) == 1
    collection = changed.world.gorgons if target.kind == "gorgon" else changed.world.pilots
    assert next(x for x in collection if x.id == target.entity).tags[-1].label == detail.tag
    assert set(changed.sheets) == set(canon.sheets)
    intense = set_depth(changed, target, actor, 2, "actual-intense-source")
    # The existing beyond-intense-source-legal-no-heat ruling preserves the Bond,
    # granting overflow only to its actual Heat-bearing participants.
    assert "quality_time" in rules.available(intense, target, actor, bindings(intense))
    assert "reduced_socialization" in rules.available(intense, target, actor, bindings(intense))
    before = intense.model_dump_json()
    identity = str(uuid4())
    result = rules.social(
        intense, target, actor, instruction, bindings(intense), "actual-overflow", identity
    )
    assert intense.model_dump_json() == before
    assert depth(result, target, actor) == 2
    edge = next(x for x in result.actor_bonds if {x.first, x.second} == {target, actor})
    assert edge.source_event == "actual-overflow"
    assert result.sheets[actor.entity].heat == intense.sheets[actor.entity].heat + 2
    assert set(result.sheets) == set(intense.sheets)
    assert result.sheets["3"] == intense.sheets["3"]
    assert result.handler_heat == intense.handler_heat
    assert result.harpy_states == intense.harpy_states
    assert result.native_harpies == intense.native_harpies
    assert result.janus_cores == intense.janus_cores
    assert rules.view(result, target, bindings(result)).heat is None
    rows = result.world.gorgons if target.kind == "gorgon" else result.world.pilots
    original_target = next(x for x in collection if x.id == target.entity)
    actual_target = next(x for x in rows if x.id == target.entity)
    assert actual_target.tags[:-1] == original_target.tags
    assert actual_target.tags[-1].id == identity
    assert actual_target.tags[-1].label == detail.tag
    assert actual_target.tags[-1].giver_entity == actor.model_dump_json()
    assert actual_target.model_dump(exclude={"tags"}) == original_target.model_dump(
        exclude={"tags"}
    )
