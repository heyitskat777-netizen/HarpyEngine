"""A bonded NPC's contact, decision and exact Off-Duty deadline."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_doppelganger_reveal import original_bonds
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Cell

RULE = "strain.rebellion.low.6.2"
KIND = "strain_rebel_defection"


class Case(Model):
    id: str
    source_event: str
    period: str
    npc: str
    controller: int
    faction: str
    rebel: str
    rebel_controller: int
    bonds: tuple[ActorRef, ...]
    contact: str = Field(min_length=1, max_length=1200)
    known_name: str
    known_jobs: tuple[str, ...]
    known_cell: Cell
    report_event: str | None = None
    stay_scene: str | None = None
    stay_account: str | None = None
    resolved_event: str | None = None
    outcome: Literal["stayed", "defected", "prevented"] | None = None


def cases(state: GameState) -> tuple[Case, ...]:
    return tuple(Case.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


def put(state: GameState, case: Case) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, case.id)] + [
        dict(kind=KIND, id=case.id, body=case.model_dump_json())
    ]


def audience(state: GameState, case: Case, user: int) -> tuple[bool, bool]:
    if state.world is None:
        return False, False
    return (
        user == case.controller
        and any(x.id == case.npc and x.controller == user for x in state.world.npcs),
        user == case.rebel_controller
        and case.report_event is not None
        and any(x.id == case.rebel and x.alive and x.controller == user for x in state.world.npcs),
    )


def contact(
    state: GameState,
    *,
    identity: str,
    event: str,
    period: str,
    target: str | None,
    group: str | None,
    recipient: str | None,
    account: str,
) -> None:
    world = state.world
    if world is None or state.strain is None:
        raise ValueError("Recover the actual map and preparing Strain cycle")
    npc = next((x for x in world.npcs if x.id == target), None)
    rebel = next((x for x in world.npcs if x.id == recipient), None)
    if (
        npc is None
        or not npc.alive
        or npc.captive_of is not None
        or npc.faction == group
        or group in npc.secret_factions
        or rebel is None
        or not rebel.alive
        or rebel.captive_of is not None
        or rebel.faction != group
        or not any(x.id == group and x.kind == "rebel" and x.active for x in world.factions)
        or any(x.id == identity or (x.npc == target and x.outcome is None) for x in cases(state))
    ):
        raise ValueError(
            "Choose the original uncommitted Bond and a member of the active Rebel Group"
        )
    assert group is not None
    bonds = original_bonds(state, npc)
    if not bonds:
        raise ValueError("The contacted NPC must hold an actual current Bond")
    put(
        state,
        Case(
            id=identity,
            source_event=event,
            period=period,
            npc=npc.id,
            controller=npc.controller,
            faction=group,
            rebel=rebel.id,
            rebel_controller=rebel.controller,
            bonds=bonds,
            contact=account,
            known_name=npc.name,
            known_jobs=npc.jobs,
            known_cell=npc.cell,
        ),
    )


def settle(state: GameState, period: str, event: str) -> None:
    for case in cases(state):
        if case.period != period or case.outcome is not None:
            continue
        world = state.world
        assert world is not None and state.strain is not None
        npc = next((x for x in world.npcs if x.id == case.npc), None)
        faction = next((x for x in world.factions if x.id == case.faction), None)
        actor = next((x for x in world.npcs if x.id == case.rebel), None)
        if npc is None:
            raise ValueError("Recover the original contacted Bond before its deadline")
        if not npc.alive or npc.captive_of is not None or faction is None or not faction.active:
            put(state, case.model_copy(update=dict(outcome="prevented", resolved_event=event)))
            continue
        if (
            actor is None
            or not actor.alive
            or actor.captive_of is not None
            or actor.faction != case.faction
            or actor.controller != case.rebel_controller
            or npc.controller != case.controller
        ):
            raise ValueError("Recover the original defection and actual Rebel contact authority")
        state.world = update(
            world,
            npcs=tuple(
                x.model_copy(update=dict(faction=case.faction)) if x.id == npc.id else x
                for x in world.npcs
            ),
        )
        state.strain = state.strain.model_copy(
            update={"levels": state.strain.levels | {"rebellion": "high"}}
        )
        put(
            state,
            case.model_copy(
                update=dict(outcome="defected", report_event=event, resolved_event=event)
            ),
        )
