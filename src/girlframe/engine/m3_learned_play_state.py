"""Actual one-use lessons and the lifetime of their original mechanical marks."""

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
