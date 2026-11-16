"""Explicit native Play identification; goal-text negation does not erase a declaration."""

import re

from girlframe.engine.m2 import PLAY_IDS

LABELS = dict(
    zip(
        PLAY_IDS,
        ("Keep Your Head", "Check Your Sensors", "Engage", "Disobey Orders", "Flirt"),
        strict=True,
    )
)


def requested_play(text: str) -> str | None:
    for identity, label in LABELS.items():
        patterns: tuple[str, ...] = (re.escape(label).replace(r"\ ", r"[ _]+"), re.escape(identity))
        if identity == "check_sensors":
            patterns += (r"check[ _]+sensors",)
        match = re.search(r"\b(?:" + "|".join(patterns) + r")\b", text, re.I)
        if match is None:
            continue
        prefix = text[: match.start()].casefold()
        if re.search(r"\b(?:not|never)\b|\b(?:don't|won't)\b", prefix):
            continue
        if re.search(r"\b(?:declare|roll|resolve|request)\b", prefix):
            return identity
    return None
