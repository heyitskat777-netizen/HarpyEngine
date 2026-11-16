"""Read-only original native Play proof and audience-safe immediate outcome adapters."""

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import PLAY_IDS
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError


def native_snapshot(
    c: Connection,
    observer: DirectorObservationService,
    scene_id: str,
    source_id: str,
    source_revision: int,
    action_id: str,
) -> dict[str, Any]:
    observer._scope()
    scene = observer._scene(c, scene_id)
    policy = observer._state(c, scene_id)
    if policy.policy.mode != "shadow" or not observer._consented(c, scene, policy):
        raise WorkflowError("OBSERVATION_DISABLED: current scene consent is required.")
    game = observer.game
    game.unpaused(c)
    source = observer._latest_source(c, source_id)
    inputs = t.director["inputs"]
    if (
        source is None
        or source.kind != "message"
        or source.actor.kind != "pilot"
        or source.source_revision != source_revision
        or not c.scalar(
            sa.select(inputs.c.source_id)
            .where(
                inputs.c.campaign_id == observer.store.campaign_id,
                inputs.c.scene_id == scene_id,
                inputs.c.source_id == source_id,
            )
            .limit(1)
        )
    ):
        raise WorkflowError("STALE_SOURCE: require the original accepted Pilot declaration.")
    action = game.action(c, action_id)
    data = action["data"]
    if (
        action["scene_id"] != scene_id
        or str(action["actor_id"]) != source.author_id
        or data.get("play") not in PLAY_IDS
        or {str(x) for x in data["participants"]} != {str(x) for x in scene["participants"]}
        or data["prepared"]["context"] != source.text
        or any(
            data.get(key)
            for key in (
                "m3",
                "actor_basic",
                "private_audience",
                "gorgon_play",
                "void_keep",
                "handler_play_m3",
                "kicked_puppy",
                "nightmare_core",
                "dampener",
                "princess_child",
                "ankou_feedback_child",
                "bonded_child",
                "red_queen_child",
                "changeling_child",
            )
        )
    ):
        raise WorkflowError("UNSUPPORTED_NATIVE_SOURCE: require the original ordinary native Play.")
    canon = load_state(c, observer.store.campaign_id)
    game.action_characters(c, action, canon)
    game.pilot_cast(c, canon, scene, owners=(int(action["actor_id"]),))
    if source.actor.incarnation != game.character_binding(
        c, canon, int(action["actor_id"]), require_current_profile=False
    ):
        raise WorkflowError("STALE_ACTOR: the original character changed.")
    receipts = t.m2["m2_receipts"]
    receipt = (
        c.execute(
            sa.select(receipts).where(
                receipts.c.campaign_id == observer.store.campaign_id,
                receipts.c.action_id == action_id,
            )
        )
        .mappings()
        .first()
    )
    if not receipt or json.loads(receipt["body_json"]) != data.get("receipt"):
        raise WorkflowError("UNPROVEN_RECEIPT: original native dice are required.")
    lineage = None
    if action["parent_id"] is not None:
        if data["play"] != "disobey_orders":
            raise WorkflowError("UNSUPPORTED_LINEAGE: this child family needs its own proof.")
        parent = game.action(c, action["parent_id"])
        orders = t.m2["m2_orders"]
        order = (
            c.execute(
                sa.select(orders).where(
                    orders.c.campaign_id == observer.store.campaign_id,
                    orders.c.id == data["prepared"].get("order_id"),
                )
            )
            .mappings()
            .first()
        )
        if (
            not order
            or parent["data"].get("play") != "receive_orders"
            or parent["scene_id"] != scene_id
            or parent["actor_id"] != action["actor_id"]
            or parent["data"].get("order_id") != order["id"]
            or order["target_id"] != action["actor_id"]
            or order["channel_id"] != action["channel_id"]
        ):
            raise WorkflowError("UNPROVEN_LINEAGE: retain the actual superior order and child.")
        game.action_characters(c, parent, canon)
        lineage = {
            "parent_id": parent["id"],
            "order_id": order["id"],
            "parent_state": parent["state"],
        }
    elif data["play"] == "disobey_orders":
        raise WorkflowError("UNPROVEN_LINEAGE: Disobey must retain its Receive Orders parent.")
    children = t.m2["m2_actions"]
    if c.scalar(
        sa.select(children.c.id)
        .where(
            children.c.campaign_id == observer.store.campaign_id, children.c.parent_id == action_id
        )
        .limit(1)
    ):
        raise WorkflowError("UNSUPPORTED_LINEAGE: nested child consumers remain explicit.")
    pending = game.pending(c, action_id)
    # Every exposed result must come from original committed native state history.
    event_id = data.get("response_event")
    if event_id:
        event = c.scalar(
            sa.select(t.events.c.payload_json).where(
                t.events.c.campaign_id == observer.store.campaign_id,
                t.events.c.id == event_id,
                t.events.c.kind == "m2.choice_resolved",
            )
        )
        history = c.scalar(
            sa.select(t.m2["m2_state_history"].c.event_id).where(
                t.m2["m2_state_history"].c.campaign_id == observer.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == event_id,
            )
        )
        if not event or not history or json.loads(event).get("action_id") != action_id:
            raise WorkflowError("UNPROVEN_OUTCOME: native choice/history provenance is required.")
    if action["state"] == "complete" and (pending or not event_id):
        raise WorkflowError("UNPROVEN_OUTCOME: completion still has an outstanding native choice.")
    stage = "complete" if action["state"] == "complete" else "pending_choices"
    if (
        data["play"] == "keep_your_head"
        and len(pending) == 1
        and pending[0]["kind"] == "handler_keep"
    ):
        if "positive" not in data["result"] or "negative" not in data["result"]:
            raise WorkflowError("UNPROVEN_TRAITS: retain actual committed actor choices.")
        observer_game_handler = canon.handler
        if str(pending[0]["actor_id"]) != str(observer_game_handler):
            raise WorkflowError("STALE_HANDLER: preserve original Handler ownership.")
        stage = "awaiting_keep_ruling"
    followups = [
        {"id": x.id, "kind": x.kind, "owner": str(x.owner), "state": x.state}
        for x in canon.obligations
        if x.action == action_id and x.state == "pending"
    ]
    # Scene work can outlive the immediate Play; use the latest append-only revision.
    work = t.m3["m3_required_work"]
    latest = {
        row["id"]: row
        for row in c.execute(
            sa.select(work)
            .where(
                work.c.campaign_id == observer.store.campaign_id,
                work.c.scene_id == scene_id,
            )
            .order_by(work.c.revision)
        ).mappings()
    }
    followups.extend(
        {"id": row["id"], "kind": row["kind"], "owner": row["owner_id"], "state": row["state"]}
        for row in latest.values()
        if row["state"] != "resolved"
    )
    if lineage and lineage["parent_state"] != "complete":
        followups.append(
            {
                "id": lineage["parent_id"],
                "kind": "native_parent",
                "owner": str(action["actor_id"]),
                "state": lineage["parent_state"],
            }
        )
    return {
        "scene": scene,
        "source": source,
        "action": action,
        "receipt": dict(receipt),
        "pending": pending,
        "stage": stage,
        "followups": followups,
        "lineage": lineage,
        "canonical": canon,
    }
