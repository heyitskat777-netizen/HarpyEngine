"""High Void 6.1 keeps each actual Strain roll and the arrival it requires."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_strain_state import Event
from girlframe.engine.m3_world_state import AdversaryPilot, Gorgon

RULE = "strain.void.high.6.1"
KIND = "strain_void_rift"
PAGE = 145


class Arrival(Model):
    work: str
    period: str
    roll: str
    source: str
    actor: ActorRef | None = None
    performed: str | None = None


class Rift(Model):
    id: str
    duration: int = Field(ge=1, le=6)
    rng_source: Literal["os", "test_injected"]
    arrivals: tuple[Arrival, ...]


def rifts(state: GameState) -> tuple[Rift, ...]:
    return tuple(Rift.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


def save(state: GameState, value: Rift) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.id)] + [
        dict(kind=KIND, id=value.id, body=value.model_dump_json())
    ]


def open_rift(
    state: GameState,
    selected: Event,
    source: str,
    duration: int,
    rng_source: Literal["os", "test_injected"],
) -> None:
    if selected.rule_id != RULE or any(x.id == selected.id for x in rifts(state)):
        raise ValueError("Open a rift only from its actual original High Void choice")
    arrival = Arrival(
        work=selected.id + ":effect", period=selected.period_id, roll=selected.id, source=source
    )
    save(state, Rift(id=selected.id, duration=duration, rng_source=rng_source, arrivals=(arrival,)))


def upcoming(state: GameState, roll: Event, source: str) -> tuple[tuple[str, Arrival], ...]:
    work = []
    for rift in rifts(state):
        if len(rift.arrivals) > rift.duration or any(x.roll == roll.id for x in rift.arrivals):
            continue
        identity = str(uuid5(NAMESPACE_URL, f"girlframe:void-rift:{rift.id}:{roll.id}"))
        arrival = Arrival(work=identity, period=roll.period_id, roll=roll.id, source=source)
        save(state, rift.model_copy(update={"arrivals": (*rift.arrivals, arrival)}))
        work.append((rift.id, arrival))
    return tuple(work)


def pending(state: GameState, work: str) -> tuple[Rift, Arrival]:
    if state.strain is not None:
        for rift in rifts(state):
            if not any(x.id == rift.id and x.rule_id == RULE for x in state.strain.events):
                continue
            for arrival in rift.arrivals:
                if (
                    arrival.work == work
                    and not arrival.performed
                    and any(
                        x.id == arrival.roll and x.period_id == arrival.period
                        for x in state.strain.events
                    )
                ):
                    return rift, arrival
    raise ValueError("Recover the actual rift and unfulfilled original Strain arrival")


def perform(state: GameState, work: str, actor: ActorRef, event: str) -> None:
    rift, arrival = pending(state, work)
    resolved = arrival.model_copy(update={"actor": actor, "performed": event})
    save(
        state,
        rift.model_copy(
            update={"arrivals": tuple(resolved if x.work == work else x for x in rift.arrivals)}
        ),
    )


def arrive(
    state: GameState,
    work: str,
    period: str,
    event: str,
    account: str,
    gorgon: Gorgon | None,
    harpy: AdversaryPilot | None,
    victim: str | None,
) -> GameState:
    from girlframe.engine.m3_gorgon_arrival import aggressive_casualty
    from girlframe.engine.m3_promotional_opportunity import in_responsibility
    from girlframe.engine.m3_world import introduce_gorgon, update

    _, arrival = pending(state, work)
    world = state.world
    incoming = gorgon or harpy
    if (
        world is None
        or arrival.period != period
        or incoming is None
        or (gorgon is not None and harpy is not None)
        or incoming.cell is None
        or not in_responsibility(state, incoming.cell)
        or incoming.tags
        or any(
            incoming.id == x.id
            for group in (world.gorgons, world.pilots, world.npcs, world.locations)
            for x in group
        )
        or incoming.id
        in (
            {x.id for x in state.native_harpies}
            | {x.id for x in state.harpy_states}
            | {x.id for x in state.janus_cores}
        )
    ):
        raise ValueError("Introduce one new original Gorgon or Harpy at a responsible map square")
    aggressive = gorgon is not None and gorgon.gorgon_class == "aggressive"
    if aggressive != (victim is not None):
        raise ValueError("Only an Aggressive introduction requires an actual NPC casualty")
    if gorgon is not None:
        if gorgon.position_event is not None or gorgon.flesh_layers_event is not None:
            raise ValueError("An arrival cannot import a previous placement or flesh-layer source")
        incoming_gorgon = gorgon.model_copy(update={"position_event": event})
        state.world = introduce_gorgon(world, incoming_gorgon, event=event).world
        actor = ActorRef(kind="gorgon", entity=gorgon.id)
        if aggressive:
            npc = next(
                (x for x in world.npcs if x.id == victim and x.alive and x.cell == gorgon.cell),
                None,
            )
            if npc is None:
                raise ValueError("Choose the actual living NPC at this Aggressive arrival")
            state = aggressive_casualty(state, incoming_gorgon, npc, work, event, account)
    else:
        assert harpy is not None
        if (
            harpy.kind != "harpy"
            or harpy.girl.upper() != "HARPY"
            or harpy.controller != state.handler
            or not harpy.alive
            or harpy.exposed
            or harpy.custody != "free"
            or harpy.faction is not None
            or harpy.rebel_resources_json is not None
            or not harpy.frame.strip()
            or {x.family for x in harpy.assets} != {"girl", "frame"}
            or any(x.damaged for x in harpy.assets)
        ):
            raise ValueError(
                "Introduce the source Handler's free Harpy with actual Girl and Frame components"
            )
        actor = ActorRef(kind="external_pilot", entity=harpy.id)
        if any(x.facts.actor == actor for x in state.harpy_setups):
            raise ValueError("The actual Harpy arrival must have its own new identity")
        state.world = update(world, pilots=(*world.pilots, harpy))
    perform(state, work, actor, event)
    return state
