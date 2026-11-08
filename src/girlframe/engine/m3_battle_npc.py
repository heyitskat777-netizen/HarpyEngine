"""Printed NPC Conversation moves usable as an actual, scoped Core counter.

PDF188–191 describe these as guidelines, not a second numerical combat system.
Only moves with wholly conversational effects are listed here. Mechanical moves
use their own real resource services and are not mislabelled narrative damage.
"""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

NARRATIVE = {
    "base_personnel": ("Keep things running", 189),
    "civilian": ("Avoid eye contact", 189),
    "creep": ("Make a lewd comment", 189),
    "doctor": ("Record something on your notepad", 190),
    "ex_pilot": ("Give tired advice", 190),
    "family": ("Make an impossible demand", 190),
    "fan": ("Ask a violating question with stars in your eyes", 190),
    "guard": ("Step in the way", 190),
    "handler": ("Gloat", 190),
    "intelligence_agent": ("Give a fake name, job, or goal", 190),
    "journalist": ("Take a picture that's going to get you in trouble", 190),
    "mechanic": ("Crack a joke", 191),
    "patron": ("Ask for an uncomfortable favour from the Girls", 191),
    "pilot_candidate": ("Overestimate yourself", 191),
    "prisoner": ("Perform a pointless act of defiance", 191),
    "protestor": ("Shout slogans", 191),
    "psychologist": ("Ask a probing question", 191),
    "public_relations": ("Smooth things over", 191),
    "scientist": ("Justify your actions", 191),
    "smuggler": ("Sneer", 191),
}


# A Flirt escape price is the NPC's own real consequence, not a second attack.
SELF_SOURCE = "npc_flirt_escape"
SELF_EFFECTS = ("injure_tag", "move", "kill")


def escape_damage_id(damage: str) -> str:
    return str(uuid5(NAMESPACE_URL, "npc-flirt-escape-damage:" + damage))


class FlirtSelfDamage(Model):
    id: str
    source_kind: Literal["npc_flirt_escape"] = "npc_flirt_escape"
    damage: str
    action: str
    choice: str
    npc: ActorRef
    controller: int
    cast: SceneCast
    event: str


def self_damage(state: GameState, identity: str) -> FlirtSelfDamage:
    values = [
        FlirtSelfDamage.model_validate_json(value["body"])
        for value in state.facts
        if value.get("kind") == "npc_flirt_self_damage" and value.get("id") == identity
    ]
    if len(values) != 1:
        raise ValueError("Recover the exact actual NPC Flirt self-cost")
    return values[0]
