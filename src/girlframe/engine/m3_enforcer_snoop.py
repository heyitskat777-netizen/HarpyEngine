"""Printed Snoop selection counts and actual owned discoveries, without invented possessions."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m3_actor_state import ActorRef, Model

PLAY = "snoop"
QUESTIONS = ("illegal", "embarrassing", "valuable", "personal", "rebel_evidence")
LABELS = {
    "illegal": "What illegal item do I find?",
    "embarrassing": "What embarrassing thing do I show off?",
    "valuable": "What valuable thing do I pocket?",
    "personal": "What personal thing do I ruin or defile?",
    "rebel_evidence": "What could prove rebel activity?",
    "missed": "What are you glad I missed?",
}


class Discovery(Model):
    question: Literal["illegal", "embarrassing", "valuable", "personal", "rebel_evidence", "missed"]
    author: int = Field(gt=0)
    source_event: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=1200)
    item: str | None = None
    asset: str | None = None
    object_name: str | None = Field(default=None, max_length=120)
    object_description: str | None = Field(default=None, max_length=1200)


class Source(Model):
    actor: ActorRef
    target: ActorRef
    actor_controller: int = Field(gt=0)
    target_controller: int = Field(gt=0)
    grant: str = Field(min_length=1)
    scene: str = Field(min_length=1)
    access: str = Field(min_length=1, max_length=1200)


def select(level: str, options: tuple[str, ...]) -> tuple[str, ...]:
    maximum = 1 if level == "low" else 2
    if (
        level not in ("low", "mid", "high")
        or not 1 <= len(options) <= maximum
        or len(set(options)) != len(options)
        or not set(options) <= set(QUESTIONS)
    ):
        raise ValueError("Choose the exact permitted distinct printed Snoop questions")
    return options + (("missed",) if level == "low" else ())
