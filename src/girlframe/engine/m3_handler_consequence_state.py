"""Handler body consequences are actual source events, not invented Asset hit points."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model

Choice = Literal["opportunity", "chance_to_act", "weakness", "injury", "death"]


class HandlerBody(Model):
    actor: ActorRef
    persona_json: str | None = None
    tags_json: str
    heat: int = Field(ge=0)


class HandlerArchive(Model):
    id: str = Field(min_length=1)
    actor: ActorRef
    body: HandlerBody
    source_event: str = Field(min_length=1)
    consequence: str = Field(min_length=1)
    account: str = Field(min_length=1, max_length=1200)
    appointment: str = Field(min_length=1)
    links_json: str

    @model_validator(mode="after")
    def actual_body(self) -> "HandlerArchive":
        if self.actor.kind != "handler" or self.body.actor != self.actor:
            raise ValueError("Archive the actual original Handler body")
        return self


class HandlerConsequence(Model):
    id: str = Field(min_length=1)
    actor: ActorRef
    opponent: ActorRef | None = None
    trigger: Literal["asset_damage", "helpless"]
    source_event: str = Field(min_length=1)
    source_action: str | None = None
    source_work: str | None = None
    source_request: str | None = None
    appointment: str = Field(min_length=1)
    state: Literal["pending", "resolved", "ended"] = "pending"
    choice: Choice | None = None
    account: str = Field(default="", max_length=1200)
    effect_event: str | None = None
    ended_by: str | None = None

    @model_validator(mode="after")
    def owned(self) -> "HandlerConsequence":
        if self.actor.kind != "handler" or self.opponent == self.actor:
            raise ValueError("Use the actual Handler body and distinct actual opponent")
        if self.state == "resolved" and (
            self.choice is None or not self.account.strip() or not self.effect_event
        ):
            raise ValueError("The Handler must actually choose and describe the source consequence")
        if self.state == "ended" and (self.ended_by is None or not self.effect_event):
            raise ValueError("An already-dead body needs its actual source ending")
        return self


class HandlerInjury(Model):
    id: str = Field(min_length=1)
    actor: ActorRef
    consequence: str = Field(min_length=1)
    description: str = Field(min_length=1, max_length=1200)
    source_event: str = Field(min_length=1)
    recovery_event: str | None = None
    recovery_account: str = ""


class HandlerOpportunity(Model):
    id: str = Field(min_length=1)
    actor: ActorRef
    beneficiary: ActorRef | None = None
    consequence: str = Field(min_length=1)
    kind: Literal["opportunity", "chance_to_act", "weakness"]
    description: str = Field(min_length=1, max_length=1200)
    source_event: str = Field(min_length=1)
    ended_event: str | None = None


class HandlerFatalSource(Model):
    """Printed actual death, distinct from a Handler choosing the Assets substitute."""

    id: str = Field(min_length=1)
    actor: ActorRef
    source_event: str = Field(min_length=1)
    source_action: str = Field(min_length=1)
    source_choice: str | None = None
    clause: Literal["go_for_the_core.high", "go_for_the_core.mid", "go_for_the_core.low"]
    appointment: str = Field(min_length=1)
    account: str = Field(min_length=1, max_length=1200)
