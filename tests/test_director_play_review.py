"""Full catalog referrals, durable triage, scoped controller work and no invented effects."""

import json

import pytest
from test_director_adjudication import prepare
from test_director_conversation import routed as routed
from test_director_observation import observed as observed
from test_director_observation import send
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine.m2 import PLAY_IDS
from girlframe.engine.m3_handler_play_state import BASIC, EXTRA
from girlframe.engine.m3_plays import ASSET_IDS, FIXED_IDS, HEAT_IDS, JANUS_ROLL_IDS, ROLL_IDS
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.director_play_catalog import NATIVE_RULES, PlayCatalog
from girlframe.services.director_play_review import DirectorPlayReviewService
from girlframe.services.onboarding import WorkflowError


def test_entire_inventory_and_every_native_identifier_have_explicit_review_routes():
    catalog = PlayCatalog()
    rolled = set((*PLAY_IDS, *ROLL_IDS, *FIXED_IDS, *HEAT_IDS, *ASSET_IDS, *JANUS_ROLL_IDS))
    handlers = {"handler_" + key for key, _ in (*BASIC, *EXTRA)}
    assert (
        rolled
        | handlers
        | {
            "receive_orders",
            "gorgon_attack",
            "gorgon_collateral",
            "gorgon_warp",
            "handler_advocate_alone",
            "handler_frantic_breakdown",
            "handler_casualty_parts",
            "handler_mistress_favor",
            "handler_trainer_private",
            "handler_dogrunner_private",
            "handler_insurgent_private",
        }
        == NATIVE_RULES.keys()
    )
    for identity in NATIVE_RULES:
        matched = catalog.recognize(
            "GM, I declare " + identity + " to attempt this synthetic task."
        )
        assert len(matched) == 1 and matched[0].play_id == identity
        assert catalog.registry.entry(matched[0].rule_id)
    for entry in catalog.registry.entries:
        assert catalog.get(entry.id).rule_id == entry.id
    assert len(catalog.recognize("GM, I declare Sex Play.")) > 1
    assert catalog.recognize("GM, I declare Princess Sex Play.")[0].play_id == "princess_sex"
    assert not catalog.recognize("I will not declare Dive Deep.")
    assert (
        catalog.recognize("GM, I call Keep Your Head to hold steady.")[0].play_id
        == "keep_your_head"
    )
    assert (
        catalog.recognize("GM, I choose Check Sensors to inspect the approach.")[0].play_id
        == "check_sensors"
    )
    assert not catalog.recognize("GM, if I choose Keep Your Head, what happens?")
    assert not catalog.declared("I request water.")
    assert catalog.declared("GM, I declare an unknown training technique.")
    for identity, label in (*BASIC, *EXTRA):
        if identity == "off_duty":
            label = "Handler Go Off-Duty"
        routes = catalog.recognize("GM, I request " + label + ".")
        assert len(routes) == 1 and routes[0].play_id == "handler_" + identity
    assert [x.play_id for x in catalog.recognize("GM, resolve Keep Your Head and spend Heat?")] == [
        "keep_your_head"
    ]
    assert [
        x.play_id for x in catalog.recognize("GM, declare Keep Your Head to endure an attack.")
    ] == ["keep_your_head"]
    assert {x.play_id for x in catalog.recognize("GM, I declare Engage and Keep Your Head.")} == {
        "engage",
        "keep_your_head",
    }


@pytest.mark.parametrize(
    "declaration,expected",
    [
        ("Receive Orders", "receive_orders"),
        ("Dive Deep", "dive_deep"),
        ("Brief Them on the Situation", "handler_brief"),
        ("Nanobot Injection", "nanobot_injection"),
        ("Sex Play", None),
        ("Spin an Imaginary Engine Play", None),
        ("ancillary.soldier.sex-play", "ancillary.soldier.sex-play"),
    ],
)
def test_declarations_persist_replayable_gm_review_without_spending_or_handler_speech(
    routed, declaration, expected
):
    observer, context, scene, game, dice = routed
    conversation = DirectorConversationService(context)
    review = DirectorPlayReviewService(context)
    _, source = send(observer, scene, "declaration", text="GM, I declare " + declaration + ".")
    before = state(game).model_dump_json()
    result = conversation.process_message(PLAYER, "request", scene, source.source_id, 1)
    assert result["handler"] is None
    assert result["gm"]["reply"]["play_id"] == expected
    identity = result["gm"]["play_review_id"]
    assert conversation.process_message(PLAYER, "request", scene, source.source_id, 1) == result
    assert review.view(PLAYER, scene, identity)["status"] == "awaiting_gm_review"
    assert len(review.queue(ADMIN, scene)) == 1
    assert "SYNTHETIC_GM_SECRET_CANARY" in json.dumps(review.gm(ADMIN, scene, identity))
    assert "SYNTHETIC_GM_SECRET_CANARY" not in json.dumps(review.view(PLAYER, scene, identity))
    with pytest.raises(WorkflowError):
        review.gm(PLAYER, scene, identity)
    with pytest.raises(WorkflowError):
        review.view(OTHER, scene, identity)
    assert state(game).model_dump_json() == before and dice.calls == 0


