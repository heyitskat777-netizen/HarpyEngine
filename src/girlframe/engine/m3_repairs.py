"""Actual mission/period transitions for Low Budget 4/2; restrictions do not stack."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_repair_state import Shortage


def clone(state: GameState) -> GameState:
    return GameState.model_validate_json(state.model_dump_json())


def schedule(state: GameState, source: str, period: str) -> Shortage:
    if (
        state.strain is None
        or period not in state.strain.periods
        or any(x.id == source for x in state.repair_shortages)
    ):
        raise ValueError("Bind the shortage once to its actual saved Strain period")
    return Shortage(id=source, source_period=period)


def dispatch(original: GameState, mission: str, event: str) -> GameState:
    state = clone(original)
    state.repair_shortages = [
        x.model_copy(update={"mission": mission, "dispatch_event": event})
        if x.mission is None
        else x
        for x in state.repair_shortages
    ]
    return state


def mission_ended(original: GameState, mission: str, event: str) -> GameState:
    state = clone(original)
    state.repair_shortages = [
        x.model_copy(update={"mission_end_event": event})
        if x.mission == mission and x.mission_end_event is None
        else x
        for x in state.repair_shortages
    ]
    return state


def begin_period(original: GameState, period: str) -> GameState:
    state = clone(original)
    state.repair_shortages = [
        x.model_copy(update={"period": period})
        if x.mission_end_event is not None and x.period is None
        else x
        for x in state.repair_shortages
    ]
    return state


def active(state: GameState, period: str) -> tuple[str, ...]:
    return tuple(x.id for x in state.repair_shortages if x.period == period and not x.closed)


def close_period(original: GameState, period: str) -> GameState:
    state = clone(original)
    state.repair_shortages = [
        x.model_copy(update={"closed": True}) if x.period == period else x
        for x in state.repair_shortages
    ]
    return state
