"""Private canon event indexes and append-only dependency status."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection, Select

from girlframe.database import tables as t
from girlframe.scenes.canon import FactStatus
from girlframe.services import campaign_time_history as calendar

FACT = "canon.world_fact"
GRANT = "canon.knowledge_granted"
PROPOSAL = "canon.proposed"
REVIEW = "canon.reviewed"
DRAFT = "canon.briefing_drafted"


def grants(campaign: str, recipient: int) -> Select[Any]:
    return calendar.query(campaign, GRANT).where(
        sa.func.json_extract(t.events.c.payload_json, "$.recipient") == recipient
    )


def statuses(c: Connection, campaign: str) -> dict[str, FactStatus]:
    events = t.events
    rows = c.execute(
        calendar.query(campaign, FACT)
        .with_only_columns(
            events.c.id,
            sa.func.json_extract(events.c.payload_json, "$.supersedes"),
            sa.func.json_extract(events.c.payload_json, "$.depends_on"),
        )
        .order_by(events.c.seq)
    ).all()
    superseded = {old for _, old, _ in rows if old is not None}
    result: dict[str, FactStatus] = {}
    for identity, _, requires in rows:
        if identity in superseded:
            result[identity] = "superseded"
        elif any(result.get(ref) != "current" for ref in json.loads(requires or "[]")):
            result[identity] = "needs_review"
        else:
            result[identity] = "current"
    return result


def fact_status(c: Connection, campaign: str, fact_id: str) -> FactStatus | None:
    return statuses(c, campaign).get(fact_id)
