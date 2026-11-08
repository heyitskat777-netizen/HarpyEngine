"""Actual source-legal participants without Heat do not receive invented resources."""

from uuid import uuid4

import pytest
from test_beneath_service import ready
from test_ledger import ledger as ledger
from test_m2_game import state
from test_world import gorgon, initial

from girlframe.engine.m3_actor_bonds import change, current_ref, depth, set_depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import AdversaryPilot, Asset


@pytest.mark.parametrize("kind", ["gorgon", "external_pilot"])
def test_otherwise_legal_beyond_intense_preserves_real_edge_and_only_actual_heat(ledger, kind):
    game, _, _ = ready(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = initial()
        if kind == "gorgon":
            other = ActorRef(kind="gorgon", entity="actual-bonded-gorgon")
            canon.world = update(
                canon.world,
                gorgons=(*canon.world.gorgons, gorgon("benevolent", other.entity, revealed=True)),
            )
        else:
            other = ActorRef(kind="external_pilot", entity="actual-bonded-rebel")
            canon.world = update(
                canon.world,
                pilots=(
                    *canon.world.pilots,
                    AdversaryPilot(
                        id=other.entity,
                        name="Actual Bonded Rebel",
                        kind="rebel",
                        girl="OLDGEN",
                        frame="JANUS",
                        controller=3,
                        cell=(0, 0),
                        revealed=True,
                        assets=(
                            Asset(
                                id="actual-physical-trait",
                                family="girl",
                                name="Actual trait",
                                description="An existing source capability",
                            ),
                        ),
                    ),
                ),
            )
        actor = current_ref(canon, 2)
        source_event = str(uuid4())
        canon = set_depth(canon, actor, other, 2, source_event)
        game.event(
            c,
            1,
            str(uuid4()),
            "synthetic.actual_intense_source_relationship",
            canon,
            event_id=source_event,
        )
    before = state(game)
    after = change(before, actor, other, 1, str(uuid4()))
    assert depth(after, actor, other) == 2 and after.sheets["2"].heat == before.sheets["2"].heat + 2
    assert after.world == before.world
    assert (
        not hasattr(next(x for x in after.world.gorgons if x.id == other.entity), "heat")
        if kind == "gorgon"
        else not hasattr(next(x for x in after.world.pilots if x.id == other.entity), "heat")
    )


@pytest.mark.parametrize("girl", [False, True])
def test_handler_overflow_uses_only_actual_current_girl_context_heat(ledger, girl):
    from girlframe.engine.m3_handler_consequences import active_handler

    if girl:
        from test_battle_director import source

        game, *_ = source(ledger)
    else:
        game, _, _ = ready(ledger)
    before = state(game)
    actor = current_ref(before, 2)
    handler = active_handler(before)
    assert handler is not None
    before = set_depth(before, actor, handler, 2, str(uuid4()))
    after = change(before, actor, handler, 1, str(uuid4()))
    assert after.sheets["2"].heat == before.sheets["2"].heat + 2
    assert after.handler_heat == before.handler_heat + (2 if girl else 0)
