"""Commit an authorized Handler report at the native scene close boundary."""

import json
from collections.abc import Iterator
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.director import KnowledgeReference
from girlframe.ai.director_dossiers import HandlerExperience, HandlerExperienceSelection
from girlframe.ai.observation import Observation
from girlframe.database import tables as t
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.activity_fiction import ActivityFiction
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import OnboardingStore, WorkflowError


def _offers(
    context: DirectorContextService, c: Connection, scene: str, handler: ActorRef
) -> list[dict[str, Any]]:
    return [
        row
        for row in ActivityFiction(context)._delivered(c, scene, handler)
        if row.get("fiction", {}).get("offers_help") and len(row["recipients"]) == 1
    ]


def _public_pilot_source(
    observer: DirectorObservationService,
    c: Connection,
    scene: dict[str, Any],
    ref: KnowledgeReference,
) -> Observation | None:
    if ref.classification != "reported_claim" or ref.origin_scene is not None:
        return None
    source_id = ref.source_id
    if source_id.startswith("knowledge-acquired:"):
        table = t.director_context["shadow"]
        raw = c.scalar(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == observer.store.campaign_id,
                table.c.scene_id == scene["id"],
                table.c.id == source_id,
            )
        )
        source_id = json.loads(raw)["source"]["id"] if raw else ""
    source = observer._latest_source(c, source_id)
    inputs = t.director["inputs"]
    if (
        source is None
        or source.kind != "message"
        or source.fictional_channel != "comms"
        or source.actor.kind != "pilot"
        or source.actor.token not in ref.known_by
        or source.audience_ids != tuple(sorted(str(x) for x in scene["participants"]))
        or not c.scalar(
            sa.select(inputs.c.source_id).where(
                inputs.c.campaign_id == observer.store.campaign_id,
                inputs.c.scene_id == scene["id"],
                inputs.c.source_id == source_id,
                inputs.c.source_revision == source.source_revision,
            )
        )
    ):
        return None
    return source


def file_report(
    store: OnboardingStore,
    c: Connection,
    scene: dict[str, Any],
    close_event: str,
    reports: tuple[str, ...],
    experience: HandlerExperienceSelection | None = None,
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
    if experience is not None and experience.reference_id not in selected:
        raise WorkflowError(
            "HANDLER_EXPERIENCE_SOURCE: select a report approved for this closeout."
        )
    table = t.director_context["shadow"]
    exported = []
    memory = None
    for ref in refs:
        if ref.origin_scene is not None:
            if ref.id in selected:
                raise WorkflowError("SCENE_REPORT_SOURCE: file a report from its original scene.")
            continue
        known = handler.token in ref.known_by
        if not known and ref.id not in selected:
            continue
        chosen = experience is not None and ref.id == experience.reference_id
        if chosen or not known:
            source = _public_pilot_source(observer, c, scene, ref)
            if source is None:
                raise WorkflowError("SCENE_REPORT_SCOPE: select an accepted public pilot report.")
            if chosen and experience is not None:
                memory = experience.model_dump(mode="json") | {
                    "pilot": source.actor.model_dump(mode="json")
                }
                if experience.offer_reference or experience.kind == "accepted_help":
                    offer = next(
                        (
                            entry
                            for entry in _offers(context, c, identity, handler)
                            if entry["reference"] == experience.offer_reference
                            and entry["after_sequence"] < source.sequence
                            and entry["recipients"] == [memory["pilot"]]
                        ),
                        None,
                    )
                    if offer is None or experience.kind not in ("accepted_help", "declined_help"):
                        raise WorkflowError(
                            "HANDLER_COMMITMENT_OFFER: select the Pilot's reply to a heard offer."
                        )
                    memory["offer_text"] = offer.get("dialogue", offer["text"])
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
                    **({"experience": memory} if memory else {}),
                },
                sort_keys=True,
            ),
        )
    )
    return len(exported)


def closeout_options(
    context: DirectorContextService,
    c: Connection,
    scene: dict[str, Any],
) -> list[dict[str, str]]:
    observer = context.observations
    handler = active_handler(load_state(c, context.store.campaign_id))
    if handler is None:
        return []
    return [
        {"id": ref.id, "text": ref.text}
        for ref in context._current(c, scene["id"])
        if _public_pilot_source(observer, c, scene, ref) is not None
    ]


def commitment_offers(
    context: DirectorContextService, c: Connection, scene: dict[str, Any]
) -> list[dict[str, Any]]:
    handler = active_handler(load_state(c, context.store.campaign_id))
    if handler is None:
        return []
    return [
        {"reference": row["reference"], "text": row.get("dialogue", row["text"])}
        for row in _offers(context, c, scene["id"], handler)
    ]


def _authorized_reports(
    context: DirectorContextService,
    c: Connection,
    actor: ActorRef,
) -> Iterator[tuple[str, dict[str, Any], set[str]]]:
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
        yield row.scene_id, saved, context._archived(c, row.scene_id)


def authorized_closed_scenes(
    context: DirectorContextService, c: Connection, actor: ActorRef
) -> set[str]:
    return {scene for scene, _, _ in _authorized_reports(context, c, actor)}


def handler_reports(
    context: DirectorContextService,
    c: Connection,
    actor: ActorRef,
    *,
    scene: str | None = None,
) -> tuple[KnowledgeReference, ...]:
    result = [
        KnowledgeReference.model_validate_json(json.dumps(ref))
        for _, saved, retired in _authorized_reports(context, c, actor)
        for ref in saved["references"]
        if ref["id"] not in retired
    ]
    if scene is not None:
        from girlframe.services.director_canon import handler_canon

        result.extend(handler_canon(context, c, scene, actor, int(actor.entity), closed_only=True))
    return context._actor_references(
        tuple(x.model_copy(update={"known_by": (actor.token,)}) for x in result[-100:]), actor
    )


def handler_experiences(
    context: DirectorContextService,
    c: Connection,
    handler: ActorRef,
    pilots: tuple[ActorRef, ...],
    *,
    limit: int | None = 3,
) -> tuple[HandlerExperience, ...]:
    if not pilots:
        return ()
    result = []
    for _, saved, retired in _authorized_reports(context, c, handler):
        memory = saved.get("experience")
        if (
            not memory
            or memory["reference_id"] in retired
            or memory.get("offer_reference") in retired
            or ActorRef.model_validate(memory["pilot"]) not in pilots
        ):
            continue
        ref = next(
            (ref for ref in saved["references"] if ref["id"] == memory["reference_id"]), None
        )
        if ref is not None:
            result.append(
                HandlerExperience.model_validate_json(
                    json.dumps(
                        memory
                        | {
                            "scene": ref["origin_scene"],
                            "close_event": saved["close_event"],
                            "reported_text": ref["text"],
                        }
                    )
                )
            )
    # Keep recent experiences in order so a later report can supersede an earlier preference.
    return tuple(result[-limit:] if limit is not None else result)


def closed_scene_audience(store: OnboardingStore, c: Connection, scene: str) -> tuple[int, ...]:
    """Recover the audience from an approved native closeout even after a channel rebind."""
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
    return tuple(json.loads(raw)["people"]) if raw is not None else ()


def report_participant(store: OnboardingStore, c: Connection, scene: str, user: int) -> bool:
    """Allow original participants to revoke report use after a channel is rebound."""
    return user in closed_scene_audience(store, c, scene)
