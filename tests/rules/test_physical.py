"""Character, vessel, occupied Frame and current assigned Frame remain distinct."""

import json

import pytest
from pydantic import ValidationError
from test_actors import bindings
from test_actors import canon as canon
from test_actors import ledger as ledger

from girlframe.engine import m3_physical as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_frame_state import FrameRuntime
from girlframe.engine.m3_physical_state import InitialPlacement


def proposal(canon, *, mode="piloting", girl_cell=(0, 0), frame_cell=(0, 0)):
    ref = ActorRef(kind="pilot", entity="2", incarnation=canon.sheets["2"].character_id)
    actual = resolve(canon, ref, bindings(canon))
    return InitialPlacement(
        actor=ref,
        frame_instance=actual.frame_instance,
        girl_cell=girl_cell,
        frame_cell=frame_cell,
        mode=mode,
        account="PRIVATE_ACTUAL_ORIGINAL_PHYSICAL_FACTS",
        facts_confirmed=True,
    )


def place(canon, pick=None):
    return rules.initial(
        canon,
        bindings(canon),
        pick or proposal(canon),
        "actual-vessel",
        "actual-owned-proposal",
        "actual-distinct-review",
    )


@pytest.mark.parametrize("mode", ("outside_frame", "inside_frame", "piloting"))
def test_owned_original_facts_place_actual_vessel_without_moving_other_roles_or_resources(
    canon, mode
):
    original = canon.model_dump_json()
    result = place(canon, proposal(canon, mode=mode))
    assert canon.model_dump_json() == original and result.sheets == canon.sheets
    assert result.world == canon.world and result.bonds == canon.bonds
    actor = resolve(result, proposal(canon).actor, bindings(result))
    assert actor.cell == actor.frame_cell == (0, 0)
    assert actor.vessel_id == "actual-vessel" and actor.vessel_id != actor.ref.incarnation
    assert actor.inside_frame is (mode != "outside_frame")
    assert actor.piloting is (mode == "piloting")
    assert actor.occupied_frame_instance == (
        actor.frame_instance if mode != "outside_frame" else None
    )
    assert actor.position_sha256 is not None
    assert actor.source_sha256 == resolve(canon, actor.ref, bindings(canon)).source_sha256


def test_same_humans_npc_is_not_moved_by_girl_placement(canon):
    result = place(canon, proposal(canon, mode="outside_frame", girl_cell=(2, 0)))
    assert resolve(result, proposal(canon).actor, bindings(result)).cell == (2, 0)
    assert resolve(result, ActorRef(kind="npc", entity="2"), ()).cell == (0, 0)
    assert result.world.npcs == canon.world.npcs


def test_legacy_unknown_positions_stay_unknown_and_cannot_be_inferred_from_cast_or_owner(canon):
    legacy = canon.model_dump(mode="json")
    del legacy["placements"]
    loaded = GameState.model_validate_json(json.dumps(legacy))
    assert not loaded.placements
    view = resolve(loaded, proposal(canon).actor, bindings(loaded))
    assert view.cell is view.frame_cell is view.vessel_id is None
    assert view.inside_frame is view.piloting is view.position_sha256 is None


@pytest.mark.parametrize("mode", ("inside_frame", "piloting"))
def test_occupancy_requires_same_actual_cell(canon, mode):
    with pytest.raises(ValidationError, match="actual Frame"):
        proposal(canon, mode=mode, girl_cell=(1, 0))


def test_initial_recording_is_not_a_repeatable_movement_or_body_reset_command(canon):
    result = place(canon)
    before = result.model_dump_json()
    with pytest.raises(ValueError, match="cannot reset or move"):
        place(result, proposal(result, girl_cell=(1, 0), frame_cell=(1, 0)))
    assert result.model_dump_json() == before


def test_new_assigned_frame_does_not_move_girl_or_copy_old_frame_location(canon):
    result = place(canon)
    old = resolve(result, proposal(canon).actor, bindings(result))
    result.sheets["2"].frame_runtime = FrameRuntime(
        id="new-frame", generation=1, source_work="actual-new-frame-source"
    )
    current = resolve(result, old.ref, bindings(result))
    assert current.cell == old.cell and current.vessel_id == old.vessel_id
    assert current.frame_instance == "new-frame" and current.frame_cell is None
    assert current.occupied_frame_instance == old.frame_instance
    assert current.inside_frame is True and current.piloting is None
    assert result.placements[0].frame_instance == old.frame_instance
    with pytest.raises(ValueError, match="cannot reset or move"):
        place(result, proposal(result))


def test_scrapped_frame_can_record_occupancy_without_claiming_piloting(canon):
    canon.sheets["2"].frame_scrapped = True
    with pytest.raises(ValueError, match="scrapped Frame"):
        place(canon)
    result = place(canon, proposal(canon, mode="inside_frame"))
    actual = resolve(result, proposal(canon).actor, bindings(result))
    assert actual.inside_frame is True and actual.piloting is False


def test_later_scrapping_stops_piloting_without_moving_or_ejecting_the_girl(canon):
    result = place(canon)
    original = result.placements[0]
    result.sheets["2"].frame_scrapped = True
    actor = resolve(result, original.actor, bindings(result))
    assert actor.inside_frame is True and actor.piloting is False
    assert (
        actor.cell == original.girl_cell
        and actor.occupied_frame_instance == original.frame_instance
    )
    assert result.placements[0] == original


@pytest.mark.parametrize("wrong", ("frame", "map", "character"))
def test_wrong_current_frame_map_or_character_cannot_be_placed(canon, wrong):
    pick = proposal(canon)
    if wrong == "frame":
        pick = pick.model_copy(update={"frame_instance": "other-frame"})
    elif wrong == "map":
        pick = pick.model_copy(update={"girl_cell": (99, 99), "frame_cell": (99, 99)})
    else:
        pick = pick.model_copy(
            update={"actor": pick.actor.model_copy(update={"incarnation": "other-character"})}
        )
    before = canon.model_dump_json()
    with pytest.raises(ValueError):
        place(canon, pick)
    assert canon.model_dump_json() == before


def test_physical_proposal_does_not_accept_npc_proxy_or_unconfirmed_facts(canon):
    pick = proposal(canon)
    for patch in (
        {"actor": ActorRef(kind="npc", entity="2")},
        {"facts_confirmed": False},
        {"account": " "},
    ):
        with pytest.raises(ValidationError):
            place(canon, pick.model_copy(update=patch))
    with pytest.raises(ValidationError, match="distinct events"):
        rules.initial(canon, bindings(canon), pick, "vessel", "same-event", "same-event")


def test_canonical_original_placements_reject_duplicate_actor_or_vessel_records(canon):
    result = place(canon)
    data = result.model_dump(mode="json")
    data["placements"].append(data["placements"][0])
    with pytest.raises(ValidationError, match="distinct actors and vessels"):
        GameState.model_validate_json(json.dumps(data))


def test_actual_girl_position_constrains_a_later_improvement_scene_without_casting_movement(
    canon,
):
    from test_comforts import offered as comfort_offered
    from test_comforts import scene as comfort_scene

    state, actor, benefit = comfort_offered(canon)
    state = place(state, proposal(state, mode="outside_frame", girl_cell=(2, 0)))
    with pytest.raises(ValueError, match="already at the scene"):
        comfort_scene(state, actor, benefit, location="base0")
    recorded = comfort_scene(state, actor, benefit, location="base1")
    assert recorded.scene.location == "base1"
    assert state.placements[0].girl_cell == (2, 0) and state.placements[0].frame_cell == (0, 0)
