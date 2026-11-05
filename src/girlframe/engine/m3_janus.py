"""Actual JANUS Core bindings and one source for its shared physical Frame resources."""

from collections.abc import Sequence
from typing import Any

from girlframe.engine.m2 import AssetState, GameState, PilotSheet
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_janus_state import BASELINE, CoreFacts, JanusCore
from girlframe.engine.m3_void_state import HarpyAsset, HarpyTag
from girlframe.engine.m3_world_state import Cell

CORE = "frame.janus.harpy-core"
BATTERY = "frame.janus.living-battery"
RULES = (
    "frame.janus.pandora",
    "frame.janus.obedience-training",
    "frame.janus.void-storage",
    "frame.janus.universal-plug",
    "frame.janus.a-girl-is-kinda-like-a-pet",
)


def ref(core: JanusCore) -> ActorRef:
    return ActorRef(kind="external_pilot", entity=core.id)


def find(state: GameState, actor: ActorRef) -> JanusCore | None:
    return next((x for x in state.janus_cores if ref(x) == actor), None)


def core(state: GameState, actor: ActorRef) -> JanusCore:
    found = find(state, actor)
    if found is None:
        raise ValueError("Recover this actual source-admitted original JANUS Core")
    return found


def bound(state: GameState, owner: ActorRef, frame: str) -> JanusCore | None:
    matches = [x for x in state.janus_cores if x.frame_owner == owner and x.frame_instance == frame]
    if len(matches) > 1:
        raise ValueError("Recover the unique actual original Core bound to this physical JANUS")
    return matches[0] if matches else None


def _reborn_frame(state: GameState, owner: ActorRef, instance: str) -> Any:
    from girlframe.engine.m3_frame_control import frame_address

    matches = [
        x
        for x in state.harpy_states
        if x.alive
        and x.origin == owner
        and x.frame_instance == instance
        and frame_address(state, ActorRef(kind="external_pilot", entity=x.id), instance)
        == (owner, instance)
    ]
    if len(matches) > 1:
        raise ValueError("Recover the unique actual same-Frame rebirth source")
    return matches[0] if matches else None


def frame_sheet(state: GameState, owner: ActorRef, instance: str) -> PilotSheet:
    if owner.kind != "pilot":
        raise ValueError(
            "This source is the actual original Pilot-owned Frame, not a controller alias"
        )
    current = state.sheets.get(owner.entity)
    if (
        current is not None
        and current.character_id == owner.incarnation
        and (
            current.frame_runtime.id
            if current.frame_runtime
            else "initial:" + str(owner.incarnation)
        )
        == instance
    ):
        return PilotSheet.model_validate_json(current.model_dump_json())
    parked = next(
        (x for x in state.parked_frames if x.owner == owner and x.frame_instance == instance), None
    )
    if parked is not None:
        return PilotSheet.model_validate_json(parked.frame_json)
    reborn = _reborn_frame(state, owner, instance)
    if reborn is not None:
        archive = next(x for x in state.career_archives if x.id == reborn.original_archive)
        # The immutable sheet supplies only the original schema/address. Live Frame
        # resources come exclusively from the source-proved resulting body.
        sheet = PilotSheet.model_validate_json(archive.sheet_json)
        sheet.assets = [
            AssetState.model_validate_json(x.model_dump_json())
            for x in reborn.assets
            if x.family == "frame"
        ]
        return sheet
    raise ValueError("Recover the original current or parked JANUS Frame; no successor alias")


def _save_frame(
    state: GameState, owner: ActorRef, instance: str, sheet: PilotSheet, event: str
) -> None:
    before = frame_sheet(state, owner, instance)
    if [x for x in before.assets if x.family == "frame"] == [
        x for x in sheet.assets if x.family == "frame"
    ]:
        return
    sheet.revision = before.revision + 1
    current = state.sheets.get(owner.entity)
    if (
        current is not None
        and current.character_id == owner.incarnation
        and (
            current.frame_runtime.id
            if current.frame_runtime
            else "initial:" + str(owner.incarnation)
        )
        == instance
    ):
        state.sheets[owner.entity] = sheet
    else:
        parked = next(
            (x for x in state.parked_frames if x.owner == owner and x.frame_instance == instance),
            None,
        )
        if parked is None:
            reborn = _reborn_frame(state, owner, instance)
            if reborn is None:
                raise ValueError("The actual original physical Frame is unavailable")
            assets = tuple(x for x in reborn.assets if x.family != "frame") + tuple(
                HarpyAsset.model_validate_json(x.model_dump_json())
                for x in sheet.assets
                if x.family == "frame"
            )
            state.harpy_states = [
                x.model_copy(update={"assets": assets}) if x.id == reborn.id else x
                for x in state.harpy_states
            ]
        else:
            state.parked_frames = [
                x.model_copy(update={"frame_json": sheet.model_dump_json()}) if x == parked else x
                for x in state.parked_frames
            ]
    state.facts.append(
        dict(
            kind="janus_frame_resource_changed",
            owner=owner.model_dump_json(),
            frame=instance,
            event=event,
        )
    )


