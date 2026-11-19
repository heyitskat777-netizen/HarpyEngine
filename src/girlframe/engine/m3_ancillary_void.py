"""Nonterminal Void changes to an original Ancillary Acolyte's resources."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_ancillary import find, put
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import AdversaryPilot, Asset


def body(state: GameState, actor: ActorRef) -> AdversaryPilot | None:
    if state.world is None:
        return None
    role = find(state, actor)
    if role is None or role.draft.book != "ABYSSAL ACOLYTE":
        return None
    return next((x for x in state.world.pilots if x.id == actor.entity and x.alive), None)


def gains(state: GameState, actor: ActorRef) -> tuple[Asset, ...]:
    actual = body(state, actor)
    assets = tuple(x for x in actual.assets if x.family == "girl" and not x.void) if actual else ()
    return tuple(x for x in assets if x.battery_asset is None) if len(assets) >= 2 else ()


def set_assets(state: GameState, actor: ActorRef, assets: tuple[Asset, ...]) -> None:
    if state.world is None or body(state, actor) is None:
        raise ValueError("Recover the original Acolyte's actual Assets.")
    state.world = update(
        state.world,
        pilots=tuple(
            x.model_copy(update=dict(assets=assets)) if x.id == actor.entity else x
            for x in state.world.pilots
        ),
    )


def gain(state: GameState, actor: ActorRef, asset: str, description: str, *, unmark: bool) -> None:
    actual, role = body(state, actor), find(state, actor)
    if (
        actual is None
        or role is None
        or not 0 < len(description.strip()) <= 1200
        or not any(x.id == asset for x in gains(state, actor))
    ):
        raise ValueError("Rewrite an actual eligible uncorrupted Girl Asset.")
    set_assets(
        state,
        actor,
        tuple(
            x.model_copy(update=dict(void=True, description=description.strip()))
            if x.id == asset
            else x
            for x in actual.assets
        ),
    )
    if unmark:
        identities = tuple(
            x.model_copy(update=dict(marked=False)) if not x.protected and not x.am_limiter else x
            for x in role.identities
        )
        put(state, role.model_copy(update=dict(identities=identities)))
