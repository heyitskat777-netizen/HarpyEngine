"""Actual Gorgon Asset contests and separately confirmed Core exposure."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_world import expose_gorgon, update


class Contest(Model):
    attacker: ActorRef
    defender: ActorRef
    attacking_assets: tuple[str, ...] = Field(min_length=1, max_length=25)
    defending_assets: tuple[str, ...] = Field(min_length=1, max_length=25)
    attacker_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    defender_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    winner: Literal["attacker", "defender"]
    losing_asset: str = Field(min_length=1)
    approach: Literal["direct", "indirect"]
    account: str = Field(min_length=1, max_length=1200)
    trigger_confirmed: Literal[True]

    @model_validator(mode="after")
    def actual_contest(self) -> "Contest":
        if (
            self.attacker.kind != "gorgon"
            or self.defender.kind != "gorgon"
            or self.attacker == self.defender
            or len(set(self.attacking_assets)) != len(self.attacking_assets)
            or len(set(self.defending_assets)) != len(self.defending_assets)
            or not self.account.strip()
        ):
            raise ValueError("Pit two distinct actual Gorgons and their distinct actual Assets")
        return self


class Exposure(Model):
    actor: ActorRef
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    account: str = Field(min_length=1, max_length=1200)
    weakness_confirmed: Literal[True]

    @model_validator(mode="after")
    def actual_weakness(self) -> "Exposure":
        if self.actor.kind != "gorgon" or not self.account.strip():
            raise ValueError("Confirm the actual Gorgon and its actual conversational weakness")
        return self


def eligible(state: GameState, attacker: ActorRef, defender: ActorRef) -> None:
    if (
        state.world is None
        or attacker.kind != "gorgon"
        or defender.kind != "gorgon"
        or attacker == defender
    ):
        raise ValueError("This branch requires two distinct actual Gorgons")
    first, second = (resolve(state, ref, ()) for ref in (attacker, defender))
    for ref in (attacker, defender):
        gorgon = next(x for x in state.world.gorgons if x.id == ref.entity)
        if gorgon.gorgon_class == "dormant":
            raise ValueError("UNSUPPORTED_RULE: resolve the actual dormancy/awakening interaction")
    original = next(x for x in state.world.gorgons if x.id == attacker.entity)
    if original.gorgon_class == "benevolent":
        raise ValueError("A Benevolent Gorgon will not initiate an Attack")
    if first.cell is None or second.cell is None or first.cell != second.cell:
        raise ValueError("UNSUPPORTED_RULE: this contest branch covers co-located Gorgons")
    if any(not any(not x.damaged for x in actor.assets) for actor in (first, second)):
        raise ValueError("Each actual Gorgon needs an undamaged Asset to pit in this contest")


def _source(state: GameState, event: str) -> None:
    if not event.strip() or any(x.get("source_event") == event for x in state.facts):
        raise ValueError("Use one new actual combat source event")


def contest(original: GameState, choice: Contest, event: str) -> GameState:
    choice = Contest.model_validate_json(choice.model_dump_json())
    state = GameState.model_validate_json(original.model_dump_json())
    eligible(state, choice.attacker, choice.defender)
    first, second = (resolve(state, ref, ()) for ref in (choice.attacker, choice.defender))
    if (
        first.source_sha256 != choice.attacker_sha256
        or second.source_sha256 != choice.defender_sha256
    ):
        raise ValueError("STALE_CONTEST: review both actual Gorgons and their Assets")
    for actor, selected in ((first, choice.attacking_assets), (second, choice.defending_assets)):
        if not set(selected) <= {x.id for x in actor.assets if not x.damaged}:
            raise ValueError("Pit only each Gorgon's actual undamaged owned Assets")
    loser = choice.defender if choice.winner == "attacker" else choice.attacker
    selected = choice.defending_assets if choice.winner == "attacker" else choice.attacking_assets
    if choice.losing_asset not in selected:
        raise ValueError("Destroy one Asset actually pitted by the losing Gorgon")
    assert state.world is not None
    target = next(x for x in state.world.gorgons if x.id == loser.entity)
    if choice.approach == "direct" and any(
        x.id == target.protected_asset and not x.damaged for x in target.assets
    ):
        raise ValueError("The Directed protective Asset cannot be overcome by direct attack")
    _source(state, event)
    asset = next(x for x in target.assets if x.id == choice.losing_asset)
    changed = target.model_copy(
        update={
            "assets": tuple(x for x in target.assets if x.id != asset.id),
            "destroyed_assets": (*target.destroyed_assets, asset),
        }
    )
    state.world = update(
        state.world, gorgons=tuple(changed if x.id == target.id else x for x in state.world.gorgons)
    )
    state.facts.append(
        {"kind": "gorgon_asset_contest", "source_event": event, "contest": choice.model_dump_json()}
    )
    return state


def expose(original: GameState, choice: Exposure, event: str) -> GameState:
    choice = Exposure.model_validate_json(choice.model_dump_json())
    state = GameState.model_validate_json(original.model_dump_json())
    actor = resolve(state, choice.actor, ())
    if actor.offstage_source is not None:
        raise ValueError("OFFSTAGE_RIFT: this actual Gorgon must return before map Core exposure")
    if actor.source_sha256 != choice.source_sha256:
        raise ValueError("STALE_CORE: review the actual Gorgon and Core plan")
    _source(state, event)
    assert state.world is not None
    state.world = expose_gorgon(state.world, choice.actor.entity, choice.account)
    state.facts.append(
        {"kind": "gorgon_core_exposed", "source_event": event, "exposure": choice.model_dump_json()}
    )
    return state
