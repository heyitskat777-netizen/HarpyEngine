"""Source-bound native or grafted Nightmare Core on its actual owned Frame."""

from girlframe.engine.frame_classes import FRAME_CLASSES, frame_class, official_frame
from girlframe.engine.m2 import GameState, PilotSheet
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_careers import can_pilot
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import FrameRuleReceipt

RULE = "frame.class.priestess.nightmare-core"
DONORS = tuple(x for x in FRAME_CLASSES if frame_class(x) == "priestess")


def current(state: GameState, actor: ActorRef) -> tuple[PilotSheet, str]:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if (
        sheet is None
        or str(sheet.owner) != actor.entity
        or sheet.character_id != actor.incarnation
        or sheet.frame_scrapped
        or not can_pilot(state, actor)
        or official_frame(sheet.frame) not in FRAME_CLASSES
    ):
        raise ValueError("Use the actual original Pilot's current usable official Frame")
    return sheet, sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(
        actor.incarnation
    )


def native(state: GameState, actor: ActorRef) -> tuple[PilotSheet, str]:
    sheet, frame = current(state, actor)
    if frame_class(sheet.frame) != "priestess":
        raise ValueError("Use the actual original Pilot's current native Priestess Frame")
    return sheet, frame


def receipt_eligible(state: GameState, receipt: FrameRuleReceipt) -> bool:
    """Check only this implemented rule, including while its exact receipt is suspended."""
    try:
        sheet, frame = current(state, receipt.actor)
        own = frame_class(sheet.frame) == "priestess"
        return (
            receipt.rule_id == RULE
            and receipt.frame_instance == frame
            and receipt.frame == sheet.frame
            and frame_class(receipt.donor_frame) == "priestess"
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


def held(state: GameState, actor: ActorRef) -> FrameRuleReceipt | None:
    values = [
        x
        for x in state.requisitions
        if isinstance(x, FrameRuleReceipt)
        and x.actor == actor
        and receipt_eligible(state, x)
        and not suspended(state, x.id)
    ]
    if len(values) > 1:
        raise ValueError("Recover one actual original Nightmare Core acquisition receipt")
    return values[0] if values else None
