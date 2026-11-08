"""Paraphrased NPC role labels from the Girl creation pages in creation_catalog."""

from pydantic import BaseModel, ConfigDict, Field

NPC_ROLES = {
    "PRINCESS": (
        "Doe-eyed captain",
        "Corrupt politician",
        "Glamorous celebrity",
        "Cute junior Handler",
    ),
    "MOCKINGBIRD": ("Lunch lady", "Surgeon", "Silent guard", "Vent dweller"),
    "STIM-BLISSED": ("Fried ex-pilot", "Janitor", "Checkup nurse", "Supply corps leader"),
    "NEWGIRL": ("Pilot sister", "Junior engineer", "Recruiting agent", "Town girl"),
    "CASUALTY": ("Stray cat", "Physiotherapist", "Civilian contact", "Prisoner"),
    "OLDGEN": ("Retired Handler", "Hospitalized former pilot", "Familiar Mockingbird", "Director"),
    "VATGROWN": ("Head scientist", "Medical team", "Older vat-sibling", "Wealthy patron"),
    "ALPHA": (
        "Guard with taser",
        "School acquaintance now officer",
        "Terrified civilian",
        "Victim of injury",
    ),
    "AM": ("Design commissioner", "Cheerful techie", "Blank record", "Dormant copy"),
    "BONDED": ("Relationship critic", "Experimental therapist", "Avoided older man", "Other girl"),
}


class NpcBond(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    slot: int = Field(ge=0, le=3)
    name: str = Field(default="", max_length=80)
    feelings: str = Field(default="", max_length=500)
