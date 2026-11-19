"""The new Rebel Group destroys the original and takes its actual Pilots."""

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_alpha_state import Broken
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Faction

RULE = "strain.rebellion.endgame.8"
KIND = "rebel_group_takeover"


class Prisoner(Model):
    actor: ActorRef
    captor: ActorRef
    source: str
    scene: str
    account: str = Field(min_length=1, max_length=1200)
    broken: str | None = None
    breaking_account: str = Field(default="", max_length=1200)


class Takeover(Model):
    id: str
    source: str
    period: str
    handler: ActorRef
    original: Faction
    replacement: Faction
    organization: str
    pilots: tuple[ActorRef, ...]
    prisoners: tuple[Prisoner, ...] = ()
    completed: str | None = None


def takeovers(state: GameState) -> tuple[Takeover, ...]:
    return tuple(
        Takeover.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def save(state: GameState, value: Takeover) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.id)] + [
        dict(kind=KIND, id=value.id, body=value.model_dump_json())
    ]


def complete(state: GameState, value: Takeover, event: str) -> Takeover:
    world = state.world
    if (
        world is None
        or value.original not in world.factions
        or value.completed
        or {x.actor for x in value.prisoners} != set(value.pilots)
        or any(
            not x.broken
            or not any(
                pilot.id == x.actor.entity
                and pilot.alive
                and pilot.custody == "captured"
                and pilot.custody_event == x.source
                for pilot in world.pilots
            )
            or not any(
                effect.source_work == value.id
                and effect.source_event == x.broken
                and effect.subject == x.actor
                and effect.inflictor == x.captor
                and not effect.removed_event
                for effect in state.alpha_broken
            )
            for x in value.prisoners
        )
    ):
        raise ValueError(
            "Resolve the original living Rebel Pilots' actual capture and breaking first"
        )
    state.world = update(
        world,
        factions=tuple(
            x.model_copy(update=dict(active=False)) if x.id == value.original.id else x
            for x in world.factions
        ),
    )
    result = value.model_copy(update=dict(completed=event))
    save(state, result)
    return result


def organize(state: GameState, value: Takeover) -> Takeover:
    world = state.world
    if (
        world is None
        or value.original not in world.factions
        or not value.original.active
        or value.original.kind != "rebel"
        or value.replacement.kind != "rebel"
        or not value.replacement.active
        or not same_handler_body(state, value.handler)
        or any(
            x.id == value.replacement.id or x.name == value.replacement.name for x in world.factions
        )
        or any(x.id == value.id for x in takeovers(state))
    ):
        raise ValueError("Write up the distinct actual new Rebel Group for this original takeover")
    state.world = update(world, factions=(*world.factions, value.replacement))
    if not value.pilots:
        return complete(state, value, value.organization)
    save(state, value)
    return value


def capture(state: GameState, value: Takeover, prisoner: Prisoner, controller: int) -> Takeover:
    world = state.world
    pilot = (
        next((x for x in world.pilots if x.id == prisoner.actor.entity), None) if world else None
    )
    if (
        world is None
        or pilot is None
        or pilot.kind != "rebel"
        or not pilot.alive
        or pilot.faction != value.original.id
        or pilot.custody != "free"
        or value.completed
        or prisoner.actor not in value.pilots
        or any(x.actor == prisoner.actor for x in value.prisoners)
        or not any(x.id == value.replacement.id and x.active for x in world.factions)
    ):
        raise ValueError(
            "Capture the actual original free Pilot once under the new group's custody"
        )
    state.world = update(
        world,
        pilots=tuple(
            x.model_copy(
                update=dict(custody="captured", custodian=controller, custody_event=prisoner.source)
            )
            if x.id == pilot.id
            else x
            for x in world.pilots
        ),
    )
    changed = value.model_copy(update=dict(prisoners=(*value.prisoners, prisoner)))
    save(state, changed)
    return changed


def break_pilot(
    state: GameState, value: Takeover, prisoner: Prisoner, event: str, account: str
) -> Takeover:
    world = state.world
    if (
        world is None
        or prisoner not in value.prisoners
        or prisoner.broken
        or value.completed
        or not any(
            x.id == prisoner.actor.entity
            and x.alive
            and x.custody == "captured"
            and x.custody_event == prisoner.source
            for x in world.pilots
        )
    ):
        raise ValueError("Break only the actual original living captive from this takeover")
    state.alpha_broken.append(
        Broken(
            id="rebel-takeover:" + value.id + ":" + prisoner.actor.token,
            subject=prisoner.actor,
            inflictor=prisoner.captor,
            source_work=value.id,
            source_event=event,
        )
    )
    changed = value.model_copy(
        update=dict(
            prisoners=tuple(
                x.model_copy(update=dict(broken=event, breaking_account=account))
                if x == prisoner
                else x
                for x in value.prisoners
            )
        )
    )
    if len(changed.prisoners) == len(changed.pilots) and all(x.broken for x in changed.prisoners):
        return complete(state, changed, event)
    save(state, changed)
    return changed
