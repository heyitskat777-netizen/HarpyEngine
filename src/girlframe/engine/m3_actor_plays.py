"""Actual Handler/Harpy basic resources, without proxy Pilot sheets."""

from collections.abc import Sequence
from uuid import uuid4

from girlframe.engine.m2 import (
    TRAITS,
    ChoiceAnswer,
    DirectorContext,
    GameState,
    IdentityState,
    TagState,
)
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_harpy_defeat import harpy
from girlframe.engine.m3_harpy_defeat import update as update_harpy
from girlframe.engine.m3_void_state import HarpyIdentity, HarpyTag


def tags(state: GameState, actor: ActorRef) -> Sequence[TagState | HarpyTag]:
    if actor.kind == "clone_am":
        from girlframe.engine.m3_clone_am import tags as clone_tags

        return clone_tags(state, actor)
    if actor.kind == "external_pilot":
        return harpy(state, actor).tags
    context(state, actor)
    return state.handler_tags


def _put_harpy(state: GameState, actor: ActorRef, **values: object) -> None:
    changed = update_harpy(state, actor, **values)
    state.harpy_states, state.native_harpies = changed.harpy_states, changed.native_harpies
    state.janus_cores = changed.janus_cores


def context(state: GameState, actor: ActorRef) -> DirectorContext:
    if actor.kind != "handler" or state.handler != int(actor.entity):
        raise ValueError("Use the actual Handler's Girl-rules role")
    value = next(
        (x for x in state.director_contexts if x.id == actor.incarnation and x.active), None
    )
    if value is None:
        raise ValueError("Recover the actual active Director presence")
    return value


def keep(level: str, answer: ChoiceAnswer, *, harpy_mode: bool = False) -> dict[str, list[str]]:
    if harpy_mode:
        if "sexy" in (*answer.options, *answer.denied):
            raise ValueError("The Harpy trait is beautiful, replacing sexy")
        normalized = answer.model_copy(
            update={
                "options": tuple("sexy" if x == "beautiful" else x for x in answer.options),
                "denied": tuple("sexy" if x == "beautiful" else x for x in answer.denied),
            }
        )
        result = keep(level, normalized)
        return {k: ["beautiful" if x == "sexy" else x for x in v] for k, v in result.items()}
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
    if actor.kind == "clone_am":
        from girlframe.engine.m3_clone_am import add_tag as clone_tag

        clone_tag(state, actor, label, participants)
        return
    if actor.kind == "external_pilot":
        actual_harpy = harpy(state, actor)
        _put_harpy(
            state,
            actor,
            tags=(
                *actual_harpy.tags,
                HarpyTag(
                    id=str(uuid4()),
                    label=label.strip(),
                    giver=actual_harpy.controller,
                    giver_ref=actor,
                    observers=participants,
                ),
            ),
        )
        return
    actual = context(state, actor)
    state.handler_tags.append(
        TagState(id=str(uuid4()), label=label.strip(), giver=actual.handler, observers=participants)
    )
    actual.revision += 1


def harpy_keep(
    state: GameState, actor: ActorRef, level: str, answer: ChoiceAnswer
) -> dict[str, list[str]]:
    body = harpy(state, actor)
    owned = set(getattr(body, "plays", ()))
    experienced = "girl.oldgen.elder-bitch" in owned
    if answer.flag is not None and not experienced:
        raise ValueError("This actual Harpy does not own the experienced trait rule")
    selected = answer.model_copy(update={"flag": None})
    result = keep(level, selected, harpy_mode=True)
    automatic = set()
    if "girl.princess.objectively-beautiful" in owned:
        automatic.add("beautiful")
    if "girl.alpha.itching-for-a-fight" in owned:
        automatic.add("vicious")
    if automatic & set(answer.denied):
        raise ValueError("An actual retained automatic trait cannot be denied")
    result["positive"] = sorted(set(result["positive"]) | automatic)
    result["negative"] = sorted(set(result["negative"]) - automatic)
    if experienced and answer.flag is True:
        result["positive"].append("experienced")
    return result


def proposal(
    state: GameState,
    target: ActorRef,
    proposer: ActorRef | None,
    controller: int,
    bindings: tuple[ProfileBinding, ...],
    tag_id: str,
    scene: str,
    direction: int,
    account: str,
    *,
    ooc_controller: int | None = None,
) -> int:
    actual_target = resolve(state, target, bindings, require_current_profile=False)
    actual = resolve(state, proposer, bindings, require_current_profile=False) if proposer else None
    if (
        (actual is not None and actual.controller != controller)
        or (actual is None and controller not in (state.handler, ooc_controller))
        or controller == actual_target.controller
    ):
        raise ValueError("Only another human can propose a Tag through their actual role")
    tag = next((x for x in tags(state, target) if x.id == tag_id), None)
    if (
        tag is None
        or controller not in tag.observers
        or tag.scene_used == scene
        or direction not in (-1, 1)
        or not account.strip()
    ):
        raise ValueError("Propose one observed, unused Tag with a direction and relevance")
    from girlframe.engine.m3_actor_bonds import bond_ref
    from girlframe.engine.m3_actor_bonds import depth as actual_depth

    depth = (
        actual_depth(state, bond_ref(state, target), bond_ref(state, proposer)) if proposer else 0
    )
    return direction * (2 if depth else 1)


