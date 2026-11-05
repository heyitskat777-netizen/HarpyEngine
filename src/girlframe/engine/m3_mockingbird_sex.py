"""Printed intimacy effects change actual original resources and retain their sole origin."""

from collections.abc import Sequence
from typing import Literal

from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_bonds import change, make_helpless
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_core import Followup, corrupt
from girlframe.engine.m3_harpy_resources import HarpyResource
from girlframe.engine.m3_mockingbird import SEX, give_tag, owns
from girlframe.engine.m3_mockingbird_state import Capability, Exposure, Starry
from girlframe.engine.m3_world_state import AdversaryPilot, Gorgon


def assets(state: GameState, actor: ActorRef) -> tuple[HarpyResource, ...]:
    if actor.kind == "pilot":
        sheet = state.sheets.get(actor.entity)
        if sheet is None or sheet.character_id != actor.incarnation:
            raise ValueError("Recover the actual original counterpart's resources")
        return tuple(sheet.assets)
    if actor.kind == "external_pilot":
        from girlframe.engine.m3_harpy_defeat import harpy

        try:
            harpy(state, actor)
        except ValueError:
            pass
        else:
            from girlframe.engine.m3_harpy_resources import assets as harpy_assets

            return harpy_assets(state, actor)
    from girlframe.engine.m3_items import mechanical_assets

    values: list[HarpyResource] = list(mechanical_assets(state, actor))
    if state.world:
        base: AdversaryPilot | Gorgon | None = None
        if actor.kind == "external_pilot":
            base = next((x for x in state.world.pilots if x.id == actor.entity), None)
        elif actor.kind == "gorgon":
            base = next((x for x in state.world.gorgons if x.id == actor.entity), None)
        if base is not None:
            values[:0] = list(base.assets)
    if len({x.id for x in values}) != len(values):
        raise ValueError("Recover the actual counterpart's unique mechanical Asset origins")
    return tuple(values)


def update_assets(
    original: GameState, actor: ActorRef, values: Sequence[HarpyResource], event: str
) -> GameState:
    old = assets(original, actor)
    proposed = {x.id: x for x in values}
    allowed = {"void", "description", "concealed"}
    if (
        not event
        or set(proposed) != {x.id for x in old}
        or len(proposed) != len(values)
        or any(
            type(x) is not type(proposed[x.id])
            or x.model_dump(exclude=allowed) != proposed[x.id].model_dump(exclude=allowed)
            for x in old
        )
    ):
        raise ValueError(
            "Change only actual corruption/concealment at every existing sole Asset origin"
        )
    for value in values:
        type(value).model_validate_json(value.model_dump_json())
    state = GameState.model_validate_json(original.model_dump_json())
    if actor.kind == "pilot":
        state.sheets[actor.entity].assets = [
            AssetState.model_validate_json(proposed[x.id].model_dump_json()) for x in old
        ]
        state.sheets[actor.entity].revision += 1
        return state
    if actor.kind == "external_pilot":
        from girlframe.engine.m3_harpy_defeat import harpy, update
        from girlframe.engine.m3_void_state import HarpyState

        try:
            body = harpy(state, actor)
        except ValueError:
            body = None
        if isinstance(body, HarpyState):
            state = update(state, actor, assets=tuple(proposed[x.id] for x in body.assets))
        elif state.world is not None:
            state.world = state.world.model_copy(
                update={
                    "pilots": tuple(
                        row.model_copy(update={"assets": tuple(proposed[x.id] for x in row.assets)})
                        if row.id == actor.entity
                        else row
                        for row in state.world.pilots
                    )
                }
            )
    elif actor.kind == "gorgon":
        assert state.world is not None
        state.world = state.world.model_copy(
            update={
                "gorgons": tuple(
                    row.model_copy(update={"assets": tuple(proposed[x.id] for x in row.assets)})
                    if row.id == actor.entity
                    else row
                    for row in state.world.gorgons
                )
            }
        )
    from girlframe.engine.m3_items import actual_asset, same_holder

    state.held_items = [
        item.model_copy(
            update={"asset_json": proposed[actual.id].model_dump_json(), "state_event": event}
        )
        if same_holder(original, item.holder, actor)
        and (actual := actual_asset(original, item)) is not None
        else item
        for item in state.held_items
    ]
    return state


def exposure(
    state: GameState,
    actor: ActorRef,
    target: ActorRef,
    kind: Literal["teaching", "both_risk", "low_tag"],
    action: str,
    event: str,
) -> GameState:
    value = Exposure(
        id="mock-exposure:" + action + ":" + kind,
        source_action=action,
        actor=actor,
        counterpart=target,
        kind=kind,
        source_event=event,
    )
    state.mockingbird = state.mockingbird.model_copy(
        update={"exposures": (*state.mockingbird.exposures, value)}
    )
    return state


def infect(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    target: ActorRef,
    asset: str,
    description: str,
    action: str,
    event: str,
) -> tuple[GameState, tuple[Followup, ...]]:
    if not owns(original, actor, SEX):
        raise ValueError("Use this actual original person's owned Sex Play")
    view = resolve(original, target, bindings, require_current_profile=False)
    if target.kind == "pilot":
        paid = corrupt(
            original.sheets[target.entity],
            asset,
            description,
            piloting=view.inside_frame is True
            and view.occupied_frame_instance == view.frame_instance,
        )
        state = GameState.model_validate_json(original.model_dump_json())
        state.sheets[target.entity] = paid.sheet
        return state, paid.followups
    actual = assets(original, target)
    chosen = next((x for x in actual if x.id == asset and not x.void), None)
    if chosen is None or not description.strip() or len(description) > 1200:
        raise ValueError(
            "Rewrite the actual counterpart's uncorrupted Asset with its real Void alteration"
        )
    state = update_assets(
        original,
        target,
        tuple(
            x.model_copy(update={"void": True, "description": description}) if x.id == asset else x
            for x in actual
        ),
        event,
    )
    return state, ()


def starry(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    target: ActorRef,
    capability: Capability,
    action: str,
    event: str,
    observers: tuple[int, ...],
) -> GameState:
    from girlframe.engine.m3_mockingbird_state import CAPABILITIES

    if not owns(original, actor, SEX) or capability not in CAPABILITIES:
        raise ValueError("Choose one actual conversation capability from the owned printed rule")
    identity = "starry:" + action
    state = give_tag(original, bindings, target, actor, "Starry-Eyed", identity, event, observers)
    grant = Starry(
        id=identity,
        speaker=actor,
        holder=target,
        tag=identity,
        capability=capability,
        source_event=event,
        action=action,
    )
    state.mockingbird = state.mockingbird.model_copy(
        update={"starry": (*state.mockingbird.starry, grant)}
    )
    from girlframe.engine.m3_actor_bonds import bond_ref

    return change(state, bond_ref(state, actor), bond_ref(state, target), 1, event)


def helpless(
    original: GameState, actor: ActorRef, target: ActorRef, action: str, event: str
) -> GameState:
    if not owns(original, actor, SEX):
        raise ValueError("Only the actual acting original person suffers this source result")
    return exposure(
        make_helpless(original, actor, target, event), actor, target, "low_tag", action, event
    )