def position(state: GameState, value: JanusCore) -> Cell | None:
    if value.attached:
        from girlframe.engine.m3_actors import frame_position

        return frame_position(state, value.frame_owner, value.frame_instance)
    return value.cell


def has_tag(value: JanusCore, semantic: str) -> bool:
    identity = value.control_tags.get(semantic, value.baseline_tags.get(semantic))
    return any(x.id == identity for x in value.tags)


def drugged(state: GameState, actor: ActorRef) -> bool:
    value = find(state, actor)
    return value is not None and value.alive and has_tag(value, "drugged")


def can_act(state: GameState, actor: ActorRef) -> None:
    value = find(state, actor)
    if value is not None and has_tag(value, "restrained"):
        raise ValueError("RESTRAINED_CORE: the actual printed Restrained Tag prevents making Plays")


def can_speak(state: GameState, actor: ActorRef, *, mental_link: bool = False) -> None:
    value = find(state, actor)
    if value is not None and has_tag(value, "muzzled") and not mental_link:
        raise ValueError(
            "MUZZLED_CORE: physical speech is blocked. Use an actual direct neural link."
        )


def update(original: GameState, actor: ActorRef, **values: Any) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    prior = core(state, actor)
    immutable = {
        "id",
        "controller",
        "frame_owner",
        "frame_instance",
        "source_setup",
        "proposed_event",
        "source_event",
        "judge",
        "appointment",
        "source_facts",
        "body_vessel",
        "baseline_tags",
    }
    if set(values) & immutable:
        raise ValueError("Do not reassign the original source, person, Frame or printed Tag IDs")
    changed = JanusCore.model_validate_json(prior.model_copy(update=values).model_dump_json())
    state.janus_cores = [changed if x.id == prior.id else x for x in state.janus_cores]
    return state


def base_assets(state: GameState, actor: ActorRef) -> tuple[HarpyAsset | AssetState, ...]:
    value = core(state, actor)
    if not value.attached and not value.linked:
        return value.girl_assets
    sheet = frame_sheet(state, value.frame_owner, value.frame_instance)
    return (*value.girl_assets, *(x for x in sheet.assets if x.family == "frame"))


