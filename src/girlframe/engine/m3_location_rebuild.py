"""One direct advancement restores one actual existing Location, preserving its identity."""

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Location

RULE = "handler-advancement.direct-spend.rebuild-location"


class Effect(Model):
    id: str = Field(min_length=1)
    award: str = Field(min_length=1)
    handler: ActorRef
    appointment: str = Field(min_length=1)
    event: str = Field(min_length=1)
    before: Location
    after: Location

    @model_validator(mode="after")
    def exact_restoration(self) -> "Effect":
        if (
            self.id != "location-rebuild:" + self.award
            or self.handler.kind != "handler"
            or self.before.condition == "intact"
            or self.after != self.before.model_copy(update=dict(condition="intact"))
        ):
            raise ValueError("Restore one actual non-intact Location without changing its identity")
        return self


def apply(state: GameState, effect: Effect) -> None:
    if (
        state.world is None
        or next((x for x in state.world.locations if x.id == effect.before.id), None)
        != effect.before
    ):
        raise ValueError("Reopen the actual existing Location before this rebuild")
    state.world = update(
        state.world,
        locations=tuple(
            effect.after if x.id == effect.before.id else x for x in state.world.locations
        ),
    )
