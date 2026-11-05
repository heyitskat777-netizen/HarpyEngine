"""Harpy resource identity and source-specific Defeat effects; never a proxy Pilot sheet."""

from typing import TYPE_CHECKING, Any

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding, SceneCast
from girlframe.engine.m3_harpy_defeat_state import NativeHarpyRuntime, Travel
from girlframe.engine.m3_void_state import HarpyState

if TYPE_CHECKING:
    from girlframe.engine.m3_harpy_resources import HarpyResource


def harpy(state: GameState, actor: ActorRef) -> HarpyState | NativeHarpyRuntime:
    if actor.kind != "external_pilot":
        raise ValueError("Use the actual original Harpy's external actor identity")
    converted = next((x for x in state.harpy_states if x.id == actor.entity), None)
    if converted is not None:
        return converted
    native = next((x for x in state.native_harpies if x.id == actor.entity), None)
    world = (
        next((x for x in state.world.pilots if x.id == actor.entity), None) if state.world else None
    )
    if (
        native is None
        or world is None
        or world.kind != "harpy"
        or world.controller != native.controller
    ):
        raise ValueError("Recover this actual native Harpy's source-owned factual runtime first")
    return native


def offstage_travel(state: GameState, actor: ActorRef) -> Travel | None:
    from girlframe.engine.m3_handler_consequences import same_handler_body

    return next(
        (
            x
            for x in reversed(state.harpy_travels)
            if x.state == "offstage"
            and (
                x.actor == actor
                or (
                    x.actor.kind == actor.kind == "handler"
                    and same_handler_body(state, actor)
                    and same_handler_body(state, x.actor)
                )
            )
        ),
        None,
    )


def fight_required(state: GameState, actor: ActorRef) -> bool:
    from girlframe.engine.m3_actor_bonds import is_helpless

    return not is_helpless(state, actor) and any(
        x.actor == actor and x.cut_link and x.phase == "awaiting_physical"
        for x in state.harpy_defeats
    )


def assets(state: GameState, actor: ActorRef) -> "tuple[HarpyResource, ...]":
    from girlframe.engine.m3_harpy_resources import assets as actual_assets

    return actual_assets(state, actor)


def update(state: GameState, actor: ActorRef, **values: Any) -> GameState:
    changed = GameState.model_validate_json(state.model_dump_json())
    body = harpy(changed, actor)
    revised = type(body).model_validate_json(body.model_copy(update=values).model_dump_json())
    if isinstance(revised, HarpyState):
        changed.harpy_states = [
            revised if x.id == actor.entity else x for x in changed.harpy_states
        ]
    else:
        changed.native_harpies = [
            revised if x.id == actor.entity else x for x in changed.native_harpies
        ]
        if changed.world is not None:
            compatibility: dict[str, Any] = {}
            if "custody" in values or "custodian" in values or "custody_event" in values:
                compatibility.update(
                    custody="converted" if revised.custody == "core" else revised.custody,
                    custodian=controller(changed, revised.custodian) if revised.custodian else None,
                    custody_event=revised.custody_event,
                )
            if revised.frame_cell is not None and "frame_cell" in values:
                compatibility["cell"] = revised.frame_cell
            if compatibility:
                changed.world = changed.world.model_copy(
                    update={
                        "pilots": tuple(
                            x.model_copy(update=compatibility) if x.id == actor.entity else x
                            for x in changed.world.pilots
                        )
                    }
                )
    return changed


def girls(state: GameState, cast: SceneCast) -> tuple[ActorRef, ...]:
    return tuple(
        role.actor
        for role in cast.roles
        if role.actor.kind == "pilot"
        and role.actor.entity in state.sheets
        and state.sheets[role.actor.entity].character_id == role.actor.incarnation
    )


def modifier(state: GameState, actor: ActorRef, cast: SceneCast) -> tuple[int, ActorRef | None]:
    from girlframe.engine.m3_actor_bonds import depth

    girl = next((x for x in girls(state, cast) if depth(state, actor, x) == 2), None)
    return (4, girl) if girl is not None else (2, None)


def controller(state: GameState, actor: ActorRef) -> int:
    if actor.kind in ("pilot", "handler"):
        return int(actor.entity)
    if actor.kind == "external_pilot":
        body = next((x for x in state.harpy_states if x.id == actor.entity), None)
        if body:
            return body.controller
    if state.world is not None:
        if (
            actor.kind == "gorgon"
            and any(x.id == actor.entity for x in state.world.gorgons)
            and state.handler is not None
        ):
            return state.handler
        values = state.world.npcs if actor.kind == "npc" else state.world.pilots
        found = next((x for x in values if x.id == actor.entity), None)
        if found:
            return found.controller
    raise ValueError("Recover the actual character's controlling human")


