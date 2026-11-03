"""Private draft-sheet contract. Review snapshots never authorize gameplay."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from girlframe.engine.creation import CreationDraft
from girlframe.engine.creation_details import (
    AcceptedCoordination,
    InitialConditions,
    PsychStringAnchor,
)
from girlframe.engine.identity import Snowflake
from girlframe.engine.shared_setup import AcceptedSetup

SOURCE_VERSION: Literal["m2-creation-review-2"] = "m2-creation-review-2"
STARTING_ACCESS = (
    "Room with a bunk",
    "Combat knife",
    "Pilot suit and civilian outfit",
    "Surgically implanted neural link",
)


class CreationRulings(BaseModel):
    """Explicit campaign choices, not a claim about printed starting defaults."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    starting_heat: Literal[0] = 0
    consume_hunger: Literal["Quiet"] = "Quiet"
    obsolescence_marked: Literal[0] = 0
    requisition_mode: Literal["long_game", "short_game_unimplemented"] = "long_game"
    provenance: Literal["handler_confirmed_campaign_ruling", "owner_approved_campaign_ruling"] = (
        "handler_confirmed_campaign_ruling"
    )


class ReviewIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    code: str
    message: str
    category: Literal["missing", "unresolved", "review"] = "missing"


class SheetBond(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    id: str
    revision: int
    counterpart: Snowflake
    depth: Literal["Personal", "Intense"]
    outgoing: bool
    context: str


class ReviewSheet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal[1] = 1
    source_version: Literal["m2-creation-review-1", "m2-creation-review-2"] = SOURCE_VERSION
    state: Literal["draft_rules_unverified"] = "draft_rules_unverified"
    owner: Snowflake
    callsign: str
    activation_callsign: str
    character_revision: int
    creation_revision: int
    setup_revision: int
    creation: CreationDraft
    bonds: tuple[SheetBond, ...] = ()
    shared: tuple[AcceptedSetup, ...] = ()
    received_court: tuple[AcceptedSetup, ...] = ()
    coordination: tuple[AcceptedCoordination, ...] = ()
    psych_strings: tuple[PsychStringAnchor, ...] = ()
    initial_conditions: InitialConditions | None = None
    status: str | None = None
    rulings: CreationRulings | None = None
    access: tuple[str, ...] = STARTING_ACCESS
    issues: tuple[ReviewIssue, ...] = ()
    # Dependency material stays in private review storage. It is never an event payload.
    dependency_tokens: tuple[str, ...] = Field(default=())

    @property
    def ready_for_rules_review(self) -> bool:
        return not any(x.category != "review" for x in self.issues)