def set_base_assets(
    original: GameState, actor: ActorRef, assets: Sequence[HarpyAsset | AssetState], *, event: str
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    value = core(state, actor)
    old = base_assets(state, actor)
    incoming = {x.id: x for x in assets}
    if not event.strip() or len(incoming) != len(assets) or set(incoming) != {x.id for x in old}:
        raise ValueError("Update exactly the existing actual Core Girl/shared Frame resources")
    for previous in old:
        proposed = incoming[previous.id]
        if type(previous) is not type(proposed) or previous.model_dump(
            exclude={"damaged", "void", "description"}
        ) != proposed.model_dump(exclude={"damaged", "void", "description"}):
            raise ValueError("Do not copy, add, reclassify or rename shared actual resources")
    if value.attached or value.linked:
        sheet = frame_sheet(state, value.frame_owner, value.frame_instance)
        sheet.assets = [
            AssetState.model_validate_json(incoming[x.id].model_dump_json())
            if x.family == "frame"
            else x
            for x in sheet.assets
        ]
        _save_frame(state, value.frame_owner, value.frame_instance, sheet, event)
    return update(
        state,
        actor,
        girl_assets=tuple(
            HarpyAsset.model_validate_json(incoming[x.id].model_dump_json())
            for x in value.girl_assets
        ),
        state_event=event,
    )


def admit(
    original: GameState,
    owner: ActorRef,
    frame: str,
    controller: int,
    facts: CoreFacts,
    *,
    identity: str,
    setup: str,
    proposed_event: str,
    event: str,
    judge: int,
    appointment: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    sheet = frame_sheet(state, owner, frame)
    if (
        sheet.frame not in ("JANUS", "JANUS-B")
        or sheet.frame_scrapped
        or bound(state, owner, frame) is not None
        or any(
            x.custody == "core" and x.core_frame_owner == owner and x.core_frame_instance == frame
            for x in state.harpy_states
        )
        or not event
        or proposed_event == event
    ):
        raise ValueError("Admit one actual original JANUS Core with real proposal and review")
    if (
        any(x.id == identity for x in state.janus_cores)
        or any(x.id == identity for x in state.harpy_states)
        or any(x.id == identity for x in state.native_harpies)
        or state.world is not None
        and any(x.id == identity for x in state.world.pilots)
    ):
        raise ValueError("This Core must be an original distinct actual person, never another PC")
    tags = tuple(
        HarpyTag(
            id=identity + ":" + role,
            label=label,
            giver=judge,
            gm_setter_appointment=appointment,
            gm_setter_event=event,
            observers=tuple(sorted({controller, judge, int(owner.entity)})),
        )
        for role, label in BASELINE
    )
    value = JanusCore(
        id=identity,
        controller=controller,
        frame_owner=owner,
        frame_instance=frame,
        source_setup=setup,
        proposed_event=proposed_event,
        source_event=event,
        judge=judge,
        appointment=appointment,
        source_facts=facts,
        body_vessel="body:" + identity,
        girl_assets=facts.girl_assets,
        heat=facts.heat,
        identities=facts.identities,
        tags=tags,
        baseline_tags={role: identity + ":" + role for role, _ in BASELINE},
        exposed=facts.exposed,
        custodian=owner,
        custody_event=event,
        state_event=event,
    )
    state.janus_cores.append(value)
    return state


def remove_base_asset(
    original: GameState, actor: ActorRef, asset_id: str, *, event: str
) -> GameState:
    """Actual source destruction removes only its existing Girl/shared-Frame origin."""
    state = GameState.model_validate_json(original.model_dump_json())
    value = core(state, actor)
    selected = next((x for x in base_assets(state, actor) if x.id == asset_id), None)
    if selected is None or not event.strip():
        raise ValueError("Destroy an actual original Core or shared JANUS Asset")
    if selected.family == "girl":
        return update(
            state,
            actor,
            girl_assets=tuple(x for x in value.girl_assets if x.id != asset_id),
            state_event=event,
        )
    sheet = frame_sheet(state, value.frame_owner, value.frame_instance)
    sheet.assets = [x for x in sheet.assets if x.id != asset_id]
    _save_frame(state, value.frame_owner, value.frame_instance, sheet, event)
    return state


def free_core(original: GameState, actor: ActorRef, event: str) -> GameState:
    """Actual last-Tag freedom is a source consequence, not a fabricated neural roll."""
    import json

    state = GameState.model_validate_json(original.model_dump_json())
    value = core(state, actor)
    if value.tags or not value.alive or not value.attached or not value.linked or not event:
        raise ValueError("Free only the actual newly tagless attached linked original Core")
    if value.takeover_event is not None:
        raise ValueError("This actual original Core already controls this Frame")
    sheet = frame_sheet(state, value.frame_owner, value.frame_instance)
    newly = [x.id for x in sheet.assets if x.family == "frame" and not x.void]
    for asset in sheet.assets:
        if asset.family == "frame":
            asset.void = True
    _save_frame(state, value.frame_owner, value.frame_instance, sheet, event)
    state = update(state, actor, takeover_event=event, state_event=event)
    state.placements = [
        x.model_copy(update={"mode": "inside_frame", "source_event": event})
        if x.actor == value.frame_owner
        and x.frame_instance == value.frame_instance
        and x.mode == "piloting"
        else x
        for x in state.placements
    ]
    state.facts.append(
        dict(
            kind="janus_core_freed",
            core=actor.model_dump_json(),
            owner=value.frame_owner.model_dump_json(),
            frame=value.frame_instance,
            event=event,
            newly_void=json.dumps(newly),
        )
    )
    return state
