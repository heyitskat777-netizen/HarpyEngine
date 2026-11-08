"""One human may control distinct actual actors without sharing their resources."""

from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_ledger import ledger as ledger_fixture
from test_m2_game import setup_game, state
from test_world import initial

from girlframe.engine import m3_actors as rules
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_director import enter
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import AdversaryPilot, Asset, Npc

ledger = ledger_fixture


@pytest.fixture
def canon(ledger):
    game, *_ = setup_game(ledger)
    canon = state(game)
    canon.world = update(
        initial(),
        npcs=(
            Npc(
                id="2",
                name=canon.sheets["2"].callsign,
                jobs=("guard",),
                detail="Distinct NPC",
                controller=2,
                cell=(0, 0),
            ),
            Npc(
                id="director",
                name="Director",
                jobs=("director",),
                detail="Authority",
                controller=3,
                cell=(0, 0),
            ),
            Npc(
                id="npc-handler",
                name="Handler",
                jobs=("handler",),
                detail="Another Handler",
                controller=2,
                cell=(0, 0),
            ),
        ),
        pilots=(
            AdversaryPilot(
                id="external",
                name="External Pilot",
                kind="harpy",
                girl="MOCKINGBIRD",
                frame="JANUS",
                controller=2,
                cell=(0, 0),
                assets=(
                    Asset(
                        id="external-asset",
                        name="Actual Frame Asset",
                        description="A printed capability",
                        family="frame",
                        void=True,
                    ),
                ),
            ),
        ),
    )
    return canon


def bindings(canon):
    return tuple(
        ProfileBinding(
            owner=x.owner, character_id=x.character_id, profile_revision=x.source_profile_revision
        )
        for x in canon.sheets.values()
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "pilot", "entity": "2"},
        {"kind": "pilot", "entity": "02", "incarnation": "char"},
        {"kind": "handler", "entity": "0"},
        {"kind": "handler", "entity": str(2**64)},
        {"kind": "npc", "entity": "npc", "controller": 2},
        {"kind": "npc", "entity": "npc", "incarnation": "fake"},
        {"kind": "unknown", "entity": "npc"},
        {"kind": "gorgon", "entity": " "},
    ],
)
def test_reference_rejects_forged_controller_generation_type_and_numeric_alias(payload):
    with pytest.raises(ValidationError):
        ActorRef.model_validate(payload)


def test_same_human_and_same_name_do_not_merge_girl_and_npc_or_borrow_traits(canon):
    profile = bindings(canon)[0]
    pc = ActorRef(kind="pilot", entity="2", incarnation=profile.character_id)
    npc = ActorRef(kind="npc", entity="2")
    first, second = (rules.resolve(canon, ref, bindings(canon)) for ref in (pc, npc))
    assert first.controller == second.controller == 2 and first.label == second.label
    assert pc.token != npc.token and len(pc.token) == len(npc.token) == 36
    assert first.rules == "girl_frame" and first.assets and first.identities
    assert second.rules == "npc" and second.girl is second.frame is second.heat is None
    assert not second.assets and not second.identities
    assert ActorRef.model_validate_json(npc.model_dump_json()).token == npc.token


def test_actual_director_other_handler_gorgon_and_external_resources_remain_distinct(canon):
    values = bindings(canon)
    director = rules.resolve(canon, ActorRef(kind="npc", entity="director"), values)
    other_handler = rules.resolve(canon, ActorRef(kind="npc", entity="npc-handler"), values)
    handler = rules.resolve(canon, ActorRef(kind="handler", entity="1"), values)
    gorgon = rules.resolve(canon, ActorRef(kind="gorgon", entity="secret"), values)
    external = rules.resolve(canon, ActorRef(kind="external_pilot", entity="external"), values)
    assert (
        director.rules == "director" and other_handler.rules == "npc" and handler.rules == "handler"
    )
    assert gorgon.controller == 1 and all(x.family == "gorgon" for x in gorgon.assets)
    assert external.rules == "external_pilot" and external.assets[0].void
    assert external.heat is None and not external.identities
    assert not handler.identities and "1" not in canon.sheets


def test_actual_character_incarnation_and_canonical_binding_prevent_old_resource_inheritance(canon):
    original = bindings(canon)
    ref = ActorRef(kind="pilot", entity="2", incarnation=original[0].character_id)
    new_id = str(uuid4())
    forged = ActorRef(kind="pilot", entity="2", incarnation=new_id)
    replaced = tuple(
        x.model_copy(update={"character_id": new_id}) if x.owner == 2 else x for x in original
    )
    for candidate, profiles in ((forged, original), (ref, replaced), (forged, replaced)):
        with pytest.raises(ValueError, match="actual current character"):
            rules.resolve(canon, candidate, profiles)
    legacy = canon.model_copy(deep=True)
    legacy.sheets["2"].character_id = None
    with pytest.raises(ValueError):
        rules.resolve(legacy, ref, original)


def test_director_context_is_a_scoped_handler_role_without_pilot_or_frame_fabrication(canon):
    actual = enter(canon, 1, "director", "presence-work", ("Afraid", "Defiant"), "source")
    context = actual.director_contexts[0]
    ref = ActorRef(kind="handler", entity="1", incarnation=context.id)
    value = rules.resolve(actual, ref, bindings(canon))
    assert value.rules == "handler_girl" and len(value.identities) == 2 and value.heat == 0
    assert not value.assets and value.girl is value.frame is None
    assert actual.order == canon.order and actual.sheets == canon.sheets
    with pytest.raises(ValueError, match="actual current Girl-rules context"):
        rules.resolve(actual, ActorRef(kind="handler", entity="1"), bindings(canon))
    roles = rules.owned(actual, 1, bindings(canon))
    assert {x.rules for x in roles} == {"handler_girl", "gorgon"}
    assert len(rules.owned(actual, 2, bindings(canon))) == 4


def test_dead_world_actor_is_unavailable_for_actions_but_can_be_read_for_history(canon):
    canon.world = update(
        canon.world,
        npcs=tuple(
            x.model_copy(update={"alive": False}) if x.id == "2" else x for x in canon.world.npcs
        ),
    )
    ref = ActorRef(kind="npc", entity="2")
    with pytest.raises(ValueError, match="living"):
        rules.resolve(canon, ref, bindings(canon))
    assert not rules.resolve(canon, ref, bindings(canon), require_alive=False).alive
    assert ref not in rules.owned_refs(canon, 2, bindings(canon))


def test_resource_snapshot_cannot_mutate_canonical_actor_and_tracks_real_source_changes(canon):
    ref = ActorRef(kind="pilot", entity="2", incarnation=canon.sheets["2"].character_id)
    before = rules.resolve(canon, ref, bindings(canon))
    with pytest.raises(ValidationError):
        before.assets[0].damaged = True
    canon.sheets["2"].heat += 1
    after = rules.resolve(canon, ref, bindings(canon))
    assert before.source_sha256 != after.source_sha256 and before.ref.token == after.ref.token
