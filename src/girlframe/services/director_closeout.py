"""Commit an authorized Handler report at the native scene close boundary."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.director import KnowledgeReference
from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import OnboardingStore, WorkflowError


def file_report(
    store: OnboardingStore,
    c: Connection,
    scene: dict[str, Any],
    close_event: str,
    reports: tuple[str, ...],
) -> int:
    """Snapshot established references and selected public reports in the close transaction."""
    observer = DirectorObservationService(store, synthetic=True)
    context = DirectorContextService(observer)
    identity = scene["id"]
    policy = observer._state(c, identity)
    if policy.policy.mode != "shadow" or not observer._consented(c, scene, policy):
        raise WorkflowError("OBSERVATION_DISABLED: retain consent for the scene closeout.")

    handler = active_handler(load_state(c, store.campaign_id))
    if handler is None and reports:
        raise WorkflowError(
            "HANDLER_UNAVAILABLE: select the actual Handler before filing a report."
        )
    if handler is None:
        return 0

    refs = context._current(c, identity)
    selected = set(reports)
    if len(selected) != len(reports) or not selected <= {x.id for x in refs}:
        raise WorkflowError("SCENE_REPORT_SOURCE: select distinct current scene references.")
    table = t.director_context["shadow"]
    exported = []
    for ref in refs:
        if ref.origin_scene is not None:
            if ref.id in selected:
                raise WorkflowError("SCENE_REPORT_SOURCE: file a report from its original scene.")
            continue
        if handler.token not in ref.known_by:
            if ref.id not in selected:
                continue
            source_id = ref.source_id
            if source_id.startswith("knowledge-acquired:"):
                raw = c.scalar(
                    sa.select(table.c.body_json).where(
                        table.c.campaign_id == store.campaign_id,
                        table.c.scene_id == identity,
                        table.c.id == source_id,
                    )
                )
                source_id = json.loads(raw)["source"]["id"] if raw else ""
            source = observer._latest_source(c, source_id)
            if (
                ref.classification != "reported_claim"
                or source is None
                or source.kind != "message"
                or source.fictional_channel != "comms"
                or source.actor.kind != "pilot"
                or source.actor.token not in ref.known_by
                or source.audience_ids != tuple(sorted(str(x) for x in scene["participants"]))
            ):
                raise WorkflowError("SCENE_REPORT_SCOPE: select an accepted public pilot report.")
        exported.append(
            ref.model_dump(mode="json") | {"origin_scene": identity, "origin_reference": ref.id}
        )

    c.execute(
        table.insert().values(
            campaign_id=store.campaign_id,
            scene_id=identity,
            id="handler-closeout:" + close_event,
            body_json=json.dumps(
                {
                    "handler": handler.model_dump(mode="json"),
                    "close_event": close_event,
                    "people": scene["participants"],
                    "consent": policy.consent_generation,
                    "references": exported,
                },
                sort_keys=True,
            ),
        )
    )
    return len(exported)


def handler_reports(
    context: DirectorContextService,
    c: Connection,
    actor: ActorRef,
) -> tuple[KnowledgeReference, ...]:
    """Read sealed reports for the original Handler while source consent remains current."""
    store, observer = context.store, context.observations
    table = t.director_context["shadow"]
    rows = c.execute(
        sa.select(table.c.scene_id, table.c.body_json)
        .join(
            t.events,
            sa.and_(
                t.events.c.campaign_id == table.c.campaign_id,
                t.events.c.id == sa.func.json_extract(table.c.body_json, "$.close_event"),
            ),
        )
        .where(
            table.c.campaign_id == store.campaign_id,
            table.c.id.like("handler-closeout:%"),
            t.events.c.kind == "m2.scene_closed",
            sa.func.json_extract(table.c.body_json, "$.handler.entity") == actor.entity,
            sa.func.json_extract(table.c.body_json, "$.handler.kind") == actor.kind,
        )
        .order_by(t.events.c.seq)
    )
    result: list[KnowledgeReference] = []
    for row in rows:
        saved = json.loads(row.body_json)
        if saved["handler"] != actor.model_dump(mode="json"):
            continue
        policy = observer._state(c, row.scene_id)
        if (
            policy.policy.mode != "shadow"
            or policy.consent_generation != saved["consent"]
            or not observer._consented(c, {"participants": saved["people"]}, policy)
        ):
            continue
        retired = context._archived(c, row.scene_id)
        result.extend(
            KnowledgeReference.model_validate_json(json.dumps(x))
            for x in saved["references"]
            if x["id"] not in retired
        )
    return context._actor_references(
        tuple(x.model_copy(update={"known_by": (actor.token,)}) for x in result[-100:]), actor
    )


def report_participant(store: OnboardingStore, c: Connection, scene: str, user: int) -> bool:
    """Allow original participants to revoke report use after a channel is rebound."""
    table = t.director_context["shadow"]
    raw = c.scalar(
        sa.select(table.c.body_json)
        .join(
            t.events,
            sa.and_(
                t.events.c.campaign_id == table.c.campaign_id,
                t.events.c.id == sa.func.json_extract(table.c.body_json, "$.close_event"),
            ),
        )
        .where(
            table.c.campaign_id == store.campaign_id,
            table.c.scene_id == scene,
            table.c.id.like("handler-closeout:%"),
            t.events.c.kind == "m2.scene_closed",
        )
    )
    return raw is not None and user in json.loads(raw)["people"]
