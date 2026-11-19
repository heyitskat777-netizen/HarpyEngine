"""Printed starting Assets for a new independent Harpy."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.creation import AssetChoice
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_world_state import AdversaryPilot, Asset, Cell

RULE = "harpy.harpy.harpy"
KIND = "harpy_creation_offer"
GIRL_ASSETS = (
    "Too Beautiful For Words",
    "Knows All Their Tricks",
    "Inescapable Voice",
    "Writhing Muscles",
    "Tentacles",
    "Extrasensory Organs",
    "Vision Projection",
    "Keratin-Reinforced Internals",
    "Prehensile Nerves",
    "Fractal Brain",
)
FRAME_ASSETS = (
    "Bonesteel Blade",
    "Ichor Gun",
    "Psychic Missiles",
    "Regenerating Flesh",
    "Ancestor Brain",
    "Nanomechanical",
    "Skimfins",
    "Bladed Tail",
    "Gorgon Extruder",
    "Meat-Pets",
    "Enormous Teeth",
    "Sensation Link",
    "All the Arms",
)


class Offer(Model):
    actor: ActorRef
    controller: int = Field(gt=0)
    issuer: int = Field(gt=0)
    appointment: str
    cell: Cell
    source: str
    phase: Literal["offered", "accepted", "declined"] = "offered"
    decision: str | None = None


class Draft(Model):
    name: str = Field(min_length=1, max_length=120)
    girl: tuple[AssetChoice, AssetChoice, AssetChoice]
    frame: tuple[AssetChoice, AssetChoice, AssetChoice, AssetChoice]

    @model_validator(mode="after")
    def starting_resources(self) -> "Draft":
        for selected, catalogue in ((self.girl, GIRL_ASSETS), (self.frame, FRAME_ASSETS)):
            names = {x.name for x in selected}
            if len(names) != len(selected) or not names <= set(catalogue):
                raise ValueError("Choose distinct starting Assets from the actual printed family")
        if not self.name.strip() or any(
            not x.description.strip() for x in (*self.girl, *self.frame)
        ):
            raise ValueError("Name the original Harpy and describe each selected starting Asset")
        return self


def offers(state: GameState) -> tuple[Offer, ...]:
    return tuple(Offer.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


def save(state: GameState, value: Offer) -> None:
    state.facts = [
        x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.actor.entity)
    ]
    state.facts.append(dict(kind=KIND, id=value.actor.entity, body=value.model_dump_json()))


def introduce(state: GameState, value: Offer, draft: Draft) -> None:
    world = state.world
    if (
        world is None
        or not world.board.contains(value.cell)
        or value.actor.kind != "external_pilot"
        or any(x.id == value.actor.entity for x in world.pilots)
        or any(x.id == value.actor.entity for x in state.harpy_states)
    ):
        raise ValueError("Use the actual original new Harpy and approved map square")
    families: tuple[tuple[Literal["girl", "frame"], tuple[AssetChoice, ...]], ...] = (
        ("girl", draft.girl),
        ("frame", draft.frame),
    )
    resources = tuple(
        Asset(
            id=f"{value.actor.entity}:{family}:{index}",
            family=family,
            name=x.name,
            description=x.description,
        )
        for family, selected in families
        for index, x in enumerate(selected)
    )
    pilot = AdversaryPilot(
        id=value.actor.entity,
        kind="harpy",
        girl="harpy",
        frame="harpy",
        name=draft.name.strip(),
        controller=value.controller,
        assets=resources,
        cell=value.cell,
    )
    state.world = world.model_copy(update=dict(pilots=(*world.pilots, pilot)))
