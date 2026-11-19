"""Original participants and their Handler playbook's private scene choices."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState, shift_status
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_intracadre_marriage import status_groups
from girlframe.engine.rolls import Face

Book = Literal["Mistress", "Trainer", "Dogrunner", "Insurgent", "Scientist", "Frantic", "Advocate"]
RULES: dict[Book, str] = {
    "Mistress": "handler-playbook.mistress.sex-play",
    "Trainer": "handler-playbook.trainer.sex-play",
    "Dogrunner": "handler-playbook.dogrunner.sex-play",
    "Insurgent": "handler-playbook.insurgent.sex-play",
    "Scientist": "handler-playbook.scientist.sex-play",
    "Frantic": "handler-playbook.frantic.sex-play",
    "Advocate": "handler-playbook.advocate.sex-play",
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
    "dogrunner_question",
    "dogrunner_answer",
    "dogrunner_response",
    "dogrunner_discipline",
    "insurgent_question",
    "insurgent_answer",
    "insurgent_no_suspicion",
    "insurgent_suspicion",
    "scientist_proposal",
    "scientist_asset",
    "scientist_void",
    "scientist_followup",
    "frantic_roll",
    "frantic_comfort",
    "frantic_girl_tag",
    "frantic_handler_tag",
    "frantic_high",
    "frantic_care",
    "frantic_verdict",
    "frantic_bond_tag",
    "frantic_discipline",
    "advocate_choice",
    "advocate_followup",
    "complete",
    "withdrawn",
]


class LabExchange(Model):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=1200)


class FranticRoll(Model):
    faces: tuple[Face, Face]
    modifier: Literal[-1, 1, 3]

    @property
    def total(self) -> int:
        return sum(self.faces) + self.modifier


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
        Literal[
            "fulfilled",
            "failed",
            "declined",
            "identity_erased",
            "speak_installed",
            "dogrunner_rewarded",
            "dogrunner_punishment",
            "insurgent_resolved",
            "insurgent_left_suspicions",
            "scientist_exchanged",
            "scientist_void_gained",
            "scientist_void_resisted",
            "frantic_comforted",
            "frantic_mutual_tags",
            "frantic_bond",
            "frantic_punishment",
            "advocate_lowered",
            "advocate_raised",
        ]
        | None
    ) = None
    identity: str | None = Field(default=None, exclude_if=lambda value: value is None)
    tag: str | None = Field(default=None, exclude_if=lambda value: value is None)
    discipline: str | None = Field(default=None, exclude_if=lambda value: value is None)
    effects: tuple[str, ...] = Field(default=(), exclude_if=lambda value: not value)
    lab: str | None = Field(default=None, exclude_if=lambda value: value is None)
    exchange: LabExchange | None = Field(default=None, exclude_if=lambda value: value is None)
    removed_asset: str | None = Field(default=None, exclude_if=lambda value: value is None)
    installed_asset: str | None = Field(default=None, exclude_if=lambda value: value is None)
    void_asset: str | None = Field(default=None, exclude_if=lambda value: value is None)
    roll: FranticRoll | None = Field(default=None, exclude_if=lambda value: value is None)
    handler_tag: str | None = Field(default=None, exclude_if=lambda value: value is None)
    damaged_asset: str | None = Field(default=None, exclude_if=lambda value: value is None)
    required_work: tuple[str, ...] = Field(default=(), exclude_if=lambda value: not value)
    action: str | None = None
    account: str = Field(default="", max_length=1200)


KINDS: dict[Book, str] = {
    "Mistress": "mistress_favor",
    "Trainer": "trainer_private_scene",
    "Dogrunner": "dogrunner_private_scene",
    "Insurgent": "insurgent_private_scene",
    "Scientist": "scientist_private_scene",
    "Frantic": "frantic_private_scene",
    "Advocate": "advocate_private_scene",
}

DISCIPLINE_BOOKS: tuple[Book, ...] = ("Dogrunner", "Frantic")
DISCIPLINE_PHASES = ("dogrunner_discipline", "frantic_discipline")
DISCIPLINE_CAUSES = frozenset(RULES[x] for x in DISCIPLINE_BOOKS)


def records(state: GameState) -> tuple[PrivateScene, ...]:
    return tuple(
        PrivateScene.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") in KINDS.values()
    )


def put(state: GameState, value: PrivateScene) -> None:
    kind = KINDS[value.playbook]
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (kind, value.id)] + [
        dict(kind=kind, id=value.id, body=value.model_dump_json())
    ]


def pending_discipline(state: GameState, value: PrivateScene) -> bool:
    return not any(x.id == value.discipline and x.state == "fulfilled" for x in state.obligations)


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
