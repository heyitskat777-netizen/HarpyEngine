"""Unassuming Doll: original-scene benefits and genuine departure/return facts."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef, Model, ProfileBinding, SceneCast

RULE = "girl.vatgrown.unassuming-doll"
PLAY = "unassuming_doll"
BENEFITS = ("quiet", "leave", "information")


class Source(Model):
    id: str
    actor: ActorRef
    caster: int
    target: ActorRef
    counterpart: int
    vessel: str
    cast: SceneCast
    roll_event: str
    total: int
    event: str
    attention_choice: str | None = None
    attention_event: str | None = None
    punishment: str | None = None
    tag: TagState | None = None
    benefit_choice: str | None = None
    benefit_event: str | None = None
    benefits: tuple[str, ...] = ()
    complete: bool = False
    completed_event: str | None = None


class Effect(Model):
    id: str
    action: str
    actor: ActorRef
    caster: int
    vessel: str
    scene: str
    kind: Literal["quiet", "leave", "information", "object"]
    choice: str
    event: str


class Act(Model):
    id: str
    actor: ActorRef
    scene: str
    source_action: str
    event: str
    kind: Literal["play", "question", "departure", "return"]
    effects: tuple[str, ...]


class Departure(Model):
    id: str
    effect: str
    effects: tuple[str, ...]
    actor: ActorRef
    vessel: str
    before: SceneCast
    after: SceneCast
    event: str
    account: str


class Return(Model):
    id: str
    departure: str
    actor: ActorRef
    vessel: str
    before: SceneCast
    after: SceneCast
    event: str
    account: str


class Information(Model):
    id: str
    action: str
    giver: ActorRef
    controller: int
    recipient: ActorRef
    recipient_controller: int
    cast: SceneCast
    question: str
    requested_event: str
    answer: str = ""
    choice: str | None = None
    event: str | None = None


KINDS: dict[type[Model], str] = {
    Source: "vatgrown_doll_source",
    Effect: "vatgrown_doll_effect",
    Act: "vatgrown_doll_act",
    Departure: "vatgrown_doll_departure",
    Return: "vatgrown_doll_return",
    Information: "vatgrown_doll_information",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def put(state: GameState, value: Model) -> None:
    kind, identity = KINDS[type(value)], value.model_dump()["id"]
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == identity)
    ]
    state.facts.append(dict(kind=kind, id=identity, body=value.model_dump_json()))


def source(state: GameState, identity: str) -> Source:
    result = next((x for x in records(state, Source) if x.id == identity), None)
    if result is None:
        raise ValueError("Recover the original actual Unassuming Doll source")
    return result


def _active_at(state: GameState, value: Effect, cast: SceneCast) -> bool:
    if (
        not cast.open
        or cast.id != value.scene
        or not any(x.actor == value.actor for x in cast.roles)
    ):
        return False
    if any(value.id in x.effects for x in records(state, Departure)):
        return False
    from girlframe.engine.m3_actors import resolve

    try:
        bound = tuple(
            ProfileBinding(
                owner=x.owner,
                character_id=x.character_id,
                profile_revision=x.source_profile_revision,
            )
            for x in state.sheets.values()
            if x.character_id
        )
        if (
            resolve(state, value.actor, bound, require_current_profile=False).vessel_id
            != value.vessel
        ):
            return False
    except ValueError:
        return False
    return not any(value.id in x.effects for x in records(state, Act))


def active(state: GameState, value: Effect) -> bool:
    cast = next((x for x in state.scene_casts if x.id == value.scene), None)
    return cast is not None and _active_at(state, value, cast)


def notice_blocked(state: GameState, actor: ActorRef, scene: str) -> bool:
    return any(
        x.actor == actor and x.scene == scene and x.kind == "quiet" and active(state, x)
        for x in records(state, Effect)
    )


def object_treatment(state: GameState, actor: ActorRef, scene: str) -> bool:
    return any(
        x.actor == actor and x.scene == scene and x.kind == "object" and active(state, x)
        for x in records(state, Effect)
    )


def stage_act(
    state: GameState,
    actor: ActorRef,
    scene: str,
    source_action: str,
    event: str,
    kind: Literal["play", "question", "departure", "return"],
) -> bool:
    effects = tuple(
        x.id
        for x in records(state, Effect)
        if x.actor == actor
        and x.scene == scene
        and x.kind in ("quiet", "object")
        and active(state, x)
    )
    if not effects:
        return False
    identity = str(uuid5(NAMESPACE_URL, "doll-act:" + event + ":" + actor.token))
    put(
        state,
        Act(
            id=identity,
            actor=actor,
            scene=scene,
            source_action=source_action,
            event=event,
            kind=kind,
            effects=effects,
        ),
    )
    return True


def record_departure(
    state: GameState, effect: Effect, before: SceneCast, after: SceneCast, event: str, account: str
) -> Departure:
    if (
        effect.kind != "leave"
        or before.id != effect.scene
        or before.id != after.id
        or not before.open
        or not after.open
        or not any(x.actor == effect.actor for x in before.roles)
        or any(x.actor == effect.actor for x in after.roles)
        or not account.strip()
        or len(account) > 1200
        or any(x.effect == effect.id for x in records(state, Departure))
    ):
        raise ValueError("Record the original person's actual unopposed scene exit once")
    value = Departure(
        id=str(uuid5(NAMESPACE_URL, "doll-departure:" + effect.id)),
        effect=effect.id,
        effects=tuple(
            x.id
            for x in records(state, Effect)
            if x.actor == effect.actor and _active_at(state, x, before)
        ),
        actor=effect.actor,
        vessel=effect.vessel,
        before=before,
        after=after,
        event=event,
        account=account,
    )
    put(state, value)
    # Leaving the actual scene is itself acting; no map/Frame/body fields are touched.
    put(
        state,
        Act(
            id=str(uuid5(NAMESPACE_URL, "doll-act:" + event + ":" + effect.actor.token)),
            actor=effect.actor,
            scene=before.id,
            source_action=effect.action,
            event=event,
            kind="departure",
            effects=tuple(
                x.id
                for x in records(state, Effect)
                if x.id in value.effects and x.kind in ("quiet", "object")
            ),
        ),
    )
    return value


def record_return(
    state: GameState,
    departure: Departure,
    before: SceneCast,
    after: SceneCast,
    event: str,
    account: str,
) -> Return:
    if (
        before.id != after.id
        or not before.open
        or not after.open
        or any(x.actor == departure.actor for x in before.roles)
        or not any(x.actor == departure.actor for x in after.roles)
        or not account.strip()
        or len(account) > 1200
        or any(x.departure == departure.id for x in records(state, Return))
    ):
        raise ValueError("Record the original person's actual factual re-entry once")
    value = Return(
        id=str(uuid5(NAMESPACE_URL, "doll-return:" + departure.id)),
        departure=departure.id,
        actor=departure.actor,
        vessel=departure.vessel,
        before=before,
        after=after,
        event=event,
        account=account,
    )
    put(state, value)
    put(
        state,
        Act(
            id=str(uuid5(NAMESPACE_URL, "doll-act:" + event + ":" + departure.actor.token)),
            actor=departure.actor,
            scene=after.id,
            source_action=source(
                state, next(x.action for x in records(state, Effect) if x.id == departure.effect)
            ).id,
            event=event,
            kind="return",
            effects=tuple(
                x.id
                for x in records(state, Effect)
                if x.actor == departure.actor
                and x.scene == after.id
                and x.kind in ("quiet", "object")
                and active(state, x)
            ),
        ),
    )
    return value
