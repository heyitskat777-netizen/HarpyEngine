import pytest

from girlframe.engine.m3_missions import Mission, complete, dispatch, end, respond


def active(participants=(2,)):
    mission = Mission(
        id="synthetic-mission", handler=1, objective="Synthetic rescue", offered_to=participants
    )
    for uid in participants:
        mission = respond(mission, uid, mission.revision, "accept")
    return dispatch(mission, 1, 1, mission.revision, frozenset({2, 3, 4}))


def test_mission_answers_are_owned_and_absence_is_not_acceptance():
    mission = Mission(id="offer", handler=1, objective="Synthetic defence", offered_to=(2, 3))
    with pytest.raises(ValueError):
        respond(mission, 4, 1, "accept")
    with pytest.raises(ValueError):
        dispatch(mission, 1, 1, 1, frozenset({2, 3}))
    first = respond(mission, 2, 1, "accept")
    with pytest.raises(ValueError):
        respond(first, 2, 2, "decline")
    with pytest.raises(ValueError):
        respond(first, 3, 1, "accept")
    both = respond(first, 3, 2, "decline")
    launched = dispatch(both, 1, 1, 3, frozenset({2, 3}))
    assert launched.participants == (2,) and mission.responses == {}
    with pytest.raises(ValueError):
        dispatch(both, 3, 1, 3, frozenset({2, 3}))
    with pytest.raises(ValueError):
        dispatch(both, 1, 99, 3, frozenset({2, 3}))


def test_absent_dog_punishment_remains_real_pending_work():
    mission = active()
    result = end(
        mission, 1, 1, mission.revision, success=True, status_order=(2, 3), ace_policy=None
    )
    assert [(x.owner, x.amount) for x in result.grants] == [(2, 1), (2, 1)]
    assert len(result.consequences) == 1 and result.consequences[0].owner == 3
    with pytest.raises(ValueError):
        complete(
            result.mission,
            result.mission.revision,
            resolved_consequences=frozenset(),
            all_other_mandatory_work_resolved=True,
        )
    with pytest.raises(ValueError):
        complete(
            result.mission,
            result.mission.revision,
            resolved_consequences=frozenset(result.mission.consequence_ids),
            all_other_mandatory_work_resolved=False,
        )
    done = complete(
        result.mission,
        result.mission.revision,
        resolved_consequences=frozenset(result.mission.consequence_ids),
        all_other_mandatory_work_resolved=True,
    )
    assert done.phase == "complete"


@pytest.mark.parametrize(
    "policy,expected", [("current_ace", [(2, 1), (3, 1)]), ("participants_only", [(2, 1)])]
)
def test_absent_ace_policy_is_explicit_not_invented(policy, expected):
    mission = active()
    with pytest.raises(ValueError, match="UNRESOLVED_RULING"):
        end(mission, 1, 1, mission.revision, success=True, status_order=(3, 2), ace_policy=None)
    result = end(
        mission, 1, 1, mission.revision, success=True, status_order=(3, 2), ace_policy=policy
    )
    assert [(x.owner, x.amount) for x in result.grants] == expected


def test_failed_mission_still_grants_base_permission_and_retains_each_required_cause():
    mission = active((2, 3))
    result = end(
        mission,
        1,
        1,
        mission.revision,
        success=False,
        status_order=(2, 3),
        ace_policy="current_ace",
    )
    assert [(x.owner, x.reason) for x in result.consequences] == [
        (2, "mission_failure"),
        (3, "mission_failure"),
        (3, "dog_mission_end"),
    ]
    assert len(result.mission.consequence_ids) == 3
    with pytest.raises(ValueError):
        end(
            result.mission,
            1,
            1,
            result.mission.revision,
            success=False,
            status_order=(2, 3),
            ace_policy="current_ace",
        )
    assert sum(x.amount for x in result.grants if x.owner == 2) == 2
    assert sum(x.amount for x in result.grants if x.owner == 3) == 1
