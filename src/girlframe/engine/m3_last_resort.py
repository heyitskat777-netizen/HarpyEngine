"""An actual hidden Last / Resort reserve and its original Cadre trigger."""

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_world_state import Cell

RULE = "handler-advancement.handler-advancement.last-resort"


class Acquisition(Model):
    id: str
    award: str
    handler: ActorRef
    appointment: str
    event: str
    base: str
    cell: Cell
    chassis: str
    cadre: tuple[ActorRef, ...]
    account: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def actual(self) -> "Acquisition":
        if (
            self.handler.kind != "handler"
            or not self.cadre
            or len(set(self.cadre)) != len(self.cadre)
            or any(x.kind != "pilot" for x in self.cadre)
        ):
            raise ValueError(
                "Retain the actual Handler and original Cadre roster for Last / Resort"
            )
        return self


def acquisitions(state: GameState) -> tuple[Acquisition, ...]:
    return tuple(
        Acquisition.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "last_resort_acquisition"
    )


def put(state: GameState, value: Acquisition) -> None:
    state.facts.append(
        dict(kind="last_resort_acquisition", id=value.id, body=value.model_dump_json())
    )


def loss_threshold(state: GameState, value: Acquisition) -> tuple[tuple[ActorRef, ...], int]:
    from girlframe.engine.m3_actor_bonds import current_ref

    roster = {*value.cadre, *(current_ref(state, uid) for uid in state.order)}
    dead = tuple(
        archive.actor
        for archive in state.career_archives
        if archive.actor in roster and archive.ending in ("death", "execution")
    )
    return tuple(dict.fromkeys(dead)), (len(roster) + 1) // 2
