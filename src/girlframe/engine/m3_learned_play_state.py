"""One actual Vatgrown learning source grants one use, without changing playbook identity."""

from pydantic import Field

from girlframe.engine.m3_actor_state import ActorRef, Model


class LearnedPlayUse(Model):
    id: str = Field(min_length=1)
    actor: ActorRef
    teacher: ActorRef
    session: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    event: str = Field(min_length=1)
    claimed_action: str | None = None
    rolled_event: str | None = None
