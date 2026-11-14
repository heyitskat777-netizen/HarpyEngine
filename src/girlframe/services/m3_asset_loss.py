"""Finite followups for genuine Supply Drop expiry and Budget removal sources."""

from typing import TYPE_CHECKING, Any, Literal
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_janus_storage import effective_assets
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

Reason = Literal[
    "supply_drop_expiry",
    "budget_removal",
    "ankou_feedback",
    "ankou_feedback_sequence",
    "ankou_processor_unlink",
    "consume_partake",
    "consume_starvation_expiry",
    "doctor_wings",
    "doctor_wings_return",
]
REASONS = (
    "supply_drop_expiry",
    "budget_removal",
    "ankou_feedback",
    "ankou_feedback_sequence",
    "ankou_processor_unlink",
    "consume_partake",
    "consume_starvation_expiry",
    "doctor_wings",
    "doctor_wings_return",
)


def snapshots(game: "GameService", c: Connection, event: str) -> tuple[GameState, GameState]:
    history = t.m2["m2_state_history"]
    sequence = c.scalar(
        sa.select(t.events.c.seq).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    )
    if sequence is None:
        raise WorkflowError("Recover the actual asset-loss event")
    rows = list(
        c.scalars(
            sa.select(history.c.body_json)
            .join(
                t.events,
                sa.and_(
                    t.events.c.campaign_id == history.c.campaign_id,
                    t.events.c.id == history.c.event_id,
                ),
            )
            .where(history.c.campaign_id == game.store.campaign_id, t.events.c.seq <= sequence)
            .order_by(t.events.c.seq.desc())
            .limit(2)
        )
    )
    if len(rows) != 2:
        raise WorkflowError("Recover the actual immutable before/after asset-loss states")
    return GameState.model_validate_json(rows[1]), GameState.model_validate_json(rows[0])


def identity(reason: str, source_id: str, actor: ActorRef, suffix: str) -> str:
    return str(
        uuid5(
            NAMESPACE_URL,
            "girlframe:asset-loss:" + reason + ":" + source_id + ":" + actor.token + ":" + suffix,
        )
    )


def last_frame(before: GameState, after: GameState, actor: ActorRef) -> bool:
    old = before.sheets.get(actor.entity) if actor.kind == "pilot" else None
    new = after.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if (
        old is None
        or new is None
        or old.character_id != actor.incarnation
        or new.character_id != actor.incarnation
    ):
        return False
    a = [x for x in old.assets if x.family == "frame"]
    b = [x for x in new.assets if x.family == "frame"]
    return (
        not new.frame_scrapped
        and bool({x.id for x in a} - {x.id for x in b})
        and any(not x.damaged for x in a)
        and not any(not x.damaged for x in b)
    )


