import pytest
from pydantic import ValidationError

from girlframe.engine import m3_strain as rules
from girlframe.engine.m3_strain_state import TRACKS, Event, Request


def facts(**updates):
    return rules.StartFacts(
        **(
            {name: False for name in rules.StartFacts.model_fields if name != "account"}
            | {"account": "Synthetic factual trigger review"}
            | updates
        )
    )


@pytest.mark.parametrize(
    "scenario,count",
    [
        ("business_as_usual", 0),
        ("disaster_management", 1),
        ("barely_hanging_on", 2),
        ("falling_apart", 3),
    ],
)
def test_starting_scenario_requires_explicit_exact_high_tracks(scenario, count):
    state = rules.initial(scenario, frozenset(TRACKS[:count]))
    assert sum(level == "high" for level in state.levels.values()) == count
    with pytest.raises(ValueError):
        rules.initial(scenario, frozenset(TRACKS[: (count + 1) % 4]))


@pytest.mark.parametrize(
    "track,trigger",
    [
        ("void", "at_least_half_have_void"),
        ("void", "harpy_or_prevented_since_last"),
        ("rebellion", "girl_leaked_information"),
        ("rebellion", "girl_attempted_handler_kill_escape_or_rebel_capture"),
        ("budget", "structure_destroyed"),
        ("budget", "girl_death_or_severe"),
        ("budget", "frame_full_or_all_frames_some_repairs"),
    ],
)
def test_each_printed_low_to_high_trigger_is_sufficient(track, trigger):
    state = rules.initial("business_as_usual", frozenset())
    updated = rules.start(state, "period", facts(**{trigger: True}))
    assert updated.levels[track] == "high" and state.levels[track] == "low"


@pytest.mark.parametrize(
    "track,conditions",
    [
        ("void", ("no_girl_void", "all_gorgons_dormant_or_benevolent")),
        ("rebellion", ("rebel_handler_killed", "rebel_pilot_captured_and_broken")),
        (
            "budget",
            (
                "last_mission_success_no_frame_death_infrastructure_loss",
                "budget_contributor_moderately_punished",
            ),
        ),
    ],
)
def test_high_to_low_requires_both_printed_conditions(track, conditions):
    state = rules.initial("disaster_management", frozenset({track}))
    for condition in conditions:
        assert rules.start(state, "period", facts(**{condition: True})).levels[track] == "high"
    assert (
        rules.start(state, "period", facts(**dict.fromkeys(conditions, True))).levels[track]
        == "low"
    )


@pytest.mark.parametrize("track", TRACKS)
@pytest.mark.parametrize("severity", ["low", "high"])
@pytest.mark.parametrize("face", range(1, 7))
@pytest.mark.parametrize("column", [1, 2])
def test_all_72_table_columns_select_the_actual_saved_die_without_implementing_its_effect(
    track, severity, face, column
):
    state = rules.initial("business_as_usual", frozenset())
    state = rules.copy(
        state,
        periods=("period",),
        requests=(Request(id="request", period_id="period", track=track, severity=severity),),
    )
    rolled = rules.roll(state, "request", face)
    assert rolled.events[0].column is None
    with pytest.raises(ValueError, match="rerolled"):
        rules.roll(rolled, "request", 6)
    chosen = rules.choose(rolled, "request", column)
    assert chosen.events[0].rule_id == f"strain.{track}.{severity}.{face}.{column}"
    assert rules.PAGES[(track, severity)] in (144, 145, 147, 148, 150, 151)
    with pytest.raises(ValueError):
        rules.choose(chosen, "request", column)


