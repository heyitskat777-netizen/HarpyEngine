"""Actual played-memory scene contexts, never a reconstructed historical world."""

import hashlib
from typing import Any, Literal

from pydantic import Field

from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

RULE = "handler-advancement.handler-advancement.deep-brain-spikes"


class Acquisition(Model):
    id: str
    award: str
    handler: ActorRef
    appointment: str
    event: str
    account: str = Field(min_length=1, max_length=1200)


class TagUse(Model):
    actor: ActorRef
    tag: str
    source: str
    virtual: bool = False


class Contribution(Model):
    event: str
    actor: ActorRef
    account: str = Field(min_length=1, max_length=1200)
    action: str | None = None


class Memory(Model):
    id: str
    acquisition: str
    handler: ActorRef
    appointment: str
    subject: ActorRef
    mode: Literal["there", "watching"]
    period: Literal["offscreen", "before_game"]
    beginning: str = Field(min_length=1, max_length=1800)
    circumstances: str = Field(min_length=1, max_length=1200)
    channel: int
    scene: str
    present_scene: str
    present_revision: int
    present_cast: SceneCast
    participants: tuple[int, ...]
    event: str
    tag_uses: tuple[TagUse, ...] = ()
    contributions: tuple[Contribution, ...] = ()
    phase: Literal["active", "returned"] = "active"
    return_cause: Literal["relevance_clear", "major_discrepancy"] | None = None
    return_account: str | None = None
    return_event: str | None = None


def acquisitions(state: GameState) -> tuple[Acquisition, ...]:
    return tuple(
        Acquisition.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "deep_brain_spikes_acquisition"
    )


def memories(state: GameState) -> tuple[Memory, ...]:
    return tuple(
        Memory.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "deep_brain_spikes_memory"
    )


def put(state: GameState, value: Acquisition | Memory) -> None:
    kind = (
        "deep_brain_spikes_acquisition"
        if isinstance(value, Acquisition)
        else "deep_brain_spikes_memory"
    )
    if isinstance(value, Acquisition) and any(x.id == value.id for x in acquisitions(state)):
        raise ValueError("Preserve the immutable genuine advancement acquisition")
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))


def active(state: GameState, scene: str) -> Memory | None:
    values = [x for x in memories(state) if x.phase == "active" and x.scene == scene]
    if len(values) > 1:
        raise ValueError("Recover this scene's single actual played-memory context")
    return values[0] if values else None


def scene_context(state: GameState, scene: str) -> dict[str, Any] | None:
    value = active(state, scene)
    if value is None:
        return None
    # Only context is exposed through ordinary controls. Memory content stays private.
    return dict(
        id=value.id,
        kind="memory",
        label="Deep-Brain-Spikes memory scene",
        present_scene=value.present_scene,
        mode=value.mode,
        instruction="Remembered fiction; real current-actor Plays keep their actual effects.",
    )


def require_return(state: GameState, scene: str) -> None:
    if active(state, scene):
        raise ValueError(
            "Record the actual relevance or major discrepancy through Deep-Brain-Spikes return"
        )


def _tag_source(tag: TagState) -> str:
    return hashlib.sha256(
        tag.model_dump_json(
            exclude={
                "marked",
                "scene_used",
                "observers",
                "rejection_pending",
            }
        ).encode()
    ).hexdigest()


def _tag_rows(state: GameState) -> list[tuple[ActorRef, TagState, bool]]:
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.engine.m3_cute_uniforms import tags
    from girlframe.engine.m3_handler_consequences import active_handler

    result = [
        (current_ref(state, sheet.owner), tag, False)
        for sheet in state.sheets.values()
        for tag in sheet.tags
    ]
    result.extend(
        (current_ref(state, sheet.owner), tag, True)
        for sheet in state.sheets.values()
        for tag in tags(state, sheet.owner)
    )
    handler = active_handler(state)
    if handler:
        result.extend((handler, tag, False) for tag in state.handler_tags)
    return result


def saved_tag_uses(state: GameState, scene: str) -> tuple[TagUse, ...]:
    return tuple(
        TagUse(actor=actor, tag=tag.id, source=_tag_source(tag), virtual=virtual)
        for actor, tag, virtual in _tag_rows(state)
        if tag.scene_used == scene
    )


def restore_present_usage(state: GameState, value: Memory) -> None:
    """Merge only surviving same-source present usage; never restore resources or marks."""
    from girlframe.engine.m3_cute_uniforms import save_tag

    rows = _tag_rows(state)
    changed: set[str] = set()
    for saved in value.tag_uses:
        for actor, tag, virtual in rows:
            if (actor, tag.id, _tag_source(tag), virtual) == (
                saved.actor,
                saved.tag,
                saved.source,
                saved.virtual,
            ):
                if tag.scene_used != value.present_scene:
                    tag.scene_used = value.present_scene
                    if actor.kind == "pilot":
                        changed.add(actor.entity)
                    if virtual:
                        save_tag(state, int(actor.entity), tag)
    for uid in changed:
        state.sheets[uid].revision += 1
