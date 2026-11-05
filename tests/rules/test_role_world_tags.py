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
def test_actual_world_tag_and_bond_without_proxy_sheet_then_intense_heat_is_gated(canon, target):
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
    assert "quality_time" not in rules.available(intense, target, actor, bindings(intense))
    assert "reduced_socialization" in rules.available(intense, target, actor, bindings(intense))
    with pytest.raises(ValueError, match="actual resources"):
        rules.social(
            intense, target, actor, instruction, bindings(intense), "no-fake-heat", str(uuid4())
        )
