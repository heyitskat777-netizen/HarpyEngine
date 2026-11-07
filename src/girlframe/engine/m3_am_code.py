"""Just Code Identity/memory maintenance; the original mind/body is never copied."""

from typing import Literal
from uuid import uuid4

from pydantic import Field

from girlframe.engine.m2 import GameState, IdentityState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

RULE = "girl.am.just-code"
PLAY = "am_just_code"
FOLLOW = ("obedient", "immediate", "hesitant", "mouthing_off", "gritted_teeth")


class Maintenance(Model):
    id: str
    actor: ActorRef
    operator: ActorRef
    owner: int
    controller: int
    discovery: str = Field(default="", exclude_if=lambda value: not value)
    new_operator: bool = Field(default=False, exclude_if=lambda value: not value)
    operator_lower: bool = Field(default=False, exclude_if=lambda value: not value)
    operator_human: bool = Field(default=True, exclude_if=lambda value: value)
    new_discovery: str | None = Field(default=None, exclude_if=lambda value: value is None)
    cast: SceneCast
    registry: str
    proposed_event: str
    proposal: str = Field(min_length=1, max_length=1200)
    position: str
    vessel: str
    frame: str
    cell: tuple[int, int]
    order_scope: Literal["spoken_statement"] = "spoken_statement"
    records_access: str | None = Field(default=None, exclude_if=lambda value: value is None)
    selected_options: tuple[Literal["identities", "records", "backup", "body", "branch"], ...] = (
        Field(default=("identities",), exclude_if=lambda value: value == ("identities",))
    )
    phase: Literal["proposed", "ready", "active", "complete"] = "proposed"
    confirmed_event: str | None = None
    confirmation: str = ""
    root: str | None = None
    action: str | None = None
    effect_event: str | None = None
    replacements: dict[str, str] = Field(default_factory=dict)
    memory_erasure: str | None = Field(default=None, exclude_if=lambda value: value is None)
    backup: str | None = Field(default=None, exclude_if=lambda value: value is None)
    body_swap: str | None = Field(default=None, exclude_if=lambda value: value is None)
    branch: str | None = Field(default=None, exclude_if=lambda value: value is None)
    order: str | None = None
    order_event: str | None = None
    instruction: str = ""
    spoken_words: str = ""
    performance: str = ""


def sessions(state: GameState) -> tuple[Maintenance, ...]:
    return tuple(
        Maintenance.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "am_code"
    )


def session(state: GameState, identity: str) -> Maintenance:
    value = next((x for x in sessions(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the actual original circuit-maintenance source")
    return value


def put(state: GameState, value: Maintenance) -> None:
    state.facts = [
        x for x in state.facts if not (x.get("kind") == "am_code" and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind="am_code", id=value.id, body=value.model_dump_json()))


def choices(state: GameState, actor: ActorRef) -> tuple[IdentityState, ...]:
    from girlframe.engine.m3_leviathan_obsession import require_identity_change

    sheet = state.sheets.get(actor.entity)
    if actor.kind != "pilot" or sheet is None or sheet.character_id != actor.incarnation:
        raise ValueError("Only the actual original current AM owns these Identities")
    result = []
    for item in sheet.identities:
        if item.protected or item.paired or item.am_limiter:
            continue
        try:
            require_identity_change(state, actor, (item.id,))
        except ValueError:
            continue
        result.append(item)
    return tuple(result)


def rewrite(
    original: GameState,
    identity: str,
    selected: dict[str, str],
    event: str,
    *,
    memory_scope: Literal["none", "selected", "all"] = "none",
    memories: str = "",
) -> GameState:
    from girlframe.engine.m3_am_memory import erase

    state = GameState.model_validate_json(original.model_dump_json())
    value = session(state, identity)
    eligible = {x.id: x for x in choices(state, value.actor)}
    if (
        value.phase != "active"
        or value.effect_event
        or not event
        or not set(selected) <= set(eligible)
        or any(
            not x.strip() or len(x) > 120 or any(ord(c) < 32 for c in x) for x in selected.values()
        )
    ):
        raise ValueError(
            "Replace only actual source-unlocked, non-Limited original Identities once"
        )
    sheet = state.sheets[value.actor.entity]
    changed = {}
    for old_id, label in selected.items():
        old = eligible[old_id]
        new_id = str(uuid4())
        updated = IdentityState(id=new_id, name=label.strip(), marked=old.marked, slot=old.slot)
        sheet.identities = [updated if x.id == old_id else x for x in sheet.identities]
        sheet.sedation_locked = tuple(new_id if x == old_id else x for x in sheet.sedation_locked)
        changed[old_id] = new_id
    if changed:
        sheet.revision += 1
    erased = erase(
        state,
        value.id,
        value.actor,
        value.operator,
        value.action or "",
        event,
        memory_scope,
        memories,
    )
    put(
        state,
        value.model_copy(
            update=dict(
                effect_event=event,
                replacements=changed,
                memory_erasure=erased,
                phase="active"
                if value.records_access or set(value.selected_options) & {"body", "branch"}
                else "complete",
            )
        ),
    )
    return GameState.model_validate_json(state.model_dump_json())
