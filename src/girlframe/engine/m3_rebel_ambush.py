"""Low Rebellion's actual surprise attack, bound to the next dispatched mission."""

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_missions import Mission

RULE = "strain.rebellion.low.5.1"
KIND = "strain_rebel_ambush"


class Ambush(Model):
    id: str
    period: str
    source: str
    handler: ActorRef
    attacker: ActorRef
    controller: int
    account: str = Field(min_length=1, max_length=1200)
    mission: str | None = None
    dispatch: str | None = None
    channel: int | None = None
    scene: str | None = None
    target: ActorRef | None = None
    opening: str | None = None
    opening_account: str = Field(default="", max_length=1200)
    action: str | None = None
    completed: str | None = None


def ambushes(state: GameState) -> tuple[Ambush, ...]:
    return tuple(
        Ambush.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def save(state: GameState, ambush: Ambush) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, ambush.id)] + [
        dict(kind=KIND, id=ambush.id, body=ambush.model_dump_json())
    ]


def attacker(state: GameState, actor: ActorRef) -> int:
    from girlframe.engine.m3_actor_resources import rebel_inventory

    world = state.world
    pilot = (
        next(
            (x for x in world.pilots if actor.kind == "external_pilot" and x.id == actor.entity),
            None,
        )
        if world
        else None
    )
    if (
        world is None
        or pilot is None
        or pilot.kind != "rebel"
        or not pilot.alive
        or pilot.custody != "free"
        or not any(x.active and x.kind == "rebel" and x.id == pilot.faction for x in world.factions)
        or rebel_inventory(state, actor) is None
        or not any(x.family == "frame" and not x.damaged for x in pilot.assets)
    ):
        raise ValueError(
            "Choose an actual active Rebel Pilot with an operating Frame and confirmed inventory"
        )
    return pilot.controller


def arm(
    state: GameState, work: str, period: str, event: str, rebel: ActorRef, account: str
) -> None:
    controller = attacker(state, rebel)
    handler = active_handler(state)
    if handler is None or controller == state.handler or any(x.id == work for x in ambushes(state)):
        raise ValueError(
            "Use an independently controlled original Rebel and the actual Strain source once"
        )
    save(
        state,
        Ambush(
            id=work,
            period=period,
            source=event,
            handler=handler,
            attacker=rebel,
            controller=controller,
            account=account,
        ),
    )


def bind(state: GameState, mission: Mission, dispatch: str) -> None:
    for ambush in ambushes(state):
        if ambush.mission is None:
            save(state, ambush.model_copy(update=dict(mission=mission.id, dispatch=dispatch)))
