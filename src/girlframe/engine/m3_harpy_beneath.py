"""Actual Harpy/Core Beneath choices; Status never belongs to its human controller.

Book PDF22/printed20, inherited PDF181/179; Harpies outside Status PDF195/193.
"""

import json
from typing import Any

from girlframe.engine.m2 import GameState, Obligation
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_beneath import PLAY as PLAY
from girlframe.engine.m3_beneath import choices as choices

MARKER = "harpy_beneath"


def roles(action: dict[str, Any], level: str) -> tuple[ActorRef, ActorRef]:
    meta = action["data"][MARKER]
    actor, target = (ActorRef.model_validate(meta[k]) for k in ("actor", "target"))
    return (target, actor) if level == "low" else (actor, target)


def status_applicable(actor: ActorRef) -> bool:
    return actor.kind == "pilot"


def lock(
    state: GameState,
    *,
    action: str,
    choice: str,
    setter: ActorRef,
    victim: ActorRef,
    setter_owner: int,
    victim_owner: int,
    tag: str,
    label: str,
) -> Obligation:
    identity = action + ":harpy-tag-permission:" + choice
    if any(x.id == identity for x in state.obligations):
        raise ValueError("This actual source already locked the selected Tag")
    gate = Obligation(
        id=identity,
        kind="tag_rejection_permission",
        owner=setter_owner,
        target=victim_owner,
        action=action,
        details=dict(
            tag=tag,
            label=label,
            source_kind=MARKER,
            locker_actor=setter.model_dump_json(),
            bearer_actor=victim.model_dump_json(),
            source_choice=choice,
            effect_choice=choice,
        ),
    )
    state.obligations.append(gate)
    return gate


def participants(gate: Obligation) -> tuple[ActorRef, ActorRef]:
    if gate.kind != "tag_rejection_permission" or gate.details.get("source_kind") != MARKER:
        raise ValueError("Use the actual typed Harpy/Girl Tag lock")
    return (
        ActorRef.model_validate_json(gate.details["locker_actor"]),
        ActorRef.model_validate_json(gate.details["bearer_actor"]),
    )


def locks(state: GameState, actor: ActorRef, tag: str) -> tuple[Obligation, ...]:
    return tuple(
        x
        for x in state.obligations
        if x.kind == "tag_rejection_permission"
        and x.details.get("source_kind") == MARKER
        and x.details.get("tag") == tag
        and participants(x)[1] == actor
    )


def record(
    state: GameState,
    action: str,
    choice: str,
    setter: ActorRef,
    victim: ActorRef,
    selected: tuple[str, ...],
    event: str,
    account: str,
) -> None:
    if any(
        x.get("kind") == MARKER and x.get("action") == action and x.get("choice") == choice
        for x in state.facts
    ):
        raise ValueError("Apply this actual original Beneath decision once")
    state.facts.append(
        dict(
            kind=MARKER,
            action=action,
            choice=choice,
            setter=setter.model_dump_json(),
            victim=victim.model_dump_json(),
            options=json.dumps(selected),
            event=event,
            account=account,
        )
    )
