"""Durable restrictions from the original, resolved Trainer order."""

from typing import TYPE_CHECKING, Literal

from girlframe.engine.m3_actor_state import ActorRef, Model

if TYPE_CHECKING:
    from girlframe.engine.m2 import GameState

Phrase = Literal["speak", "sit", "play_gentle", "play_rough", "heel", "hunt"]
PHRASES: tuple[tuple[Phrase, str], ...] = (
    ("speak", "Speak"),
    ("sit", "Sit"),
    ("play_gentle", "Play Gentle"),
    ("play_rough", "Play Rough"),
    ("heel", "Heel"),
    ("hunt", "Hunt"),
)
PHRASE_LABELS: dict[str, str] = dict(PHRASES)
TARGETED = frozenset(("play_gentle", "play_rough"))


class Seated(Model):
    target: ActorRef
    issuer: ActorRef
    order: str
    choice: str
    event: str
    released: str | None = None


class Heel(Model):
    target: ActorRef
    issuer: ActorRef
    order: str
    event: str
    scene: str
    channel: int
    reached: str | None = None


def pending_heel(state: "GameState", target: ActorRef) -> Heel | None:
    for fact in reversed(state.facts):
        if fact.get("kind") == "trainer_heel" and fact.get("target") == target.token:
            record = Heel.model_validate_json(fact["body"])
            if record.target == target:
                return record if record.reached is None else None
    return None


def save_heel(state: "GameState", record: Heel) -> None:
    state.facts.append(
        dict(kind="trainer_heel", target=record.target.token, body=record.model_dump_json())
    )


def sitting(state: "GameState", target: ActorRef) -> Seated | None:
    for fact in reversed(state.facts):
        if fact.get("kind") == "trainer_sitting" and fact.get("target") == target.token:
            record = Seated.model_validate_json(fact["body"])
            if record.target == target:
                return record if record.released is None else None
    return None


def save_sitting(state: "GameState", record: Seated) -> None:
    state.facts.append(
        dict(kind="trainer_sitting", target=record.target.token, body=record.model_dump_json())
    )


def require_can_leave_seat(state: "GameState", target: ActorRef) -> None:
    if sitting(state, target) is not None:
        raise ValueError("The original Sit order still requires leave from its issuer")
