"""Shared floor decisions over existing Activity inputs and NPC address receipts."""

import json

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.observation import Observation, SceneTurn
from girlframe.database import tables as t

NPC_ADDRESSED = "activity.npc_addressed"


def current_turn(c: Connection, campaign: str, scene: str, turn: SceneTurn) -> Observation | None:
    table = t.director["inputs"]
    raw = c.scalar(
        sa.select(table.c.body_json)
        .where(
            table.c.campaign_id == campaign,
            table.c.scene_id == scene,
            table.c.source_id == turn.source_id,
        )
        .order_by(table.c.source_revision.desc())
        .limit(1)
    )
    if raw is None:
        return None
    source = Observation.model_validate_json(raw)
    return source if source.source_revision == turn.revision else None


def npc_owned(c: Connection, campaign: str, scene: str, source_ids: tuple[str, ...]) -> set[str]:
    source = sa.func.json_extract(t.events.c.payload_json, "$.source_turn.source_id")
    return set(
        c.scalars(
            sa.select(source).where(
                t.events.c.campaign_id == campaign,
                t.events.c.kind == NPC_ADDRESSED,
                sa.func.json_extract(t.events.c.payload_json, "$.window.scene_id") == scene,
                source.in_(source_ids),
            )
        )
    )


def has_delivered_reply(c: Connection, campaign: str, scene: str, source_id: str) -> bool:
    table = t.director_context["shadow"]
    handler_drafts = table.alias()
    rows = c.scalars(
        sa.select(handler_drafts.c.body_json)
        .join_from(
            table,
            handler_drafts,
            sa.and_(
                handler_drafts.c.campaign_id == table.c.campaign_id,
                handler_drafts.c.scene_id == table.c.scene_id,
                table.c.id == "handler-delivery:" + handler_drafts.c.id,
            ),
        )
        .where(table.c.campaign_id == campaign, table.c.scene_id == scene)
    )
    for raw in rows:
        draft = json.loads(raw)
        if draft.get("source_id") == source_id or any(
            report["source_id"] == source_id for report in draft.get("batch_reports", ())
        ):
            return True
    return bool(
        c.scalar(
            sa.select(table.c.id)
            .where(
                table.c.campaign_id == campaign,
                table.c.scene_id == scene,
                table.c.id.like("npc-delivery:%"),
                sa.func.json_extract(table.c.body_json, "$.source") == source_id,
            )
            .limit(1)
        )
    )


def floor_claims(
    c: Connection,
    campaign: str,
    scene: str,
    inputs: tuple[Observation, ...],
    cast: dict[str, int],
) -> tuple[set[str], set[str]]:
    """A named peer reply covers its exact original turn, with both still audible."""
    claimed_npc = npc_owned(c, campaign, scene, tuple(item.source_id for item in inputs))
    covered: set[str] = set()
    input_ids = {item.source_id for item in inputs}
    table = t.director["inputs"]
    newer = table.alias()
    linked = c.scalars(
        sa.select(table.c.body_json).where(
            table.c.campaign_id == campaign,
            table.c.scene_id == scene,
            sa.func.json_extract(table.c.body_json, "$.covers_turn.source_id").in_(input_ids),
            ~sa.exists(
                sa.select(newer.c.source_id).where(
                    newer.c.campaign_id == campaign,
                    newer.c.scene_id == scene,
                    newer.c.source_id == table.c.source_id,
                    newer.c.source_revision > table.c.source_revision,
                )
            ),
        )
    )
    answers = {item.source_id: item for item in inputs if item.covers_turn is not None}
    for body in linked:
        item = Observation.model_validate_json(body)
        answers[item.source_id] = item
    for answer in answers.values():
        turn = answer.covers_turn
        if turn is None or answer.source_id in claimed_npc or answer.cast_controllers != cast:
            continue
        if answer.gm_addressed or answer.fictional_channel != "comms":
            continue
        source = current_turn(c, campaign, scene, turn)
        if (
            source is not None
            and source.cast_controllers == cast
            and source.sequence < answer.sequence
        ):
            covered.update((source.source_id, answer.source_id))
    return claimed_npc, covered