def test_gm_triage_is_private_fresh_and_never_commits_a_native_outcome(routed):
    observer, context, scene, game, dice = routed
    conversation, review = DirectorConversationService(context), DirectorPlayReviewService(context)
    _, source = send(observer, scene, "declaration", text="GM, I declare Dive Deep.")
    result = conversation.process_message(PLAYER, "request", scene, source.source_id, 1)
    identity = result["gm"]["play_review_id"]
    packet = review.gm(ADMIN, scene, identity)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError):
        review.review(
            PLAYER,
            "not-the-gm",
            scene,
            identity,
            packet["fingerprint"],
            "dive_deep",
            "native_workflow",
            "Requester cannot approve its own routing.",
        )
    with pytest.raises(WorkflowError, match="WRONG_REVIEW_PLAY"):
        review.review(
            ADMIN,
            "wrong-play",
            scene,
            identity,
            packet["fingerprint"],
            "keep_your_head",
            "native_workflow",
            "This is not the declared Play.",
        )
    with pytest.raises(WorkflowError, match="UNKNOWN_REVIEW_PLAY"):
        review.review(
            ADMIN,
            "unknown-play",
            scene,
            identity,
            packet["fingerprint"],
            "imaginary_play",
            "native_workflow",
            "Unknown names cannot create native routes.",
        )
    args = (
        ADMIN,
        "triage",
        scene,
        identity,
        packet["fingerprint"],
        "dive_deep",
        "native_workflow",
        "SYNTHETIC_PRIVATE_GM_TRIAGE",
    )
    saved = review.review(*args)
    assert review.review(*args) == saved
    assert review.view(PLAYER, scene, identity)["status"] == "native_workflow"
    assert "SYNTHETIC_PRIVATE_GM_TRIAGE" not in json.dumps(review.view(PLAYER, scene, identity))
    assert "SYNTHETIC_PRIVATE_GM_TRIAGE" not in json.dumps(review.handler_work(ADMIN, scene))
    with game.store.transaction() as c:
        canon = state(game)
        canon.facts.append({"kind": "gm_only", "body": "Changed actual review context."})
        game.event(c, ADMIN.user_id, "change", "synthetic.review_context", canon)
    with pytest.raises(WorkflowError, match="STALE_PLAY_REVIEW"):
        review.review(
            ADMIN,
            "stale",
            scene,
            identity,
            packet["fingerprint"],
            "dive_deep",
            "native_workflow",
            "Obsolete review",
        )
    assert review.view(PLAYER, scene, identity)["status"] == "awaiting_gm_review"
    assert dice.calls == 0
    assert json.loads(before)["revision"] + 1 == state(game).revision


def test_handler_work_uses_original_owner_choices_without_needing_a_chat_referral(routed):
    _, context, scene, game, dice = routed
    _, _, native, _, _ = prepare(
        routed,
        "GM, I declare Check Your Sensors to inspect the hangar.",
        "sensors",
        play="check_sensors",
    )
    review = DirectorPlayReviewService(context)
    work = review.handler_work(ADMIN, scene)
    assert [x["kind"] for x in work["work"]["choices"]] == ["handler_sensors"]
    assert not review.owner_work(OTHER, scene)["choices"]
    assert review.gm_work(ADMIN, scene)["choices"][0]["action_id"] == native
    with pytest.raises(WorkflowError, match="HANDLER_REVIEW_NOT_OWNED"):
        review.handler_work(PLAYER, scene)
    assert "SYNTHETIC_GM_SECRET_CANARY" not in json.dumps(work)
    assert "SYNTHETIC_PC_ONLY_REFERENCE" not in json.dumps(work)
    assert game.inspect(PLAYER, native)["state"] != "complete" and dice.calls == 1


def test_disabled_and_unimplemented_sources_cannot_be_reviewed_into_native_mechanics(routed):
    observer, context, scene, game, dice = routed
    conversation, review = DirectorConversationService(context), DirectorPlayReviewService(context)
    _, source = send(observer, scene, "disabled", text="GM, I declare ancillary.soldier.sex-play.")
    identity = conversation.process_message(PLAYER, "request", scene, source.source_id, 1)["gm"][
        "play_review_id"
    ]
    packet = review.gm(ADMIN, scene, identity)
    assert packet["candidates"][0]["adapter"] == "module_disabled"
    with pytest.raises(WorkflowError, match="BLOCKED_PLAY_ADAPTER"):
        review.review(
            ADMIN,
            "blocked",
            scene,
            identity,
            packet["fingerprint"],
            "ancillary.soldier.sex-play",
            "native_workflow",
            "Cannot create an implementation by reviewing it.",
        )
    assert dice.calls == 0
