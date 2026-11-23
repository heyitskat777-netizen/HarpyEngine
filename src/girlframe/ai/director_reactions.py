"""Role-scoped living-campaign reactions; proposals never execute mechanical effects."""

from typing import Any, Literal, Protocol

from pydantic import Field

from girlframe.ai.activity_batch import FictionBeat
from girlframe.ai.contracts import Contract
from girlframe.engine.m3_actor_state import ActorRef


class ReactionProposal(Contract):
    request_id: str
    kind: Literal[
        "WAIT", "DIALOGUE", "REFUSE", "COMPROMISE", "DELAY", "SCENE_OFFER", "REQUEST_ACTION"
    ]
    text: str = Field(default="", max_length=1600)
    cited_references: tuple[str, ...] = Field(default=(), max_length=20)
    rationale: str = Field(min_length=1, max_length=1200)
    route: Literal[
        "none", "gm_outcome", "worldbuilding", "controller_response", "native_choice"
    ] = "none"
    source_work_id: str | None = None
    effects: tuple[()] = ()
    fiction: FictionBeat | None = Field(default=None, exclude_if=lambda value: value is None)
    intended_recipients: tuple[ActorRef, ...] = Field(
        default=(), max_length=6, exclude_if=lambda value: not value
    )
    play_id: str | None = Field(
        default=None, max_length=120, exclude_if=lambda value: value is None
    )


class ReactionProvider(Protocol):
    def propose(self, packet: dict[str, Any]) -> ReactionProposal: ...
