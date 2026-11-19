"""A High Rebellion betrayal preserves the original NPC, Handler and rescuers."""

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_doppelganger_reveal import original_bonds
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Model, Npc

RULE = "strain.rebellion.high.3.1"
KIND = "strain_rebel_bond_attack"


class Attack(Model):
    id: str
    source: str
    period: str
    handler: ActorRef
    assassin: ActorRef
    controller: int
    faction: str
    account: str = Field(min_length=1, max_length=1200)
    cast: SceneCast | None = None
    defenders: tuple[ActorRef, ...] = ()
    attempt: str | None = None
    attempt_account: str = Field(default="", max_length=1200)
    defense: str | None = None
    finished: str | None = None


def attacks(state: GameState) -> tuple[Attack, ...]:
    return tuple(
        Attack.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def save(state: GameState, value: Attack) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.id)] + [
        dict(kind=KIND, id=value.id, body=value.model_dump_json())
    ]


def actor(state: GameState, identity: str, *, alive: bool = True) -> Npc:
    npc = next((x for x in state.world.npcs if x.id == identity), None) if state.world else None
    if (
        npc is None
        or alive
        and not npc.alive
        or npc.captive_of is not None
        or npc.source_kind is not None
        or "director" in npc.jobs
        or npc.controller == state.handler
    ):
        raise ValueError("Choose a living ordinary NPC under independent control")
    return npc


def arm(
    state: GameState, work: str, period: str, event: str, identity: str, faction: str, account: str
) -> None:
    handler = active_handler(state)
    npc = actor(state, identity)
    world = state.world
    if (
        handler is None
        or world is None
        or not original_bonds(state, npc)
        or not any(x.id == faction and x.kind == "rebel" and x.active for x in world.factions)
        or any(
            x.id == work or x.assassin.entity == identity and not x.finished for x in attacks(state)
        )
    ):
        raise ValueError("Use an original living Bond and an actual active Rebel Group")
    state.world = update(
        world,
        npcs=tuple(
            x.model_copy(
                update=dict(secret_factions=tuple(dict.fromkeys((*x.secret_factions, faction))))
            )
            if x.id == npc.id
            else x
            for x in world.npcs
        ),
    )
    save(
        state,
        Attack(
            id=work,
            source=event,
            period=period,
            handler=handler,
            assassin=ActorRef(kind="npc", entity=npc.id),
            controller=npc.controller,
            faction=faction,
            account=account,
        ),
    )
