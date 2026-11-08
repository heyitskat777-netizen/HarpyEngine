"""Actual Living Battery choices, mental Assets and source-bound expiry; no second RNG."""

import json
from collections.abc import Sequence

from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_bonds import change as bond_change
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_harpy_defeat import harpy
from girlframe.engine.m3_harpy_defeat import update as update_harpy
from girlframe.engine.m3_janus import find as core_body
from girlframe.engine.m3_janus_link_state import (
    BatteryAsset,
    BatteryChoice,
    BatteryLink,
    BorrowedAsset,
    MentalChoice,
)
from girlframe.engine.m3_void_state import HarpyAsset, HarpyState
from girlframe.engine.m3_world_state import Asset


def get(state: GameState, identity: str) -> BatteryLink:
    value = next((x for x in state.battery_links if x.id == identity), None)
    if value is None:
        raise ValueError("Recover this actual original spinal neural link")
    return value


def put(state: GameState, value: BatteryLink) -> None:
    if any(x.id == value.id for x in state.battery_links):
        state.battery_links = [value if x.id == value.id else x for x in state.battery_links]
    else:
        state.battery_links.append(value)


def active(value: BatteryLink) -> bool:
    return value.phase not in ("unplugged", "ended")


def has_mental_channel(state: GameState, first: ActorRef, second: ActorRef) -> bool:
    from girlframe.engine.m3_frame_control import neural_contact_live
    from girlframe.engine.m3_items import same_holder

    return any(
        active(x)
        and (x.connection is None or neural_contact_live(state, x.connection))
        and "question" in x.selected
        and (
            (same_holder(state, x.caster, first) and same_holder(state, x.battery, second))
            or (same_holder(state, x.caster, second) and same_holder(state, x.battery, first))
        )
        for x in state.battery_links
    )


def _pilot(state: GameState, actor: ActorRef) -> bool:
    if actor.kind != "pilot":
        return False
    sheet = state.sheets.get(actor.entity)
    if sheet is None or sheet.character_id != actor.incarnation:
        raise ValueError("Use the actual original living caster, never a successor's sheet")
    return True


def _append_mental(
    state: GameState, link: BatteryLink, choice: MentalChoice, event: str
) -> tuple[GameState, BorrowedAsset]:
    source = BatteryAsset(link=link.id, choice=choice)
    if any(x.source == source for x in link.borrowed):
        raise ValueError("This actual link's mental Asset was already granted once")
    if _pilot(state, link.caster):
        state.sheets[link.caster.entity].assets.append(
            AssetState(
                id=source.asset_id,
                family="girl",
                name=source.name,
                description="Additional mental Asset only while this original neural link remains.",
                battery_asset=source,
            )
        )
    else:
        body = harpy(state, link.caster)
        if isinstance(body, HarpyState):
            state = update_harpy(
                state,
                link.caster,
                assets=(
                    *body.assets,
                    HarpyAsset(
                        id=source.asset_id,
                        family="girl",
                        name=source.name,
                        void=False,
                        description="Additional link-only mental Asset.",
                        battery_asset=source,
                    ),
                ),
            )
        elif core_body(state, link.caster) is not None:
            current_core = core_body(state, link.caster)
            assert current_core is not None
            state = update_harpy(
                state,
                link.caster,
                girl_assets=(
                    *current_core.girl_assets,
                    HarpyAsset(
                        id=source.asset_id,
                        family="girl",
                        name=source.name,
                        void=False,
                        description="Additional link-only mental Asset.",
                        battery_asset=source,
                    ),
                ),
            )
        else:
            if state.world is None:
                raise ValueError("Recover the actual original native Harpy resource authority")
            state.world = state.world.model_copy(
                update={
                    "pilots": tuple(
                        x.model_copy(
                            update={
                                "assets": (
                                    *x.assets,
                                    Asset(
                                        id=source.asset_id,
                                        family="girl",
                                        name=source.name,
                                        void=False,
                                        description="Additional link-only mental Asset.",
                                        battery_asset=source,
                                    ),
                                )
                            }
                        )
                        if x.id == link.caster.entity
                        else x
                        for x in state.world.pilots
                    )
                }
            )
    return state, BorrowedAsset(source=source, event=event)