def create_loss_work(
    game: "GameService",
    c: Connection,
    before: GameState,
    after: GameState,
    *,
    scope: dict[str, Any],
    actor: ActorRef,
    event: str,
    reason: Reason,
    source_id: str,
    in_battle: bool | None = None,
) -> list[str]:
    if reason not in REASONS:
        raise WorkflowError("Use an actual implemented asset-loss source")
    actual = resolve(
        before, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    source_action = None
    if reason == "ankou_feedback":
        from girlframe.services.m3_ankou_feedback import prove_loss_source

        source = prove_loss_source(game, c, after, event, source_id, actor)
        if source.get("piloting") != actual.piloting or source.get("in_battle") != in_battle:
            raise WorkflowError("Preserve this actual Feedback tear's physical source context.")
        source_action = source["source_action"]
    if reason == "ankou_processor_unlink":
        from girlframe.services.m3_ankou_support import prove_unlink_loss

        source = prove_unlink_loss(game, c, after, event, source_id, actor)
        if source.get("piloting") != actual.piloting or source.get("in_battle") != in_battle:
            raise WorkflowError("Preserve the actual temporary processor loss context")
        source_action = source.get("source_action")
    if reason == "ankou_feedback_sequence":
        from girlframe.services.m3_ankou_feedback_sequences import (
            prove_loss_source as prove_sequence_loss,
        )

        source = prove_sequence_loss(game, c, after, event, source_id, actor)
        if source.get("piloting") != actual.piloting or source.get("in_battle") != in_battle:
            raise WorkflowError("Preserve this actual standalone Feedback loss context")
        source_action = source.get("source_action")
    if reason in ("consume_partake", "consume_starvation_expiry"):
        from girlframe.services.m3_consume_support import prove_loss_source as prove_consume_loss

        source = prove_consume_loss(game, c, after, event, source_id, actor)
        if source.get("piloting") != actual.piloting or source.get("in_battle") != in_battle:
            raise WorkflowError("Preserve the actual original consumption loss context.")
        source_action = source.get("source_action")
    if reason == "doctor_wings_return":
        from girlframe.services.m3_doctor_return import prove_loss_source as prove_return_loss

        context = prove_return_loss(game, c, after, event, source_id, actor)
        if context["piloting"] != actual.piloting:
            raise WorkflowError("Preserve the actual returning component's loss context")
    if reason == "doctor_wings":
        from girlframe.services.m3_doctor_wings_void import prove_loss_source as prove_wings_loss

        context = prove_wings_loss(game, c, after, event, source_id, actor)
        if context["piloting"] != actual.piloting:
            raise WorkflowError("Preserve the actual donor's physical source context")
    body = dict(
        reason=reason,
        source_id=source_id,
        loss_event=event,
        owner=actor.model_dump(mode="json"),
        character=actor.incarnation,
        immediate=True,
        source_action=source_action,
        piloting=actual.piloting,
        in_battle=in_battle,
    )
    result = []

    def add(kind: str, suffix: str, details: dict[str, Any]) -> None:
        work_id = identity(reason, source_id, actor, suffix)
        work = t.m3["m3_required_work"]
        if not c.scalar(
            sa.select(work.c.id)
            .where(work.c.campaign_id == game.store.campaign_id, work.c.id == work_id)
            .limit(1)
        ):
            owner = int(actor.entity) if kind != "supply_drop_frame_context" else after.handler
            if owner is None:
                raise WorkflowError("Recover the actual Handler for this Frame-loss context")
            related(
                c, game.store, scope, work_id, owner, int(actor.entity), kind, body | details, event
            )
        result.append(work_id)

    if last_frame(before, after, actor):
        if actual.piloting is None:
            raise WorkflowError(
                "Prove the actual piloting context before removing last Frame protection"
            )
        if actual.piloting:
            if in_battle is None:
                if reason != "supply_drop_expiry":
                    raise WorkflowError("Record actual battle context before this Budget removal")
                add("supply_drop_frame_context", "context", dict(source_pdf=160))
            elif in_battle:
                add("defeat", "defeat", dict(source_pdf=29, trigger="last_frame_asset_removed"))
    for family in ("girl", "frame"):
        old = [x for x in effective_assets(before, actor) if x.family == family]
        new = [x for x in effective_assets(after, actor) if x.family == family]
        if new and all(x.void for x in new) and not (old and all(x.void for x in old)):
            add(
                "void_threshold", "void:" + family, dict(source_pdf=19, details=dict(family=family))
            )
    return result


def prove_loss_work(
    game: "GameService", c: Connection, row: dict[str, Any], body: dict[str, Any], actor: ActorRef
) -> None:
    reason = body.get("reason")
    if reason not in REASONS:
        raise WorkflowError("Recover this actual implemented asset-loss source")
    source_id = body.get("source_id")
    event = body.get("loss_event")
    if not isinstance(source_id, str) or not isinstance(event, str):
        raise WorkflowError("Recover the exact immutable loss source/event")
    before, after = snapshots(game, c, event)
    if reason == "supply_drop_expiry":
        from girlframe.services.m3_supply_drop import prove_loss_source as prove_supply_loss

        context = prove_supply_loss(game, c, after, event, source_id, actor)
    elif reason == "ankou_feedback":
        from girlframe.services.m3_ankou_feedback import prove_loss_source as prove_feedback_loss

        context = prove_feedback_loss(game, c, after, event, source_id, actor)
        if body.get("source_action") != context.get("source_action"):
            raise WorkflowError("Preserve the actual held Feedback parent, not an external loss.")
    elif reason == "ankou_processor_unlink":
        from girlframe.services.m3_ankou_support import prove_unlink_loss

        context = prove_unlink_loss(game, c, after, event, source_id, actor)
        if body.get("source_action") != context.get("source_action"):
            raise WorkflowError("Preserve the actual processor unlink source")
    elif reason == "ankou_feedback_sequence":
        from girlframe.services.m3_ankou_feedback_sequences import (
            prove_loss_source as prove_sequence_loss,
        )

        context = prove_sequence_loss(game, c, after, event, source_id, actor)
        if body.get("source_action") != context.get("source_action"):
            raise WorkflowError("Preserve the actual standalone Feedback source")
    elif reason in ("consume_partake", "consume_starvation_expiry"):
        from girlframe.services.m3_consume_support import prove_loss_source as prove_consume_loss

        context = prove_consume_loss(game, c, after, event, source_id, actor)
        if body.get("source_action") != context.get("source_action"):
            raise WorkflowError("Preserve the actual original consumption parent and receipt.")
    elif reason == "doctor_wings_return":
        from girlframe.services.m3_doctor_return import prove_loss_source as prove_return_loss

        context = prove_return_loss(game, c, after, event, source_id, actor)
    elif reason == "doctor_wings":
        from girlframe.services.m3_doctor_wings_void import prove_loss_source as prove_wings_loss

        context = prove_wings_loss(game, c, after, event, source_id, actor)
    else:
        from girlframe.services.m3_budget_removal import prove_loss_source as prove_budget_loss

        context = prove_budget_loss(game, c, after, event, source_id, actor)
    if (
        body.get("owner") != actor.model_dump(mode="json")
        or body.get("character") != actor.incarnation
    ):
        raise WorkflowError("Preserve the actual original loss subject")
    if row["kind"] == "defeat":
        actual = resolve(
            before, actor, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        if (
            not last_frame(before, after, actor)
            or actual.piloting is not True
            or context.get("piloting") is not True
            or context.get("in_battle") is not True
            or row["id"] != identity(reason, source_id, actor, "defeat")
        ):
            raise WorkflowError("This actual loss requires source-proved piloting and battle")
    else:
        family = body.get("details", {}).get("family")
        old = [x for x in effective_assets(before, actor) if x.family == family]
        new = [x for x in effective_assets(after, actor) if x.family == family]
        if (
            family not in ("girl", "frame")
            or not new
            or not all(x.void for x in new)
            or old
            and all(x.void for x in old)
            or row["id"] != identity(reason, source_id, actor, "void:" + family)
        ):
            raise WorkflowError("Recover this newly exposed actual full Void family")
