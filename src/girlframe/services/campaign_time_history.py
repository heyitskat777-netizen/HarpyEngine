"""Read the canonical asynchronous-time records from the private engine ledger."""

import json
from collections.abc import Iterator
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection, RowMapping, Select

from girlframe.database import tables as t
from girlframe.scenes.campaign_time import Anchor, ScenePlan
from girlframe.services.onboarding import WorkflowError

INITIALIZED = "timeline.initialized"
SCHEDULED = "timeline.scene_scheduled"
CUT = "timeline.cut_committed"
LATE_ENTRY = "timeline.late_entry"
LATE_CLOSED = "timeline.late_closed"


def query(campaign: str, *kinds: str) -> Select[Any]:
    return sa.select(t.events).where(
        t.events.c.campaign_id == campaign,
        t.events.c.kind.in_(kinds),
    )


def history(
    c: Connection, campaign: str, *kinds: str
) -> Iterator[tuple[RowMapping, dict[str, Any]]]:
    for row in c.execute(query(campaign, *kinds).order_by(t.events.c.seq)).mappings():
        yield row, json.loads(row["payload_json"])


def anchor(c: Connection, campaign: str) -> tuple[str, Anchor] | None:
    row = (
        c.execute(query(campaign, INITIALIZED, CUT).order_by(t.events.c.seq.desc()).limit(1))
        .mappings()
        .first()
    )
    if row is None:
        return None
    return row["id"], Anchor.model_validate_json(
        json.dumps(json.loads(row["payload_json"])["anchor"])
    )


def booking(c: Connection, campaign: str, scene: str) -> ScenePlan | None:
    row = (
        c.execute(
            query(campaign, SCHEDULED)
            .where(sa.func.json_extract(t.events.c.payload_json, "$.scene") == scene)
            .order_by(t.events.c.seq.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    return ScenePlan.model_validate_json(json.dumps(json.loads(row["payload_json"])["plan"]))


def require_due(c: Connection, campaign: str, scene: str) -> ScenePlan | None:
    current = anchor(c, campaign)
    if current is None:
        return None
    plan = booking(c, campaign, scene)
    if plan is None:
        raise WorkflowError("The Handler must schedule this scene before gameplay.")
    if plan.narrative_only:
        raise WorkflowError("This opening scene is reserved for roleplay.")
    if plan.start.order > current[1].position.order:
        raise WorkflowError("This scene's fictional opening slot has not arrived.")
    if plan.end.order < current[1].position.order:
        raise WorkflowError("This scene's playable span has ended.")
    return plan


def require_reserved(
    c: Connection, campaign: str, scene: str, player: int, incarnation: str | None
) -> None:
    plan = booking(c, campaign, scene)
    if plan is not None and player not in plan.participants:
        raise WorkflowError("The Handler must schedule this Pilot before they can join.")
    if plan is not None and plan.pilot_bindings and plan.pilot_bindings[str(player)] != incarnation:
        raise WorkflowError("Only the Pilot who followed the guide can join this booking.")
