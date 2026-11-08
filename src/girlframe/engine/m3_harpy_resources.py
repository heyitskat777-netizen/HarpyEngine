"""One read/write view over actual Harpy Assets and source-owned carried objects."""

from collections.abc import Sequence

from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_item_state import HeldItem
from girlframe.engine.m3_void_state import HarpyAsset, HarpyState
from girlframe.engine.m3_world_state import Asset

HarpyResource = AssetState | HarpyAsset | Asset
_MUTABLE = {"damaged", "void", "description"}


def _base(state: GameState, actor: ActorRef) -> tuple[HarpyResource, ...]:
    from girlframe.engine.m3_harpy_defeat import harpy
    from girlframe.engine.m3_janus import base_assets, find

    if find(state, actor) is not None:
        return base_assets(state, actor)
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
        and item.location_mode == "carried"
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
    from girlframe.engine.m3_janus import find, set_base_assets

    if find(state, actor) is not None:
        core_assets = tuple(
            selected
            for x in base
            if isinstance(selected := proposed[x.id], (HarpyAsset, AssetState))
        )
        if len(core_assets) != len(base):
            raise ValueError("JANUS resources must retain their actual Core/Frame types")
        state = set_base_assets(state, actor, core_assets, event=event)
    elif converted is not None:
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
        actual = (
            actual_asset(state, item)
            if (same_holder(state, item.holder, actor) and item.location_mode == "carried")
            else None
        )
        replacement = proposed[actual.id] if actual is not None else None
        if replacement is not None and replacement != actual:
            item = item.model_copy(
                update={"asset_json": replacement.model_dump_json(), "state_event": event}
            )
        revised.append(item)
    state.held_items = revised
    return state


def destroy_asset(original: GameState, actor: ActorRef, asset_id: str, *, event: str) -> GameState:
    """Remove one actual source Asset; physical wreckage retains its immutable origin."""
    from girlframe.engine.m3_items import actual_asset, same_holder

    selected = next((x for x in assets(original, actor) if x.id == asset_id), None)
    if selected is None or not event.strip():
        raise ValueError("Destroy an actual original Harpy Asset with its real source event")
    if any(
        x.get("kind") == "harpy_asset_destroyed"
        and x.get("actor") == actor.model_dump_json()
        and x.get("asset_id") == asset_id
        and x.get("event") == event
        for x in original.facts
    ):
        raise ValueError("This actual Asset destruction already has its original source")
    state = GameState.model_validate_json(original.model_dump_json())
    base = _base(state, actor)
    source_item = None
    if any(x.id == asset_id for x in base):
        from girlframe.engine.m3_janus import find, remove_base_asset

        body = next((x for x in state.harpy_states if x.id == actor.entity), None)
        if find(state, actor) is not None:
            state = remove_base_asset(state, actor, asset_id, event=event)
        elif body is not None:
            state.harpy_states = [
                x.model_copy(update=dict(assets=tuple(a for a in x.assets if a.id != asset_id)))
                if x.id == actor.entity
                else x
                for x in state.harpy_states
            ]
        else:
            assert state.world is not None
            state.world = state.world.model_copy(
                update=dict(
                    pilots=tuple(
                        x.model_copy(
                            update=dict(assets=tuple(a for a in x.assets if a.id != asset_id))
                        )
                        if x.id == actor.entity
                        else x
                        for x in state.world.pilots
                    )
                )
            )
    else:
        item = next(
            (
                x
                for x in state.held_items
                if same_holder(state, x.holder, actor)
                and x.location_mode == "carried"
                and (a := actual_asset(state, x)) is not None
                and a.id == asset_id
            ),
            None,
        )
        if item is None:
            raise ValueError("Recover the Asset's sole actual original resource authority")
        source_item = item.model_dump_json()
        state.held_items = [
            HeldItem.model_validate_json(
                x.model_copy(
                    update=dict(
                        asset_json=None,
                        asset_id=None,
                        asset_owner=None,
                        condition="ruined",
                        state_event=event,
                    )
                ).model_dump_json()
            )
            if x.id == item.id
            else x
            for x in state.held_items
        ]
    state.facts.append(
        dict(
            kind="harpy_asset_destroyed",
            actor=actor.model_dump_json(),
            asset_id=asset_id,
            asset_json=selected.model_dump_json(),
            source_item=source_item or "",
            event=event,
        )
    )
    return GameState.model_validate_json(state.model_dump_json())
