"""Finite actual body, Status and found-object adapters for source-owned Bonded effects."""

import json
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_bonded import Selection, Source, records
from girlframe.engine.m3_intracadre_marriage import status_groups
from girlframe.engine.m3_item_state import HeldItem
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def place_above(state: GameState, actor: ActorRef, pair: ActorRef) -> None:
    groups = list(status_groups(state))
    own = next(x for x in groups if int(actor.entity) in x)
    other = next(x for x in groups if int(pair.entity) in x)
    if own == other:
        raise WorkflowError(
            "BONDED_STATUS_SOURCE_CONFLICT: actual equal Status cannot also be directly above"
        )
    groups.remove(own)
    groups.insert(groups.index(other), own)
    state.order = tuple(uid for group in groups for uid in group)


def _selected(state: GameState, source: Source, event: str) -> Selection:
    selected = [
        x
        for x in records(state, Selection)
        if x.source == source.id and x.event == event and x.kind == "bonded_side"
    ]
    if len(selected) != 1 or selected[0].person != source.actor:
        raise WorkflowError("Recover the actual original owner's Side result choice")
    return selected[0]


def arrive(
    game: "GameService",
    c: Connection,
    state: GameState,
    source: Source,
    event: str,
    account: str,
    *,
    weapon: bool,
) -> None:
    from girlframe.services.m2_state import load_state
    from girlframe.services.m3_bonded import pair_lineage, prove
    from girlframe.services.m3_dose_up import _roll_source

    if source.kind != "side" or source.action is None or not account.strip():
        raise WorkflowError("Use the actual original Side source and physical arrival account")
    # Prove the committed original source, not a second entitlement after its
    # one-use lesson was consumed. Current Pair/body provenance still must hold.
    saved_source = prove(game, c, load_state(c, game.store.campaign_id), source.id)
    if saved_source != source:
        raise WorkflowError("Recover the saved original Side result before arrival")
    actual_pair, pair_event = pair_lineage(game, c, state, source.actor)
    if actual_pair != source.pair or pair_event != source.pair_source:
        raise WorkflowError("Preserve this source's original Pair rather than a successor account")
    action = game.action(c, source.action)
    _, total = _roll_source(game, c, action)
    if action["data"].get("bonded", {}).get("source") != source.id:
        raise WorkflowError("Recover the actual original Side action")
    selection = _selected(state, source, event)
    if "arrive" not in selection.options or (
        weapon and (total < 11 or "weapon" not in selection.options)
    ):
        raise WorkflowError("Apply only the actual selected Side result and high weapon benefit")
    bound = profiles(c, game.store.campaign_id)
    own, target = (
        resolve(state, ref, bound, require_current_profile=False)
        for ref in (source.actor, source.pair)
    )
    old = next((x for x in state.placements if x.actor == source.actor), None)
    paired = next((x for x in state.placements if x.actor == source.pair), None)
    if (
        old is None
        or paired is None
        or target.cell is None
        or own.cell is None
        or own.offstage_source
        or target.offstage_source
        or old.custody is not None
        or not old.vitals_active
        or old.incapacitated
        or old.subsumed
        or own.vessel_id != source.vessels.get(source.actor.token)
        or target.vessel_id != source.vessels.get(source.pair.token)
    ):
        raise WorkflowError(
            "BONDED_ARRIVAL_BODY_SOURCE_REQUIRED: retain actual bodies, custody "
            "and physical Pair location"
        )
    occupied_owner = None
    occupied_instance = None
    mode = "outside_frame"
    if target.inside_frame is True:
        occupied_owner = paired.occupied_frame_owner or source.pair
        occupied_instance = paired.occupied_frame_instance or target.frame_instance
        if occupied_instance is None:
            raise WorkflowError("Recover the actual Pair's occupied physical Frame")
        mode = "inside_frame"
        if occupied_owner == source.actor:
            if occupied_instance != old.frame_instance or old.frame_cell != target.cell:
                raise WorkflowError(
                    "Recover the original parked Frame that actually contains the Pair"
                )
            occupied_owner = occupied_instance = None
    replacement = old.model_copy(
        update=dict(
            girl_cell=target.cell,
            mode=mode,
            occupied_frame_owner=occupied_owner,
            occupied_frame_instance=occupied_instance,
            source_event=event,
            account=account,
        )
    )
    replacement = type(old).model_validate_json(replacement.model_dump_json())
    state.placements = [replacement if x.actor == source.actor else x for x in state.placements]
    state.facts.append(
        dict(
            kind="bonded_arrival",
            source=source.id,
            event=event,
            body=json.dumps(
                dict(
                    actor=source.actor.model_dump(mode="json"),
                    pair=source.pair.model_dump(mode="json"),
                    origin=old.model_dump(mode="json"),
                    destination=replacement.model_dump(mode="json"),
                )
            ),
        )
    )
    if weapon:
        details = json.loads(selection.text)
        name, description = details.get("weapon_name", ""), details.get("weapon_description", "")
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(description, str)
            or not description.strip()
        ):
            raise WorkflowError("Name and describe the actual source-granted found weapon")
        item_id = "bonded-weapon:" + str(uuid5(NAMESPACE_URL, source.id))
        if any(x.id == item_id for x in state.held_items):
            raise WorkflowError("Preserve the original once-created found object")
        state.held_items.append(
            HeldItem(
                id=item_id,
                holder=source.actor,
                name=name,
                description=description,
                source_event=event,
                source_owner=source.actor,
                proposed_event=source.event,
                confirmed_by=source.actor,
                confirmed_controller=source.controllers[source.actor.token],
                confirmed_event=event,
                factual_source_action=source.action,
                weapon=True,
            )
        )


