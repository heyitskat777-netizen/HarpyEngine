"""The ordinary Warboy's pronouns are a printed modifier, with scoped uses."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import bond_ref, depth
from girlframe.engine.m3_actor_state import ActorRef, ActorView
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_ancillary import RULE as ANCILLARY
from girlframe.engine.m3_ancillary import STARTERS, find
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

RULE = "ancillary.warboy.boy"
KIND = "warboy_pronoun_used"
PRONOUNS = "he/him"


def pronouns(game: "GameService", state: GameState, ref: ActorRef) -> str | None:
    original = find(state, ref)
    if original is None or original.draft.book != "WARBOY":
        return None
    access = Access(game.store)
    if access.registry is None:
        return None
    try:
        access.registry.require_available(ANCILLARY)
        access.registry.require_available(STARTERS["WARBOY"].rule)
        access.require_specialist_rule(RULE)
    except (ValueError, WorkflowError):
        return None
    return PRONOUNS


def identifier(actor: ActorRef) -> str:
    return "warboy-pronouns:" + actor.token


def observed(game: "GameService", state: GameState, actor: ActorView) -> bool:
    from girlframe.services.m3_consume_support import knowledge_allowed

    return bool(
        actor.rules == "ancillary"
        and pronouns(game, state, actor.ref)
        and state.world
        and knowledge_allowed(state, actor.ref)
        and any(x.id == actor.ref.entity and x.revealed and x.alive for x in state.world.pilots)
    )


def available(state: GameState, actor: ActorRef, scene: str) -> bool:
    return not any(
        x.get("kind") == KIND and x.get("actor") == actor.token and x.get("scene") == scene
        for x in state.facts
    )


def amount(
    game: "GameService",
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    target: ActorView,
    proposer: ActorRef | None,
    controller: int,
    direction: int | None,
    account: str,
) -> int:
    if proposer is None or controller == target.controller or direction not in (-1, 1):
        raise WorkflowError("Use another actual co-present role and an ordinary Tag direction.")
    actor = resolve(state, proposer, profiles(c, game.store.campaign_id))
    if (
        not observed(game, state, target)
        or not available(state, target.ref, action["scene_id"])
        or actor.controller != controller
        or actor.cell is None
        or target.cell != actor.cell
        or actor.offstage_source
        or target.offstage_source
        or not account.strip()
    ):
        raise WorkflowError("This original character's pronouns are unavailable as a Tag.")
    strength = 2 if depth(state, bond_ref(state, target.ref), bond_ref(state, proposer)) else 1
    return direction * strength


def mark(state: GameState, action: dict[str, Any], actor: ActorRef) -> None:
    if not available(state, actor, action["scene_id"]):
        raise WorkflowError("Those pronouns have already been used in the original scene.")
    state.facts.append(
        dict(
            kind=KIND,
            actor=actor.token,
            scene=action["scene_id"],
            action=action["id"],
            pronouns=PRONOUNS,
        )
    )
