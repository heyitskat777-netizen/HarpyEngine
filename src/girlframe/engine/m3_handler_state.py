"""Original Handler persona and source-bound, human-authored starting choices."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_actor_state import ActorRef, Model

Playbook = Literal[
    "Mistress", "Dogrunner", "Scientist", "Frantic", "Insurgent", "Trainer", "Advocate"
]
PLAYBOOKS: tuple[Playbook, ...] = (
    "Mistress",
    "Dogrunner",
    "Scientist",
    "Frantic",
    "Insurgent",
    "Trainer",
    "Advocate",
)
GearKind = Literal["stash", "bedroom", "title", "studio", "outfits", "weapon", "pet"]
GEAR = (
    ("stash", "Recreational stash"),
    ("bedroom", "Cushy bedroom"),
    ("title", "Hereditary title"),
    ("studio", "Film studio and propaganda crew"),
    ("outfits", "Custom outfits and toys"),
    ("weapon", "Custom weapon"),
    ("pet", "Pet"),
)
HISTORY_LABELS: dict[str, tuple[str, ...]] = {
    "Mistress": ("Private journal", "Personal recruitment", "Previous pet"),
    "Dogrunner": ("First-day treatment", "Post-mission care", "Unequal treatment"),
    "Scientist": ("Regular lab upkeep", "Protection from the Director", "Family relationship"),
    "Frantic": ("Called for comfort", "Former team", "Repeated second chances"),
    "Insurgent": ("Civilian rebel concerns", "Unexplained nighttime outings", "Known secret"),
    "Trainer": (
        "Long control: Sit and Heel",
        "Resistance: Hunt",
        "Slow conditioning: Speak and Play Gentle",
    ),
    "Advocate": ("Unwanted attention", "Personal recruitment request", "Prior online friendship"),
}
TRAINER_PHRASES = {0: ("sit", "heel"), 1: ("hunt",), 2: ("speak", "play_gentle")}


class GearDetail(Model):
    kind: GearKind
    description: str = Field(default="", max_length=700)


class StartingBond(Model):
    pilot: ActorRef
    depth: Literal[1, 2] = 1
    rank: Literal["ace", "dog"]
    history: str = Field(min_length=1, max_length=1200)
    prompt: int | None = Field(default=None, ge=0, le=2)

    @model_validator(mode="after")
    def original_girl(self) -> "StartingBond":
        if self.pilot.kind != "pilot" or not self.history.strip():
            raise ValueError("Choose an actual original Girl and describe the shared history")
        return self


class NpcStarting(Model):
    npc: ActorRef
    controller: Snowflake
    history: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def actual_npc(self) -> "NpcStarting":
        if self.npc.kind != "npc" or not self.history.strip():
            raise ValueError("Choose an actual NPC and describe the proposed shared relationship")
        return self


class Draft(Model):
    playbook: Playbook | None = None
    name: str = Field(default="", max_length=120)
    appearance: str = Field(default="", max_length=1200)
    outfit: str = Field(default="", max_length=1200)
    background: str = Field(default="", max_length=1200)
    gear: tuple[GearDetail, ...] = Field(default=(), max_length=2)
    starting: tuple[StartingBond, ...] = Field(default=(), max_length=2)
    surveilled: tuple[str, ...] = Field(default=(), max_length=2)
    sympathizer: str | None = None
    npc_starting: tuple[NpcStarting, ...] = Field(default=(), max_length=3)

    @model_validator(mode="after")
    def distinct_choices(self) -> "Draft":
        if len({x.kind for x in self.gear}) != len(self.gear):
            raise ValueError("Choose two different gear options")
        if len({x.pilot for x in self.starting}) != len(self.starting):
            raise ValueError("Choose different original Girls for the starting Bonds")
        if len({x.rank for x in self.starting}) != len(self.starting):
            raise ValueError("One Girl is the Ace and another is the Dog")
        if len(set(self.surveilled)) != len(self.surveilled):
            raise ValueError("Choose distinct NPCs within the Surveilled selection")
        if len({x.npc for x in self.npc_starting}) != len(self.npc_starting):
            raise ValueError("Describe each actual starting NPC relationship once")
        selected = set(self.surveilled) | ({self.sympathizer} if self.sympathizer else set())
        if any(x.npc.entity not in selected for x in self.npc_starting):
            raise ValueError("Propose starting relationships only for the selected NPC Bonds")
        for value in (
            self.name,
            self.appearance,
            self.outfit,
            self.background,
            *(x.description for x in self.gear),
        ):
            if value and not value.strip():
                raise ValueError("Use meaningful descriptions or leave incomplete fields empty")
        if self.playbook != "Insurgent" and (self.surveilled or self.sympathizer):
            raise ValueError("Starting surveillance choices belong to Insurgent")
        return self

    @property
    def missing(self) -> tuple[str, ...]:
        fields = [
            x
            for x in ("playbook", "name", "appearance", "outfit", "background")
            if not getattr(self, x)
        ]
        if len(self.gear) != 2:
            fields.append("two gear choices")
        fields.extend(dict(GEAR)[x.kind] + " description" for x in self.gear if not x.description)
        expected = 1 if self.playbook == "Scientist" else 2
        if len(self.starting) != expected:
            fields.append("starting Bond and rank selections")
        elif self.playbook == "Mistress" and sorted(x.depth for x in self.starting) != [1, 2]:
            fields.append("one Personal and one Intense starting Bond")
        elif self.playbook != "Mistress" and any(x.depth != 1 for x in self.starting):
            fields.append("Personal starting Bonds")
        if self.playbook == "Insurgent" and (not self.surveilled or not self.sympathizer):
            fields.append("Insurgent starting NPC labels")
        return tuple(fields)


class SavedDraft(Model):
    persona_id: str = Field(min_length=1)
    appointment: str = Field(min_length=1)
    draft: Draft
    generation: str = "initial"
    source_work: str | None = None


class Agreement(Model):
    persona_id: str
    appointment: str
    handler: Snowflake
    name: str
    bond: StartingBond
    phrases: tuple[str, ...] = ()
    generation: str = "initial"


class NpcAgreement(Model):
    persona_id: str
    appointment: str
    handler: Snowflake
    name: str
    relationship: NpcStarting
    generation: str = "initial"


class Conditioning(Model):
    pilot: ActorRef
    phrases: tuple[str, ...]
    source_event: str


class HandlerPersona(Model):
    id: str = Field(min_length=1)
    owner: Snowflake
    appointment: str = Field(min_length=1)
    draft: Draft
    source_event: str = Field(min_length=1)
    conditioning: tuple[Conditioning, ...] = ()
    sticky_dogs: tuple[ActorRef, ...] = ()
