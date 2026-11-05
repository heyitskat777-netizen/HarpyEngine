"""Real object custody; only a proved actual Asset carries mechanical Asset properties."""

from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_bonds import make_helpless
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_core import install
from girlframe.engine.m3_item_state import HeldItem, ItemTransfer
from girlframe.engine.m3_role_punishments import view


def asset_item_id(actor: ActorRef, asset: str) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:physical-item:" + actor.token + ":" + asset))


def same_holder(state: GameState, first: ActorRef, second: ActorRef) -> bool:
    if first == second:
        return True
    if first.kind != "handler" or second.kind != "handler":
        return False
    from girlframe.engine.m3_handler_consequences import body_original, same_handler_body

    return (
        same_handler_body(state, first)
        and same_handler_body(state, second)
        and body_original(state, first).actor == body_original(state, second).actor
    )


def body_ref(state: GameState, actor: ActorRef) -> ActorRef:
    if actor.kind == "handler":
        from girlframe.engine.m3_handler_consequences import body_original, same_handler_body

        if not same_handler_body(state, actor):
            raise ValueError("Use the actual current original Handler body, not a successor alias")
        return body_original(state, actor).actor
    return actor


def actual_asset(state: GameState, item: HeldItem) -> AssetState | None:
    if (
        item.asset_json is None
        or item.asset_id is None
        or item.asset_owner is None
        or not same_holder(state, item.asset_owner, item.holder)
    ):
        return None
    if item.holder.kind == "pilot":
        sheet = state.sheets.get(item.holder.entity)
        if sheet is None or sheet.character_id != item.holder.incarnation:
            return None
        return next((x for x in sheet.assets if x.id == item.asset_id), None)
    saved = AssetState.model_validate_json(item.asset_json)
    if saved.battery_asset is not None:
        raise ValueError("A link-only mental Asset cannot become a physical carried object")
    if saved.id != item.asset_id:
        raise ValueError("Recover the actual mechanical Item's source-bound Asset identity")
    return saved


def mechanical_assets(state: GameState, holder: ActorRef) -> tuple[AssetState, ...]:
    """NPC/Handler actual object Assets, never a counter manufactured from descriptions."""
    return tuple(
        asset
        for item in state.held_items
        if same_holder(state, item.holder, holder)
        and item.location_mode == "carried"
        and (asset := actual_asset(state, item)) is not None
    )


