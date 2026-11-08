"""Fictional AM recall restrictions, separate from immutable OOC evidence."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model

Scope = Literal["none", "selected", "all"]


class Erasure(Model):
    id: str
    maintenance: str
    actor: ActorRef
    operator: ActorRef
    action: str
    event: str
    through_revision: int = Field(ge=0)
    scope: Literal["selected", "all"]
    memories: tuple[str, ...] = ()

    @model_validator(mode="after")
    def actual_memories(self) -> "Erasure":
        if (self.scope == "selected") != bool(self.memories) or any(
            not x.strip() or len(x) > 1200 for x in self.memories
        ):
            raise ValueError("Erase actual selected memories or all prior memories")
        return self


def losses(state: GameState, actor: ActorRef | None = None) -> tuple[Erasure, ...]:
    return tuple(
        value
        for fact in state.facts
        if fact.get("kind") == "am_memory_erasure"
        if (value := Erasure.model_validate_json(fact["body"]))
        if actor is None or value.actor == actor
    )


def selected_memories(text: str) -> tuple[str, ...]:
    if len(text) > 1200:
        raise ValueError("Selected memory contents exceed the supported native field")
    return tuple(dict.fromkeys(x.strip() for x in text.splitlines() if x.strip()))


def can_recall(state: GameState, actor: ActorRef, memory: str, *, learned_revision: int) -> bool:
    """Check fictional knowledge; OOC historical records never restore erased recall.

    Selective memories are exact human-authored contents, not inferred transcript matches.
    A genuinely new learning after an erasure is unaffected by that earlier operation.
    """
    if learned_revision < 0 or learned_revision > state.revision or not memory.strip():
        raise ValueError("Use actual memory contents and their original learning revision")
    from girlframe.engine.m3_am_branch import remembered_before_birth

    if remembered_before_birth(state, actor, memory, learned_revision) is False:
        return False
    from girlframe.engine.m3_am_backup import recall_state

    available, actual_losses = recall_state(state, actor, learned_revision)
    if not available:
        return False
    from girlframe.engine.m3_changeling import can_recall as changeling_recall

    if not changeling_recall(state, actor, learned_revision):
        return False
    from girlframe.engine.m3_red_queen import can_recall as court_recall

    if not court_recall(state, actor, memory, learned_revision=learned_revision):
        return False
    normalized = " ".join(memory.split()).casefold()
    return not any(
        learned_revision <= loss.through_revision
        and (
            loss.scope == "all"
            or normalized in {" ".join(x.split()).casefold() for x in loss.memories}
        )
        for loss in actual_losses
    )


def erase(
    state: GameState,
    maintenance: str,
    actor: ActorRef,
    operator: ActorRef,
    action: str,
    event: str,
    scope: Scope,
    text: str,
) -> str | None:
    if scope not in ("none", "selected", "all") or (scope == "selected") != bool(text.strip()):
        raise ValueError("Choose no erasure, exact selected memories, or all prior memories")
    if scope == "none":
        return None
    if not action or not event or any(x.maintenance == maintenance for x in losses(state)):
        raise ValueError("Apply only this original rolled maintenance's memory effect once")
    value = Erasure(
        id=str(uuid5(NAMESPACE_URL, "girlframe:am-memory:" + maintenance)),
        maintenance=maintenance,
        actor=actor,
        operator=operator,
        action=action,
        event=event,
        through_revision=state.revision,
        scope=scope,
        memories=selected_memories(text) if scope == "selected" else (),
    )
    state.facts.append(dict(kind="am_memory_erasure", id=value.id, body=value.model_dump_json()))
    return value.id
