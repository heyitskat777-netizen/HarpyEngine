"""Actual JANUS paid entitlements on their original physical Frame."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_janus import RULES
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import FrameRuleReceipt

PANDORA, TRAINING, STORAGE, UNIVERSAL, PET = RULES
TITLES = {
    PANDORA: "PANDORA",
    TRAINING: "Obedience Training",
    STORAGE: "Void Storage",
    UNIVERSAL: "Universal Plug",
    PET: "A Girl Is Kinda Like a Pet",
}


def held(state: GameState, actor: ActorRef, rule: str) -> FrameRuleReceipt | None:
    if actor.kind != "pilot":
        return None
    sheet = state.sheets.get(actor.entity)
    if sheet is None or sheet.character_id != actor.incarnation or sheet.frame_scrapped:
        return None
    frame = sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(actor.incarnation)
    values = [
        x
        for x in state.requisitions
        if isinstance(x, FrameRuleReceipt)
        and x.actor == actor
        and x.frame_instance == frame
        and x.rule_id == rule
        and x.donor_frame == "JANUS"
        and rule in RULES
        and not suspended(state, x.id)
    ]
    if len(values) > 1:
        raise ValueError("Recover one actual original JANUS acquisition receipt")
    return values[0] if values else None
