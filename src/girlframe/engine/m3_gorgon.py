"""Actual Gorgon actions; this first consumer covers the ordinary NPC Attack branch."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_world import update


class NpcAttack(Model):
    attacker: ActorRef
    target: ActorRef
    assets: tuple[str, ...] = Field(min_length=1, max_length=25)
    attacker_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    target_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    account: str = Field(min_length=1, max_length=1200)
    trigger_confirmed: Literal[True]

    @model_validator(mode="after")
    def actual_roles(self) -> "NpcAttack":
        if (
            self.attacker.kind != "gorgon"
            or self.target.kind != "npc"
            or len(set(self.assets)) != len(self.assets)
            or any(not x.strip() for x in self.assets)
            or not self.account.strip()
        ):
            raise ValueError("Choose a real Gorgon, NPC, distinct actual Assets and attack account")
        return self


def eligible(state: GameState, attacker: ActorRef, target: ActorRef) -> None:
    """Bounded implemented branch; unsupported mandatory consequences are never waived."""
    if attacker.kind != "gorgon" or target.kind != "npc" or state.world is None:
        raise ValueError("This Attack branch requires an actual Gorgon and ordinary NPC")
    first, second = resolve(state, attacker, ()), resolve(state, target, ())
    gorgon = next(x for x in state.world.gorgons if x.id == attacker.entity)
    if gorgon.gorgon_class == "benevolent":
        raise ValueError("A Benevolent Gorgon will not Attack or cause Collateral Damage")
    if gorgon.gorgon_class == "dormant":
        raise ValueError("UNSUPPORTED_RULE: the actual dormancy/awakening response needs its port")
    if any(
        study.protected
        and study.manager == target.entity
        and any(
            site.id == study.location
            and study.zone in site.protection_sources
            and site.cell == second.cell
            for site in state.world.locations
        )
        for study in state.world.field_studies
    ):
        raise ValueError("Break the actual quarantine before attacking its protected study manager")
    if "director" in second.jobs:
        raise ValueError(
            "UNSUPPORTED_RULE: this Director's death needs its own replacement resolver"
        )
    if first.cell is None or second.cell is None or first.cell != second.cell:
        raise ValueError(
            "UNSUPPORTED_RULE: this branch covers co-located targets; ranged reach needs review"
        )
    if not any(not x.damaged for x in first.assets):
        raise ValueError("The Gorgon needs an undamaged actual Asset for its Attack")


def attack_npc(original: GameState, attack: NpcAttack, source_event: str) -> GameState:
    attack = NpcAttack.model_validate_json(attack.model_dump_json())
    state = GameState.model_validate_json(original.model_dump_json())
    eligible(state, attack.attacker, attack.target)
    first, second = (resolve(state, ref, ()) for ref in (attack.attacker, attack.target))
    if (
        first.source_sha256 != attack.attacker_sha256
        or second.source_sha256 != attack.target_sha256
    ):
        raise ValueError("STALE_ATTACK: review the actual Gorgon and NPC again")
    if not set(attack.assets) <= {x.id for x in first.assets if not x.damaged}:
        raise ValueError("Attack using only the Gorgon's actual undamaged Assets")
    if not source_event.strip() or any(x.get("source_event") == source_event for x in state.facts):
        raise ValueError("An actual Attack needs one new source event")
    assert state.world is not None
    state.world = update(
        state.world,
        npcs=tuple(
            x.model_copy(update={"alive": False}) if x.id == attack.target.entity else x
            for x in state.world.npcs
        ),
    )
    state.facts.append(
        {
            "kind": "gorgon_attack_npc",
            "source_event": source_event,
            "attack": attack.model_dump_json(),
        }
    )
    return state
