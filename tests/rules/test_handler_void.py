"""Source Handler physiology and real Director bodies never borrow a Pilot's Assets."""

import pytest
from test_actors import canon as canon
from test_actors import ledger as ledger
from test_world import initial

from girlframe.engine import m3_handler_void as rules
from girlframe.engine.m2 import DirectorContext
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_world_state import Npc


@pytest.mark.parametrize("director", [False, True])
@pytest.mark.parametrize("choice", ["knife", "drugs", "surgery"])
def test_three_real_handler_choices_preserve_original_body_and_distinct_actual_resources(
    canon, director, choice
):
    actor = active_handler(canon)
    if director:
        actor = ActorRef(kind="npc", entity="actual-director")
        canon.world = initial().model_copy(
            update={
                "npcs": (
                    Npc(
                        id=actor.entity,
                        name="Actual Director",
                        controller=3,
                        cell=(0, 0),
                        jobs=("director",),
                        detail="Actual separate body",
                    ),
                )
            }
        )
    before = canon.model_dump_json()
    state, identity = rules.require(
        canon,
        actor,
        work="actual-source-void-work",
        source_event="actual-corruption-source",
        appointment="actual-appointment",
    )
    assert canon.model_dump_json() == before
    episode = state.handler_void[-1]
    assert episode.actor == episode.body == actor
    assert episode.controller == (3 if director else 1)
    state = rules.choose(
        state,
        identity,
        choice,
        "actual-patient-choice",
        account="Actual performed cut/injection or requested medical procedure",
        site="Left forearm",
        manifestation="flesh" if choice == "drugs" else None,
    )
    current = state.handler_void[-1]
    assert state.sheets == canon.sheets and state.handler_heat == canon.handler_heat
    if choice == "knife":
        assert current.phase == "removed" and not current.void_present and current.wound
        assert current.removal_event == "actual-patient-choice"
    elif choice == "drugs":
        assert current.phase == "stabilized" and current.void_present and current.spread_halted
        assert current.manifestation == "flesh" and current.site == "Left forearm"
        assert not current.removal_event
        state = rules.choose(
            state,
            identity,
            "surgery",
            "actual-later-treatment-request",
            account="Actual personnel surgery request",
        )
        state = rules.surgery(
            state,
            identity,
            "actual-later-performed-surgery",
            "Actual personnel performed source-local removal",
        )
        assert state.handler_void[-1].phase == "removed"
        assert state.handler_void[-1].removal_event == "actual-later-performed-surgery"
    else:
        assert current.phase == "surgery" and current.void_present and not current.removal_event
        state = rules.surgery(
            state,
            identity,
            "actual-performed-surgery",
            "Actual personnel performed this real removal",
        )
        assert not state.handler_void[-1].void_present
    with pytest.raises(ValueError):
        rules.choose(state, identity, "knife", "replay", account="Cannot remove twice")


def test_handler_girl_context_cannot_substitute_handler_physiology_for_actual_girl_void(canon):
    actor = active_handler(canon)
    canon.director_contexts.append(
        DirectorContext(
            id="actual-handler-girl-context",
            handler=1,
            directors=("actual-director",),
            source_works=("actual-director-source",),
            identities=[],
            source_event="actual-context-source",
            body_actor=actor,
        )
    )
    with pytest.raises(ValueError, match="normal Handler"):
        rules.require(
            canon,
            actor,
            work="actual-void-source",
            source_event="actual-effect",
            appointment="actual-appointment",
        )


def test_actual_original_ending_is_not_surgery_or_corruption_removal(canon):
    actor = active_handler(canon)
    state, identity = rules.require(
        canon,
        actor,
        work="actual-source",
        source_event="actual-effect",
        appointment="actual-appointment",
    )
    ended = rules.end_actor(state, actor, "actual-original-death")
    current = ended.handler_void[-1]
    assert current.phase == "ended" and current.ended_event == "actual-original-death"
    assert current.void_present and not current.removal_event
    assert ended.sheets == state.sheets
    with pytest.raises(ValueError):
        rules.choose(
            ended, identity, "knife", "successor-attempt", account="Cannot act through dead body"
        )
