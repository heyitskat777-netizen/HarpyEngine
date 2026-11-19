"""A declared physical Gorgon Play is a source intent, never an invented Girl roll."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_gorgon_type_tags import LABELS, TypeTag
from girlframe.engine.m3_growth import Adaptation, Regrowth
from girlframe.engine.m3_jackdaw import EFFECTS
from girlframe.engine.m3_jackdaw import Range as JackdawRange
from girlframe.engine.m3_mother_sprite import BirthPlan


class Declaration(Model):
    kind: (
        Literal[
            "attack",
            "collateral",
            "warp",
            "corrupt",
            "growth_adapt",
            "growth_regrow",
            "mother_sprite",
            "jackdaw_jam",
            "jackdaw_catatonia",
            "jackdaw_hallucinations",
            "jackdaw_hallucinations_day",
            "parasite_hitch",
            "intimate_contact",
            "intimate_frame_contact",
            "sentinel_withdraw",
            "sentinel_release",
            "incubus_conditioning",
            "grow_unreal",
            "parasite_detach",
        ]
        | TypeTag
    )
    actor: ActorRef
    assets: tuple[str, ...] = ()
    actor_sha256: str = Field(min_length=64, max_length=64)
    target: ActorRef | None = None
    target_sha256: str | None = Field(default=None, min_length=64, max_length=64)
    account: str = Field(min_length=1, max_length=1200)
    reach_confirmed: Literal[True]
    tag: str | None = Field(default=None, max_length=120, exclude_if=lambda value: value is None)
    adaptation: Adaptation | None = Field(default=None, exclude_if=lambda value: value is None)
    regrowth: Regrowth | None = Field(default=None, exclude_if=lambda value: value is None)
    birth: BirthPlan | None = Field(default=None, exclude_if=lambda value: value is None)
    interference: JackdawRange | None = Field(default=None, exclude_if=lambda value: value is None)

    day: int | None = Field(default=None, ge=1, exclude_if=lambda value: value is None)

    shed: str | None = Field(default=None, max_length=100, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def source_shape(self) -> "Declaration":
        if self.actor.kind != "gorgon" or len(set(self.assets)) != len(self.assets):
            raise ValueError("Declare distinct actual Assets of the actual attacking Gorgon")
        if not all(x.strip() for x in self.assets) or not self.account.strip():
            raise ValueError("State the actual physical attack/destruction and source capabilities")
        if bool(self.assets) != (self.kind in ("attack", "collateral")):
            raise ValueError("Attack and Collateral require actual owned Assets")
        if self.kind in (
            "attack",
            "incubus_inflict",
            "mother_mutation",
            "doppleganger_bond",
            "jackdaw_hallucinations",
            "jackdaw_hallucinations_day",
            "parasite_hitch",
            "intimate_contact",
            "intimate_frame_contact",
            "sentinel_withdraw",
            "sentinel_release",
            "incubus_conditioning",
            "grow_unreal",
        ):
            if self.target is None or self.target_sha256 is None or self.target == self.actor:
                raise ValueError("This Play needs its actual distinct target body and source")
        elif self.target is not None or self.target_sha256 is not None:
            raise ValueError("This Play targets the actual environment, not a substituted person")
        if self.kind in ("incubus_inflict", "mother_mutation"):
            if self.tag not in dict(LABELS[self.kind]):
                raise ValueError("Choose a printed Tag for this Gorgon effect")
        elif self.kind in ("doppleganger_bond", "incubus_conditioning"):
            if not self.tag or not self.tag.strip():
                raise ValueError("Use the actual owned Tag for this Gorgon Play")
        elif self.tag is not None:
            raise ValueError("This Gorgon Play has no direct Tag choice")
        if (self.adaptation is not None) != (self.kind == "growth_adapt") or (
            self.regrowth is not None
        ) != (self.kind == "growth_regrow"):
            raise ValueError("Use this exact Growth Play's owned choices")
        if (self.birth is not None) != (self.kind == "mother_sprite"):
            raise ValueError("Declare the original Mother's paid Sprite design")
        if (self.interference is not None) != (self.kind in EFFECTS):
            raise ValueError("Declare the actual audible range of this Jackdaw Play")
        if (self.day is not None) != (self.kind == "jackdaw_hallucinations_day"):
            raise ValueError("Choose the exact next fictional day of actual exposure")
        if (self.shed is not None and bool(self.shed.strip())) != (self.kind == "grow_unreal"):
            raise ValueError("Choose the actual original Growth Asset this source sacrifices")
        return self
