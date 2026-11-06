"""Source eligibility for named, already implemented Class consumers."""

from typing import TYPE_CHECKING, Literal

from girlframe.engine.frame_classes import FRAME_CLASSES, FrameClass, frame_class
from girlframe.engine.m3_actor_state import ActorRef

if TYPE_CHECKING:
    from girlframe.engine.m2 import GameState, PilotSheet
    from girlframe.engine.m3_requisition_state import FrameRuleReceipt

CLASSES: dict[str, FrameClass] = {
    "frame.class.autocrat.untouchable-frame": "autocrat",
    "frame.class.autocrat.martyr": "autocrat",
    "frame.class.legion.dampener-link": "legion",
    "frame.class.legion.kicked-puppy": "legion",
    "frame.class.legion.modular-build": "legion",
    "frame.class.legion.home-of-a-sort": "legion",
    "frame.class.priestess.sup-of-primordial-flesh": "priestess",
    "frame.class.autocrat.handlers-special-girl": "autocrat",
    "frame.class.priestess.appearance-matrix": "priestess",
    "frame.class.priestess.nightmare-core": "priestess",
    "frame.class.autocrat.succubus-protocol": "autocrat",
    "frame.class.autocrat.clone-am": "autocrat",
}


def acquisition(
    state: "GameState", actor: ActorRef, rule: str, donor: str | None = None
) -> tuple["PilotSheet", str, Literal["ability_unlock", "frame_grafting"], Literal[2, 3], str]:
    from girlframe.engine.m3_nightmare import current

    required = CLASSES[rule]
    sheet, frame = current(state, actor)
    own = frame_class(sheet.frame) == required
    if own and donor not in (None, sheet.frame) or not own and donor not in donors(rule):
        raise ValueError("Select an actual eligible Class donor for this non-native graft")
    return (
        sheet,
        frame,
        "ability_unlock" if own else "frame_grafting",
        2 if own else 3,
        sheet.frame if own else str(donor),
    )


def donors(rule: str) -> tuple[str, ...]:
    return tuple(x for x in FRAME_CLASSES if frame_class(x) == CLASSES[rule])


def offer(
    state: "GameState", actor: ActorRef, rule: str
) -> tuple["PilotSheet", str, Literal["ability_unlock", "frame_grafting"], Literal[2, 3], str]:
    from girlframe.engine.m3_nightmare import current

    sheet, _ = current(state, actor)
    donor = sheet.frame if frame_class(sheet.frame) == CLASSES[rule] else donors(rule)[0]
    return acquisition(state, actor, rule, donor)


def eligible(state: "GameState", receipt: "FrameRuleReceipt") -> bool:
    if receipt.rule_id not in CLASSES:
        return False
    from girlframe.engine.m3_class_retention import eligible as retained

    if retained(state, receipt):
        return True
    try:
        sheet, frame, kind, price, donor = acquisition(
            state, receipt.actor, receipt.rule_id, receipt.donor_frame
        )
        return (
            receipt.frame == sheet.frame
            and receipt.frame_instance == frame
            and receipt.kind == kind
            and receipt.price == price
            and receipt.donor_frame == donor
        )
    except (ValueError, KeyError):
        return False


def sheet_eligible(sheet: "PilotSheet", receipt: "FrameRuleReceipt") -> bool:
    """The same exact source on an archived original sheet, without reviving its role."""
    if receipt.rule_id not in CLASSES or receipt.actor.kind != "pilot":
        return False
    try:
        own = frame_class(sheet.frame) == CLASSES[receipt.rule_id]
        return (
            str(sheet.owner) == receipt.actor.entity
            and sheet.character_id == receipt.actor.incarnation
            and receipt.frame == sheet.frame
            and receipt.frame_instance
            == (
                sheet.frame_runtime.id
                if sheet.frame_runtime
                else "initial:" + str(sheet.character_id)
            )
            and frame_class(receipt.donor_frame) == CLASSES[receipt.rule_id]
            and (
                receipt.kind == "ability_unlock"
                and own
                and receipt.donor_frame == sheet.frame
                or receipt.kind == "frame_grafting"
                and not own
            )
        )
    except (ValueError, KeyError):
        return False


def held(state: "GameState", actor: ActorRef, rule: str) -> "FrameRuleReceipt | None":
    from girlframe.engine.m3_class_retention import RULES, binding
    from girlframe.engine.m3_privileges import suspended
    from girlframe.engine.m3_requisition_state import FrameRuleReceipt

    if rule not in CLASSES:
        return None
    values = [
        x
        for x in state.requisitions
        if isinstance(x, FrameRuleReceipt)
        and x.rule_id == rule
        and x.actor == actor
        and eligible(state, x)
        and not any(
            suspended(state, identity)
            for identity in (binding(state, x)[1] if rule in RULES else (x.id,))
        )
    ]
    if len(values) > 1:
        raise ValueError("Recover one actual original Class acquisition source")
    return values[0] if values else None
