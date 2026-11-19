"""Printed Ancillary traits that can modify ordinary source-bound Tag windows."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import bond_ref, depth
from girlframe.engine.m3_actor_state import ActorRef, ActorView
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_ancillary import RULE as ANCILLARY
from girlframe.engine.m3_ancillary import STARTERS, Book, find
from girlframe.engine.m3_chained_darling import RULE as DANGEROUS
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

BOY = "ancillary.warboy.boy"
PRONOUNS = "he/him"


@dataclass(frozen=True)
class Trait:
    book: Book
    rule: str
    key: str
    label: str
    consumption: str
    directions: tuple[int, ...]

    def identifier(self, actor: ActorRef) -> str:
        return self.key.replace("_", "-") + ":" + actor.token


WARBOY = Trait(
    "WARBOY",
    BOY,
    "warboy_pronouns",
    "Pronouns (" + PRONOUNS + ")",
    "warboy_pronoun_used",
    (-1, 1),
)
PILOT = Trait(
    "CHAINED DARLING",
    DANGEROUS,
    "chained_pilot",
    "Pilot",
    "chained_pilot_tag_used",
    (-1,),
)
TRAITS = {x.book: x for x in (WARBOY, PILOT)}


def approved(game: "GameService", state: GameState, actor: ActorRef) -> Trait | None:
    original = find(state, actor)
    trait = TRAITS.get(original.draft.book) if original else None
    if trait is None:
        return None
    access = Access(game.store)
    if access.registry is None:
        return None
    try:
        access.registry.require_available(ANCILLARY)
        access.registry.require_available(STARTERS[trait.book].rule)
        access.require_specialist_rule(trait.rule)
    except (ValueError, WorkflowError):
        return None
    return trait


def pronouns(game: "GameService", state: GameState, ref: ActorRef) -> str | None:
    return PRONOUNS if approved(game, state, ref) == WARBOY else None


def observed(game: "GameService", state: GameState, actor: ActorView) -> Trait | None:
    from girlframe.services.m3_consume_support import knowledge_allowed

    if (
        actor.rules != "ancillary"
        or state.world is None
        or not knowledge_allowed(state, actor.ref)
        or not any(x.id == actor.ref.entity and x.revealed and x.alive for x in state.world.pilots)
    ):
        return None
    return approved(game, state, actor.ref)


def available(state: GameState, actor: ActorRef, scene: str, trait: Trait) -> bool:
    return not any(
        x.get("kind") == trait.consumption
        and x.get("actor") == actor.token
        and x.get("scene") == scene
        for x in state.facts
    )


def amount(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    target: ActorView,
    trait: Trait,
    proposer: ActorRef | None,
    controller: int,
    direction: int | None,
    account: str,
) -> int:
    if proposer is None or controller == target.controller or direction not in trait.directions:
        raise WorkflowError("Use another actual co-present role and an allowed Tag direction.")
    actor = resolve(state, proposer, profiles(c, game.store.campaign_id))
    if (
        observed(game, state, target) != trait
        or not available(state, target.ref, action["scene_id"], trait)
        or actor.controller != controller
        or actor.cell is None
        or target.cell != actor.cell
        or actor.offstage_source
        or target.offstage_source
        or not account.strip()
    ):
        raise WorkflowError("This original character's trait is unavailable as a Tag.")
    strength = 2 if depth(state, bond_ref(state, target.ref), bond_ref(state, proposer)) else 1
    return direction * strength


def mark(state: GameState, action: dict[str, Any], actor: ActorRef, trait: Trait) -> None:
    if not available(state, actor, action["scene_id"], trait):
        raise WorkflowError("This trait has already been used in the original scene.")
    state.facts.append(
        dict(
            kind=trait.consumption,
            actor=actor.token,
            scene=action["scene_id"],
            action=action["id"],
            trait=trait.label,
        )
    )
