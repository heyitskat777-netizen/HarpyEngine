"""Exact paid Class source retained by an actual optional Frame Swap."""

from typing import TYPE_CHECKING

from girlframe.engine.frame_classes import frame_class
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_frame_swap_state import SwapReceipt
from girlframe.engine.m3_requisition_state import FrameRuleReceipt

if TYPE_CHECKING:
    from girlframe.engine.m2 import GameState

# Each consumer needs its own original-source/current-Frame adapter. Hardware is not implied.
RULES = frozenset(
    (
        "frame.class.legion.dampener-link",
        "frame.class.legion.kicked-puppy",
        "frame.class.autocrat.untouchable-frame",
        "frame.class.autocrat.martyr",
        "frame.class.autocrat.succubus-protocol",
        "frame.class.priestess.sup-of-primordial-flesh",
    )
)


class Retention(Model):
    purchase: str
    swap: str
    actor: ActorRef
    old_frame: str
    frame: str
    rule: str
    event: str


def links(state: "GameState") -> tuple[Retention, ...]:
    values = tuple(
        Retention.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "class_rule_retained"
    )
    if len({x.swap for x in values}) != len(values):
        raise ValueError("One paid Frame Swap retains exactly one Class source")
    return values


def binding(state: "GameState", paid: FrameRuleReceipt) -> tuple[str, tuple[str, ...]]:
    if paid.rule_id not in RULES or paid not in state.requisitions:
        raise ValueError("Use an explicitly adapted original retained Class purchase")
    from girlframe.engine.m3_class_grafts import CLASSES

    required = CLASSES[paid.rule_id]
    own = frame_class(paid.frame) == required
    if (
        frame_class(paid.donor_frame) != required
        or (paid.kind == "ability_unlock" and (not own or paid.donor_frame != paid.frame))
        or (paid.kind == "frame_grafting" and own)
    ):
        raise ValueError("Preserve the original native or graft acquisition source")
    assigned, receipts = paid.frame_instance, [paid.id]
    for link in links(state):
        if link.purchase != paid.id:
            continue
        receipt = next((x for x in state.requisitions if x.id == link.swap), None)
        if (
            not isinstance(receipt, SwapReceipt)
            or receipt.actor != paid.actor
            or link.actor != paid.actor
            or receipt.old_frame != assigned
            or link.old_frame != assigned
            or receipt.new_frame != link.frame
            or receipt.source_event != link.event
            or receipt.selection.retained_rule != paid.rule_id
            or link.rule != paid.rule_id
            or receipt.selection.retained_receipt != paid.id
        ):
            raise ValueError("Recover the exact original paid Class retention chain")
        assigned = receipt.new_frame
        receipts.append(receipt.id)
    return assigned, tuple(receipts)


def eligible(state: "GameState", paid: FrameRuleReceipt) -> bool:
    from girlframe.engine.m3_nightmare import current

    try:
        assigned, receipts = binding(state, paid)
        _, actual = current(state, paid.actor)
        return len(receipts) > 1 and assigned == actual
    except (ValueError, KeyError):
        return False


def retain(state: "GameState", paid: FrameRuleReceipt, swap: SwapReceipt) -> None:
    assigned, _ = binding(state, paid)
    if (
        swap.old_frame != assigned
        or swap.selection.retained_receipt != paid.id
        or swap.selection.retained_rule != paid.rule_id
        or swap.actor != paid.actor
    ):
        raise ValueError("Retain the selected actual original Class source once")
    if any(x.swap == swap.id for x in links(state)):
        raise ValueError("This paid Frame Swap already retained its one actual rule")
    value = Retention(
        purchase=paid.id,
        swap=swap.id,
        actor=paid.actor,
        old_frame=assigned,
        frame=swap.new_frame,
        rule=paid.rule_id,
        event=swap.source_event,
    )
    state.facts.append(dict(kind="class_rule_retained", id=swap.id, body=value.model_dump_json()))
    binding(state, paid)


def swap_source(state: "GameState", swap: SwapReceipt) -> FrameRuleReceipt | None:
    from girlframe.engine.m3_privileges import suspended

    paid = next(
        (
            x
            for x in state.requisitions
            if isinstance(x, FrameRuleReceipt) and x.id == swap.selection.retained_receipt
        ),
        None,
    )
    if paid is None or paid.rule_id not in RULES:
        return None
    assigned, receipts = binding(state, paid)
    if (
        swap.id not in receipts
        or swap.new_frame != assigned
        or not eligible(state, paid)
        or any(suspended(state, x) for x in receipts)
    ):
        return None
    return paid
