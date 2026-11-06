"""Prove every original acquisition and actual four-Permission retention event."""

from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_class_retention as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.services.m3_privileges import purchase_proof
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def proof(
    game: "GameService", c: Connection, state: GameState, paid: FrameRuleReceipt
) -> tuple[str, tuple[str, ...]]:
    purchase_proof(c, game.store, paid)
    assigned, receipts = rules.binding(state, paid)
    for identity in receipts[1:]:
        swap = next(x for x in state.requisitions if x.id == identity)
        purchase_proof(c, game.store, swap)
        link = next(x for x in rules.links(state) if x.swap == identity)
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == swap.source_event,
            )
        )
        if raw is None or link not in rules.links(GameState.model_validate_json(raw)):
            raise WorkflowError("Recover the actual paid original Class retention event")
    return assigned, receipts
