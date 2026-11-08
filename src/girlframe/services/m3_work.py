"""Append context-bound required work from trusted source events, never UI claims."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m3_work_scope import WorkScope
from girlframe.services.onboarding import OnboardingStore, WorkflowError


def bind_scene_context(
    c: Connection, store: OnboardingStore, identity: str, channel: int, event: str
) -> None:
    source = (
        c.execute(
            sa.select(t.events.c.kind, t.events.c.payload_json).where(
                t.events.c.campaign_id == store.campaign_id,
                t.events.c.id == event,
            )
        )
        .mappings()
        .first()
    )
    scene = t.m2["m2_scenes"]
    actual = c.scalar(
        sa.select(scene.c.id).where(
            scene.c.campaign_id == store.campaign_id,
            scene.c.channel_id == str(channel),
        )
    )
    payload = json.loads(source["payload_json"]) if source else {}
    if (
        source is None
        or source["kind"] != "m2.scene_bound"
        or actual != identity
        or payload.get("scene_id") != identity
        or str(payload.get("channel")) != str(channel)
    ):
        raise WorkflowError("A scene context needs its actual same-campaign bind source.")
    contexts = t.m3["m3_scene_contexts"]
    existing = (
        c.execute(
            sa.select(contexts).where(
                contexts.c.campaign_id == store.campaign_id,
                contexts.c.id == identity,
            )
        )
        .mappings()
        .first()
    )
    if existing:
        if existing["binding_event"] != event or existing["channel_id"] != str(channel):
            raise WorkflowError("The actual original scene context cannot be reassigned.")
        return
    c.execute(
        contexts.insert().values(
            campaign_id=store.campaign_id, id=identity, channel_id=str(channel), binding_event=event
        )
    )


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
    try:
        scope = WorkScope(
            mission_id=parent.get("mission_id"),
            off_duty_id=parent.get("off_duty_id"),
            scene_id=parent.get("scene_id"),
            campaign_context=parent.get("campaign_context", False),
        )
    except ValueError:
        raise WorkflowError("Required work needs exactly one matching campaign context.") from None
    if parent.get("campaign_id") != store.campaign_id:
        raise WorkflowError("Required work needs exactly one matching campaign context.")
    if not c.scalar(
        sa.select(t.events.c.id).where(
            t.events.c.campaign_id == store.campaign_id,
            t.events.c.id == event,
        )
    ):
        raise WorkflowError("Required work needs its actual matching campaign source event.")
    if scope.kind != "campaign":
        name, context_id = {
            "mission": ("m3_missions", scope.mission_id),
            "off_duty": ("m3_off_duty", scope.off_duty_id),
            "scene": ("m3_scene_contexts", scope.scene_id),
        }[scope.kind]
        context = t.m3[name]
        if not c.scalar(
            sa.select(context.c.id).where(
                context.c.campaign_id == store.campaign_id,
                context.c.id == context_id,
            )
        ):
            raise WorkflowError("Required work needs an actual matching parent context.")
    c.execute(
        t.m3["m3_required_work"]
        .insert()
        .values(
            campaign_id=store.campaign_id,
            id=identity,
            revision=1,
            **scope.model_dump(),
            owner_id=str(owner),
            subject_id=str(subject),
            kind=kind,
            state="pending",
            body_json=json.dumps(body, sort_keys=True),
            event_id=event,
        )
    )
