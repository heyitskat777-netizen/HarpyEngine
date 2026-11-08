"""Starting player-Bond constraints; no gameplay or consent is inferred by AI."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from girlframe.engine.identity import Snowflake

# Paraphrased prompt labels; source pages are in creation_catalog.py.
PROMPTS = {
    "PRINCESS": ("Past fame", "Kept a damaging secret"),
    "MOCKINGBIRD": ("Harpy obsession", "Remembering former humanity"),
    "STIM-BLISSED": ("Shared intoxication", "Sedation before piloting"),
    "NEWGIRL": ("Mentor",),
    "CASUALTY": ("A lost mutual friend", "Piloting expectations"),
    "OLDGEN": ("Meeting again years later", "Last Cadre survivors"),
    "VATGROWN": ("Watching from afar", "An earlier conversation"),
    "ALPHA": ("Past violence", "A visit to the bunk"),
    "AM": ("Body maintenance", "Recruitment"),
    "BONDED": ("Support after breaking", "A sister's protection"),
}


class BondProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    target_id: Snowflake
    prompt: int = Field(ge=0, le=1)
    context: str = Field(default="", max_length=500)


def starting_kind(girl: str) -> Literal["Personal", "Intense"]:
    return "Intense" if girl == "BONDED" else "Personal"


def starting_role(girl: str) -> str:
    return {"BONDED": "Pair", "NEWGIRL": "Mentor"}.get(girl, "Girl")