def prove_found_weapon(
    game: "GameService", c: Connection, state: GameState, item: HeldItem
) -> None:
    from girlframe.services.m3_bonded import prove
    from girlframe.services.m3_dose_up import _roll_source
    from girlframe.services.m3_items import _snapshot

    birth = _snapshot(c, game, item.source_event)
    if birth is None or item.factual_source_action is None:
        raise WorkflowError("Recover the real original Side found-weapon event")
    action = game.action(c, item.factual_source_action)
    meta = action["data"].get("bonded", {})
    source = prove(game, c, birth, meta.get("source", ""))
    _, total = _roll_source(game, c, action)
    selected = _selected(birth, source, item.source_event)
    details = json.loads(selected.text)
    event = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == item.source_event,
        )
    ).first()
    expected = "bonded-weapon:" + str(uuid5(NAMESPACE_URL, source.id))
    if (
        source.kind != "side"
        or total < 11
        or set(selected.options) != {"arrive", "weapon"}
        or item.id != expected
        or source.action != item.factual_source_action
        or item.source_owner != source.actor
        or item.confirmed_by != source.actor
        or item.confirmed_controller != source.controllers[source.actor.token]
        or item.confirmed_event != item.source_event
        or not item.weapon
        or item.name != details.get("weapon_name")
        or item.description != details.get("weapon_description")
        or item.asset_id is not None
        or item.asset_json is not None
        or event is None
        or event.kind != "m3.choice_resolved"
        or event.actor_id != str(item.confirmed_controller)
    ):
        raise WorkflowError(
            "Preserve the actual high Side receipt, original human choice and found object"
        )


def issue_requested_order(
    game: "GameService",
    c: Connection,
    state: GameState,
    viewer: Any,
    key: str,
    channel: int,
    target: int,
    instruction: str,
    *,
    dose_up: bool,
) -> dict[str, str] | None:
    """Give the requested real Order inside its original, same-recipient Sex Action."""
    from uuid import uuid4

    from girlframe.engine.m3_bonded import get
    from girlframe.services.m3_bonded import bind_order, order_authority

    if str(viewer.user_id) not in state.sheets or str(target) not in state.sheets:
        return None
    authority = order_authority(game, c, state, viewer.user_id, target, instruction)
    if authority is None:
        return None
    if dose_up:
        raise WorkflowError("Complete the actual requested Pair Order before a separate Dose Order")
    source = get(state, authority["source"])
    if source.action is None:
        raise WorkflowError("Recover the real original rolled Pair Sex action")
    parent = game.action(c, source.action)
    lock = game.lock(c, channel)
    if (
        parent["state"] in ("complete", "aborted")
        or parent["actor_id"] != str(target)
        or parent["channel_id"] != str(channel)
        or lock is None
        or lock["state"] != "held"
        or lock["action_id"] != parent["id"]
        or parent["data"].get("order_id")
    ):
        raise WorkflowError("Preserve the original held Pair Sex source before issuing its Order")
    identity, event = str(uuid4()), str(uuid4())
    c.execute(
        t.m2["m2_orders"]
        .insert()
        .values(
            campaign_id=game.store.campaign_id,
            id=identity,
            issuer_id=str(viewer.user_id),
            target_id=str(target),
            channel_id=str(channel),
            state="awaiting_response",
            body_json=json.dumps(dict(text=instruction, bonded=authority)),
        )
    )
    bind_order(game, c, state, authority, identity, event)
    parent["data"].update(order_id=identity, order_text=instruction)
    game.request(c, parent, target, "order_response", dict(order_id=identity))
    game.save_action(c, parent, state="awaiting_choices")
    game.event(
        c,
        viewer.user_id,
        key,
        "m2.order_issued",
        state,
        event_id=event,
        action_id=parent["id"],
        order_id=identity,
        bonded_source=source.id,
        bonded_detail=authority["detail"],
    )
    return dict(action_id=parent["id"], order_id=identity)
