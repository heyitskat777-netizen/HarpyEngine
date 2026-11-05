"""Original cleanup scene or source-owned random exposure at a past mission site."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_off_duty import Scene


class Cleanup(Model):
    id: str
    source_work: str
    source_event: str
    period: str
    mission: str
    location: str
    handler: ActorRef
    people: tuple[ActorRef, ...]
    mode: Literal["scene", "exposure"]
    phase: Literal["scene", "rewrite", "threshold", "complete"]
    account: str = Field(min_length=1, max_length=2400)
    scene: Scene | None = None
    selected: int | None = None
    rng_source: Literal["os", "test_injected"] | None = None
    asset: str | None = None
    description: str | None = None
    storage: bool = False
    gain_event: str | None = None
    thresholds: tuple[str, ...] = ()
    ended_event: str | None = None

    @model_validator(mode="after")
    def original_source(self) -> "Cleanup":
        if (
            not self.people
            or len(set(self.people)) != len(self.people)
            or any(x.kind != "pilot" for x in self.people)
            or self.handler.kind != "handler"
            or (self.mode == "scene") != (self.scene is not None)
            or (self.mode == "exposure") != (self.selected is not None)
            or (self.selected is not None and not 0 <= self.selected < len(self.people))
            or (self.mode == "exposure") != (self.rng_source is not None)
            or (self.phase == "complete") != (self.ended_event is not None)
            or (self.mode == "scene" and self.phase not in ("scene", "complete"))
            or (self.phase == "threshold" and not self.thresholds)
        ):
            raise ValueError("Preserve the actual cleanup scene or single original exposure draw")
        return self


def cases(state: GameState) -> tuple[Cleanup, ...]:
    return tuple(
        Cleanup.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "budget_cleanup"
    )


def get(state: GameState, identity: str) -> Cleanup:
    value = next((x for x in cases(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Open the original mission-site cleanup")
    return value


def put(state: GameState, value: Cleanup) -> None:
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "budget_cleanup" and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind="budget_cleanup", id=value.id, body=value.model_dump_json()))


def create(
    state: GameState,
    work: str,
    event: str,
    period: str,
    mission: str,
    location: str,
    mode: Literal["scene", "exposure"],
    account: str,
    selected: int | None = None,
    rng_source: Literal["os", "test_injected"] | None = None,
) -> GameState:
    handler = active_handler(state)
    place = (
        next((x for x in state.world.locations if x.id == location), None) if state.world else None
    )
    if (
        handler is None
        or place is None
        or not state.order
        or any(x.source_work == work for x in cases(state))
    ):
        raise ValueError("Use the original Handler, actual Cadre and existing past-mission site")
    people = tuple(current_ref(state, uid) for uid in state.order)
    scene = (
        Scene(
            kind="budget_cleanup",
            participants=(int(handler.entity), *state.order),
            summary=account,
            character_ids={x.entity: str(x.incarnation) for x in people},
        )
        if mode == "scene"
        else None
    )
    value = Cleanup(
        id=work + ":cleanup",
        source_work=work,
        source_event=event,
        period=period,
        mission=mission,
        location=location,
        handler=handler,
        people=people,
        mode=mode,
        phase="scene" if mode == "scene" else "rewrite",
        account=account,
        scene=scene,
        selected=selected,
        rng_source=rng_source,
    )
    changed = GameState.model_validate_json(state.model_dump_json())
    put(changed, value)
    return changed
