"""Explicit human casting, distinct from fictional travel, exposure or consent."""

from typing import Any

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, CastRole, ProfileBinding, SceneCast
from girlframe.engine.m3_actors import resolve


def join(
    casts: list[SceneCast], identity: str, actor: ActorView, controller: int, source: str
) -> SceneCast:
    cast = next((x for x in casts if x.id == identity and x.open), None)
    if cast is None or not actor.alive or actor.controller != controller:
        raise ValueError("Join an open scene using your actual living role")
    if any(
        x.open
        and any(
            y.actor == actor.ref
            or (actor.ref.kind == y.actor.kind == "handler" and y.actor.entity == actor.ref.entity)
            for y in x.roles
        )
        for x in casts
    ):
        raise ValueError("Withdraw this actual role from its current scene before joining")
    return SceneCast.model_validate_json(
        cast.model_copy(
            update={
                "roles": (
                    *cast.roles,
                    CastRole(actor=actor.ref, controller=controller, source_event=source),
                ),
                "revision": cast.revision + 1,
            }
        ).model_dump_json()
    )


def withdraw(cast: SceneCast, ref: ActorRef, controller: int) -> SceneCast:
    role = next((x for x in cast.roles if x.actor == ref), None)
    if not cast.open or role is None or role.controller != controller:
        raise ValueError("Withdraw only your own actual casting record")
    values: dict[str, Any] = {
        "roles": tuple(x for x in cast.roles if x != role),
        "revision": cast.revision + 1,
    }
    if cast.adjudicator == ref:
        values["adjudicator"] = None
    return SceneCast.model_validate_json(cast.model_copy(update=values).model_dump_json())


def validate_role(cast: SceneCast, actor: ActorView) -> CastRole:
    role = next((x for x in cast.roles if x.actor == actor.ref), None)
    if not cast.open or role is None or role.controller != actor.controller or not actor.alive:
        raise ValueError("STALE_CAST: the actual role needs explicit current-controller casting")
    return role


def choose_adjudicator(
    state: GameState,
    cast: SceneCast,
    ref: ActorRef,
    controller: int,
    bindings: tuple[ProfileBinding, ...],
) -> SceneCast:
    actor = resolve(state, ref, bindings)
    validate_role(cast, actor)
    if actor.rules != "director" or actor.controller != controller or controller == state.handler:
        raise ValueError("Offer only your actual cast Director for Handler-rule responses")
    if cast.adjudicator == ref:
        raise ValueError("Your Director is already the selected rules adjudicator")
    return cast.model_copy(update={"adjudicator": ref, "revision": cast.revision + 1})


def adjudicator(
    state: GameState,
    cast: SceneCast,
    bindings: tuple[ProfileBinding, ...],
    *,
    acting: ActorRef | None = None,
) -> ActorView:
    if cast.adjudicator is not None:
        actor = resolve(state, cast.adjudicator, bindings)
        validate_role(cast, actor)
        if actor.rules != "director" or actor.controller == state.handler:
            raise ValueError("Recover the actual Director's rule authority and current controller")
        if acting is not None and acting.kind == "handler":
            context = next(
                (x for x in state.director_contexts if x.id == acting.incarnation and x.active),
                None,
            )
            if context is None or actor.ref.entity not in context.directors:
                raise ValueError("This Handler needs the actual Director in its current presence")
        return actor
    if state.handler is not None and cast.facilitator == state.handler:
        return resolve(state, ActorRef(kind="handler", entity=str(state.handler)), bindings)
    raise ValueError("Choose an actual Handler-rule adjudicator for this scene")
