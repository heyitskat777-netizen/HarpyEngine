"""Printed Handler Assets replacement choices, body endings and source-owned history."""

import json
from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequence_state import (
    Choice,
    HandlerArchive,
    HandlerBody,
    HandlerConsequence,
    HandlerFatalSource,
    HandlerInjury,
    HandlerOpportunity,
)


def active_handler(state: GameState) -> ActorRef | None:
    if state.handler is None:
        return None
    if state.handler_persona is not None:
        actor = ActorRef(
            kind="handler", entity=str(state.handler), incarnation=state.handler_persona.id
        )
        return None if any(x.actor == actor for x in state.handler_archives) else actor
    if state.handler_archives:
        return None
    return ActorRef(kind="handler", entity=str(state.handler))


def same_handler_body(state: GameState, actor: ActorRef) -> bool:
    current = active_handler(state)
    if current is None or actor.kind != "handler" or actor.entity != current.entity:
        return False
    return (
        actor == current
        or (actor.incarnation is None and not state.handler_archives)
        or any(
            x.handler == int(actor.entity)
            and x.id == actor.incarnation
            and (x.body_actor == current or (x.body_actor is None and not state.handler_archives))
            for x in state.director_contexts
        )
    )


def body_original(state: GameState, actor: ActorRef) -> HandlerBody:
    if same_handler_body(state, actor):
        current = active_handler(state)
        assert current is not None
        return HandlerBody(
            actor=current,
            persona_json=state.handler_persona.model_dump_json() if state.handler_persona else None,
            tags_json=json.dumps([x.model_dump(mode="json") for x in state.handler_tags]),
            heat=state.handler_heat,
        )
    saved = next(
        (
            x
            for x in reversed(state.handler_archives)
            if x.actor == actor
            or (
                actor.kind == "handler"
                and actor.entity == x.actor.entity
                and (
                    (actor.incarnation is None and json.loads(x.links_json).get("legacy_alias"))
                    or any(
                        context["id"] == actor.incarnation
                        for context in json.loads(x.links_json).get("director_contexts", ())
                    )
                )
            )
        ),
        None,
    )
    if saved is None:
        raise ValueError("Recover the actual current or archived original Handler body")
    return saved.body


def require(
    original: GameState,
    handler: ActorRef,
    *,
    trigger: str,
    source_action: str | None,
    source_event: str,
    opponent: ActorRef | None,
    appointment: str,
    source_work: str | None = None,
    source_request: str | None = None,
    occurrence: str = "0",
) -> tuple[GameState, str]:
    state = GameState.model_validate_json(original.model_dump_json())
    if not same_handler_body(state, handler) or trigger not in ("asset_damage", "helpless"):
        raise ValueError(
            "Only a real current Handler body's actual damage/Helpless trigger uses this choice"
        )
    if not source_event or not appointment or not occurrence:
        raise ValueError(
            "Keep the actual source event, appointment and distinct trigger occurrence"
        )
    identity = str(
        uuid5(
            NAMESPACE_URL,
            "girlframe:handler-consequence:"
            + source_event
            + ":"
            + handler.token
            + ":"
            + occurrence,
        )
    )
    existing = next((x for x in state.handler_consequences if x.id == identity), None)
    requested = HandlerConsequence.model_validate(
        dict(
            id=identity,
            actor=handler,
            opponent=opponent,
            trigger=trigger,
            source_action=source_action,
            source_event=source_event,
            source_work=source_work,
            source_request=source_request,
            appointment=appointment,
        )
    )
    if existing is not None:
        if (
            existing.model_copy(
                update={
                    "state": "pending",
                    "choice": None,
                    "account": "",
                    "effect_event": None,
                    "ended_by": None,
                }
            )
            != requested
        ):
            raise ValueError("One actual damage occurrence cannot be reassigned to another person")
        return state, identity
    state.handler_consequences.append(requested)
    return state, identity


