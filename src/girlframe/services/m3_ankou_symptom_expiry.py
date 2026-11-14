"""Expire exact symptom resources through proven moves, never successor accounts."""

import json

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_ankou as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.services.m2_game import GameService
from girlframe.services.m3_asset_loss import snapshots
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError


def holder(
    game: GameService, c: Connection, state: GameState, use: rules.TagUse
) -> ActorRef | None:
    original = rules.get(_history(c, game, use.event), rules.TagUse, use.id)
    if original != use or use.kind != "symptom" or use.ended_event:
        raise WorkflowError("Preserve the original active Processor symptom source")
    current = use.target
    birth_revision = _history(c, game, use.event).revision
    moves = []
    for move in rules.records(state, rules.TagUse):
        if move.kind != "pulse" or move.tag != use.tag:
            continue
        before, after = snapshots(game, c, move.event)
        if after.revision <= birth_revision:
            continue
        if rules.get(after, rules.TagUse, move.id) != move:
            raise WorkflowError("Preserve the actual original symptom movement record")
        moves.append((after.revision, move, before, after))
    for _, move, before, after in sorted(moves, key=lambda row: row[0]):
        action = game.action(c, move.source)
        audit = c.execute(
            sa.select(t.events.c.kind, t.events.c.payload_json).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == move.event
            )
        ).first()
        payload = json.loads(audit.payload_json) if audit else {}
        from girlframe.services.m3_ankou_support import actual_action_actor

        if (
            move.actor != current
            or actual_action_actor(action) != current
            or audit is None
            or audit.kind not in ("m2.rolled", "m3.rolled")
            or payload.get("action_id") != action["id"]
            or payload.get("receipt_id") != action["data"].get("receipt", {}).get("id")
        ):
            raise WorkflowError("Prove the exact symptom holder's actual Amygdala receipt")
        prior = next((x for x in actor_tags(before, current) if x.id == use.tag), None)
        moved = next((x for x in actor_tags(after, move.target) if x.id == use.tag), None)
        from girlframe.engine.m3_ankou_pulse import npc_move

        lossless = (
            npc_move(before, after, move.target, use.tag, move.event)
            if move.target.kind == "npc"
            else moved == prior
        )
        if (
            prior is None
            or not lossless
            or any(x.id == use.tag for x in actor_tags(after, current))
        ):
            raise WorkflowError("Preserve the original Tag through its actual lossless move")
        current = move.target
    if current.kind == "pilot":
        sheet = state.sheets.get(current.entity)
        if sheet is None or sheet.character_id != current.incarnation:
            archive = next((x for x in state.career_archives if x.actor == current), None)
            if (
                archive is None
                or archive not in _history(c, game, archive.source_event).career_archives
            ):
                raise WorkflowError("Recover the actual original symptom holder's career ending")
            # The immutable original archive remains intact. No successor resource is touched.
            return None
    return current
