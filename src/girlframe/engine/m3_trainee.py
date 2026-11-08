"""Original-person teaching, owned Trainee choices and actual mentorship duties."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m2 import GameState, IdentityState, PilotSheet, TagState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_identity_slots import replacement_slot
from girlframe.engine.m3_leviathan_obsession import require_unlocked

RULE = "girl.newgirl.trainee"


class Teaching(Model):
    id: str
    learner: ActorRef
    mentor: ActorRef
    handler: ActorRef
    cast: SceneCast
    relation_source: str
    event: str
    account: str = Field(min_length=1, max_length=1200)


class Selection(Model):
    id: str
    teaching: str
    branch: Literal["erase", "act", "challenge"]
    event: str
    account: str = Field(min_length=1, max_length=1200)
    identity: IdentityState | None = None
    tag: TagState | None = None
    embraced: IdentityState | None = None
    heat: int = Field(default=0, ge=0, le=3)
    source_action: str | None = None


class Duty(Model):
    id: str
    teaching: str
    learner: ActorRef
    mentor: ActorRef
    handler: ActorRef
    source_event: str
    phase: Literal["mentor", "mentor_punishment", "reported", "handler_punishment", "complete"]
    case: str | None = None
    report_event: str | None = None
    report_account: str = ""
    reviewed_event: str | None = None
    review_account: str = ""
    completed_event: str | None = None


KINDS = {Teaching: "trainee_teaching", Selection: "trainee_selection", Duty: "trainee_duty"}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def put(state: GameState, value: Teaching | Selection | Duty) -> None:
    kind = KINDS[type(value)]
    if not isinstance(value, Duty) and any(
        x.get("kind") == kind and x.get("id") == value.id for x in state.facts
    ):
        raise ValueError("Preserve the original actual teaching and selected outcome")
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))


def erase(
    original: PilotSheet,
    identity: str,
    tag: str | None,
    mentor_tags: tuple[TagState, ...],
    source: str,
) -> tuple[PilotSheet, IdentityState, TagState | None, IdentityState | None]:
    sheet = PilotSheet.model_validate_json(original.model_dump_json())
    old = next((x for x in sheet.identities if x.id == identity), None)
    if (
        old is None
        or old.protected
        or old.paired
        or old.am_limiter
        or old.id in sheet.sedation_locked
    ):
        raise ValueError("SOURCE_IDENTITY_REMOVAL_REQUIRED: preserve the protected original slot")
    require_unlocked(sheet.identities, (old.id,))
    chosen = next((x for x in mentor_tags if x.id == tag), None)
    if bool(mentor_tags) != bool(chosen) or tag is not None and chosen is None:
        raise ValueError("Embrace one actual current original-Mentor Tag whenever you have one")
    sheet.identities = [x for x in sheet.identities if x.id != old.id]
    created = None
    if chosen is not None:
        if chosen.rejection_pending:
            raise ValueError("Finish the actual outstanding Tag source before embracing it")
        if any(x.name.casefold() == chosen.label.casefold() for x in sheet.identities):
            raise ValueError("Duplicate Identity labels need their actual source adapter")
        created = IdentityState(
            id=str(uuid5(NAMESPACE_URL, "trainee:" + source + ":" + chosen.id)),
            name=chosen.label,
            slot=old.slot if old.slot is not None else replacement_slot(sheet, None),
        )
        sheet.identities.append(created)
        sheet.tags = [x for x in sheet.tags if x.id != chosen.id]
    sheet.revision += 1
    return PilotSheet.model_validate_json(sheet.model_dump_json()), old, chosen, created
