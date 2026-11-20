"""The latest mission clock snapshot from the existing private ledger."""

import json

from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.scenes.mission_timing import Clock
from girlframe.services.campaign_time_history import query
from girlframe.services.onboarding import WorkflowError

EVENT = "timeline.mission_clock"


def current(c: Connection, campaign: str) -> tuple[str, Clock] | None:
    row = (
        c.execute(query(campaign, EVENT).order_by(t.events.c.seq.desc()).limit(1))
        .mappings()
        .first()
    )
    if row is None:
        return None
    body = json.loads(row["payload_json"])
    return row["id"], Clock.model_validate_json(json.dumps(body["clock"]))


def active(c: Connection, campaign: str) -> Clock | None:
    value = current(c, campaign)
    return value[1] if value is not None and not value[1].closed else None


def require_closed(
    c: Connection, campaign: str, *, mission: str | None = None, scene: str | None = None
) -> None:
    clock = active(c, campaign)
    if clock is not None and (clock.mission == mission or clock.scene == scene):
        raise WorkflowError("Finish the active timed sequence before closing its mission or scene.")
