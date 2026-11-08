"""Source-owned active Mentor sets; original creation assignments remain immutable."""

from typing import TYPE_CHECKING, Literal

from girlframe.engine.m3_actor_state import ActorRef, Model

if TYPE_CHECKING:
    from girlframe.engine.m2 import GameState


class MentorSet(Model):
    learner: ActorRef
    mentors: tuple[ActorRef, ...]
    source_event: str
    session: str
    reason: Literal["newgirl_sex_group", "newgirl_sex_replacement"]


def records(state: "GameState") -> tuple[MentorSet, ...]:
    return tuple(
        MentorSet.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "mentor_set"
    )


def current_set(state: "GameState", learner: ActorRef) -> MentorSet | None:
    return next((x for x in reversed(records(state)) if x.learner == learner), None)


def active_mentors(state: "GameState", learner: ActorRef) -> tuple[ActorRef, ...]:
    sheet = state.sheets.get(learner.entity)
    if learner.kind != "pilot" or sheet is None or sheet.character_id != learner.incarnation:
        return ()
    value = current_set(state, learner)
    if value is not None:
        refs = value.mentors
    elif sheet.mentor is not None:
        setup = sheet.girl_runtime.setup if sheet.girl_runtime else None
        other = state.sheets.get(str(sheet.mentor))
        if setup and setup.mentor:
            refs = (setup.mentor,)
        elif other and other.character_id:
            refs = (
                ActorRef(kind="pilot", entity=str(sheet.mentor), incarnation=other.character_id),
            )
        else:
            refs = ()
    else:
        refs = ()
    return tuple(
        x
        for x in refs
        if x.kind == "pilot"
        and x.entity in state.sheets
        and state.sheets[x.entity].character_id == x.incarnation
    )


def is_mentor(state: "GameState", learner: ActorRef, mentor: ActorRef) -> bool:
    return mentor in active_mentors(state, learner)
