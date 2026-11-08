"""Paraphrased creation choices; book PDF 32, 46, 49, 44, 58 and 82."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from girlframe.engine.identity import Snowflake

STANDARDS = (
    "Report Cadre conduct",
    "Use official pronouns",
    "Kindness and obedience to staff",
    "Attend to Handler's daily needs",
    "No weakness before underlings",
    "Impeccable grooming",
    "Protect the family name",
    "Encourage aptitude testing",
    "No Cadre romance",
    "Custom standard",
)
MAXIMS = (
    "Strong use the weak",
    "Give thanks for the meal",
    "Piloting feels best",
    "Foundation grinds everyone down",
    "Survival comes first",
    "Nothing awaits retirement",
    "Grudges are fuel",
    "Respect your engineer",
    "Beauty in blood",
    "Don't attach to doomed dogs",
)
DESIRES = (
    "A display piece",
    "A daughter",
    "A weapon",
    "A pet",
    "A punching bag",
    "A sexual plaything",
    "A reminder",
    "A triumph",
    "An opportunity",
    "A tormentor",
    "A pair of eyes",
)
BODY_PARTS = ("Legs", "Hands", "Eyes", "Ears", "Head", "Face", "Vital Organs", "Link", "Brain")
Role = Literal["princess_peer", "princess_handler", "vatgrown_handler"]


class StandardChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    slot: int = Field(ge=0, le=9)
    custom: str = Field(default="", max_length=160)

    @model_validator(mode="after")
    def legal(self) -> Self:
        if (self.slot == 9) != bool(self.custom.strip()):
            raise ValueError("Only a custom standard takes nonempty custom text")
        return self

    @property
    def label(self) -> str:
        return self.custom.strip() if self.slot == 9 else STANDARDS[self.slot]


class DesireChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    slots: tuple[int, ...] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def legal(self) -> Self:
        if len(set(self.slots)) != len(self.slots) or any(
            x < 0 or x >= len(DESIRES) for x in self.slots
        ):
            raise ValueError("Choose one or two distinct investor desires")
        return self

    @property
    def label(self) -> str:
        return ", ".join(DESIRES[x] for x in self.slots)


class NpcInvestor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    npc_slot: int = Field(ge=0, le=3)
    desires: DesireChoice


class GirlDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    own_standard: StandardChoice | None = None
    maxims: tuple[int, ...] = Field(default=(), max_length=2)
    investors: tuple[NpcInvestor, ...] = Field(default=(), max_length=2)

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if len(set(self.maxims)) != len(self.maxims) or any(
            x < 0 or x >= len(MAXIMS) for x in self.maxims
        ):
            raise ValueError("Choose distinct sourced maxims")
        if len({x.npc_slot for x in self.investors}) != len(self.investors):
            raise ValueError("Each NPC investor has one desire selection")
        return self


class AcceptedCoordination(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    id: str
    revision: int
    role: Role
    author: Snowflake
    owner: Snowflake
    standard: StandardChoice | None = None
    desires: DesireChoice | None = None

    @model_validator(mode="after")
    def choice_matches_role(self) -> Self:
        if self.role == "vatgrown_handler":
            if self.desires is None or self.standard is not None:
                raise ValueError("Handler investor choices contain desires only")
        elif self.standard is None or self.desires is not None:
            raise ValueError("Princess choices contain one standard only")
        return self

    @property
    def label(self) -> str:
        return (
            self.standard.label
            if self.standard
            else self.desires.label
            if self.desires
            else "Unresolved"
        )


class PsychStringAnchor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    kind: Literal["pilot", "npc_role"]
    reference: str
    source_token: str


class InitialConditions(BaseModel):
    """Owner-approved initial states; never represented as printed defaults."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    provenance: Literal["owner_approved_campaign_ruling"] = "owner_approved_campaign_ruling"
    identities_marked: Literal[False] = False
    maxims_marked: Literal[False] = False
    assets_damaged: Literal[False] = False
    body_parts_damaged: Literal[False] = False
    npc_bond_depth: Literal["Personal"] = "Personal"
    permissions: Literal[0] = 0
    acquired_requisitions: tuple[str, ...] = Field(default=(), max_length=0)
    extra_tags: tuple[str, ...] = Field(default=(), max_length=0)