def choices(
    original: GameState,
    identity: str,
    selected: Sequence[BatteryChoice],
    *,
    event: str,
    heat: int = 0,
    identities: tuple[str, ...] = (),
    question: str = "",
    target_tag: str | None = None,
    bindings: tuple[ProfileBinding, ...] = (),
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    value = get(state, identity)
    if not active(value) or value.effects_event or value.tier is None or not event.strip():
        raise ValueError("Choose once from this actual final Living Battery result")
    if (
        len(set(selected)) != len(selected)
        or len(selected) != {"low": 1, "mid": 2, "high": 4}[value.tier]
        or not set(selected) <= {"heat", "bond", "identities", "cognition", "offset", "question"}
    ):
        raise ValueError("Choose exactly the actual tier's distinct printed options")
    if ("heat" in selected) != (heat in (1, 2, 3, 4)) or ("heat" not in selected and heat != 0):
        raise ValueError("Gain exactly one to four Heat only when that option is selected")
    if (
        identities
        and "identities" not in selected
        or len(identities) > 2
        or len(set(identities)) != len(identities)
    ):
        raise ValueError("Select up to two actual Identities only for the unmark option")
    if ("question" in selected) != bool(question.strip()):
        raise ValueError("The real caster asks one actual private brain question for that option")
    if target_tag is not None and (
        not value.universal or value.tier == "low" or not target_tag.strip()
    ):
        raise ValueError("Only the actual Universal Plug eight-plus may give an optional Tag")
    if value.tier == "low" and value.erasure_event is None:
        raise ValueError("Resolve the actual low-result Tag erasure before the chosen benefit")
    pilot = _pilot(state, value.caster)
    actual = state.sheets[value.caster.entity] if pilot else harpy(state, value.caster)
    if "identities" in selected and (
        not set(identities) <= {x.id for x in actual.identities if x.marked}
    ):
        raise ValueError("Unmark only chosen actual currently marked original Identities")
    if pilot:
        if "heat" in selected:
            state.sheets[value.caster.entity].heat += heat
        for item in state.sheets[value.caster.entity].identities:
            if item.id in identities:
                item.marked = False
    else:
        state = update_harpy(
            state,
            value.caster,
            heat=actual.heat + heat,
            identities=tuple(
                x.model_copy(update={"marked": False}) if x.id in identities else x
                for x in actual.identities
            ),
        )
    if "bond" in selected:
        from girlframe.engine.m3_role_punishments import bond_ref

        state = bond_change(
            state, bond_ref(state, value.caster), bond_ref(state, value.battery), 1, event
        )
    borrowed = []
    for choice in ("cognition", "offset"):
        if choice in selected:
            state, grant = _append_mental(state, value, choice, event)
            borrowed.append(grant)
    if target_tag is not None:
        from girlframe.engine.m3_mockingbird import give_tag

        state = give_tag(
            state,
            bindings,
            value.battery,
            value.caster,
            target_tag,
            "battery:" + value.id + ":tag",
            event,
            tuple(sorted({value.caster_controller, value.battery_controller})),
        )
    changed = BatteryLink.model_validate_json(
        value.model_copy(
            update=dict(
                selected=tuple(selected),
                borrowed=tuple(borrowed),
                effects_event=event,
                question=question.strip(),
                target_tag=target_tag,
                phase="question" if "question" in selected else "connected",
            )
        ).model_dump_json()
    )
    put(state, changed)
    if pilot:
        state.sheets[value.caster.entity].revision += 1
    return state


def expire_link_assets(original: GameState, link: BatteryLink, event: str) -> GameState:
    """Remove only exact source extras, preserving every current ordinary Asset/damage."""
    state = GameState.model_validate_json(original.model_dump_json())
    ids = {x.source.asset_id for x in link.borrowed}
    if not event.strip():
        raise ValueError("Actual neural unlink/ending needs its real source event")
    sheet = state.sheets.get(link.caster.entity) if link.caster.kind == "pilot" else None
    if sheet is not None and sheet.character_id == link.caster.incarnation:
        previous = tuple(sheet.assets)
        sheet.assets = [
            x
            for x in sheet.assets
            if not (x.id in ids and x.battery_asset and x.battery_asset.link == link.id)
        ]
        if tuple(sheet.assets) != previous:
            sheet.revision += 1
    elif link.caster.kind == "external_pilot":
        body = harpy(state, link.caster)
        if isinstance(body, HarpyState):
            state = update_harpy(
                state,
                link.caster,
                assets=tuple(
                    x
                    for x in body.assets
                    if not (x.id in ids and x.battery_asset and x.battery_asset.link == link.id)
                ),
            )
        elif core_body(state, link.caster) is not None:
            value = core_body(state, link.caster)
            assert value is not None
            state = update_harpy(
                state,
                link.caster,
                girl_assets=tuple(
                    x
                    for x in value.girl_assets
                    if not (x.id in ids and x.battery_asset and x.battery_asset.link == link.id)
                ),
            )
        elif state.world is not None:
            state.world = state.world.model_copy(
                update={
                    "pilots": tuple(
                        x.model_copy(
                            update={
                                "assets": tuple(
                                    a
                                    for a in x.assets
                                    if not (
                                        a.id in ids
                                        and a.battery_asset
                                        and a.battery_asset.link == link.id
                                    )
                                )
                            }
                        )
                        if x.id == link.caster.entity
                        else x
                        for x in state.world.pilots
                    )
                }
            )
    # A genuine same-person rebirth has a different physical brain/body. It cannot
    # inherit the old body's connection merely because the constructor copied Assets.
    if link.caster.kind == "pilot":
        state.harpy_states = [
            x.model_copy(
                update={
                    "assets": tuple(
                        a
                        for a in x.assets
                        if not (a.id in ids and a.battery_asset and a.battery_asset.link == link.id)
                    )
                }
            )
            if x.origin == link.caster and x.source_event == event
            else x
            for x in state.harpy_states
        ]
    return state


def battery_tags(state: GameState, actor: ActorRef) -> tuple[tuple[str, str], ...]:
    if actor.kind == "pilot":
        _pilot(state, actor)
        return tuple((x.id, x.label) for x in state.sheets[actor.entity].tags)
    if actor.kind == "external_pilot":
        from girlframe.engine.m3_mockingbird import actor_tags

        return tuple((x.id, x.label) for x in actor_tags(state, actor))
    if actor.kind == "handler":
        from girlframe.engine.m3_handler_consequences import same_handler_body

        if not same_handler_body(state, actor):
            raise ValueError("Use this actual original Handler's own current Tags")
        return tuple((x.id, x.label) for x in state.handler_tags)
    values = (
        state.world.npcs
        if state.world and actor.kind == "npc"
        else state.world.gorgons
        if state.world and actor.kind == "gorgon"
        else ()
    )
    found = next((x for x in values if x.id == actor.entity and x.alive), None)
    if found is None:
        raise ValueError("Use the actual living original battery and its existing Tags")
    return tuple((x.id, x.label) for x in found.tags)


def erase_low_tag(original: GameState, identity: str, tag: str | None, *, event: str) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    value = get(state, identity)
    current = battery_tags(state, value.battery)
    if value.tier != "low" or value.erasure_event or not event:
        raise ValueError("Erase one actual Tag only for this unresolved low Living Battery result")
    if not current:
        if tag is not None:
            raise ValueError("No Tag exists to erase; do not manufacture a replacement Tag")
        put(state, value.model_copy(update=dict(erased_absent=True, erasure_event=event)))
        return state
    if tag is None or tag not in {x[0] for x in current}:
        raise ValueError("Choose an actual source-bound battery Tag to erase")
    if value.battery.kind == "pilot":
        sheet = state.sheets[value.battery.entity]
        sheet.tags = [x for x in sheet.tags if x.id != tag]
        sheet.revision += 1
    elif value.battery.kind == "external_pilot":
        try:
            body = harpy(state, value.battery)
        except ValueError:
            if state.world is None:
                raise ValueError(
                    "Recover the actual external battery's sole Tag resource"
                ) from None
            state.world = state.world.model_copy(
                update={
                    "pilots": tuple(
                        x.model_copy(update={"tags": tuple(t for t in x.tags if t.id != tag)})
                        if x.id == value.battery.entity
                        else x
                        for x in state.world.pilots
                    )
                }
            )
        else:
            state = update_harpy(
                state, value.battery, tags=tuple(x for x in body.tags if x.id != tag)
            )
    elif value.battery.kind == "handler":
        state.handler_tags = [x for x in state.handler_tags if x.id != tag]
    else:
        assert state.world is not None
        field = "npcs" if value.battery.kind == "npc" else "gorgons"
        state.world = state.world.model_copy(
            update={
                field: tuple(
                    x.model_copy(update={"tags": tuple(t for t in x.tags if t.id != tag)})
                    if x.id == value.battery.entity
                    else x
                    for x in getattr(state.world, field)
                )
            }
        )
    put(
        state,
        value.model_copy(
            update=dict(
                erased_tag=tag,
                erasure_event=event,
                erasure_before_tags=tuple(x[0] for x in current),
            )
        ),
    )
    return state


def corrupt_frame(original: GameState, identity: str, *, event: str) -> GameState:
    """The actual final Tag removal corrupts only the original connected physical Frame."""
    from girlframe.engine.m3_frame_control import takeover
    from girlframe.engine.m3_janus import _save_frame, frame_sheet

    value = get(original, identity)
    if (
        value.erased_tag is None
        or value.erasure_event != event
        or battery_tags(original, value.battery)
    ):
        raise ValueError("Only actual final-Tag erasure can cause this Frame-wide Void")
    state = takeover(original, value, event)
    if value.caster_frame_owner.kind == "pilot":
        sheet = frame_sheet(state, value.caster_frame_owner, value.caster_frame)
        source_ids = [x.id for x in sheet.assets if x.family == "frame" and not x.void]
        for asset in sheet.assets:
            if asset.family == "frame":
                asset.void = True
        _save_frame(state, value.caster_frame_owner, value.caster_frame, sheet, event)
    else:
        from girlframe.engine.m3_harpy_resources import assets, set_assets

        pool = assets(state, value.caster_frame_owner)
        source_ids = [x.id for x in pool if x.family == "frame" and not x.void]
        state = set_assets(
            state,
            value.caster_frame_owner,
            tuple(x.model_copy(update={"void": True}) if x.family == "frame" else x for x in pool),
            event=event,
        )
    put(state, value.model_copy(update={"frame_takeover": event}))
    state.facts.append(
        dict(
            kind="living_battery_frame_corruption",
            link=identity,
            frame=value.caster_frame,
            owner=value.caster_frame_owner.model_dump_json(),
            event=event,
            newly_void=json.dumps(source_ids),
        )
    )
    return state
