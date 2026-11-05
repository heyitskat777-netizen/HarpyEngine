"""Native LEGION Flirt alternatives, bound to the real original giver and resources."""

from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_dampener import native
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import FrameRuleReceipt

RULE = "frame.class.legion.kicked-puppy"
QUESTION = "kicked_care"
QUESTION_TEXT = "How do you want to care for me?"


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


def target_gave(tag: TagState, target: ActorRef) -> bool:
    if target.kind != "pilot" or tag.gm_setter_appointment is not None:
        return False
    if tag.giver_actor is not None:
        return tag.giver_actor == target
    # The immutable original character field is a legacy source binding, not a current UID lookup.
    return (
        tag.giver_character is not None
        and tag.giver_character == target.incarnation
        and str(tag.giver) == target.entity
    )
