import pytest
from test_actor_resources import handler
from test_actors import bindings
from test_actors import canon as canon_fixture
from test_ledger import ledger as ledger_fixture

from girlframe.engine import m3_actor_plays as rules
from girlframe.engine.m2 import ChoiceAnswer, TagState
from girlframe.engine.m3_actor_state import ActorRef

canon, ledger = canon_fixture, ledger_fixture


@pytest.mark.parametrize(
    "level,answer",
    [
        ("low", ChoiceAnswer(options=("tough", "sexy"))),
        ("mid", ChoiceAnswer(options=("tough", "sexy"), denied=("sexy",))),
        ("high", ChoiceAnswer(text="")),
        ("high", ChoiceAnswer(options=("sexy",), text="Tag")),
        ("low", ChoiceAnswer(options=("tough",), flag=True)),
    ],
)
def test_actual_handler_keep_rejects_illegal_counts_overlapping_traits_and_borrowed_passives(
    level, answer
):
    with pytest.raises(ValueError):
        rules.keep(level, answer)


def test_actual_handler_tag_embrace_adds_until_cap_then_replaces_one_real_identity(canon):
    state, ref = handler(canon)
    actual = state.director_contexts[-1]
    for i in range(3):
        rules.add_tag(state, ref, "Repeated label", (1, 2))
        tag = state.handler_tags[-1]
        assert not rules.mark(state, ref, tag.id, str(i))
        with pytest.raises(ValueError):
            rules.mark(state, ref, tag.id, str(i))
        assert rules.mark(state, ref, tag.id, "repeat:" + str(i))
        if i < 2:
            rules.embrace(state, ref, tag.id, ())
        else:
            with pytest.raises(ValueError):
                rules.embrace(state, ref, tag.id, ())
            rules.embrace(state, ref, tag.id, (actual.identities[0].id,))
    assert len(actual.identities) == 4 and len({x.id for x in actual.identities}) == 4
    assert not state.handler_tags


def test_tags_require_actual_other_human_observation_and_explicit_bond_port(canon):
    state, ref = handler(canon)
    state.handler_tags.append(TagState(id="tag", label="Known", giver=2, observers=(2,)))
    pilot = ActorRef(kind="pilot", entity="2", incarnation=state.sheets["2"].character_id)
    for depth in (0, 1, 2):
        state.bonds["1:2"] = depth
        assert rules.proposal(
            state, ref, pilot, 2, bindings(state), "tag", "scene", -1, "Relevance"
        ) == (-2 if depth else -1)
    for actual, controller in (
        (pilot, 1),
        (ActorRef(kind="npc", entity="director"), 3),
    ):
        with pytest.raises(ValueError):
            rules.proposal(
                state, ref, actual, controller, bindings(state), "tag", "scene", 1, "Relevance"
            )
    # A separately controlled actual person uses their own graph Bond, never
    # the same human's Pilot edge above.
    external = ActorRef(kind="external_pilot", entity="external")
    assert (
        rules.proposal(
            state, ref, external, 2, bindings(state), "tag", "scene", 1, "Actual relevance"
        )
        == 1
    )
    assert not state.handler_tags[0].marked


def test_rejection_requires_real_pending_tag_and_preserves_other_tags(canon):
    state, ref = handler(canon)
    state.handler_tags = [
        TagState(id="pending", label="Reject", giver=2, rejection_pending=True),
        TagState(id="other", label="Retain", giver=2),
    ]
    with pytest.raises(ValueError):
        rules.reject(state, ref, "other")
    rules.reject(state, ref, "pending")
    assert [x.id for x in state.handler_tags] == ["other"]
    state.director_contexts[-1] = state.director_contexts[-1].model_copy(
        update={"active": False, "directors": ()}
    )
    with pytest.raises(ValueError):
        rules.context(state, ref)