def give_tag(
    original: GameState,
    target: ActorRef,
    giver: ActorRef,
    label: str,
    event: str,
    identity: str,
    observers: tuple[int, ...],
) -> GameState:
    from girlframe.engine.m2 import TagState
    from girlframe.engine.m3_void_state import HarpyTag
    from girlframe.engine.m3_world_state import WorldTag

    state = GameState.model_validate_json(original.model_dump_json())
    human = controller(state, giver)
    if not label.strip():
        raise ValueError("The actual printed chooser must provide the Tag")
    if target.kind == "pilot":
        sheet = state.sheets.get(target.entity)
        if sheet is None or sheet.character_id != target.incarnation:
            raise ValueError("The original Tag recipient ended; no replacement may inherit it")
        sheet.tags.append(
            TagState(id=identity, label=label, giver=human, giver_actor=giver, observers=observers)
        )
        sheet.revision += 1
    elif target.kind == "handler":
        from girlframe.engine.m3_handler_consequences import same_handler_body

        if not same_handler_body(state, target):
            raise ValueError("Use the actual current original Handler body")
        state.handler_tags.append(
            TagState(id=identity, label=label, giver=human, giver_actor=giver, observers=observers)
        )
    elif target.kind == "external_pilot" and (
        any(x.id == target.entity for x in state.harpy_states)
        or any(x.id == target.entity for x in state.native_harpies)
    ):
        body = harpy(state, target)
        state = update(
            state,
            target,
            tags=(
                *body.tags,
                HarpyTag(
                    id=identity, label=label, giver=human, giver_ref=giver, observers=observers
                ),
            ),
        )
    elif state.world is not None:
        field = {"npc": "npcs", "gorgon": "gorgons", "external_pilot": "pilots"}.get(target.kind)
        if field is None:
            raise ValueError("This actual recipient has no printed Tag resource")
        rows = getattr(state.world, field)
        if not any(x.id == target.entity and x.alive for x in rows):
            raise ValueError("The actual original Tag recipient is unavailable")
        value = WorldTag(id=identity, label=label, giver_entity=giver.token)
        state.world = state.world.model_copy(
            update={
                field: tuple(
                    x.model_copy(update={"tags": (*x.tags, value)}) if x.id == target.entity else x
                    for x in rows
                )
            }
        )
    else:
        raise ValueError("Recover the actual original Tag recipient")
    return state


def escape(original: GameState, actor: ActorRef, event: str) -> GameState:
    body = harpy(original, actor)
    if body.subsumed or not body.vitals_active:
        raise ValueError("Actual subsumption/extraction must resolve without inventing revival")
    state = update(
        original,
        actor,
        cell=None,
        frame_cell=None if body.linked else body.frame_cell,
        custody="free",
        custodian=None,
        custody_event=None,
        condition_event=event,
    )
    from girlframe.engine.m3_battle import end_actor_casts

    return end_actor_casts(state, actor, event)


def shutdown(original: GameState, actor: ActorRef, event: str, *, cut_link: bool) -> GameState:
    body = harpy(original, actor)
    if cut_link and (body.subsumed or not body.vitals_active):
        raise ValueError("Do not invent a living free body from actual subsumption")
    return update(
        original,
        actor,
        linked=False if cut_link else body.linked,
        frame_shutdown=True,
        body_incapacitated=False if cut_link else True,
        condition_event=event,
    )


def die(original: GameState, actor: ActorRef, event: str) -> GameState:
    from girlframe.engine.m3_battle import end_actor_casts

    state = GameState.model_validate_json(original.model_dump_json())
    body = harpy(state, actor)
    if isinstance(body, HarpyState):
        state = update(state, actor, alive=False, body_incapacitated=True, condition_event=event)
    else:
        assert state.world is not None
        state.world = state.world.model_copy(
            update={
                "pilots": tuple(
                    x.model_copy(update={"alive": False}) if x.id == actor.entity else x
                    for x in state.world.pilots
                )
            }
        )
        state = update(state, actor, body_incapacitated=True, condition_event=event)
    from girlframe.engine.m3_enforcer import end_grasps
    from girlframe.engine.m3_physical import interrupt_journeys

    state = end_grasps(interrupt_journeys(state, actor, event, "Actual Harpy death"), actor, event)
    return end_actor_casts(state, actor, event)


def kidnap(
    original: GameState,
    actor: ActorRef,
    girl: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    event: str,
    account: str,
) -> GameState:
    from girlframe.engine.m3_actor_bonds import is_helpless
    from girlframe.engine.m3_physical import extract

    state = GameState.model_validate_json(original.model_dump_json())
    sheet = state.sheets.get(girl.entity)
    placement = next((x for x in state.placements if x.actor == girl), None)
    if (
        girl.kind != "pilot"
        or sheet is None
        or sheet.character_id != girl.incarnation
        or placement is None
        or not (
            is_helpless(state, girl)
            or not any(x.family == "frame" and not x.damaged for x in sheet.assets)
        )
    ):
        raise ValueError("Choose an actually defeated Girl with source-proven physical access")
    body = harpy(state, actor)
    if body.cell is None or placement.girl_cell is None or body.cell != placement.girl_cell:
        raise ValueError("The kidnapping needs actual physical access to the defeated Girl")
    if placement.mode != "outside_frame":
        state = extract(state, bindings, girl, event, account)
        placement = next(x for x in state.placements if x.actor == girl)
    moved = placement.model_copy(
        update=dict(
            girl_cell=None,
            mode="outside_frame",
            custody=actor,
            source_event=event,
            account=account,
            occupied_frame_owner=None,
            occupied_frame_instance=None,
        )
    )
    state.placements = [moved if x.actor == girl else x for x in state.placements]
    from girlframe.engine.m3_battle import end_actor_casts

    state = end_actor_casts(state, girl, event)
    return escape(state, actor, event)
