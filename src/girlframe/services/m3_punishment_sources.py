"""Prove an immediate consequence against its actual saved Punishment."""

import json
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_janus_storage import effective_assets
from girlframe.services.m3_asset_loss import snapshots
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService
    from girlframe.services.m3_punishments import PunishmentService


def prove(
    game: "GameService",
    c: Connection,
    work_id: str,
    event: str,
    actor: ActorRef,
    kinds: Sequence[str],
) -> tuple[dict[str, Any], GameState, GameState]:
    audit = (
        c.execute(
            sa.select(t.events.c.kind, t.events.c.payload_json).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    work = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(work).where(
                work.c.campaign_id == game.store.campaign_id,
                work.c.id == work_id,
                work.c.event_id == event,
                work.c.kind == "punishment",
                work.c.state == "resolved",
                work.c.subject_id == actor.entity,
            )
        )
        .mappings()
        .first()
    )
    metadata = json.loads(audit["payload_json"]) if audit else {}
    details = json.loads(row["body_json"]) if row else {}
    kind = metadata.get("punishment")
    if (
        audit is None
        or audit["kind"] != "m3.punishment_applied"
        or row is None
        or metadata.get("work_id") != work_id
        or kind not in kinds
        or details.get("applied_event") != event
        or details.get("character") != actor.incarnation
        or details.get("punishment", {}).get("kind") != kind
    ):
        raise WorkflowError("Recover the original applied Punishment for this consequence.")
    before, after = snapshots(game, c, event)
    for state in (before, after):
        sheet = state.sheets.get(actor.entity)
        if sheet is None or sheet.character_id != actor.incarnation:
            raise WorkflowError("Preserve the actually punished character.")
    return dict(row), before, after


def void_families(before: GameState, after: GameState, actor: ActorRef) -> list[str]:
    result = []
    for family in ("girl", "frame"):
        old = [asset for asset in effective_assets(before, actor) if asset.family == family]
        new = [asset for asset in effective_assets(after, actor) if asset.family == family]
        if (
            old
            and any(not asset.void for asset in old)
            and new
            and all(asset.void for asset in new)
        ):
            result.append(family)
    return result


LEGACY = {
    "punishment_ankou_feedback": ("sedation",),
    "punishment_void_threshold_check": (
        "frame_disassembly",
        "compliance_surgery",
        "link_surgery_reversal",
    ),
}


def recover(
    service: "PunishmentService",
    viewer: GuildViewer,
    key: str,
    identity: str,
    revision: int,
    game_revision: int,
) -> dict[str, Any]:
    """Replace one owned legacy marker with its original canonical consequences."""
    game = service.game

    def operation(c: Connection) -> dict[str, Any]:
        from girlframe.engine import m3_ankou
        from girlframe.services.m2_state import load_state
        from girlframe.services.m3_ankou_feedback_sequences import materialize
        from girlframe.services.m3_work import related

        row = service._row(c, identity)
        kinds = LEGACY.get(row["kind"])
        if kinds is None:
            raise WorkflowError("Choose an older Punishment marker.")
        service._check(c, row, revision, game_revision)
        body = service._body(row)
        source = body.get("source_work")
        table = t.m3["m3_required_work"]
        marker_event = c.scalar(
            sa.select(table.c.event_id).where(
                table.c.campaign_id == service.store.campaign_id,
                table.c.id == identity,
                table.c.revision == 1,
            )
        )
        if not isinstance(source, str) or not isinstance(marker_event, str):
            raise WorkflowError("Recover the actual original Punishment and marker event.")
        parent = c.execute(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == service.store.campaign_id,
                table.c.id == source,
                table.c.event_id == marker_event,
                table.c.state == "resolved",
                table.c.kind == "punishment",
            )
        ).scalar_one_or_none()
        original = json.loads(parent or "{}").get("character")
        if (
            not original
            or row["owner_id"] != row["subject_id"]
            or body.get("owner") != viewer.user_id
        ):
            raise WorkflowError("The original Punishment and owner must be proved before recovery.")
        actor = ActorRef(kind="pilot", entity=row["subject_id"], incarnation=original)
        parent_row, before, after = prove(game, c, source, marker_event, actor, kinds)
        if any(
            row[k] != parent_row[k]
            for k in ("scene_id", "mission_id", "off_duty_id", "campaign_context")
        ):
            raise WorkflowError("The saved marker does not match its original Punishment scope.")
        state = load_state(c, service.store.campaign_id)
        if (
            game.character_binding(c, state, viewer.user_id, require_current_profile=False)
            != original
        ):
            raise WorkflowError("This follow-up belongs to the original pilot career.")
        event = str(uuid4())
        recovered = []
        if row["kind"] == "punishment_ankou_feedback":
            old, new = before.sheets[actor.entity], after.sheets[actor.entity]
            if (
                new.frame != "PROJECT ANKOU"
                or all(x.marked for x in old.identities)
                or not new.identities
                or not all(x.marked for x in new.identities)
            ):
                raise WorkflowError("The original Sedation did not mark the last Ankou Identity.")
            saved = next(
                (
                    x
                    for x in m3_ankou.records(state, m3_ankou.FeedbackSequence)
                    if x.source == source
                    and (x.punishment_event or x.event) == marker_event
                    and x.reason == "punishment"
                ),
                None,
            )
            if saved is None:
                saved = m3_ankou.FeedbackSequence(
                    id=m3_ankou.identity("feedback", source, marker_event),
                    actor=actor,
                    cast=None,
                    source=source,
                    event=event,
                    punishment_event=marker_event,
                    reason="punishment",
                    count=1,
                )
                m3_ankou.put(state, saved)
            recovered.append(saved.id)
            game.event(
                c,
                viewer.user_id,
                key,
                "m3.punishment_followup_recovered",
                state,
                event_id=event,
                work_id=identity,
            )
            materialize(game, c, event)
        else:
            families = void_families(before, after, actor)
            if not families:
                raise WorkflowError("The original Asset loss did not produce a new Void threshold.")
            game.event(
                c,
                viewer.user_id,
                key,
                "m3.punishment_followup_recovered",
                event_id=event,
                work_id=identity,
            )
            for family in families:
                existing = c.scalar(
                    sa.select(table.c.id)
                    .where(
                        table.c.campaign_id == service.store.campaign_id,
                        table.c.event_id == marker_event,
                        table.c.kind == "void_threshold",
                        sa.func.json_extract(table.c.body_json, "$.source_work") == source,
                        sa.func.json_extract(table.c.body_json, "$.details.family") == family,
                    )
                    .limit(1)
                )
                child = existing or str(
                    uuid5(
                        NAMESPACE_URL, f"girlframe:punishment:void:{source}:{marker_event}:{family}"
                    )
                )
                if not existing:
                    related(
                        c,
                        service.store,
                        parent_row,
                        child,
                        viewer.user_id,
                        viewer.user_id,
                        "void_threshold",
                        dict(
                            reason="punishment",
                            source_work=source,
                            immediate=True,
                            owner=actor.model_dump(mode="json"),
                            character=original,
                            source_action=None,
                            source_pdf=19,
                            details=dict(family=family),
                        ),
                        marker_event,
                    )
                recovered.append(child)
        service._save(c, row, event, state="resolved", body=body | {"recovered_work": recovered})
        return {"id": identity, "state": "recovered", "followups": recovered}

    return service._write(
        viewer,
        key,
        identity,
        "m3.punishment_followup_recovery",
        dict(id=identity, revision=revision, game_revision=game_revision),
        operation,
    )
