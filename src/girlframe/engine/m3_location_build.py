"""One direct advancement creates one real Location without replacing existing world state."""

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Cell, Location

RULE = "handler-advancement.direct-spend.build-location"


class Effect(Model):
    id: str = Field(min_length=1)
    award: str = Field(min_length=1)
    handler: ActorRef
    appointment: str = Field(min_length=1)
    event: str = Field(min_length=1)
    location: Location

    @model_validator(mode="after")
    def exact_new_site(self) -> "Effect":
        if (
            self.id != "location-build:" + self.award
            or self.handler.kind != "handler"
            or self.location.condition != "intact"
            or self.location.allegiance != "foundation"
            or self.location.blocked_by
        ):
            raise ValueError("Build one actual intact Foundation site from this original award")
        return self


def require_site(state: GameState, cell: Cell) -> None:
    world = state.world
    if (
        world is None
        or not world.board.contains(cell)
        or any(x.cell == cell for x in world.locations)
    ):
        raise ValueError("Choose an actual in-board square without an existing major location")
    if (
        cell in world.territory
        or any(x.active and x.kind == "rebel" and cell in x.cells for x in world.factions)
        or any(x.alive and x.cell == cell for x in world.npcs)
        or any(x.alive and x.cell == cell for x in world.gorgons)
        or any(x.alive and x.cell == cell for x in world.pilots)
    ):
        raise ValueError(
            "SOURCE_PORT_REQUIRED: resolve actual occupied or disputed site before construction"
        )


def apply(state: GameState, effect: Effect) -> None:
    require_site(state, effect.location.cell)
    assert state.world is not None
    state.world = update(state.world, locations=state.world.locations + (effect.location,))
