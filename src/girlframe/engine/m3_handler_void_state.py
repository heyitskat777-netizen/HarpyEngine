"""Original Handler body corruption and actual source-owned removal or stabilization."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_actor_state import ActorRef, Model


class HandlerVoid(Model):
    id: str = Field(min_length=1)
    actor: ActorRef
    body: ActorRef
    controller: Snowflake
    work: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    appointment: str = Field(min_length=1)
    phase: Literal["choice", "stabilized", "surgery", "removed", "ended"] = "choice"
    choice: Literal["knife", "drugs", "surgery"] | None = None
    choice_event: str | None = None
    void_present: bool = True
    spread_halted: bool = False
    manifestation: Literal["brain", "bones", "flesh", "abstract"] | None = None
    site: str = Field(default="", max_length=300)
    account: str = Field(default="", max_length=1200)
    wound: str = Field(default="", max_length=1200)
    removal_event: str | None = None
    surgery_account: str = Field(default="", max_length=1200)
    ended_event: str | None = None

    @model_validator(mode="after")
    def actual_effect(self) -> "HandlerVoid":
        if (
            self.actor.kind not in ("handler", "npc")
            or self.body.kind != self.actor.kind
            or self.actor.entity != self.body.entity
            or self.actor.kind == "handler"
            and self.actor.entity != str(self.controller)
        ):
            raise ValueError(
                "Corruption stays with the actual original Handler body and controller"
            )
        if self.phase == "stabilized" and (
            self.choice != "drugs"
            or not self.spread_halted
            or not self.void_present
            or self.manifestation is None
            or not self.site.strip()
            or not self.account.strip()
        ):
            raise ValueError("Drugs halt actual localized corruption; they do not invent removal")
        if self.phase == "removed" and (
            self.void_present
            or not self.removal_event
            or not (self.wound.strip() or self.surgery_account.strip())
        ):
            raise ValueError("Actual performed removal needs its own source and factual account")
        if self.phase == "ended" and self.ended_event is None:
            raise ValueError("Only an actual original-body ending closes this condition")
        return self