@pytest.mark.parametrize("track", TRACKS)
@pytest.mark.parametrize("prior_count", [0, 2, 3])
def test_recursive_or_endgame_threshold_counts_other_occurrences_of_same_track(track, prior_count):
    state = rules.initial("business_as_usual", frozenset())
    prior = tuple(
        Event(
            id=f"prior-{i}", period_id="period", track=track, severity="low", face=i + 1, column=1
        )
        for i in range(prior_count)
    )
    state = rules.copy(
        state,
        periods=("period",),
        events=prior,
        requests=(Request(id="request", period_id="period", track=track, severity="high"),),
    )
    chosen = rules.choose(rules.roll(state, "request", 6), "request", 2)
    if prior_count <= 2:
        assert [(x.kind, x.severity) for x in chosen.requests] == [
            ("roll", "low"),
            ("roll", "high"),
        ]
        assert all(x.parent == "request" for x in chosen.requests)
    else:
        assert len(chosen.requests) == 1 and chosen.requests[0].kind == "endgame"


def test_recursive_queue_survives_restart_and_never_discards_remaining_rolls_or_endgame():
    state = rules.start(rules.initial("falling_apart", frozenset(TRACKS)), "period", facts())
    # Keep other tracks' actual base requests pending while expanding the Void branch.
    while request := next(
        (x for x in state.requests if x.track == "void" and x.kind == "roll"), None
    ):
        state = rules.choose(rules.roll(state, request.id, 6), request.id, 2)
        state = type(state).model_validate_json(state.model_dump_json())
    assert len([x for x in state.events if x.track == "void"]) == 5
    assert {x.track for x in state.requests} == set(TRACKS)
    endgame = next(x for x in state.requests if x.kind == "endgame")
    state = rules.choose_endgame(state, endgame.id, 6)
    assert 6 not in rules.endgame_options(state, "void")
    assert 7 in rules.endgame_options(state, "void")  # The two advancement slots are distinct.
    assert 3 not in rules.endgame_options(state, "rebellion")
    assert len(state.requests) == 2  # No worker batch limit erased unrelated work.
    with pytest.raises(ValueError, match="pending Strain"):
        rules.start(state, "another-period", facts())


def test_repeat_flags_change_only_the_next_period_without_rerolling_receipts():
    state = rules.initial("business_as_usual", frozenset())
    for period in ("period-1", "period-2"):
        state = rules.start(state, period, facts())
        for request in tuple(state.requests):
            state = rules.choose(rules.roll(state, request.id, 1), request.id, 1)
    assert state.repeated == frozenset(TRACKS) and set(state.levels.values()) == {"low"}
    previous = state.events
    changed = rules.start(state, "period-3", facts())
    assert set(changed.levels.values()) == {"high"} and not changed.repeated
    assert changed.events == previous
    with pytest.raises(ValueError):
        rules.start(changed, "period-3", facts())


def test_malformed_die_column_and_unsupported_endgame_fail_without_substitution():
    state = rules.start(rules.initial("business_as_usual", frozenset()), "period", facts())
    with pytest.raises(ValidationError):
        rules.roll(state, state.requests[0].id, 7)
    rolled = rules.roll(state, state.requests[0].id, 2)
    with pytest.raises(ValueError):
        rules.choose(rolled, rolled.events[0].id, True)
    request = Request(
        id="endgame", period_id="period", track="rebellion", kind="endgame", parent="source-event"
    )
    source = Event(
        id="source-event", period_id="period", track="rebellion", severity="high", face=6, column=2
    )
    state = rules.copy(state, requests=(request,), events=(source,))
    with pytest.raises(ValueError, match="Ancillary"):
        rules.choose_endgame(state, request.id, 3)


def test_recursive_requests_cannot_fabricate_source_provenance():
    state = rules.start(rules.initial("business_as_usual", frozenset()), "period", facts())
    child = Request(id="child", period_id="period", track="void", severity="low", parent="missing")
    with pytest.raises(ValidationError, match="actual selected"):
        rules.copy(state, requests=(child,))
    wrong = Event(
        id="missing", period_id="period", track="budget", severity="high", face=6, column=2
    )
    with pytest.raises(ValidationError, match="actual selected"):
        rules.copy(state, events=(wrong,), requests=(child,))
    with pytest.raises(ValidationError, match="actual source event"):
        Request(id="endgame", period_id="period", track="void", kind="endgame")
