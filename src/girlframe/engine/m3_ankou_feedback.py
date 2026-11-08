"""Source-bound native Ankou final-Identity commitments and actual Feedback choices."""

from typing import Literal

from girlframe.engine.m2 import GameState, IdentityState, PilotSheet, PlayInput
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast

RULE = "frame.ankou.feedback-loop"
KIND = "ankou_feedback"


class Feedback(Model):
    id: str
    action: str
    actor: ActorRef
    frame: str
    cast: SceneCast
    registry: str
    mark_event: str
    prepared: PlayInput
    identity: IdentityState
    heat_before: int
    heat_committed: int
    committed_revision: int
    phase: Literal["choice", "purpose", "purpose_identity", "child", "resolved", "ended"] = "choice"
    choice: Literal["bond", "purpose", "tear", "die"] | None = None
    target: ActorRef | None = None
    target_controller: int | None = None
    choice_event: str | None = None
    request: str | None = None
    purpose: str | None = None
    purpose_event: str | None = None
    purpose_given: bool | None = None
    new_identity: str | None = None
    lost_asset: str | None = None
    child: str | None = None
    child_event: str | None = None
    resolved_event: str | None = None
    resume_revision: int | None = None
    rolled_event: str | None = None
    receipt: str | None = None
    archive: str | None = None
    prevention: bool = False
    loss_work: tuple[str, ...] = ()


class CommittedInputs(Model):
    source: str
    commit_event: str
    actor: ActorRef
    prepared: PlayInput
    resume_revision: int
    heat_committed: int


def sources(state: GameState) -> tuple[Feedback, ...]:
    return tuple(
        Feedback.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def get(state: GameState, identity: str) -> Feedback:
    value = next((x for x in sources(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the actual source-bound Ankou Feedback")
    return value


def put(state: GameState, value: Feedback) -> None:
    state.facts = [
        x for x in state.facts if not (x.get("kind") == KIND and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=KIND, id=value.id, body=value.model_dump_json()))


def final_mark(state: GameState, sheet: PilotSheet, entry: str | None) -> bool:
    if sheet.frame != "PROJECT ANKOU" or sheet.frame_scrapped or entry is None:
        return False
    identity = next((x for x in sheet.identities if x.id == entry and not x.marked), None)
    if identity is None:
        return False
    from girlframe.engine.m3_clone_am import additional_identities

    effective = (*sheet.identities, *additional_identities(state, sheet.owner))
    return all(x.marked or x.id == identity.id for x in effective)
