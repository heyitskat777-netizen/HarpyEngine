"""Actual secret possessions and frame-specific prepared comforts retain their provenance."""

from typing import TYPE_CHECKING, Literal, cast
from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_class_retention import binding
from girlframe.engine.m3_frame_swap_state import SwapReceipt
from girlframe.engine.m3_requisition_state import FrameRuleReceipt

if TYPE_CHECKING:
    from girlframe.engine.m3_home import Installation

KIND = "home_reinstalled"


class HomeObject(Model):
    id: str
    purchase: str
    choice: str
    origin_frame: str
    origin_event: str


class Realization(Model):
    id: str
    purchase: str
    choice: Literal["napping", "bottle"]
    frame: str
    event: str
    prior_realization: str | None = None
    object_ids: tuple[str, ...] = ()


class PreparedHome(Model):
    purchase: str
    actor: ActorRef
    frame: str
    choices: tuple[str, ...]
    objects: tuple[HomeObject, ...]
    realizations: tuple[Realization, ...]


class HomeTransfer(Model):
    purchase: str
    actor: ActorRef
    old_frame: str
    frame: str
    swap: str
    event: str
    object_ids: tuple[str, ...]
    realizations: tuple[Realization, ...]
    confirmed_by: int
    confirmed: Literal[True]


def _id(*parts: str) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:home:" + ":".join(parts)))


def objects(state: GameState, paid: FrameRuleReceipt) -> tuple[HomeObject, ...]:
    from girlframe.engine.m3_home import installed

    origin = installed(state, paid)
    return tuple(
        HomeObject(
            id=_id(origin.purchase, choice),
            purchase=origin.purchase,
            choice=choice,
            origin_frame=origin.frame,
            origin_event=origin.event,
        )
        for choice in origin.items
        if choice != "napping"
    )


def _realizations(
    origin: "Installation",
    items: tuple[HomeObject, ...],
    frame: str,
    event: str,
    prior: tuple[Realization, ...] = (),
) -> tuple[Realization, ...]:
    return tuple(
        Realization(
            id=_id(origin.purchase, choice, frame, event),
            purchase=origin.purchase,
            choice=cast(Literal["napping", "bottle"], choice),
            frame=frame,
            event=event,
            prior_realization=next((x.id for x in prior if x.choice == choice), None),
            object_ids=tuple(x.id for x in items if x.choice == choice),
        )
        for choice in origin.items
        if choice in ("napping", "bottle")
    )


def transfers(state: GameState, paid: FrameRuleReceipt) -> tuple[HomeTransfer, ...]:
    values = tuple(
        HomeTransfer.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )
    if len({(x.purchase, x.swap) for x in values}) != len(values):
        raise ValueError("One actual Home preparation per paid Swap")
    return tuple(x for x in values if x.purchase == paid.id)


def prepared(state: GameState, paid: FrameRuleReceipt) -> PreparedHome:
    from girlframe.engine.m3_home import installed

    origin = installed(state, paid)
    assigned, chain = binding(state, paid)
    items = objects(state, paid)
    values = transfers(state, paid)
    if tuple(x.swap for x in values) != chain[1:]:
        raise ValueError("Recover every actual Home reinstallation")
    frame = origin.frame
    fixtures = _realizations(origin, items, frame, origin.event)
    for change in values:
        swap = next((x for x in state.requisitions if x.id == change.swap), None)
        if (
            not isinstance(swap, SwapReceipt)
            or change.actor != paid.actor
            or change.confirmed_by != int(paid.actor.entity)
            or (swap.actor, swap.old_frame, swap.new_frame, swap.source_event)
            != (paid.actor, frame, change.frame, change.event)
            or change.old_frame != frame
            or change.object_ids != tuple(x.id for x in items)
            or change.realizations
            != _realizations(origin, items, change.frame, change.event, fixtures)
        ):
            raise ValueError("Recover the same Home possessions and actual prepared comforts")
        frame, fixtures = change.frame, change.realizations
    if frame != assigned:
        raise ValueError("Recover the Home's current actually prepared Frame")
    return PreparedHome(
        purchase=paid.id,
        actor=paid.actor,
        frame=frame,
        choices=origin.items,
        objects=items,
        realizations=fixtures,
    )


def accessible(state: GameState, paid: FrameRuleReceipt) -> None:
    from girlframe.engine.m3_physical import cockpit_lock

    value = prepared(state, paid)
    pose = next((x for x in state.placements if x.actor == paid.actor), None)
    if (
        pose is None
        or pose.frame_instance != value.frame
        or pose.mode != "outside_frame"
        or pose.occupied_frame_owner is not None
        or pose.custody is not None
        or pose.incapacitated
        or not pose.vitals_active
        or pose.subsumed
        or pose.girl_cell is None
        or pose.frame_cell != pose.girl_cell
        or cockpit_lock(state, paid.actor, value.frame) is not None
    ):
        raise ValueError("Use the actual accessible Home colocated with its outside original owner")


def transfer(
    before: GameState,
    after: GameState,
    paid: FrameRuleReceipt,
    swap: SwapReceipt,
    *,
    confirmed: bool,
) -> None:
    from girlframe.engine.m3_home import held, installed

    accessible(before, paid)
    previous = prepared(before, paid)
    origin = next(x for x in before.placements if x.actor == paid.actor)
    delivered = next((x for x in after.placements if x.actor == paid.actor), None)
    parked = next((x for x in after.parked_frames if x.frame_instance == previous.frame), None)
    retained_ids = {
        x.id for x in before.sheets[paid.actor.entity].assets if x.family == "frame"
    } & {x.id for x in after.sheets[paid.actor.entity].assets if x.family == "frame"}
    if (
        not confirmed
        or held(before, paid.actor) != paid
        or paid not in after.requisitions
        or swap not in after.requisitions
        or swap in before.requisitions
        or swap.actor != paid.actor
        or swap.old_frame != previous.frame
        or swap.selection.retained_receipt != paid.id
        or swap.selection.retained_rule != paid.rule_id
        or binding(after, paid)[0] != swap.new_frame
        or installed(before, paid) != installed(after, paid)
        or transfers(before, paid) != transfers(after, paid)
        or objects(before, paid) != objects(after, paid)
        or retained_ids != {swap.selection.retained_asset}
        or delivered is None
        or parked is None
        or delivered.vessel_id != origin.vessel_id
        or delivered.mode != "outside_frame"
        or delivered.frame_instance != swap.new_frame
        or delivered.frame_cell != origin.girl_cell
        or delivered.girl_cell != origin.girl_cell
        or delivered.source_event != swap.source_event
        or parked.owner != paid.actor
        or parked.source_event != swap.source_event
        or parked.cell != origin.frame_cell
    ):
        raise ValueError("Confirm actual same-possession Home transfer and new comfort preparation")
    change = HomeTransfer(
        purchase=paid.id,
        actor=paid.actor,
        old_frame=previous.frame,
        frame=swap.new_frame,
        swap=swap.id,
        event=swap.source_event,
        object_ids=tuple(x.id for x in previous.objects),
        realizations=_realizations(
            installed(before, paid),
            previous.objects,
            swap.new_frame,
            swap.source_event,
            previous.realizations,
        ),
        confirmed_by=int(paid.actor.entity),
        confirmed=True,
    )
    after.facts.append(dict(kind=KIND, body=change.model_dump_json()))
    prepared(after, paid)
