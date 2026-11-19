"""Original participants and their Handler playbook's private scene choices."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState, shift_status
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_intracadre_marriage import status_groups

Book = Literal["Mistress", "Trainer"]
RULES: dict[Book, str] = {
    "Mistress": "handler-playbook.mistress.sex-play",
    "Trainer": "handler-playbook.trainer.sex-play",
}
Phase = Literal[
    "invite",
    "scene",
    "favor",
    "decision",
    "owed",
    "review",
    "trainer_question",
    "trainer_answer",
    "trainer_install",
    "complete",
    "withdrawn",
]


class PrivateScene(Model):
    id: str
    handler: ActorRef
    girl: ActorRef
    scene: str
    channel: int
    event: str
    playbook: Book = Field(default="Mistress", exclude_if=lambda value: value == "Mistress")
    phase: Phase = "invite"
    attestations: tuple[ActorRef, ...] = ()
    favor: str = Field(default="", max_length=1200)
    accepted_event: str | None = None
    outcome: (
        Literal["fulfilled", "failed", "declined", "identity_erased", "speak_installed"] | None
    ) = None
    identity: str | None = Field(default=None, exclude_if=lambda value: value is None)
    action: str | None = None
    account: str = Field(default="", max_length=1200)


def records(state: GameState) -> tuple[PrivateScene, ...]:
    return tuple(
        PrivateScene.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") in ("mistress_favor", "trainer_private_scene")
    )


def put(state: GameState, value: PrivateScene) -> None:
    kind = "mistress_favor" if value.playbook == "Mistress" else "trainer_private_scene"
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (kind, value.id)] + [
        dict(kind=kind, id=value.id, body=value.model_dump_json())
    ]


def change_rank(state: GameState, owner: int, *, ace: bool) -> None:
    groups = status_groups(state)
    index = next(i for i, group in enumerate(groups) if owner in group)
    if len(groups[index]) != 1:
        raise ValueError("Review this shared Status before the printed solitary rank change")
    distance = index if ace else len(groups) - 1 - index
    for _ in range(distance):
        shift_status(state, owner, 1 if ace else -1)
    if distance:
        state.sheets[str(owner)].revision += 1
