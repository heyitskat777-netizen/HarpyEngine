"""Printed direct Tag effects of Gorgons in the same scene."""

from typing import Literal

from girlframe.engine.m3_actor_state import ActorView

TypeTag = Literal["incubus_inflict", "mother_mutation", "doppleganger_bond"]
TYPES: dict[TypeTag, str] = {
    "incubus_inflict": "incubus",
    "mother_mutation": "mother",
    "doppleganger_bond": "doppleganger",
}
RULES: dict[TypeTag, str] = {
    "incubus_inflict": "gorgon-type.incubus.incubus-type",
    "mother_mutation": "gorgon-type.mother.mother-type",
    "doppleganger_bond": "gorgon-type.doppleganger.doppleganger-type",
}
LABELS: dict[str, tuple[tuple[str, str], ...]] = {
    "incubus_inflict": (
        ("bliss", "Blissed out"),
        ("touch", "Craving touch"),
        ("dysphoria", "Dysphoric"),
        ("anxiety", "Paralyzing anxiety"),
        ("grief", "Grief without source"),
    ),
    "mother_mutation": (
        ("engulf", "Engulfing flesh"),
        ("branch", "Branching flesh"),
        ("meld", "Melding flesh"),
        ("entwine", "Entwining flesh"),
        ("ooze", "Oozing flesh"),
        ("rip", "Ripping flesh"),
        ("crawl", "Crawling flesh"),
        ("scatter", "Scattering flesh"),
        ("twist", "Twisting flesh"),
        ("calcify", "Calcifying flesh"),
    ),
}


def present(kind: TypeTag, gorgon: ActorView, target: ActorView) -> bool:
    target_supported = target.rules in ("girl_frame", "npc")
    skin_reached = (
        kind != "mother_mutation" or target.rules == "npc" or target.inside_frame is False
    )
    return (
        gorgon.alive
        and target.alive
        and target_supported
        and skin_reached
        and gorgon.cell is not None
        and gorgon.cell == target.cell
        and not (gorgon.offstage_source or target.offstage_source)
    )
