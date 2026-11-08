"""Original Mentor-authored fictional names preserve the actual Newgirl's resources."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.shared_setup import CallsignChoice

RULE = "girl.newgirl.mentor"


class Naming(Model):
    id: str
    learner: ActorRef
    mentor: ActorRef
    assignment: str
    before: str
    callsign: str
    event: str


def records(state: GameState) -> tuple[Naming, ...]:
    return tuple(
        Naming.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "mentor_naming"
    )


def rename(
    original: GameState,
    learner: ActorRef,
    mentor: ActorRef,
    assignment: str,
    callsign: str,
    event: str,
) -> GameState:
    selected = CallsignChoice(callsign=callsign).callsign
    if (
        learner.kind != "pilot"
        or mentor.kind != "pilot"
        or learner == mentor
        or not assignment
        or not event
        or learner.entity not in original.sheets
        or mentor.entity not in original.sheets
        or original.sheets[learner.entity].character_id != learner.incarnation
        or original.sheets[mentor.entity].character_id != mentor.incarnation
        or original.sheets[learner.entity].mentor != int(mentor.entity)
    ):
        raise ValueError("Use the actual distinct original Newgirl and proved assigned Mentor")
    if any(x.id == event for x in records(original)):
        raise ValueError("Preserve the immutable original Mentor name choice")
    state = GameState.model_validate_json(original.model_dump_json())
    sheet = state.sheets[learner.entity]
    previous = sheet.callsign
    sheet.callsign = selected
    sheet.revision += 1
    value = Naming(
        id=event,
        learner=learner,
        mentor=mentor,
        assignment=assignment,
        before=previous,
        callsign=selected,
        event=event,
    )
    state.facts.append(dict(kind="mentor_naming", id=value.id, body=value.model_dump_json()))
    return state