def _end(
    state: GameState,
    target: ActorRef,
    request: HandlerConsequence | HandlerFatalSource,
    source_event: str,
    account: str,
) -> GameState:
    from girlframe.engine.m3_actor_bonds import migrate_actor, migrate_helpless
    from girlframe.engine.m3_enforcer import end_grasps
    from girlframe.engine.m3_physical import interrupt_journeys

    body = body_original(state, target)
    body_refs = {
        target,
        *(
            ActorRef(kind="handler", entity=target.entity, incarnation=x.id)
            for x in state.director_contexts
            if x.active and x.handler == int(target.entity)
        ),
    }
    if not state.handler_archives:
        body_refs.add(ActorRef(kind="handler", entity=target.entity))
    ended_requests = {x.id for x in state.handler_consequences if same_handler_body(state, x.actor)}
    links = dict(
        bonds=dict(state.bonds),
        actor_bonds=[
            x.model_dump(mode="json")
            for x in state.actor_bonds
            if x.first in body_refs or x.second in body_refs
        ],
        director_contexts=[
            x.model_dump(mode="json")
            for x in state.director_contexts
            if x.handler == int(target.entity)
        ],
        legacy_alias=not state.handler_archives,
        casts=[
            x.model_dump(mode="json")
            for x in state.scene_casts
            if any(
                role.actor.kind == "handler" and role.actor.entity == target.entity
                for role in x.roles
            )
        ],
    )
    state = migrate_helpless(migrate_actor(state, target, source_event), target, source_event)
    for actual in body_refs:
        state = end_grasps(
            interrupt_journeys(state, actual, source_event, account), actual, source_event
        )
    for sheet in state.sheets.values():
        for tag in sheet.tags:
            if (
                tag.giver == int(target.entity)
                and tag.giver_actor is None
                and tag.gm_setter_appointment is None
            ):
                tag.giver_actor = target
    state.bonds = {
        key: value for key, value in state.bonds.items() if target.entity not in key.split(":")
    }
    state.handler_archives.append(
        HandlerArchive(
            id="handler-death:" + request.id,
            actor=target,
            body=body,
            source_event=source_event,
            consequence=request.id,
            account=account,
            appointment=request.appointment,
            links_json=json.dumps(links, sort_keys=True),
        )
    )
    state.handler_persona = None
    state.handler_tags, state.handler_heat = [], 0
    state.director_contexts = [
        context.model_copy(
            update={
                "active": False,
                "termination_reason": "handler_death",
                "termination_event": source_event,
                "revision": context.revision + 1,
            }
        )
        if context.handler == int(target.entity) and context.active
        else context
        for context in state.director_contexts
    ]
    state.scene_casts = [
        cast.model_copy(
            update={
                "roles": tuple(
                    x
                    for x in cast.roles
                    if not (x.actor.kind == "handler" and x.actor.entity == target.entity)
                ),
                "revision": cast.revision + 1,
            }
        )
        if any(x.actor.kind == "handler" and x.actor.entity == target.entity for x in cast.roles)
        else cast
        for cast in state.scene_casts
    ]
    state.handler_opportunities = [
        x.model_copy(update={"ended_event": source_event})
        if x.actor in body_refs and x.ended_event is None
        else x
        for x in state.handler_opportunities
    ]
    state.handler_consequences = [
        x.model_copy(
            update={"state": "ended", "ended_by": request.id, "effect_event": source_event}
        )
        if x.id != request.id and x.id in ended_requests and x.state == "pending"
        else x
        for x in state.handler_consequences
    ]
    return state


def apply(
    original: GameState, identity: str, choice: Choice, account: str, source_event: str
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    request = next((x for x in state.handler_consequences if x.id == identity), None)
    if request is None or request.state != "pending" or not same_handler_body(state, request.actor):
        raise ValueError("Resume the actual original Handler body's pending source consequence")
    if not account.strip() or len(account) > 1200 or not source_event:
        raise ValueError("Describe the actual offered opening, persistent injury or death")
    if choice == "injury":
        state.handler_injuries.append(
            HandlerInjury(
                id="injury:" + identity,
                actor=request.actor,
                consequence=identity,
                description=account.strip(),
                source_event=source_event,
            )
        )
    elif choice in ("opportunity", "chance_to_act", "weakness"):
        state.handler_opportunities.append(
            HandlerOpportunity(
                id="opportunity:" + identity,
                actor=request.actor,
                beneficiary=request.opponent,
                consequence=identity,
                kind=choice,
                description=account.strip(),
                source_event=source_event,
            )
        )
    elif choice == "death":
        current = active_handler(state)
        assert current is not None
        state = _end(state, current, request, source_event, account.strip())
    else:
        raise ValueError("Choose an actual printed Handler Assets replacement effect")
    state.handler_consequences = [
        x.model_copy(
            update={
                "state": "resolved",
                "choice": choice,
                "account": account.strip(),
                "effect_event": source_event,
            }
        )
        if x.id == identity
        else x
        for x in state.handler_consequences
    ]
    return GameState.model_validate_json(state.model_dump_json())


def force_end(original: GameState, fatal: HandlerFatalSource) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    if not same_handler_body(state, fatal.actor) or any(
        x.id == fatal.id for x in state.handler_fatal_sources
    ):
        raise ValueError("Use this actual current original Handler and its distinct fatal source")
    current = active_handler(state)
    assert current is not None
    state.handler_fatal_sources.append(fatal)
    return GameState.model_validate_json(
        _end(state, current, fatal, fatal.source_event, fatal.account).model_dump_json()
    )
