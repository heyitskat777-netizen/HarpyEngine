"""Original humans can recover actual AM memory effects without publishing them."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_am_code as code
from girlframe.engine import m3_am_memory as rules
from girlframe.engine.m2 import GameState
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Erasure:
    from girlframe.services.m3_am_scrutinized import _history

    value = next((x for x in rules.losses(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual original memory-erasure source")
    maintenance = code.session(state, value.maintenance)
    original = next(
        (x for x in rules.losses(_history(game, c, value.event)) if x.id == identity), None
    )
    choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    row = c.execute(
        sa.select(responses.c.answer_json)
        .join(
            choices,
            sa.and_(
                choices.c.campaign_id == responses.c.campaign_id,
                choices.c.id == responses.c.choice_id,
            ),
        )
        .where(
            responses.c.campaign_id == game.store.campaign_id,
            responses.c.event_id == value.event,
            responses.c.actor_id == str(maintenance.controller),
            choices.c.kind == "am_code_edit",
            choices.c.action_id == value.action,
        )
    ).first()
    fields = json.loads(row.answer_json).get("fields", {}) if row else {}
    if (
        original != value
        or maintenance.memory_erasure != value.id
        or maintenance.actor != value.actor
        or maintenance.operator != value.operator
        or maintenance.action != value.action
        or maintenance.effect_event != value.event
        or fields.get("memory_scope") != value.scope
        or rules.selected_memories(fields.get("memories", "")) != value.memories
    ):
        raise WorkflowError("Recover the actual operator's immutable rolled memory erasure")
    return value


class MemoryService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        from girlframe.services.m3_am_code import access, source

        with self.store.engine.connect() as c:
            access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            value = next((x for x in rules.losses(state) if x.id == identity), None)
            if value is None:
                raise WorkflowError("Recover your original private memory effect")
            maintenance = code.session(state, value.maintenance)
            if viewer.user_id not in (maintenance.owner, maintenance.controller):
                raise WorkflowError("These private memory effects belong to their original humans")
            value = prove(self.game, c, state, identity)
            maintenance = source(self.game, c, state, value.maintenance)
            return dict(
                id=value.id,
                maintenance=maintenance.id,
                actor=state.sheets[value.actor.entity].callsign,
                scope=value.scope,
                memories=value.memories,
                through_revision=value.through_revision,
                event=value.event,
            )
