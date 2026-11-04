"""Explicit human casting, distinct from fictional travel, exposure or consent."""

from girlframe.engine.m3_actor_state import ActorRef, ActorView, CastRole, SceneCast


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
    return cast.model_copy(
        update={"roles": tuple(x for x in cast.roles if x != role), "revision": cast.revision + 1}
    )


def validate_role(cast: SceneCast, actor: ActorView) -> CastRole:
    role = next((x for x in cast.roles if x.actor == actor.ref), None)
    if not cast.open or role is None or role.controller != actor.controller or not actor.alive:
        raise ValueError("STALE_CAST: the actual role needs explicit current-controller casting")
    return role
