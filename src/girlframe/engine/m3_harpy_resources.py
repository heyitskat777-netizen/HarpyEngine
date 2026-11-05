"""One read/write view over actual Harpy Assets and source-owned carried objects."""

from collections.abc import Sequence

from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_void_state import HarpyAsset, HarpyState
from girlframe.engine.m3_world_state import Asset

HarpyResource = AssetState | HarpyAsset | Asset
_MUTABLE = {"damaged", "void", "description"}


def _base(state: GameState, actor: ActorRef) -> tuple[HarpyAsset, ...] | tuple[Asset, ...]:
    from girlframe.engine.m3_harpy_defeat import harpy

    body = harpy(state, actor)
    if isinstance(body, HarpyState):
        return body.assets
    assert state.world is not None
    return next(x.assets for x in state.world.pilots if x.id == actor.entity)


def assets(state: GameState, actor: ActorRef) -> tuple[HarpyResource, ...]:
    """Union existing authorities; a carried Asset never becomes a second body slot."""
    from girlframe.engine.m3_items import actual_asset, same_holder

    result: list[HarpyResource] = list(_base(state, actor))
    result.extend(
        actual
        for item in state.held_items
        if same_holder(state, item.holder, actor)
        and (actual := actual_asset(state, item)) is not None
    )
    if len({x.id for x in result}) != len(result):
        raise ValueError("Recover the Harpy's unique actual Asset origins; do not double count")
    return tuple(result)


def set_assets(
    original: GameState,
    actor: ActorRef,
    values: Sequence[HarpyResource],
    *,
    event: str,
) -> GameState:
    """Change only damage/corruption/description at each Asset's sole existing origin."""
    from girlframe.engine.m3_items import actual_asset, same_holder

    current = assets(original, actor)
    proposed = {x.id: x for x in values}
    if (
        not event.strip()
        or len(proposed) != len(values)
        or set(proposed) != {x.id for x in current}
    ):
        raise ValueError("Keep exactly the existing actual Harpy Assets and real source event")
    for old in current:
        new = proposed[old.id]
        if type(new) is not type(old) or old.model_dump(exclude=_MUTABLE) != new.model_dump(
            exclude=_MUTABLE
        ):
            raise ValueError("Resource updates cannot add, rename, reclassify or reassign Assets")
        type(old).model_validate_json(new.model_dump_json())
    state = GameState.model_validate_json(original.model_dump_json())
    base = _base(state, actor)
    converted = next((x for x in state.harpy_states if x.id == actor.entity), None)
    if converted is not None:
        changed = converted.model_copy(update={"assets": tuple(proposed[x.id] for x in base)})
        state.harpy_states = [
            type(x).model_validate_json(changed.model_dump_json()) if x.id == actor.entity else x
            for x in state.harpy_states
        ]
    else:
        assert state.world is not None
        state.world = state.world.model_copy(
            update={
                "pilots": tuple(
                    type(pilot).model_validate_json(
                        pilot.model_copy(
                            update={"assets": tuple(proposed[x.id] for x in base)}
                        ).model_dump_json()
                    )
                    if pilot.id == actor.entity
                    else pilot
                    for pilot in state.world.pilots
                )
            }
        )
    revised = []
    for item in state.held_items:
        actual = actual_asset(state, item) if same_holder(state, item.holder, actor) else None
        replacement = proposed[actual.id] if actual is not None else None
        if replacement is not None and replacement != actual:
            item = item.model_copy(
                update={"asset_json": replacement.model_dump_json(), "state_event": event}
            )
        revised.append(item)
    state.held_items = revised
    return state
