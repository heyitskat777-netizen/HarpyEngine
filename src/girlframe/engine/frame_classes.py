"""Printed Frame classes; JANUS-B keeps its server label and JANUS eligibility."""

from typing import Literal

from girlframe.engine.playbooks import canonical_frame

FrameClass = Literal["autocrat", "priestess", "legion"]
FrameRule = Literal["playbook", "base", "requisition", "class_requisition"]

FRAME_CLASSES: dict[str, FrameClass] = {
    "THE PRINCE": "autocrat",
    "CONSUME": "priestess",
    "JANUS": "priestess",
    "DOCTORDOCTOR MK. II": "legion",
    "WYVERN 0.4": "legion",
    "THE ENFORCER": "autocrat",
    "CHANGELING": "priestess",
    "PROJECT ANKOU": "legion",
    "THE RED QUEEN": "autocrat",
}


def official_frame(value: str) -> str:
    frame = canonical_frame(value)
    return "JANUS" if frame == "JANUS-B" else frame


def frame_class(value: str) -> FrameClass:
    return FRAME_CLASSES[official_frame(value)]
