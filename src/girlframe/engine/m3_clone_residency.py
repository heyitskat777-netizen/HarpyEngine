"""Same artificial person changes carrier only at genuine paid Frame Swap delivery."""

import hashlib

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_class_retention import binding
from girlframe.engine.m3_frame_swap_state import SwapReceipt
from girlframe.engine.m3_requisition_state import FrameRuleReceipt

KIND = "clone_residency_transferred"


class Transfer(Model):
    actor: ActorRef
    original: ActorRef
    purchase: str
    old_frame: str
    frame: str
    swap: str
    event: str
    copy_sha256: str


def transfers(state: GameState, ref: ActorRef) -> tuple[Transfer, ...]:
    values = tuple(
        Transfer.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )
    if len({(x.actor.token, x.swap) for x in values}) != len(values):
        raise ValueError("One actual copy transfers once per paid Swap")
    return tuple(x for x in values if x.actor == ref)


def residence(state: GameState, ref: ActorRef) -> str:
    from girlframe.engine.m3_clone_am import RULE, find

    value = find(state, ref)
    paid = next((x for x in state.requisitions if value and x.id == value.receipt), None)
    if (
        value is None
        or not isinstance(paid, FrameRuleReceipt)
        or paid.rule_id != RULE
        or (paid.actor, paid.frame_instance, paid.source_event)
        != (value.original, value.frame, value.source_event)
    ):
        raise ValueError("Recover the original copy's birth and paid residence source")
    assigned, chain = binding(state, paid)
    values = transfers(state, ref)
    if tuple(x.swap for x in values) != chain[1:]:
        raise ValueError("Recover every actual same-copy residency transfer")
    actual = value.frame
    for change in values:
        swap = next((x for x in state.requisitions if x.id == change.swap), None)
        if (
            not isinstance(swap, SwapReceipt)
            or change.original != value.original
            or change.purchase != paid.id
            or change.old_frame != actual
            or (swap.actor, swap.old_frame, swap.new_frame, swap.source_event)
            != (value.original, actual, change.frame, change.event)
        ):
            raise ValueError("Recover the exact paid same-copy carrier change")
        actual = change.frame
    if actual != assigned:
        raise ValueError("Recover the copy's actual current assigned carrier")
    return actual


def residence_token(state: GameState, ref: ActorRef) -> str:
    frame = residence(state, ref)
    return hashlib.sha256(
        (frame + "".join(x.model_dump_json() for x in transfers(state, ref))).encode()
    ).hexdigest()


def transfer(
    before: GameState, after: GameState, paid: FrameRuleReceipt, swap: SwapReceipt
) -> None:
    from girlframe.engine.m3_actors import fingerprint
    from girlframe.engine.m3_clone_am import copies, current, find

    values = tuple(x for x in copies(before) if x.receipt == paid.id)
    if len(values) != 1:
        raise ValueError("Transfer the one actual already-born copy")
    value = current(before, values[0].ref)
    old = residence(before, value.ref)
    origin = next((x for x in before.placements if x.actor == paid.actor), None)
    delivered = next((x for x in after.placements if x.actor == paid.actor), None)
    parked = next((x for x in after.parked_frames if x.frame_instance == old), None)
    if (
        paid not in before.requisitions
        or paid not in after.requisitions
        or swap not in after.requisitions
        or swap in before.requisitions
        or swap.actor != value.original
        or swap.old_frame != old
        or swap.selection.retained_receipt != paid.id
        or swap.selection.retained_rule != paid.rule_id
        or binding(after, paid)[0] != swap.new_frame
        or find(after, value.ref) != value
        or before.actor_bonds != after.actor_bonds
        or before.sheets[value.original.entity].heat != after.sheets[value.original.entity].heat
        or transfers(before, value.ref) != transfers(after, value.ref)
        or origin is None
        or delivered is None
        or parked is None
        or origin.mode != "outside_frame"
        or origin.frame_instance != old
        or origin.girl_cell is None
        or delivered.actor != origin.actor
        or delivered.vessel_id != origin.vessel_id
        or delivered.mode != "outside_frame"
        or delivered.frame_instance != swap.new_frame
        or delivered.frame_cell != origin.girl_cell
        or delivered.girl_cell != origin.girl_cell
        or delivered.source_event != swap.source_event
        or parked.owner != value.original
        or parked.source_event != swap.source_event
    ):
        raise ValueError("Transfer the same saved copy only with actual paid delivered replacement")
    value_transfer = Transfer(
        actor=value.ref,
        original=value.original,
        purchase=paid.id,
        old_frame=old,
        frame=swap.new_frame,
        swap=swap.id,
        event=swap.source_event,
        copy_sha256=fingerprint(value),
    )
    after.facts.append(dict(kind=KIND, body=value_transfer.model_dump_json()))
    residence(after, value.ref)