def defer_rejection(state: GameState, actor: ActorRef, tag_id: str) -> None:
    if actor.kind == "clone_am":
        from girlframe.engine.m3_clone_am import tag as clone_tag

        selected = next((x for x in tags(state, actor) if x.id == tag_id and x.marked), None)
        if selected is None:
            raise ValueError("Choose the actual marked copy Tag")
        clone_tag(state, actor, tag_id, rejection_pending=True)
        return
    if actor.kind == "external_pilot":
        from girlframe.engine.m3_tag_permissions import can_reject

        if not can_reject(state, actor, tag_id):
            raise ValueError("Original locker consent is required before choosing rejection")
    tag = next((x for x in tags(state, actor) if x.id == tag_id), None)
    if tag is None or not tag.marked:
        raise ValueError("Choose the actual marked Tag to reject")
    if actor.kind == "external_pilot":
        _put_harpy(
            state,
            actor,
            tags=tuple(
                x.model_copy(update={"rejection_pending": True}) if x.id == tag_id else x
                for x in tags(state, actor)
            ),
        )
    else:
        tag.rejection_pending = True


def mark(state: GameState, target: ActorRef, tag_id: str, scene: str) -> bool:
    tag = next((x for x in tags(state, target) if x.id == tag_id), None)
    if tag is None or tag.scene_used == scene:
        raise ValueError("The proposed Tag changed or was already used in this scene")
    was_marked = tag.marked
    if target.kind == "clone_am":
        from girlframe.engine.m3_clone_am import tag as clone_tag

        clone_tag(state, target, tag_id, marked=True, scene_used=scene)
        return was_marked
    if target.kind == "external_pilot":
        _put_harpy(
            state,
            target,
            tags=tuple(
                x.model_copy(update={"marked": True, "scene_used": scene}) if x.id == tag_id else x
                for x in tags(state, target)
            ),
        )
        return was_marked
    actual = context(state, target)
    tag.marked, tag.scene_used = True, scene
    actual.revision += 1
    return was_marked


def embrace(state: GameState, actor: ActorRef, tag_id: str, replaced: tuple[str, ...]) -> None:
    if actor.kind == "clone_am":
        from girlframe.engine.m3_clone_am import embrace as clone_embrace

        clone_embrace(state, actor, tag_id, replaced)
        return
    from girlframe.engine.m3_leviathan_obsession import require_identity_change

    require_identity_change(state, actor, replaced)
    if actor.kind == "external_pilot":
        body = harpy(state, actor)
        harpy_tag = next((x for x in body.tags if x.id == tag_id and x.marked), None)
        count = 1 if len(body.identities) >= 4 else 0
        if (
            harpy_tag is None
            or len(replaced) != count
            or not set(replaced) <= {x.id for x in body.identities if not x.protected}
        ):
            raise ValueError("Embrace the actual marked Tag with any required ordinary replacement")
        _put_harpy(
            state,
            actor,
            identities=(
                *tuple(x for x in body.identities if x.id not in replaced),
                HarpyIdentity(id=str(uuid4()), name=harpy_tag.label),
            ),
            tags=tuple(x for x in body.tags if x.id != harpy_tag.id),
        )
        return
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
    if actor.kind == "clone_am":
        from girlframe.engine.m3_clone_am import reject as clone_reject

        clone_reject(state, actor, tag_id)
        return
    if actor.kind == "external_pilot":
        from girlframe.engine.m3_tag_permissions import can_reject

        if not can_reject(state, actor, tag_id):
            raise ValueError("The original Tag locker must grant permission before rejection")
        body = harpy(state, actor)
        if not any(x.id == tag_id and x.rejection_pending for x in body.tags):
            raise ValueError("Take the actual owed action to reject this Harpy Tag")
        _put_harpy(state, actor, tags=tuple(x for x in body.tags if x.id != tag_id))
        return
    actual = context(state, actor)
    tag = next((x for x in state.handler_tags if x.id == tag_id and x.rejection_pending), None)
    if tag is None:
        raise ValueError("Take the actual pending action to reject this Tag")
    state.handler_tags = [x for x in state.handler_tags if x.id != tag_id]
    actual.revision += 1
