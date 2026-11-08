"""Carry a real destroyed Frame forward to its next actual Off-Duty period."""

import json
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_off_duty import Period
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import OnboardingStore, WorkflowError

FUTURE = "defeat_frame_replacement"
VOID_FUTURE = "void_frame_replacement"
FUTURES = (FUTURE, VOID_FUTURE)
ACTIVE = "defeat_frame_replacement_active"


def _original(c: Connection, store: OnboardingStore, identity: str) -> dict[str, Any]:
    table = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(table)
            .where(table.c.campaign_id == store.campaign_id, table.c.id == identity)
            .order_by(table.c.revision)
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None or row["kind"] not in FUTURES or not row["campaign_context"]:
        raise WorkflowError("SOURCE_DEFEAT_MISSING: recover the original destroyed Frame.")
    if row["kind"] == VOID_FUTURE:
        return _void_original(c, store, dict(row))
    body = json.loads(row["body_json"])
    try:
        actor = ActorRef.model_validate_json(json.dumps(body["owner"]))
        game = GameService(store)
        action = game.action(c, body["source_action"])
        followups = action["data"].get("defeat_followups", [])
        index = next(
            i
            for i, f in enumerate(followups)
            if f["kind"] == "frame_replacement" and f["owner"] == body["owner"]
        )
        expected = str(uuid5(NAMESPACE_URL, "girlframe:defeat:" + action["id"] + ":" + str(index)))
        event = row["event_id"]
        history = t.m2["m2_state_history"]
        raw = c.scalar(
            sa.select(history.c.body_json).where(
                history.c.campaign_id == store.campaign_id, history.c.event_id == event
            )
        )
        proof = GameState.model_validate_json(raw) if raw else None
        if (
            actor.kind != "pilot"
            or actor.incarnation != body["character"]
            or row["owner_id"] != actor.entity
            or row["subject_id"] != actor.entity
            or action["data"]["play"] != "defeat"
            or action["actor_id"] != actor.entity
            or expected != identity
            or proof is None
            or actor.entity not in proof.sheets
            or not proof.sheets[actor.entity].frame_scrapped
            or not any(
                f.get("kind") == "destroyed_frame"
                and f.get("action") == action["id"]
                and f.get("source_event") == event
                for f in proof.facts
            )
        ):
            raise ValueError()
    except (KeyError, ValueError, StopIteration):
        raise WorkflowError(
            "SOURCE_DEFEAT_MISSING: recover the original destroyed Frame."
        ) from None
    return dict(row)


def _void_original(c: Connection, store: OnboardingStore, row: dict[str, Any]) -> dict[str, Any]:
    body = json.loads(row["body_json"])
    try:
        owner = ActorRef.model_validate_json(json.dumps(body["owner"]))
        history = t.m2["m2_state_history"]
        raw = c.scalar(
            sa.select(history.c.body_json).where(
                history.c.campaign_id == store.campaign_id,
                history.c.event_id == row["event_id"],
            )
        )
        proof = GameState.model_validate_json(raw) if raw else None
        threshold = (
            next((v for v in proof.void_thresholds if v.id == body["source_threshold"]), None)
            if proof
            else None
        )
        expected = str(
            uuid5(NAMESPACE_URL, "girlframe:void-frame-replacement:" + body["source_threshold"])
        )
        if (
            owner.kind != "pilot"
            or owner.incarnation != body["character"]
            or row["id"] != expected
            or row["owner_id"] != owner.entity
            or row["subject_id"] != owner.entity
            or body["reason"] != "involuntary_void_frame_loss"
            or proof is None
            or owner.entity not in proof.sheets
            or not proof.sheets[owner.entity].frame_scrapped
            or threshold is None
            or threshold.actor != owner
            or threshold.stage != "escaped"
            or threshold.response_event != row["event_id"]
            or threshold.frame_instance != body["frame"]
            or threshold.gorgon is None
            or threshold.gorgon.model_dump(mode="json") != body["source_gorgon"]
            or proof.world is None
            or not any(g.id == threshold.gorgon.entity for g in proof.world.gorgons)
        ):
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        raise WorkflowError(
            "SOURCE_FRAME_LOSS_MISSING: recover the actual abandoned Frame."
        ) from None
    return row


def _sources(
    c: Connection, store: OnboardingStore, state: GameState
) -> list[tuple[dict[str, Any], dict[str, str] | None]]:
    from girlframe.services.m3_returned_work import proof as returned_proof

    table = t.m3["m3_required_work"]
    rows = c.execute(
        sa.select(table)
        .where(
            table.c.campaign_id == store.campaign_id,
            table.c.kind.in_((*FUTURES, ACTIVE)),
        )
        .order_by(table.c.revision)
    ).mappings()
    latest = {row["id"]: dict(row) for row in rows}
    result: list[tuple[dict[str, Any], dict[str, str] | None]] = []
    for row in latest.values():
        if row["kind"] not in FUTURES:
            continue
        body = json.loads(row["body_json"])
        owner = row["owner_id"]
        if owner not in state.sheets or state.sheets[owner].character_id != body["character"]:
            continue
        active = [
            x
            for x in latest.values()
            if x["kind"] == ACTIVE and json.loads(x["body_json"]).get("source_work") == row["id"]
        ]
        # Any real fulfillment consumes this loss forever. An unresolved task
        # already has its original period and must not be issued a second time.
        if any(
            x["state"] != "resolved"
            or json.loads(x["body_json"]).get("resolution") != "original_character_career_ended"
            for x in active
        ):
            continue
        original = _original(c, store, row["id"])
        if row["state"] != "resolved":
            result.append((original, None))
            continue
        closed = active or [row]
        current_archive = next(
            (
                a.id
                for a in reversed(state.career_archives)
                if a.actor.incarnation == body["character"]
            ),
            None,
        )
        selected = next(
            (
                x
                for x in closed
                if json.loads(x["body_json"]).get("career_archive") == current_archive
            ),
            closed[-1],
        )
        returned = returned_proof(c, store, state, selected, int(owner), body["character"])
        if returned is not None:
            result.append((original, returned))
    return result


