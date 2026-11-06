"""Authenticate the real backstory Strain source before its special Handler consequence."""

import json
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_rebel_backstory as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def prove(
    game: "GameService", c: Connection, state: GameState, handler: ActorRef, tag: str
) -> None:
    value = rules.eligible(state, handler, tag)
    if value is None:
        raise WorkflowError("Only the actual Strain-granted backstory Tag has this alternative")
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == value.source_event,
            )
        )
        .mappings()
        .first()
    )
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == value.source_event,
        )
    )
    source = GameState.model_validate_json(raw) if raw else None
    original = (
        next((x for x in rules.sources(source) if x.id == value.id), None) if source else None
    )
    if (
        row is None
        or row["kind"] != "m3.strain_effect_applied"
        or original != value
        or row["actor_id"] != value.handler.entity
        or json.loads(row["payload_json"]).get("rule_id") != rules.RULE
        or json.loads(row["payload_json"]).get("work_id") != value.source_work
    ):
        raise WorkflowError("Recover the actual original Handler backstory source")
