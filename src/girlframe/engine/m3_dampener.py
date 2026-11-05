"""Native LEGION Dampener: real Heat cost and an explicitly smaller roll basis."""

from girlframe.engine.frame_classes import frame_class
from girlframe.engine.m2 import GameState, PilotSheet
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_careers import can_pilot
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import FrameRuleReceipt

RULE = "frame.class.legion.dampener-link"


def native(state: GameState, actor: ActorRef) -> tuple[PilotSheet, str]:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if (
        sheet is None
        or sheet.character_id != actor.incarnation
        or sheet.frame_scrapped
        or not can_pilot(state, actor)
        or frame_class(sheet.frame) != "legion"
    ):
        raise ValueError("Use the actual original Pilot's current native LEGION Frame")
    return sheet, sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(
        actor.incarnation
    )


def held(state: GameState, actor: ActorRef) -> FrameRuleReceipt | None:
    try:
        sheet, frame = native(state, actor)
    except (ValueError, KeyError):
        return None
    return next(
        (
            x
            for x in state.requisitions
            if isinstance(x, FrameRuleReceipt)
            and x.actor == actor
            and x.frame_instance == frame
            and x.frame == sheet.frame
            and x.donor_frame == sheet.frame
            and x.rule_id == RULE
            and x.kind == "ability_unlock"
            and not suspended(state, x.id)
        ),
        None,
    )
