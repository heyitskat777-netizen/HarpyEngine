"""Verified starting Frame facts; unresolved counters/choices remain explicit."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class HarpyCore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    kind: Literal["harpy_core"] = "harpy_core"
    tags: tuple[str, ...] = ("Drugged", "Restrained", "Muzzled", "Recovering from Surgery")
    # The source prohibits naming the Core. This entity is distinct from the Pilot.


class FrameSetup(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    schema_version: Literal[1] = 1
    frame: str
    source_pdf_pages: tuple[int, ...]
    harpy_core: HarpyCore | None = None
    obsolescence_capacity: int | None = None
    starvation_levels: tuple[str, ...] = ()
    intrinsic_assets: tuple[str, ...] = ()
    am_roles: tuple[str, ...] = ()
    default_am_self: int | None = None
    default_am_other: int | None = None
    pending: tuple[str, ...] = ()


def frame_setup(label: str) -> FrameSetup:
    frame = "JANUS" if label == "JANUS-B" else label
    if frame == "JANUS":
        return FrameSetup(frame=frame, source_pdf_pages=(68,), harpy_core=HarpyCore())
    if frame == "CONSUME":
        return FrameSetup(
            frame=frame,
            source_pdf_pages=(65,),
            starvation_levels=("Quiet", "Gnawing", "Ravenous"),
            pending=("Verify starting starvation level",),
        )
    if frame == "DOCTORDOCTOR MK. II":
        return FrameSetup(
            frame=frame,
            source_pdf_pages=(71,),
            obsolescence_capacity=8,
            pending=("Verify starting marked obsolescence boxes",),
        )
    if frame == "WYVERN 0.4":
        return FrameSetup(frame=frame, source_pdf_pages=(74,), intrinsic_assets=("Enormous",))
    if frame == "THE RED QUEEN":
        return FrameSetup(
            frame=frame,
            source_pdf_pages=(88, 89),
            am_roles=("The Queen", "The Consort", "The Knight", "The Doll", "The Traitor"),
            default_am_self=4,
            default_am_other=1,
            pending=("Choose external AM role and other Girl; obtain setup agreement",),
        )
    return FrameSetup(frame=frame, source_pdf_pages=())
