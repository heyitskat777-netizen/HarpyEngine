"""One native Autocrat Requisition; no borrowed Frame or controller resources."""

from girlframe.engine.frame_classes import frame_class
from girlframe.engine.m2 import GameState, PilotSheet
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_careers import can_pilot
from girlframe.engine.m3_requisition_state import FrameRuleReceipt

RULE = "frame.class.autocrat.untouchable-frame"


def native(state: GameState, actor: ActorRef) -> tuple[PilotSheet, str]:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if (
        sheet is None
        or sheet.character_id != actor.incarnation
        or sheet.frame_scrapped
        or not can_pilot(state, actor)
        or frame_class(sheet.frame) != "autocrat"
    ):
        raise ValueError("Use the actual original Pilot's current native Autocrat Frame")
    return sheet, sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(
        actor.incarnation
    )


def held(state: GameState, actor: ActorRef) -> FrameRuleReceipt | None:
    from girlframe.engine.m3_class_grafts import held as acquired

    return acquired(state, actor, RULE)


def substitute(
    state: GameState,
    actor: ActorRef,
    tag_id: str,
    *,
    action: str,
    choice: str,
    event: str,
    receipt: FrameRuleReceipt,
) -> None:
    from girlframe.engine.m3_class_retention import binding
    from girlframe.engine.m3_nightmare import current

    sheet, frame = current(state, actor)
    if held(state, actor) != receipt or binding(state, receipt)[0] != frame:
        raise ValueError("Recover the actual original Frame's acquired Untouchable source")
    tag = next((x for x in sheet.tags if x.id == tag_id and not x.marked), None)
    if tag is None:
        raise ValueError("Mark only one of your own actual currently unmarked Tags")
    if any(
        x.get("kind") == "untouchable_frame_used" and x.get("choice") == choice for x in state.facts
    ):
        raise ValueError("This actual Engage damage already has its source substitution")
    tag.marked = True
    sheet.revision += 1
    state.facts.append(
        dict(
            kind="untouchable_frame_used",
            actor=actor.model_dump_json(),
            frame=frame,
            receipt=receipt.id,
            tag=tag.id,
            action=action,
            choice=choice,
            event=event,
        )
    )
