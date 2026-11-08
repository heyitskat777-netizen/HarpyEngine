"""Actual consenting source guests, distinct from account, own Frame and carrier Frame."""

from typing import Literal

from pydantic import Field

from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_world_state import Cell


class Passenger(Model):
    id: str = Field(min_length=1)
    actor: ActorRef
    controller: Snowflake
    carrier: ActorRef
    frame: str = Field(min_length=1)
    source_action: str
    step: int = Field(ge=0)
    source_event: str
    position_sha256: str
    carrier_sha256: str
    state: Literal["proposed", "declined", "boarded", "left"] = "proposed"
    accepted_event: str | None = None
    cell: Cell | None = None
    subsumed: bool = False
    vitals_active: bool = True
    chosen: str | None = None
    completed_event: str | None = None
    choice_event: str | None = None
    account: str = Field(default="", max_length=1200)
    revision: int = Field(default=1, ge=1)
    consent_event: str | None = None
    left_event: str | None = None
    medical_proposal_event: str | None = None
    medical_account: str = Field(default="", max_length=1200)
    medical_judge: Snowflake | None = None
    medical_appointment: str | None = None
    medical_recovery_event: str | None = None
