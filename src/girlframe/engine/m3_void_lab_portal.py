"""A stable laboratory aperture has a real location and an immutable Endgame source."""

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_promotional_opportunity import in_responsibility
from girlframe.engine.m3_world_state import Cell, Location

RULE = "strain.void.endgame.2"
KIND = "void_lab_portal"


class Portal(Model):
    id: str
    source: str
    opened: str
    handler: ActorRef
    site: str
    cell: Cell
    laboratory: str = Field(min_length=1, max_length=120)
    account: str = Field(min_length=1, max_length=1200)


def portals(state: GameState) -> tuple[Portal, ...]:
    return tuple(
        Portal.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def sites(state: GameState) -> tuple[Location, ...]:
    return (
        tuple(
            x
            for x in state.world.locations
            if x.foundation_operational and x.ship is None and in_responsibility(state, x.cell)
        )
        if state.world
        else ()
    )


def open_portal(state: GameState, portal: Portal) -> None:
    if (
        not portal.laboratory.strip()
        or not portal.account.strip()
        or not any(x.id == portal.site and x.cell == portal.cell for x in sites(state))
        or any(x.id == portal.id for x in portals(state))
    ):
        raise ValueError("Open the actual stable portal in an available Foundation laboratory")
    state.facts.append(dict(kind=KIND, id=portal.id, body=portal.model_dump_json()))


def projection(state: GameState) -> list[dict[str, object]]:
    eligible = {(x.id, x.cell) for x in sites(state)}
    return [
        dict(
            id=x.id,
            site=x.site,
            cell=list(x.cell),
            laboratory=x.laboratory,
            accessible=(x.site, x.cell) in eligible,
        )
        for x in portals(state)
    ]
