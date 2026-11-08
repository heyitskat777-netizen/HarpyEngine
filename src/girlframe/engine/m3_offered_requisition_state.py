"""Actual source-funded Girl gifts are distinct from paid Requisition requests."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_girl_runtime_state import has_rule

Kind = Literal["creature_comforts", "privacy", "visiting_home", "retirement"]
KINDS = ("creature_comforts", "privacy", "visiting_home", "retirement")


class OfferedAcceptance(Model):
    id: str
    offer: str
    receipt: str
    actor: ActorRef
    investor: ActorRef
    kind: Kind
    event: str
    companion: ActorRef | None = Field(default=None, exclude_if=lambda value: value is None)
    archive: str | None = Field(default=None, exclude_if=lambda value: value is None)
    confirmed_retirement: bool = False


def records(state: GameState) -> tuple[OfferedAcceptance, ...]:
    return tuple(
        OfferedAcceptance.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "offered_girl_requisition"
    )


def put(state: GameState, value: OfferedAcceptance) -> None:
    if any(x.offer == value.offer or x.receipt == value.receipt for x in records(state)):
        raise ValueError("This actual offered Requisition already has its one accepted source")
    state.facts.append(
        dict(kind="offered_girl_requisition", id=value.id, body=value.model_dump_json())
    )


def require_request(state: GameState, actor: ActorRef) -> None:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if (
        sheet
        and sheet.character_id == actor.incarnation
        and has_rule(sheet, "girl.vatgrown.just-an-experiment", "VATGROWN")
    ):
        raise ValueError(
            "JUST_AN_EXPERIMENT: this actual Vatgrown may receive an offered "
            "Girl Requisition but cannot request one"
        )