def take(
    original: GameState,
    source: ActorRef,
    recipient: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    selection: str,
    action: str,
    event: str,
    account: str,
    *,
    origin_event: str,
    replace: str | None = None,
    inside_frame: bool | None = None,
    scene: str | None = None,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    source_view = view(state, source, bindings)
    view(state, recipient, bindings)
    if (
        same_holder(state, source, recipient)
        or not account.strip()
        or not all((action, event, origin_event))
    ):
        raise ValueError("Take one actual held object between distinct original people")
    if any(x.action == action and x.event == event for x in state.item_transfers):
        raise ValueError("This source response already transferred an actual object")
    item = next(
        (x for x in state.held_items if x.id == selection and same_holder(state, x.holder, source)),
        None,
    )
    source_asset: AssetState | None = None
    if selection.startswith("asset:"):
        if source.kind != "pilot":
            raise ValueError("Only an actual canonical Girl sheet supplies this Asset source")
        source_asset = next(
            (
                x
                for x in state.sheets[source.entity].assets
                if x.id == selection[6:] and x.family == "girl" and not x.concealed
            ),
            None,
        )
        if source_asset is None:
            raise ValueError("Choose an actual accessible Girl Asset, not an invented held object")
        if source_asset.battery_asset is not None:
            raise ValueError("A temporary direct-link mental Asset is not a physical held object")
        identity = asset_item_id(source, source_asset.id)
        existing = next(
            (
                x
                for x in state.held_items
                if x.asset_owner == source and x.asset_id == source_asset.id
            ),
            None,
        )
        if existing is not None:
            item = existing
        elif any(x.id == identity for x in state.held_items):
            raise ValueError("Recover the existing actual object's custody before taking it")
        else:
            item = HeldItem(
                id=identity,
                holder=source,
                name=source_asset.name,
                description=source_asset.description or "Actual owned Girl Asset",
                source_event=event,
                source_owner=source,
                origin_event=origin_event,
                origin_asset_json=source_asset.model_dump_json(),
                state_event=event,
                asset_json=source_asset.model_dump_json(),
                asset_id=source_asset.id,
                asset_owner=source,
            )
            state.held_items.append(item)
    elif item is not None:
        source_asset = actual_asset(state, item)
    if item is None:
        raise ValueError(
            "Select an actual proved held object; missing possessions need factual confirmation"
        )
    if item.location_mode == "scene" and item.scene_id != scene:
        raise ValueError("This actual object remains in its source room, not on the person's body")
    if not same_holder(state, item.holder, source):
        raise ValueError("The original source no longer holds this actual object")
    removed: str | None = None
    last = False
    if source_asset is not None and source.kind == "pilot":
        if source_asset.family != "girl":
            raise ValueError(
                "This person-level theft does not detach a Frame's installed equipment"
            )
        removed = source_asset.id
        state.sheets[source.entity].assets = [
            x for x in state.sheets[source.entity].assets if x.id != removed
        ]
        state.sheets[source.entity].revision += 1
        last = not any(
            x.family == "girl" and not x.damaged for x in state.sheets[source.entity].assets
        )
        if last:
            placement = next((x for x in state.placements if x.actor == source), None)
            known = placement.mode != "outside_frame" if placement is not None else None
            if known is not None and inside_frame is not None and known != inside_frame:
                raise ValueError("Use the actual original body's inside/outside Frame facts")
            inside_frame = known if known is not None else inside_frame
            if inside_frame is None:
                raise ValueError(
                    "Record the factual inside/outside context before the last Girl Asset is taken"
                )
            if not inside_frame:
                state = make_helpless(state, source, recipient, event)
    if source_asset is not None and (
        source.kind == "handler"
        and source_view.rules == "handler_girl"
        or source.kind == "external_pilot"
        and source_view.girl == "harpy"
    ):
        removed = source_asset.id
        if source.kind == "external_pilot":
            from girlframe.engine.m3_harpy_resources import assets as harpy_assets

            remaining_assets = [x for x in harpy_assets(state, source) if x.id != source_asset.id]
        else:
            remaining_assets = [
                asset
                for x in state.held_items
                if x.id != item.id
                and same_holder(state, x.holder, source)
                and (asset := actual_asset(state, x)) is not None
            ]
        last = not any(x.family == "girl" and not x.damaged for x in remaining_assets)
        if last:
            known = source_view.inside_frame
            if known is not None and inside_frame is not None and known != inside_frame:
                raise ValueError("Use the actual Handler body's source-proved inside/outside facts")
            inside_frame = known if known is not None else inside_frame
            if inside_frame is None:
                raise ValueError(
                    "Record actual HandlerGirl inside/outside Frame facts before last Asset loss"
                )
            if not inside_frame:
                state = make_helpless(
                    state, body_ref(state, source), body_ref(state, recipient), event
                )
    received: str | None = None
    binding_owner: ActorRef | None = None
    asset_json = item.asset_json
    if source_asset is not None:
        if source_asset.family != "girl":
            raise ValueError("Person-level theft does not detach installed Frame equipment")
        original_asset = (
            AssetState.model_validate_json(item.origin_asset_json)
            if item.origin_asset_json
            else None
        )
        destination_id = (
            original_asset.id
            if same_holder(state, recipient, item.source_owner) and original_asset is not None
            else "item:" + item.id
        )
        actual = source_asset.model_copy(
            update={"id": destination_id, "intrinsic": None, "concealed": False}
        )
        asset_json, received, binding_owner = actual.model_dump_json(), actual.id, recipient
        if recipient.kind == "pilot":
            from girlframe.engine.m3_janus_storage import ids as stored_ids

            result = install(
                state.sheets[recipient.entity],
                actual,
                replace=replace,
                effective_void=stored_ids(state, recipient),
            )
            state.sheets[recipient.entity] = result.sheet
        elif replace is not None:
            raise ValueError(
                "NPC/Handler custody does not invent Girl Asset slots or cap replacement"
            )
    elif replace is not None:
        raise ValueError("An ordinary confirmed possession does not grant a mechanical Asset")
    changed = item.model_copy(
        update=dict(
            holder=recipient,
            transferred_event=event,
            state_event=event,
            asset_json=asset_json,
            asset_id=received,
            asset_owner=binding_owner,
            location_mode="carried",
            scene_id=None,
            location_event=event,
        )
    )
    state.held_items = [changed if x.id == item.id else x for x in state.held_items]
    state.item_transfers.append(
        ItemTransfer(
            id="transfer:" + event,
            item=item.id,
            source=source,
            recipient=recipient,
            action=action,
            event=event,
            account=account,
            prior_event=origin_event,
            removed_asset=removed,
            received_asset=received,
            last_girl_asset=last,
            inside_frame=inside_frame,
        )
    )
    return state


def damage_mechanical_asset(
    original: GameState,
    holder: ActorRef,
    asset_id: str,
    event: str,
    *,
    opponent: ActorRef,
    inside_frame: bool | None = None,
) -> GameState:
    """Damage a real HandlerGirl-held object; ordinary Handler damage uses its own rule."""
    state = GameState.model_validate_json(original.model_dump_json())
    actual = view(state, holder, ())
    if holder.kind != "handler" or actual.rules != "handler_girl":
        raise ValueError(
            "Ordinary Handler damage needs the printed actual Handler replacement consequence"
        )
    candidates = [
        (x, a)
        for x in state.held_items
        if same_holder(state, x.holder, holder)
        and (a := actual_asset(state, x)) is not None
        and a.id == asset_id
    ]
    if len(candidates) != 1 or not event:
        raise ValueError("Select one exact actual held Asset and real damage source event")
    item, asset = candidates[0]
    if asset.damaged or asset.family != "girl":
        raise ValueError("Damage one actual undamaged held Girl Asset, not an invented body slot")
    if any(
        x.get("kind") == "held_asset_damage"
        and x.get("item") == item.id
        and x.get("event") == event
        for x in state.facts
    ):
        raise ValueError("This source already damaged the actual physical object")
    damaged = asset.model_copy(update={"damaged": True})
    state.held_items = [
        x.model_copy(update=dict(asset_json=damaged.model_dump_json(), state_event=event))
        if x.id == item.id
        else x
        for x in state.held_items
    ]
    last = not any(x.family == "girl" and not x.damaged for x in mechanical_assets(state, holder))
    if last:
        if (
            actual.inside_frame is not None
            and inside_frame is not None
            and actual.inside_frame != inside_frame
        ):
            raise ValueError("Use the actual HandlerGirl's source-proved physical context")
        inside_frame = actual.inside_frame if actual.inside_frame is not None else inside_frame
        if inside_frame is None:
            raise ValueError(
                "Record actual HandlerGirl inside/outside Frame facts before last Asset damage"
            )
        if not inside_frame:
            state = make_helpless(state, body_ref(state, holder), body_ref(state, opponent), event)
    state.facts.append(
        dict(
            kind="held_asset_damage",
            item=item.id,
            asset=asset_id,
            event=event,
            holder=body_ref(state, holder).model_dump_json(),
            opponent=body_ref(state, opponent).model_dump_json(),
            last_girl_asset=str(last).lower(),
            inside_frame=str(inside_frame).lower(),
        )
    )
    return state
