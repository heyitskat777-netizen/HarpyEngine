"""Low Void 6.1 ties an actual orbital attacker to the next dispatched mission."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_strain_state import Trigger
from girlframe.engine.m3_world import destroy, introduce_gorgon
from girlframe.engine.m3_world_state import Gorgon, Model

RULE = "strain.void.low.6.1"
KIND = "orbital_threat"


class Threat(Model):
    id: str
    period: str
    source_event: str
    gorgon: str
    location: str
    account: str = Field(min_length=1, max_length=2400)
    mission: str | None = None
    dispatch_event: str | None = None
    outcome: Literal["averted", "destroyed", "already_lost"] | None = None
    resolved_event: str | None = None


def threats(state: GameState) -> tuple[Threat, ...]:
    return tuple(
        Threat.model_validate_json(fact["body"]) for fact in state.facts if fact.get("kind") == KIND
    )


def save(state: GameState, value: Threat) -> None:
    state.facts = [
        fact for fact in state.facts if (fact.get("kind"), fact.get("id")) != (KIND, value.id)
    ] + [dict(kind=KIND, id=value.id, body=value.model_dump_json())]


def introduce(
    state: GameState,
    gorgon: Gorgon,
    identity: str,
    period: str,
    event: str,
    account: str,
) -> None:
    from girlframe.engine.m3_promotional_opportunity import in_responsibility

    world = state.world
    goal = gorgon.goal
    if (
        world is None
        or gorgon.gorgon_class != "directed"
        or gorgon.cell is not None
        or gorgon.position_event is not None
        or goal is None
        or goal.kind != "location"
        or not any(
            site.id == goal.entity_id
            and site.condition != "destroyed"
            and in_responsibility(state, site.cell)
            for site in world.locations
        )
        or any(value.id == identity for value in threats(state))
    ):
        raise ValueError("Choose a new Directed Gorgon in orbit over a surviving location")
    assert goal.entity_id is not None
    state.world = introduce_gorgon(world, gorgon, event=event).world
    save(
        state,
        Threat(
            id=identity,
            period=period,
            source_event=event,
            gorgon=gorgon.id,
            location=goal.entity_id,
            account=account,
        ),
    )


def dispatch(state: GameState, mission: str, event: str) -> None:
    for value in threats(state):
        if value.mission is None:
            save(state, value.model_copy(update={"mission": mission, "dispatch_event": event}))


def settle(state: GameState, mission: str, event: str) -> bool:
    """Return whether this ending event actually destroyed a new location."""
    destroyed = False
    for value in threats(state):
        if value.mission != mission or value.outcome is not None:
            continue
        world = state.world
        assert world is not None and state.strain is not None
        gorgon = next((x for x in world.gorgons if x.id == value.gorgon), None)
        site = next((x for x in world.locations if x.id == value.location), None)
        if gorgon is None or site is None:
            raise ValueError("Recover the original orbital attacker and location")
        outcome: Literal["averted", "destroyed", "already_lost"]
        if not gorgon.alive:
            outcome = "averted"
        elif site.condition == "destroyed":
            outcome = "already_lost"
        else:
            if (
                gorgon.gorgon_class != "directed"
                or gorgon.goal is None
                or (gorgon.goal.kind, gorgon.goal.entity_id) != ("location", site.id)
            ):
                raise ValueError("Review the actual redirection of the orbital threat")
            result = destroy(world, site.id, gorgon_cause=True)
            if any(x.id == site.id and x.condition != "destroyed" for x in result.world.locations):
                raise ValueError("Review the orbital strike against this site's actual protection")
            state.world = result.world
            trigger = Trigger(
                id=value.id + ":structure",
                kind="structure_destroyed",
                entity=site.id,
                source_event=event,
            )
            state.strain = state.strain.model_copy(
                update={"triggers": state.strain.triggers + (trigger,)}
            )
            outcome = "destroyed"
            destroyed = True
        save(state, value.model_copy(update={"outcome": outcome, "resolved_event": event}))
    return destroyed