def _identity(source: str, period: str, returned: dict[str, str] | None) -> str:
    suffix = ":return:" + returned["return_event"] + ":period:" + period if returned else ""
    return str(uuid5(NAMESPACE_URL, "girlframe:defeat-replacement:" + source + suffix))


def pending(c: Connection, store: OnboardingStore, state: GameState, owner: int) -> bool:
    return any(row["owner_id"] == str(owner) for row, _ in _sources(c, store, state))


def synchronize(c: Connection, store: OnboardingStore, period: Period, event: str) -> None:
    if period.phase != "preparing":
        return
    from girlframe.services.m3_work import related

    state = load_state(c, store.campaign_id)
    table = t.m3["m3_required_work"]
    for original, returned in _sources(c, store, state):
        row = (
            c.execute(
                sa.select(table)
                .where(table.c.campaign_id == store.campaign_id, table.c.id == original["id"])
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .one()
        )
        body = json.loads(original["body_json"])
        owner = row["owner_id"]
        if owner in period.ended_characters or period.character_ids.get(owner) != body["character"]:
            continue
        sheet = state.sheets.get(owner)
        if sheet is None or not sheet.frame_scrapped:
            raise WorkflowError(
                "The original destroyed Frame needs reconciliation before Off-Duty."
            )
        identity = _identity(row["id"], period.id, returned)
        if c.scalar(
            sa.select(table.c.id).where(
                table.c.campaign_id == store.campaign_id, table.c.id == identity
            )
        ):
            continue
        related(
            c,
            store,
            dict(campaign_id=store.campaign_id, off_duty_id=period.id),
            identity,
            int(owner),
            int(owner),
            ACTIVE,
            dict(
                source_pdf=29 if row["kind"] == FUTURE else 19,
                source_work=row["id"],
                source_event=original["event_id"],
                origin_frame=sheet.frame,
                origin_frame_id=sheet.frame_runtime.id if sheet.frame_runtime else None,
                origin_fingerprint=sheet.source_fingerprint,
                origin_character_id=body["character"],
                return_proof=returned,
                immediate=True,
            ),
            event,
        )
        if returned is not None:
            # Old work remains closed by its real ending. This is a new owned
            # obligation for the actual returned original, not a reopened receipt.
            continue
        c.execute(
            table.insert().values(
                **{
                    k: v
                    for k, v in row.items()
                    if k not in ("revision", "state", "body_json", "event_id")
                },
                revision=row["revision"] + 1,
                state="resolved",
                event_id=event,
                body_json=json.dumps(
                    json.loads(row["body_json"])
                    | dict(resolution="transferred_to_next_off_duty", replacement_work=identity)
                ),
            )
        )


def check_active(c: Connection, store: OnboardingStore, row: dict[str, Any]) -> None:
    body = json.loads(row["body_json"])
    original = _original(c, store, body.get("source_work", ""))
    source = json.loads(original["body_json"])
    table = t.m3["m3_required_work"]
    first = (
        c.execute(
            sa.select(table).where(
                table.c.campaign_id == store.campaign_id,
                table.c.id == row["id"],
                table.c.revision == 1,
            )
        )
        .mappings()
        .one()
    )
    origin = json.loads(first["body_json"])
    period_table = t.m3["m3_off_duty"]
    raw = c.scalar(
        sa.select(period_table.c.body_json).where(
            period_table.c.campaign_id == store.campaign_id, period_table.c.id == row["off_duty_id"]
        )
    )
    period = Period.model_validate_json(raw) if raw else None
    returned = origin.get("return_proof")
    if returned is not None:
        from girlframe.services.m3_returned_work import proof as returned_proof

        prior = (
            c.execute(
                sa.select(table)
                .where(
                    table.c.campaign_id == store.campaign_id,
                    table.c.id == returned.get("closed_work"),
                )
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if (
            prior is None
            or not (
                prior["id"] == original["id"]
                or (
                    prior["kind"] == ACTIVE
                    and json.loads(prior["body_json"]).get("source_work") == original["id"]
                )
            )
            or returned_proof(
                c,
                store,
                load_state(c, store.campaign_id),
                dict(prior),
                int(row["subject_id"]),
                source["character"],
            )
            != returned
        ):
            raise WorkflowError("SOURCE_RETURN_MISSING: reopen the actual returned-original work.")
    expected = _identity(original["id"], row["off_duty_id"], returned)
    if (
        row["id"] != expected
        or row["kind"] != ACTIVE
        or period is None
        or period.phase != "preparing"
        or row["subject_id"] in period.ended_characters
        or period.character_ids.get(row["subject_id"]) != source["character"]
        or origin["source_event"] != original["event_id"]
        or any(
            body.get(k) != origin.get(k)
            for k in (
                "source_work",
                "source_event",
                "origin_frame",
                "origin_frame_id",
                "origin_character_id",
                "origin_fingerprint",
                "return_proof",
            )
        )
    ):
        raise WorkflowError(
            "SOURCE_REPLACEMENT_MISSING: resume the actual next Off-Duty replacement."
        )
