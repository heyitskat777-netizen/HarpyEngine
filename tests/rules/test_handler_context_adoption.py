"""Actual first naming preserves the same source-proved physical Director-context body."""

import json

import sqlalchemy as sa
from test_handler_creation import agree, complete, ready, save
from test_ledger import ADMIN
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.database import tables as t
from girlframe.engine.m2 import DirectorContext
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body


def test_initial_naming_adopts_ended_context_only_with_actual_immutable_original_body_source(
    ledger,
):
    service, game = ready(ledger)
    old = ActorRef(kind="handler", entity="1")
    context = DirectorContext(
        id="actual-ended-context",
        handler=1,
        directors=("actual-director",),
        source_works=("actual-presence",),
        identities=[],
        source_event="actual-context-body-proof",
        body_actor=old,
    )
    with ledger.transaction() as c:
        canon = state(game)
        canon.director_contexts.append(context)
        game.event(
            c, 1, "context-body-proof", "synthetic.context", canon, event_id=context.source_event
        )
        canon.director_contexts[0] = context.model_copy(
            update={
                "active": False,
                "termination_event": "actual-director-death",
                "termination_reason": "director_death",
            }
        )
        game.event(
            c,
            1,
            "actual-director-ending",
            "synthetic.director_death",
            canon,
            event_id="actual-director-death",
        )
    save(service, complete(service))
    agree(service)
    view = service.view(ADMIN)
    service.activate(ADMIN, "actual-first-body-name", view["revision"], view["game_revision"], True)
    canon = state(game)
    current = active_handler(canon)
    assert current != old and canon.director_contexts[0].body_actor == current
    alias = ActorRef(kind="handler", entity="1", incarnation=context.id)
    assert same_handler_body(canon, alias)
    with ledger.engine.connect() as c:
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.event_id == context.source_event,
            )
        )
    assert json.loads(raw)["director_contexts"][0]["body_actor"] == old.model_dump(mode="json")
