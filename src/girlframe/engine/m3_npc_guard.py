"""Printed Guard moves and explicit weapon facts over original bodies and objects."""

import hashlib
import json
from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_harpy_defeat import offstage_travel
from girlframe.engine.m3_item_state import HeldItem

Move = Literal["manhandle", "interpose", "draw_weapon"]
MOVES: tuple[tuple[str, str], ...] = (
    ("manhandle", "Manhandle the actual opponent"),
    ("interpose", "Step into the actual opponent's way"),
    ("draw_weapon", "Draw an actual carried weapon"),
)


class Weapons(Model):
    id: str = Field(min_length=1)
    actor: ActorRef
    npc_sha256: str
    inventory_sha256: str
    unarmed: bool
    scene: str
    controller: int
    event: str
    account: str = Field(min_length=1, max_length=1200)


class Performed(Model):
    event: str
    parent: str
    choice: str
    actor: ActorRef
    opponent: ActorRef
    move: Move
    scene: SceneCast
    controller: int
    weapon: str | None = None
    account: str = Field(min_length=1, max_length=1200)


def supported(state: GameState, npc: ActorRef, attacker: ActorRef, cast: SceneCast) -> bool:
    if npc.kind != "npc" or attacker.kind != "pilot" or not cast.open or state.world is None:
        return False
    body = next(
        (x for x in state.world.npcs if x.id == npc.entity and x.alive and "guard" in x.jobs), None
    )
    sheet = state.sheets.get(attacker.entity)
    placed = next((x for x in state.placements if x.actor == attacker), None)
    judge = (
        next((x.controller for x in cast.roles if x.actor == cast.adjudicator), None)
        if cast.adjudicator
        else cast.facilitator
    )
    if (
        body is None
        or sheet is None
        or sheet.character_id != attacker.incarnation
        or sheet.owner not in state.order
        or placed is None
        or placed.mode != "outside_frame"
        or placed.girl_cell is None
        or judge != body.controller
        or not any(x.actor == npc and x.controller == body.controller for x in cast.roles)
        or not any(x.actor == attacker and x.controller == sheet.owner for x in cast.roles)
        or offstage_travel(state, attacker) is not None
        or any(x.active and attacker in (x.traveler, x.supervisor) for x in state.escort_journeys)
    ):
        return False
    try:
        actual = resolve(state, npc, ())
    except ValueError:
        return False
    return (
        actual.cell == placed.girl_cell
        and actual.cell is not None
        and actual.rules == "npc"
        and not actual.offstage_source
        and actual.custody in (None, "free")
    )


def weapons(state: GameState, npc: ActorRef) -> tuple[HeldItem, ...]:
    return tuple(
        x
        for x in state.held_items
        if x.holder == npc and x.weapon and x.condition == "intact" and x.location_mode == "carried"
    )


def inventory_sha(state: GameState, npc: ActorRef) -> str:
    objects = sorted(
        (x.model_dump(mode="json") for x in state.held_items if x.holder == npc),
        key=lambda x: x["id"],
    )
    return hashlib.sha256(json.dumps(objects, sort_keys=True).encode()).hexdigest()


def assessment(state: GameState, npc: ActorRef) -> Weapons | None:
    actual = resolve(state, npc, ())
    for fact in reversed(state.facts):
        if fact.get("kind") != "npc_guard_weapons":
            continue
        value = Weapons.model_validate_json(fact["body"])
        if (
            value.actor == npc
            and value.npc_sha256 == actual.source_sha256
            and value.inventory_sha256 == inventory_sha(state, npc)
        ):
            return value
    return None


def unarmed(state: GameState, npc: ActorRef) -> bool:
    value = assessment(state, npc)
    return bool(value and value.unarmed and not weapons(state, npc))
