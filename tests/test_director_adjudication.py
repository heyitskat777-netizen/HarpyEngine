"""Actual native choices plus context determine a GM proposal, never tier alone."""

import json

import pytest
import sqlalchemy as sa
from test_director_conversation import routed as routed
from test_director_observation import observed as observed
from test_director_observation import send
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, start, state, tick

from girlframe.ai.adjudication import SyntheticAdjudicator
from girlframe.database import tables as t
from girlframe.services.director_adjudication import DirectorAdjudicationService
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.onboarding import WorkflowError


def prepare(
    routed,
    text,
    key,
    *,
    options=("tough", "in_control"),
    denied=("desperate",),
    play="keep_your_head",
    native_context=None,
):
    observer, context, scene, game, dice = routed
    # Original observer fixture owns its fake worker/gateway around the same game.
    from test_m2_game import Gateway

    from girlframe.delivery.m2_worker import GameWorker

    worker, gateway = GameWorker(game), Gateway()
    _, source = send(observer, scene, key, text=text)
    conversation = DirectorConversationService(context)
    native = start(game, play=play, context=text if native_context is None else native_context)
    tick(worker, gateway)
    pass_tags(game)
    if play == "keep_your_head":
        answer(game, PLAYER, "actor_keep", options=options, denied=denied)
    else:
        answer(
            game, PLAYER, "actor_sensors", options=("foundation_destination", "foundation_avoid")
        )
    service = DirectorAdjudicationService(conversation)
    return service, source, native, worker, gateway


def test_same_mid_roll_changes_with_traits_and_with_context(routed):
    observer, _, scene, game, dice = routed
    precise = "GM, I declare Keep Your Head to hold the calibration needle precisely on its mark."
    cold = "GM, I declare Keep Your Head to endure the freezing corridor until shelter."
    cases = [
        (precise, ("tough", "in_control"), ("desperate",), "success"),
        (precise, ("tough", "vicious"), ("in_control",), "failure"),
        (cold, ("tough", "vicious"), ("in_control",), "success"),
    ]
    verdicts = []
    for number, (text, positives, negatives, expected) in enumerate(cases):
        service, source, native, worker, gateway = prepare(
            routed, text, f"case:{number}", options=positives, denied=negatives
        )
        before = state(game).model_dump_json()
        ruling = service.adjudicate(PLAYER, f"judge:{number}", scene, source.source_id, 1, native)
        assert ruling["proposal"]["verdict"] == expected
        assert (
            service.adjudicate(PLAYER, f"judge:{number}", scene, source.source_id, 1, native)
            == ruling
        )
        assert state(game).model_dump_json() == before
        assert "SYNTHETIC_GM_SECRET_CANARY" not in json.dumps(ruling)
        with pytest.raises(WorkflowError):
            service.get(OTHER, scene, ruling["id"])
        with pytest.raises(WorkflowError):
            service.adjudicate(OTHER, "foreign", scene, source.source_id, 1, native)
        proposal = ruling["proposal"]
        answer(
            game,
            ADMIN,
            "handler_keep",
            flag=proposal["enough"],
            text=proposal["reasoning"] + "\n" + proposal["narration"],
        )
        tick(worker, gateway, 5)
        review = service.conversation.review_play(PLAYER, f"readback:{number}", scene, native)
        assert review["proof"]["total"] == 9
        assert review["verdict"] == expected and review["adjudication_id"] == ruling["id"]
        assert proposal["narration"] in review["reply"]["text"]
        verdicts.append(review["verdict"])
    assert verdicts == ["success", "failure", "success"] and dice.calls == 3


def test_unclear_goal_and_other_play_require_an_explicit_review(routed):
    _, _, scene, game, dice = routed
    service, source, native, worker, gateway = prepare(
        routed, "GM, I declare Keep Your Head to get through this situation.", "unclear"
    )
    ruling = service.adjudicate(PLAYER, "unclear-judge", scene, source.source_id, 1, native)
    assert ruling["proposal"]["verdict"] == "needs_clarification"
    assert ruling["proposal"]["enough"] is None
    answer(game, ADMIN, "handler_keep", flag=False, text="Explicit test-owner ruling after review.")
    tick(worker, gateway, 5)
    service, source, native, _, _ = prepare(
        routed,
        "GM, I declare Check Your Sensors to take stock of this situation.",
        "other-play",
        play="check_sensors",
    )
    ruling = service.adjudicate(PLAYER, "other-judge", scene, source.source_id, 1, native)
    assert ruling["proposal"]["verdict"] == "requires_play_adapter"
    assert ruling["proposal"]["enough"] is None and dice.calls == 2


def test_unbound_context_leaky_provider_and_changed_native_choice_reject(routed):
    observer, _, scene, game, dice = routed
    service, source, native, worker, gateway = prepare(
        routed,
        "GM, I declare Keep Your Head to endure the cold.",
        "unbound",
        native_context="A different declaration that was never bound to this source.",
    )
    with pytest.raises(WorkflowError, match="UNBOUND_CONTEXT"):
        service.adjudicate(PLAYER, "unbound-judge", scene, source.source_id, 1, native)
    answer(game, ADMIN, "handler_keep", flag=False, text="Explicit test-owner completion.")
    tick(worker, gateway, 5)
    service, source, native, _, _ = prepare(
        routed, "GM, I declare Keep Your Head to keep my focus under pressure.", "safe"
    )

    class Leaky(SyntheticAdjudicator):
        def adjudicate(self, request):
            return (
                super()
                .adjudicate(request)
                .model_copy(update={"narration": "SYNTHETIC_GM_SECRET_CANARY"})
            )

    service.provider = Leaky()
    with pytest.raises(WorkflowError, match="ADJUDICATION_UNAVAILABLE"):
        service.adjudicate(PLAYER, "leaky", scene, source.source_id, 1, native)

    class Changed(SyntheticAdjudicator):
        def adjudicate(self, request):
            result = super().adjudicate(request)
            answer(game, ADMIN, "handler_keep", flag=True, text="Other explicit owner decision.")
            return result

    service.provider = Changed()
    with pytest.raises(WorkflowError, match="RULING_COMMITTED"):
        service.adjudicate(PLAYER, "changed", scene, source.source_id, 1, native)
    with observer.store.engine.connect() as c:
        bodies = list(c.scalars(sa.select(t.director_context["shadow"].c.body_json)))
    assert not any(json.loads(x).get("record_type") == "gm_adjudication" for x in bodies)
    assert dice.calls == 2
