"""Low Void grants a Benevolent Gorgon a lasting Play and records its use."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import CastRole, Model

RULE = "strain.void.low.4.2"
KIND = "benevolent_contact"
Play = Literal["offer_information", "take_interest"]
PLAYS: tuple[tuple[Play, str], ...] = (
    ("offer_information", "Offer information in exchange for a favour"),
    ("take_interest", "Take an interest in a Girl"),
)


class Contact(Model):
    id: str
    event: str
    grant: str
    play: Play
    speaker: CastRole
    recipient: CastRole
    scene: str
    cast_revision: int
    account: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def roles(self) -> "Contact":
        if self.speaker.actor.kind != "gorgon" or self.recipient.actor.kind != "pilot":
            raise ValueError("A Benevolent Gorgon makes this Play toward an actual Girl")
        return self


def contacts(state: GameState) -> tuple[Contact, ...]:
    return tuple(
        Contact.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def commit(state: GameState, entry: Contact) -> None:
    actual = contacts(state)
    original = next((x for x in actual if x.id == entry.grant and x.grant == x.id), None)
    if any(x.id == entry.id for x in actual) or (
        entry.id != entry.grant
        and (
            original is None
            or original.speaker.actor != entry.speaker.actor
            or original.play != entry.play
        )
    ):
        raise ValueError("Make only the actual Gorgon's original granted Play")
    state.facts.append(dict(kind=KIND, id=entry.id, body=entry.model_dump_json()))
