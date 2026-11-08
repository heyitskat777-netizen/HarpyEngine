"""Expected source effects: actual arrival, preserved Frame, and owned obsession."""

import pytest
from test_actors import bindings
from test_actors import canon as canon_fixture
from test_ledger import ledger as ledger_fixture

from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_leviathan_arrival import arrive, requirements
from girlframe.engine.m3_leviathan_obsession import allowed_gain, influence, require_identity_change
from girlframe.engine.m3_physical_state import Placement
from girlframe.services.m3_world import _world_projection

canon = canon_fixture
ledger = ledger_fixture


def source(canon, cell=(2, 2)):
    canon.world = canon.world.model_copy(
        update={
            "gorgons": tuple(
                x.model_copy(update={"types": ("leviathan",), "cell": cell})
                if x.id == "secret"
                else x
                for x in canon.world.gorgons
            )
        }
    )
    return ActorRef(kind="gorgon", entity="secret")


@pytest.mark.parametrize("mode", ["outside_frame", "piloting"])
def test_arrival_moves_actual_body_and_only_its_actually_occupied_frame(canon, mode):
    endpoint = source(canon)
    actor = ActorRef(kind="pilot", entity="2", incarnation=canon.sheets["2"].character_id)
    actual = resolve(canon, actor, bindings(canon))
    canon.placements.append(
        Placement(
            actor=actor,
            vessel_id="actual-original-body",
            frame_instance=actual.frame_instance,
            girl_cell=(0, 0),
            frame_cell=(0, 0),
            mode=mode,
            proposed_event="owned-factual-proposal",
            source_event="judge-reviewed-actual-pose",
            account="Actual original pose",
        )
    )
    frozen = requirements(canon, actor, endpoint, bindings(canon))
    assert frozen.blocker is None and frozen.mover == actor
    result = arrive(
        canon,
        frozen,
        "real-completed-arrival",
        "Owner and mover confirm actual arrival",
        source_action="actual-low-obsession",
        bindings=bindings(canon),
    )
    placed = result.placements[0]
    assert placed.vessel_id == "actual-original-body" and placed.girl_cell == (2, 2)
    assert placed.frame_cell == ((2, 2) if mode == "piloting" else (0, 0))
    assert resolve(result, actor, bindings(result)).cell == (2, 2)
    assert result.sheets == canon.sheets and canon.placements[0].girl_cell == (0, 0)


def test_unknown_endpoint_stays_unknown_in_actual_npc_read_and_world_projection(canon):
    endpoint = source(canon, None)
    actor = ActorRef(kind="npc", entity="2")
    frozen = requirements(canon, actor, endpoint)
    result = arrive(
        canon,
        frozen,
        "actual-unknown-arrival",
        "The actual trail reaches the body",
        source_action="actual-low-obsession",
    )
    assert resolve(result, actor, ()).cell is None
    assert next(x for x in _world_projection(result)["npcs"] if x["id"] == "2")["cell"] is None
    assert result.world.npcs == canon.world.npcs


def test_mid_owned_identity_locks_and_only_its_actual_identity_gains_heat(canon):
    endpoint = source(canon)
    actor = ActorRef(kind="pilot", entity="2", incarnation=canon.sheets["2"].character_id)
    old = next(x for x in canon.sheets["2"].identities if not x.protected and not x.paired)
    result = influence(canon, endpoint, actor, "mid", "actual-owned-result", replace=old.id)
    actual = next(x for x in result.sheets["2"].identities if x.obsession_sources)
    assert actual.name == "obsessed"
    assert allowed_gain(result, actor, 3, "actual_identity", identity=actual.id) == 3
    assert allowed_gain(result, actor, 7, "stimulant", "actual-performed-punishment") == 0
    assert allowed_gain(result, actor, -2, "actual_spend") == -2
    with pytest.raises(ValueError):
        require_identity_change(result, actor, (actual.id,))
    assert canon.sheets["2"].identities[0].obsession_sources == ()
