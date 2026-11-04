"""Pure Strain start/selection/cascade scheduling, not generic event completion."""

from pydantic import Field

from girlframe.engine.m3_strain_state import (
    TRACKS,
    Endgame,
    Event,
    Model,
    Request,
    Scenario,
    Severity,
    State,
    Track,
)

PAGES = {
    ("void", "low"): 144,
    ("void", "high"): 145,
    ("rebellion", "low"): 147,
    ("rebellion", "high"): 148,
    ("budget", "low"): 150,
    ("budget", "high"): 151,
}
TABLES: tuple[Severity, ...] = ("low", "high")


class StartFacts(Model):
    """Explicit factual trigger review; booleans have no silently false defaults."""

    at_least_half_have_void: bool
    harpy_or_prevented_since_last: bool
    no_girl_void: bool
    all_gorgons_dormant_or_benevolent: bool
    girl_leaked_information: bool
    girl_attempted_handler_kill_escape_or_rebel_capture: bool
    rebel_handler_killed: bool
    rebel_pilot_captured_and_broken: bool
    structure_destroyed: bool
    girl_death_or_severe: bool
    frame_full_or_all_frames_some_repairs: bool
    last_mission_success_no_frame_death_infrastructure_loss: bool
    budget_contributor_moderately_punished: bool
    account: str = Field(min_length=1, max_length=2400)


def initial(scenario: Scenario, high: frozenset[Track]) -> State:
    count = {
        "business_as_usual": 0,
        "disaster_management": 1,
        "barely_hanging_on": 2,
        "falling_apart": 3,
    }.get(scenario)
    if count is None or len(high) != count or not high <= set(TRACKS):
        raise ValueError("Choose exactly the starting scenario's number of High tracks")
    return State(scenario=scenario, levels={x: "high" if x in high else "low" for x in TRACKS})


def copy(state: State, **updates: object) -> State:
    return State.model_validate_json(state.model_copy(update=updates).model_dump_json())


def start(state: State, period_id: str, facts: StartFacts) -> State:
    if not period_id.strip() or period_id in state.periods or not facts.account.strip():
        raise ValueError("Each actual Off-Duty period has one explicit factual Strain start")
    if state.requests or any(x.column is None for x in state.events):
        raise ValueError("Resume pending Strain rolls/column choices before starting another cycle")
    if facts.no_girl_void and facts.at_least_half_have_void:
        raise ValueError("The current canonical Void trigger facts contradict each other")
    if any(x.consumed_by is None and not getattr(facts, x.kind) for x in state.triggers):
        raise ValueError("The factual review cannot deny an unconsumed canonical Strain trigger")
    raise_high = {
        "void": facts.at_least_half_have_void or facts.harpy_or_prevented_since_last,
        "rebellion": facts.girl_leaked_information
        or facts.girl_attempted_handler_kill_escape_or_rebel_capture,
        "budget": facts.structure_destroyed
        or facts.girl_death_or_severe
        or facts.frame_full_or_all_frames_some_repairs,
    }
    lower = {
        "void": facts.no_girl_void and facts.all_gorgons_dormant_or_benevolent,
        "rebellion": facts.rebel_handler_killed and facts.rebel_pilot_captured_and_broken,
        "budget": facts.last_mission_success_no_frame_death_infrastructure_loss
        and facts.budget_contributor_moderately_punished,
    }
    levels: dict[Track, Severity] = {
        track: ("high" if raise_high[track] or track in state.repeated else "low")
        if state.levels[track] == "low"
        else ("low" if lower[track] or track in state.repeated else "high")
        for track in TRACKS
    }
    return copy(
        state,
        levels=levels,
        repeated=frozenset(),
        periods=state.periods + (period_id,),
        triggers=tuple(
            x.model_copy(update={"consumed_by": period_id}) if x.consumed_by is None else x
            for x in state.triggers
        ),
        requests=tuple(
            Request(
                id=period_id + ":strain:" + track,
                period_id=period_id,
                track=track,
                severity=levels[track],
            )
            for track in TRACKS
        ),
    )


def roll(state: State, request_id: str, face: int) -> State:
    request = next((x for x in state.requests if x.id == request_id), None)
    if request is None or request.kind != "roll" or request.severity is None:
        raise ValueError("Resume a pending Strain die request; a saved die cannot be rerolled")
    event = Event(
        id=request.id,
        period_id=request.period_id,
        track=request.track,
        severity=request.severity,
        face=face,
        parent=request.parent,
    )
    return copy(
        state,
        requests=tuple(x for x in state.requests if x.id != request_id),
        events=state.events + (event,),
    )


def choose(state: State, event_id: str, column: int) -> State:
    event = next((x for x in state.events if x.id == event_id), None)
    if event is None or event.column is not None or column not in (1, 2) or type(column) is not int:
        raise ValueError("The Handler must choose one pending die's actual event column")
    selected = Event.model_validate_json(
        event.model_copy(update={"column": column}).model_dump_json()
    )
    repeated = state.repeated
    if any(x.rule_id == selected.rule_id for x in state.events if x.column is not None):
        repeated |= {event.track}
    requests = state.requests
    if (event.severity, event.face, column) == ("high", 6, 2):
        # Both lists remain available on each actual table roll. No substitute or reroll.
        other = sum(x.track == event.track and x.column is not None for x in state.events)
        if other <= 2:
            requests += tuple(
                Request(
                    id=event.id + ":cascade:" + severity,
                    period_id=event.period_id,
                    track=event.track,
                    severity=severity,
                    parent=event.id,
                )
                for severity in TABLES
            )
        else:
            requests += (
                Request(
                    id=event.id + ":endgame",
                    period_id=event.period_id,
                    track=event.track,
                    kind="endgame",
                    parent=event.id,
                ),
            )
    return copy(
        state,
        events=tuple(selected if x.id == event_id else x for x in state.events),
        requests=requests,
        repeated=repeated,
    )


def endgame_options(
    state: State, track: Track, *, ancillary_enabled: bool = False
) -> tuple[int, ...]:
    maximum = 8 if track == "rebellion" else 7
    used = {x.option for x in state.endgames if x.track == track}
    return tuple(
        x
        for x in range(1, maximum + 1)
        if x not in used and (track != "rebellion" or x != 3 or ancillary_enabled)
    )


def choose_endgame(state: State, request_id: str, option: int) -> State:
    request = next((x for x in state.requests if x.id == request_id), None)
    if request is None or request.kind != "endgame" or request.parent is None:
        raise ValueError("Resume an actual pending Endgame request")
    if type(option) is not int or option not in endgame_options(state, request.track):
        raise ValueError("Choose an unused enabled Endgame; optional Ancillary is disabled")
    chosen = Endgame(
        id=request.id,
        period_id=request.period_id,
        track=request.track,
        option=option,
        parent=request.parent,
    )
    return copy(
        state,
        requests=tuple(x for x in state.requests if x.id != request_id),
        endgames=state.endgames + (chosen,),
    )
