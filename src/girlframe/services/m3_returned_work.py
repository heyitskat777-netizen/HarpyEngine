"""Authenticate a new obligation for a returned original without reopening old work."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.services.onboarding import OnboardingStore, WorkflowError


def _history(c: Connection, store: OnboardingStore, event: str) -> GameState:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    if raw is None:
        raise WorkflowError("SOURCE_RETURN_MISSING: recover the original return history.")
    return GameState.model_validate_json(raw)


def proof(
    c: Connection,
    store: OnboardingStore,
    state: GameState,
    closed: dict[str, Any],
    owner: int,
    character: str,
) -> dict[str, str] | None:
    """Only a real original ending and latest actual owned return justify reissue."""
    body = json.loads(closed["body_json"])
    if closed["state"] != "resolved" or body.get("resolution") != "original_character_career_ended":
        return None
    sheet = state.sheets.get(str(owner))
    if sheet is None or sheet.character_id != character:
        return None
    archive = next((x for x in state.career_archives if x.id == body.get("career_archive")), None)
    if (
        archive is None
        or archive.actor.entity != str(owner)
        or archive.actor.incarnation != character
        or body.get("original_character") != character
        or closed["event_id"] != archive.source_event
        or archive not in _history(c, store, archive.source_event).career_archives
    ):
        raise WorkflowError("SOURCE_RETURN_MISSING: recover the actual original work ending.")
    latest_archive = next(
        (x for x in reversed(state.career_archives) if x.actor == archive.actor), None
    )
    ticket = next(
        (
            x
            for x in reversed(state.career_returns)
            if x.state == "returned"
            and x.owner == owner
            and latest_archive is not None
            and x.archive == latest_archive.id
        ),
        None,
    )
    if ticket is None or ticket.response_event is None:
        return None
    actual_return = _history(c, store, ticket.response_event)
    returned_sheet = actual_return.sheets.get(str(owner))
    if (
        ticket not in actual_return.career_returns
        or latest_archive not in actual_return.career_archives
        or returned_sheet is None
        or returned_sheet.character_id != character
    ):
        raise WorkflowError("SOURCE_RETURN_MISSING: recover the actual owned return decision.")
    return {
        "closed_work": str(closed["id"]),
        "closed_archive": archive.id,
        "character": character,
        "return_id": ticket.id,
        "return_archive": ticket.archive,
        "return_event": ticket.response_event,
    }
