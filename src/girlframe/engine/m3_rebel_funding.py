"""A covert sponsor binds future printed Rebellion effects to actual insurgents."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.engine.m3_rebel_alignment import current as alignment
from girlframe.engine.m3_strain_state import Event
from girlframe.engine.m3_world_state import Faction

RULE = "strain.rebellion.endgame.5"
FUNDING = "rebel_insurgents_funded"
INFLUENCE = "rebellion_insurgent_involvement"


class Funding(Model):
    id: str
    group: str
    sponsor: ActorRef
    event: str
    account: str = Field(min_length=1, max_length=1200)


class Influence(Model):
    id: str
    roll_event: str
    funding: str | None = Field(default=None, exclude_if=lambda x: x is None)
    alignment: str | None = Field(default=None, exclude_if=lambda x: x is None)
    side: Literal["insurgents", "foundation"] = Field(
        default="insurgents", exclude_if=lambda x: x == "insurgents"
    )
    period: str
    group: str
    sponsor: ActorRef
    candidate: ActorRef | None = None
    controller: int | None = None
    nominated: str | None = None
    declined: str | None = None
    scene: str | None = None
    participation: str | None = None
    account: str = Field(default="", max_length=1200)

    @model_validator(mode="after")
    def actual_side(self) -> "Influence":
        if (self.side == "foundation" and (not self.alignment or self.funding)) or (
            self.side == "insurgents" and (not self.funding or self.alignment)
        ):
            raise ValueError("Use the actual original sponsorship or Rebel Handler alignment")
        return self


def fundings(state: GameState) -> tuple[Funding, ...]:
    return tuple(
        Funding.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == FUNDING
    )


def influences(state: GameState) -> tuple[Influence, ...]:
    return tuple(
        Influence.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == INFLUENCE
    )


def group(
    state: GameState, identity: str, kind: Literal["rebel", "foundation"] = "rebel"
) -> Faction:
    selected = (
        next((x for x in state.world.factions if x.id == identity), None) if state.world else None
    )
    if selected is None or not selected.active or selected.kind != kind:
        raise ValueError("Recover the original active group on this event's actual side")
    return selected


def fund(state: GameState, value: Funding) -> None:
    group(state, value.group)
    if alignment(state) is not None:
        raise ValueError(
            "Review how the original Rebel Handler's Foundation pressure overlaps sponsorship"
        )
    if not same_handler_body(state, value.sponsor) or fundings(state):
        raise ValueError("Record the original Handler's secret sponsorship once")
    state.facts.append(dict(kind=FUNDING, id=value.id, body=value.model_dump_json()))


def save(state: GameState, value: Influence) -> None:
    state.facts = [
        x for x in state.facts if (x.get("kind"), x.get("id")) != (INFLUENCE, value.id)
    ] + [dict(kind=INFLUENCE, id=value.id, body=value.model_dump_json())]


def bind_roll(state: GameState, roll: Event, event: str) -> None:
    if roll.track != "rebellion":
        return
    if moved := alignment(state):
        save(
            state,
            Influence(
                id=roll.id,
                roll_event=event,
                alignment=moved.id,
                side="foundation",
                period=roll.period_id,
                group=moved.opponent,
                sponsor=moved.handler,
            ),
        )
        return
    funding = next((x for x in fundings(state) if same_handler_body(state, x.sponsor)), None)
    if funding is not None:
        save(
            state,
            Influence(
                id=roll.id,
                roll_event=event,
                funding=funding.id,
                period=roll.period_id,
                group=funding.group,
                sponsor=funding.sponsor,
            ),
        )
