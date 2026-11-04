"""Append context-bound required work from trusted source events, never UI claims."""

import json
from typing import Any

from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.services.onboarding import OnboardingStore, WorkflowError


def related(
    c: Connection,
    store: OnboardingStore,
    parent: dict[str, Any],
    identity: str,
    owner: int,
    subject: int,
    kind: str,
    body: dict[str, Any],
    event: str,
) -> None:
    mission, period = parent.get("mission_id"), parent.get("off_duty_id")
    if parent.get("campaign_id") != store.campaign_id or (mission is None) == (period is None):
        raise WorkflowError("Required work needs exactly one matching campaign context.")
    c.execute(
        t.m3["m3_required_work"]
        .insert()
        .values(
            campaign_id=store.campaign_id,
            id=identity,
            revision=1,
            mission_id=mission,
            off_duty_id=period,
            owner_id=str(owner),
            subject_id=str(subject),
            kind=kind,
            state="pending",
            body_json=json.dumps(body, sort_keys=True),
            event_id=event,
        )
    )
