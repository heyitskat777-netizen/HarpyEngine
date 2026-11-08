"""Positive FactoryReset brain continuity; actor/account equality grants no lineage."""

import json
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_am_reset as reset
from girlframe.engine import m3_changeling as rules
from girlframe.engine.m2 import GameState
from girlframe.services.m3_changeling_body import brain, prove_original_brain
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def current_subject(
    game: "GameService", c: Connection, state: GameState, expected: rules.BrainRef
) -> rules.BrainRef:
    matches = [x for x in reset.records(state) if x.original == expected.actor]
    if not matches:
        actual = brain(game, c, state, expected.actor, purpose="mental")
        if not rules.same_brain(actual, expected):
            raise WorkflowError("Use the original brain; a shared controller is not continuity")
        return actual
    if len(matches) != 1:
        raise WorkflowError("Recover the unique actual FactoryReset of this original person")
    value = matches[0]
    reset.prove(state, value)
    prove_original_brain(game, c, state, expected)
    row = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == value.source_event,
        )
    ).first()
    born = _history(c, game, value.source_event)
    payload = json.loads(row.payload_json) if row else {}
    if (
        row is None
        or row.kind != "m3.am_factory_reset"
        or row.actor_id != str(value.controller)
        or payload.get("npc") != value.actor.entity
        or payload.get("archive") != value.archive
        or reset.body(born, value.actor) != value
        or value.body.vessel_id != expected.vessel
    ):
        raise WorkflowError("Recover the canonical actual reset body and original brain source")
    actual = brain(game, c, state, value.actor, purpose="mental")
    if actual.id != expected.id or actual.vessel != expected.vessel or actual.kind != "other":
        raise WorkflowError("The proved reset preserves this brain, not a replacement or Girl role")
    # Preserve the established same-NPC claim prover for any subsequent human handover.
    from girlframe.services.m3_changeling import _choice_controller

    initial = actual.model_copy(update={"controller": value.controller})
    controller = _choice_controller(game, c, state, initial)
    return actual.model_copy(update={"controller": controller})


def prove_string_subject(
    game: "GameService",
    c: Connection,
    state: GameState,
    node: rules.String,
    current: rules.BrainRef,
    birth_event: str | None = None,
) -> None:
    """Use birth history once canonical; None validates a genuinely staged new use."""
    scope = _history(c, game, birth_event) if birth_event else state
    actual = current_subject(game, c, scope, node.subject)
    if (
        not rules.same_brain(actual, current)
        or actual.kind != current.kind
        or actual.source != current.source
        or actual.controller != current.controller
    ):
        raise WorkflowError("Prove the original String's actual subject at this use's birth")
