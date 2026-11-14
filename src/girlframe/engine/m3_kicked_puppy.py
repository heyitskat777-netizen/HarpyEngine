"""Native LEGION Flirt alternatives, bound to the real original giver and resources."""

from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_requisition_state import FrameRuleReceipt

RULE = "frame.class.legion.kicked-puppy"
QUESTION = "kicked_care"
QUESTION_TEXT = "How do you want to care for me?"


def held(state: GameState, actor: ActorRef) -> FrameRuleReceipt | None:
    from girlframe.engine.m3_class_grafts import held as acquired

    return acquired(state, actor, RULE)


def target_gave(tag: TagState, target: ActorRef) -> bool:
    if target.kind not in ("pilot", "npc") or tag.gm_setter_appointment is not None:
        return False
    if tag.giver_actor is not None:
        return tag.giver_actor == target
    if target.kind != "pilot":
        return False
    # The immutable original character field is a legacy source binding, not a current UID lookup.
    return (
        tag.giver_character is not None
        and tag.giver_character == target.incarnation
        and str(tag.giver) == target.entity
    )
