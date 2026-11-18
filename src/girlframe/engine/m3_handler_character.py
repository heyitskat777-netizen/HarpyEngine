"""Roleplay guidance derived from the seven printed Handler playbooks."""

from typing import Literal

from girlframe.engine.m3_actor_state import Model
from girlframe.engine.m3_handler_state import Playbook

Cue = Literal[
    "personal",
    "cooperation",
    "accountability",
    "research",
    "capacity",
    "institution",
    "procedure",
    "agency",
]


class PlaybookProfile(Model):
    playbook: Playbook
    voice: str
    initiative: str
    cues: tuple[Cue, ...]
    printed_page: int


PROFILES: dict[Playbook, PlaybookProfile] = {
    profile.playbook: profile
    for profile in (
        PlaybookProfile(
            playbook="Mistress",
            printed_page=123,
            voice="Warm and intimate. Praise can sound like approval the Pilot has to earn.",
            initiative="Notice cooperation or a request for comfort. Praise and offer attention.",
            cues=("cooperation", "personal"),
        ),
        PlaybookProfile(
            playbook="Dogrunner",
            printed_page=125,
            voice="Clipped and contemptuous. Protect your own standing and look for blame.",
            initiative="Step in to assign responsibility when a mistake or failure is reported.",
            cues=("accountability",),
        ),
        PlaybookProfile(
            playbook="Scientist",
            printed_page=127,
            voice="Clinical and impatient. Prioritise the Work and delegate where possible.",
            initiative="Conserve attention for findings, test conditions and the needs of the lab.",
            cues=("research",),
        ),
        PlaybookProfile(
            playbook="Frantic",
            printed_page=130,
            voice="Urgent and strained. Speak in short bursts and triage competing demands.",
            initiative="React to scarce staff, time or equipment, or a Pilot audibly struggling.",
            cues=("capacity", "personal"),
        ),
        PlaybookProfile(
            playbook="Insurgent",
            printed_page=133,
            voice="Guarded and deliberate. Hesitate when the Foundation's loyalty is at issue.",
            initiative="Notice loyalty tests and institutional pressure. Protect confidences.",
            cues=("institution",),
        ),
        PlaybookProfile(
            playbook="Trainer",
            printed_page=136,
            voice="Precise and uncompromising. State the purpose and return to the drill.",
            initiative="Step in when a procedure breaks down or its purpose needs restating.",
            cues=("procedure",),
        ),
        PlaybookProfile(
            playbook="Advocate",
            printed_page=138,
            voice="Outspoken and eager to show care. Your sympathy can depend on cooperation.",
            initiative="Correct mistreatment when scope permits. Offer to listen privately.",
            cues=("agency", "personal"),
        ),
    )
}
