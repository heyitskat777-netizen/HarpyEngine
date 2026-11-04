"""Actual Handler-in-Director-presence Girl rules, without a proxy Pilot sheet."""

from uuid import uuid4

from girlframe.engine.m2 import (
    TRAITS,
    ChoiceAnswer,
    DirectorContext,
    GameState,
    IdentityState,
    TagState,
    pair_key,
)
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_actors import resolve


def context(state: GameState, actor: ActorRef) -> DirectorContext:
    if actor.kind != "handler" or state.handler != int(actor.entity):
        raise ValueError("Use the actual Handler's Girl-rules role")
    value = next(
        (x for x in state.director_contexts if x.id == actor.incarnation and x.active), None
    )
    if value is None:
        raise ValueError("Recover the actual active Director presence")
    return value


def keep(level: str, answer: ChoiceAnswer) -> dict[str, list[str]]:
    positives = set(answer.options)
    negatives = set(answer.denied)
    if answer.fields or answer.flag is not None or answer.number is not None or answer.member:
        raise ValueError("Choose only the actual Handler's ordinary Keep Your Head options")
    if level == "low":
        valid = len(positives) == 1 and positives <= set(TRAITS) and not negatives
        negatives = set(TRAITS) - positives
    elif level == "mid":
        valid = (
            len(positives) == 2
            and len(negatives) == 1
            and positives | negatives <= set(TRAITS)
            and not positives & negatives
        )
    elif level == "high":
        valid = not positives and not negatives and bool(answer.text.strip())
        positives, negatives = set(TRAITS[:-1]), {"in_control"}
    else:
        raise ValueError("Resolve the actual rolled tier")
    if not valid:
        raise ValueError("Choose the exact printed traits for this result tier")
    return {"positive": sorted(positives), "negative": sorted(negatives)}


def add_tag(state: GameState, actor: ActorRef, label: str, participants: tuple[int, ...]) -> None:
    actual = context(state, actor)
    state.handler_tags.append(
        TagState(id=str(uuid4()), label=label.strip(), giver=actual.handler, observers=participants)
    )
    actual.revision += 1


def proposal(
    state: GameState,
    target: ActorRef,
    proposer: ActorRef,
    controller: int,
    bindings: tuple[ProfileBinding, ...],
    tag_id: str,
    scene: str,
    direction: int,
    account: str,
) -> int:
    context(state, target)
    actual = resolve(state, proposer, bindings, require_current_profile=False)
    if actual.controller != controller or controller == int(target.entity):
        raise ValueError("Only another human can propose a Tag through their actual role")
    tag = next((x for x in state.handler_tags if x.id == tag_id), None)
    if (
        tag is None
        or controller not in tag.observers
        or tag.scene_used == scene
        or direction not in (-1, 1)
        or not account.strip()
    ):
        raise ValueError("Propose one observed, unused Tag with a direction and relevance")
    if proposer.kind == "pilot":
        depth = state.bonds.get(pair_key(controller, int(target.entity)), 0)
    elif proposer.kind == "npc" and state.world:
        npc = next(x for x in state.world.npcs if x.id == proposer.entity)
        depth = npc.bonds.get("handler:" + target.entity, 0)
    else:
        raise ValueError("UNSUPPORTED_RULE: this role's actual Bond port is not implemented")
    return direction * (2 if depth else 1)


def mark(state: GameState, target: ActorRef, tag_id: str, scene: str) -> bool:
    actual = context(state, target)
    tag = next((x for x in state.handler_tags if x.id == tag_id), None)
    if tag is None or tag.scene_used == scene:
        raise ValueError("The proposed Tag changed or was already used in this scene")
    was_marked = tag.marked
    tag.marked, tag.scene_used = True, scene
    actual.revision += 1
    return was_marked


def embrace(state: GameState, actor: ActorRef, tag_id: str, replaced: tuple[str, ...]) -> None:
    actual = context(state, actor)
    tag = next((x for x in state.handler_tags if x.id == tag_id), None)
    if tag is None or not tag.marked:
        raise ValueError("Resolve the actual repeated Tag")
    count = 1 if len(actual.identities) >= 4 else 0
    if len(replaced) != count or not set(replaced) <= {x.id for x in actual.identities}:
        raise ValueError("Replace one ordinary Identity only when at the four-Identity cap")
    actual.identities = [x for x in actual.identities if x.id not in replaced] + [
        IdentityState(id=str(uuid4()), name=tag.label)
    ]
    state.handler_tags = [x for x in state.handler_tags if x.id != tag.id]
    actual.revision += 1


def reject(state: GameState, actor: ActorRef, tag_id: str) -> None:
    actual = context(state, actor)
    tag = next((x for x in state.handler_tags if x.id == tag_id and x.rejection_pending), None)
    if tag is None:
        raise ValueError("Take the actual pending action to reject this Tag")
    state.handler_tags = [x for x in state.handler_tags if x.id != tag_id]
    actual.revision += 1
