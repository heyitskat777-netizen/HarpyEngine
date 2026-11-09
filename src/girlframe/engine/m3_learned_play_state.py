"""Actual one-use lessons and the lifetime of their original mechanical marks."""

import json
from typing import TYPE_CHECKING, Literal

from pydantic import Field

from girlframe.engine.m3_actor_state import ActorRef, Model

if TYPE_CHECKING:
    from girlframe.engine.m2 import GameState


class LearnedPlayUse(Model):
    id: str = Field(min_length=1)
    actor: ActorRef
    teacher: ActorRef
    session: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    event: str = Field(min_length=1)
    claimed_action: str | None = None
    rolled_event: str | None = None


class HoundStatusUse(Model):
    id: str
    lesson: str
    actor: ActorRef
    action: str
    roll_event: str
    choice: str
    event: str
    direction: Literal[-1, 1]
    receipt_sha256: str
    rank_order: tuple[int, ...]
    clear_reason: Literal["rank", "punishment"] | None = None
    cleared_event: str | None = None


def hound_status_uses(state: "GameState") -> tuple[HoundStatusUse, ...]:
    return tuple(
        HoundStatusUse.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "learned_hound_status_use"
    )


def put_hound_status(state: "GameState", value: HoundStatusUse) -> None:
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "learned_hound_status_use" and x.get("id") == value.id)
    ] + [dict(kind="learned_hound_status_use", id=value.id, body=value.model_dump_json())]


def _hound_actor(state: "GameState", actor: ActorRef | int) -> ActorRef | None:
    if isinstance(actor, int):
        sheet = state.sheets.get(str(actor))
        if sheet is None or not sheet.character_id:
            return None
        return ActorRef(kind="pilot", entity=str(actor), incarnation=sheet.character_id)
    return actor


def active_hound_status(state: "GameState", actor: ActorRef | int) -> HoundStatusUse | None:
    ref = _hound_actor(state, actor)
    if ref is None:
        return None
    sheet = state.sheets.get(ref.entity) if ref.kind == "pilot" else None
    rows = [x for x in hound_status_uses(state) if x.actor == ref and x.clear_reason is None]
    if len(rows) > 1:
        raise ValueError("Preserve the one actual original learned Hound Status mark")
    if sheet is None or sheet.character_id != ref.incarnation or not sheet.status_marked:
        return None
    return rows[0] if rows else None


def clear_hound_status(
    state: "GameState",
    actor: ActorRef | int,
    reason: Literal["rank", "punishment"],
    event: str | None = None,
) -> bool:
    """Called by the actual clearing effect; a future boolean cannot revive this mark."""
    ref = _hound_actor(state, actor)
    if ref is None:
        return False
    changed = False
    for value in hound_status_uses(state):
        if value.actor == ref and value.clear_reason is None:
            put_hound_status(
                state, value.model_copy(update=dict(clear_reason=reason, cleared_event=event))
            )
            changed = True
    return changed


def stamp_hound_clears(state: "GameState", event: str) -> None:
    """Bind already-staged real clears to the actual canonical write, never infer one."""
    for value in hound_status_uses(state):
        if value.clear_reason is not None and value.cleared_event is None:
            put_hound_status(state, value.model_copy(update=dict(cleared_event=event)))


class RiskLessonUse(Model):
    id: str
    lesson: str
    actor: ActorRef
    action: str
    offer_event: str
    roll_event: str
    receipt_sha256: str
    choice: str
    event: str
    frame: str | None
    before: int
    after: int = Field(ge=8, le=10)
    asset: str
    family: str | None = None
    work: tuple[str, ...] = ()


class CallLessonUse(Model):
    action: str
    lesson: str
    actor: ActorRef
    begin_event: str
    roll_event: str
    receipt_sha256: str
    event: str
    used: bool
    choice: str | None = None
    option: str | None = None
    step: int | None = None


def call_lesson_uses(state: "GameState") -> tuple[CallLessonUse, ...]:
    return tuple(
        CallLessonUse.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "learned_call_use"
    )


class DefensiveRiskUse(Model):
    id: str
    lesson: str
    actor: ActorRef
    frame: str
    threshold: str
    cause_event: str
    cause_action: str | None
    cause_works: tuple[str, ...]
    source_rows_sha256: str
    before_revision: int
    before_threshold_sha256: str
    event: str
    account: str = Field(min_length=1, max_length=1200)


def defensive_risk_uses(state: "GameState") -> tuple[DefensiveRiskUse, ...]:
    return tuple(
        DefensiveRiskUse.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "learned_defensive_risk_use"
    )


def put_defensive_risk(state: "GameState", value: DefensiveRiskUse) -> None:
    if any(x.id == value.id or x.threshold == value.threshold for x in defensive_risk_uses(state)):
        raise ValueError("This actual source already has its single defensive lesson use")
    state.facts.append(
        dict(kind="learned_defensive_risk_use", id=value.id, body=value.model_dump_json())
    )


def risk_lesson_uses(state: "GameState") -> tuple[RiskLessonUse, ...]:
    return tuple(
        RiskLessonUse.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "learned_risk_use"
    )


def put_risk_lesson(state: "GameState", value: RiskLessonUse) -> None:
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "learned_risk_use" and x.get("id") == value.id)
    ] + [dict(kind="learned_risk_use", id=value.id, body=value.model_dump_json())]


def risk_ward(
    state: "GameState",
    actor: ActorRef,
    source_event: str,
    source_action: str | None,
    source_work: str,
) -> RiskLessonUse | DefensiveRiskUse | None:
    """Only a paid use's exact real Void cause; holding a lesson grants nothing."""
    use = next(
        (
            x
            for x in risk_lesson_uses(state)
            if (
                x.actor == actor
                and x.event == source_event
                and x.action == source_action
                and source_work in x.work
                and x.asset
                and x.family is not None
            )
        ),
        None,
    )
    if use is None:
        candidates = tuple(
            x
            for x in defensive_risk_uses(state)
            if (
                x.actor == actor
                and x.cause_event == source_event
                and x.cause_action == source_action
                and source_work in x.cause_works
            )
        )
        if len(candidates) > 1:
            raise ValueError("Preserve one exact original defensive ward for this source")
        return candidates[0] if candidates else None
    paid = next(
        (
            json.loads(x["body"])
            for x in state.facts
            if (
                x.get("kind") == "mockingbird_risk_paid"
                and x.get("action") == use.action
                and x.get("event") == use.event
                and x.get("actor") == actor.model_dump_json()
            )
        ),
        None,
    )
    if paid is None or any(
        paid.get(key) != value
        for key, value in {
            "learned_source": use.id,
            "action": use.action,
            "actor": actor.model_dump(mode="json"),
            "event": use.event,
            "asset": use.asset,
            "family": use.family,
            "total_before": use.before,
            "total_after": use.after,
        }.items()
    ):
        raise ValueError("Prove this exact paid lesson's actual Void cause before warding it")
    return use
