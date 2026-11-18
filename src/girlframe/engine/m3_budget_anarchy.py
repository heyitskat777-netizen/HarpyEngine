"""Temporary city anarchy preserves its physical condition and exact cause."""

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_world import update

BUDGET = "strain.budget.high.5.1"
REBELLION = "strain.rebellion.high.1.2"


class Anarchy(Model):
    id: str
    source_event: str
    handler: ActorRef
    city: str
    account: str = Field(min_length=1, max_length=2400)
    method: str | None = None
    result: str | None = None
    restored_event: str | None = None
    faction: str | None = Field(default=None, exclude_if=lambda x: x is None)
    mission: str | None = Field(default=None, exclude_if=lambda x: x is None)
    dispatch_event: str | None = Field(default=None, exclude_if=lambda x: x is None)
    blockade_event: str | None = Field(default=None, exclude_if=lambda x: x is None)

    @property
    def rule_id(self) -> str:
        return REBELLION if self.faction is not None else BUDGET


def cases(state: GameState) -> tuple[Anarchy, ...]:
    return tuple(
        Anarchy.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "budget_anarchy"
    )


def get(state: GameState, identity: str) -> Anarchy:
    value = next((x for x in cases(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Open the original city's actual anarchy source")
    return value


def put(state: GameState, value: Anarchy) -> None:
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "budget_anarchy" and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind="budget_anarchy", id=value.id, body=value.model_dump_json()))


def create(
    state: GameState, work: str, event: str, city: str, account: str, *, faction: str | None = None
) -> None:
    handler = active_handler(state)
    if handler is None or any(x.id == work for x in cases(state)):
        raise ValueError("Record one original Handler and actual new city-anarchy source")
    put(
        state,
        Anarchy(
            id=work,
            source_event=event,
            handler=handler,
            city=city,
            account=account,
            faction=faction,
        ),
    )


def dispatch(state: GameState, mission: str, event: str) -> None:
    for case in cases(state):
        if case.faction is not None and case.mission is None:
            put(state, case.model_copy(update={"mission": mission, "dispatch_event": event}))


def deadline(state: GameState, mission: str, event: str) -> None:
    for case in cases(state):
        if case.mission != mission or case.restored_event or case.blockade_event:
            continue
        world = state.world
        if world is None or not any(site.id == case.city for site in world.locations):
            raise ValueError("Recover the original city affected by the Rebel protest")
        state.world = update(
            world,
            locations=tuple(
                site.model_copy(update={"blocked_by": (*site.blocked_by, case.id)})
                if site.id == case.city and case.id not in site.blocked_by
                else site
                for site in world.locations
            ),
        )
        put(state, case.model_copy(update={"blockade_event": event}))


def address(state: GameState, value: Anarchy, method: str, result: str, event: str) -> None:
    if (
        value.faction is None
        or value.mission is None
        or value.blockade_event
        or value.restored_event
        or not same_handler_body(state, value.handler)
    ):
        raise ValueError("Record the engagement during this actual protest's next mission")
    put(
        state,
        value.model_copy(update={"method": method, "result": result, "restored_event": event}),
    )


def restore(state: GameState, value: Anarchy, method: str, result: str, event: str) -> GameState:
    city = (
        next((x for x in state.world.locations if x.id == value.city), None)
        if state.world
        else None
    )
    if (
        city is None
        or city.kind != "city"
        or value.id not in city.blocked_by
        or city.condition == "destroyed"
        or value.restored_event is not None
        or not same_handler_body(state, value.handler)
        or not method.strip()
        or not result.strip()
        or not event
    ):
        raise ValueError("Record actual restored order at this original surviving city")
    changed = GameState.model_validate_json(state.model_dump_json())
    assert changed.world is not None
    changed.world = update(
        changed.world,
        locations=tuple(
            x.model_copy(update={"blocked_by": tuple(k for k in x.blocked_by if k != value.id)})
            if x.id == city.id
            else x
            for x in changed.world.locations
        ),
    )
    put(
        changed,
        value.model_copy(
            update=dict(
                method=method.strip(),
                result=result.strip(),
                restored_event=event,
            )
        ),
    )
    return changed
