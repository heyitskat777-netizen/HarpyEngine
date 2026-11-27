"""Run the real Activity review and delivery against the offline relay scenario."""

import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from test_activity_shadow_readiness import consent, publish_opening, records, review, submission
from test_director_activity_scene import P2Scene, activity_adapter
from test_director_continuity import roles
from test_director_worldbuilding import detail
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state
from test_session_zero import FACILITATOR, OUTSIDE

from girlframe.ai.conversation import HandlerNeedProposal
from girlframe.ai.model_adapters import ModelActivityBatch
from girlframe.ai.model_transport import ModelLimits, OpenAIResponses
from girlframe.engine.campaign_opening import CampaignSeats, PlannedAIPilot
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Faction
from girlframe.engine.pilot_portrayal import PILOT_PORTRAYALS
from girlframe.services.campaign_difficulty import EVENT, opening
from girlframe.services.director_time import scene_time
from girlframe.services.onboarding import WorkflowError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from run_m5_briefing_rehearsal import COMPLETION, PRIVATE, Rehearsal  # noqa: E402

READBACK = (
    "Lark, Kite, got you. I'll note what you both saw. "
    "I can't tell from here whether the relay's running."
)
SECRET = "RELAY_PRIVATE_CANARY: there is a second battery behind the steps."
WAIT = {"kind": "WAIT", "reason": "pilots_have_the_floor"}


class RelayRehearsal(Rehearsal):
    def connect(self):
        super().connect()
        model = OpenAIResponses(
            model="offline-batch",
            api_key="offline-fixture",
            limits=ModelLimits(attempts=20, output_tokens=600),
            post=self.post,
        )
        self.app = P2Scene.model_fixture(
            self.context, model, batch=model, briefing_gateway=self.provider
        )
        self.session = self.app.session

    def join(self, scene, label):
        self.scene = scene
        for actor in (ADMIN, PLAYER, OTHER):
            self.game.join_scene(actor, f"join:{label}:{actor.user_id}", self.scene_channel)
        self.app.write(ADMIN, f"review-policy:{label}", scene, "configure", {"revision": 0})
        for actor in (ADMIN, PLAYER, OTHER):
            consent(self.app, scene, actor)

    def post(self, request, timeout):
        body = json.loads(request.data)
        assert timeout == 20 and body["store"] is False and "tools" not in body
        packet = json.loads(body["input"][1]["content"])["packet"]
        assert SECRET not in json.dumps(packet) and PRIVATE not in json.dumps(packet)
        assert "SYNTHETIC_HANDLER_SECRET" not in json.dumps(packet)
        self.calls.append(packet)
        answer = self.output(packet) if callable(self.output) else self.output
        return json.dumps(
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {"type": "output_text", "text": json.dumps({"decision": answer})}
                        ],
                    }
                ],
            }
        ).encode()

    def readback(self, packet):
        criterion = next(ref for ref in packet["references"] if ref["topic"] == "completion")
        assert (
            criterion["text"] == COMPLETION and criterion["classification"] == "established_world"
        )
        assert [report["classification"] for report in packet["reports"]] == [
            "reported_claim",
            "reported_claim",
        ]
        assert "Name the person first" in packet["character_notes"]["voice"]
        assert all("relay works" not in ref["text"].lower() for ref in packet["references"])
        return {
            "kind": "NPC_DIALOGUE",
            "reason": "shared_report",
            "text": READBACK,
            "source_refs": [criterion["id"]],
            "report_ids": [report["source_id"] for report in packet["reports"]],
            "intended_recipients": [report["speaker"] for report in packet["reports"]],
        }

    def line(self, key, speaker, text, channel="comms", **changes):
        return submission(self.app, self.scene, speaker, key, text, channel=channel, **changes)

    def reports(self, *, prefix="reports"):
        self.line(prefix + ":lark", PLAYER, "Found the charged battery. It's on the shelf now.")
        self.line(prefix + ":kite", OTHER, "Same sight here. Both clips are shut.")

    def run_batch(self, seconds=120):
        self.clock.now += seconds
        result = review(self.app, self.scene)
        return result["model_outcome"] if result else None

    def canon_and_time(self):
        with self.store.engine.connect() as c:
            time = scene_time(c, self.store.campaign_id, self.scene)
        return state(self.game), time

    def approve(self, draft, key="approve-readback"):
        return self.app.write(
            ADMIN,
            key,
            self.scene,
            "handler-approve",
            {
                "draft": draft,
                "reason": "Grounded readback of two reported accounts; relay status is unknown.",
                "recipients": [report["speaker"] for report in self.calls[-1]["reports"]],
            },
        )


@pytest.fixture
def relay(ledger, request):
    variant = getattr(request, "param", "Advocate")
    trial = RelayRehearsal(ledger, "Advocate" if variant in {"unframed", "reviewed"} else variant)
    trial.calls = []
    trial.output = WAIT
    zero, approved = trial.setup(facilitator=ADMIN.user_id if variant == "reviewed" else None)
    trial.dispatch(zero, approved)
    if variant != "unframed":
        publish_opening(trial.app, trial.scene, FACILITATOR)
    return trial


@pytest.mark.parametrize("relay", ["unframed"], indirect=True)
def test_scene_opening_gates_models_after_manual_input_and_stales_running_batch(relay):
    original = relay.canon_and_time()
    relay.line("before-opening", PLAYER, "I'll wait on the stripe.")
    with pytest.raises(WorkflowError, match="SCENE_OPENING_REQUIRED"):
        relay.run_batch()
    assert relay.calls == [] and records(relay.app, relay.scene) == []
    assert relay.app.read(PLAYER, relay.scene, "scene-opening") == {"opening": None}

    preview = relay.app.read(FACILITATOR, relay.scene, "scene-opening")["draft"]
    assert preview["position"]
    payload = {
        "revision": preview["revision"],
        "draft": {"location": "Relay platform", "intro": "The shelf is in sight.", "details": []},
    }
    with pytest.raises(WorkflowError, match="SCENE_OPENING_AUTHORITY"):
        relay.app.write(
            PLAYER, "unauthorized-opening", relay.scene, "scene-opening-publish", payload
        )
    manual = activity_adapter.manual_campaign_setup(relay.game, FACILITATOR.user_id)
    receipt = manual.write(
        FACILITATOR, "frame-scene", relay.scene, "scene-opening-publish", payload
    )
    relay.store.engine.dispose()
    assert (
        relay.app.write(FACILITATOR, "frame-scene", relay.scene, "scene-opening-publish", payload)
        == receipt
    )
    with pytest.raises(WorkflowError, match="STALE_SCENE_OPENING"):
        relay.app.write(FACILITATOR, "stale-editor", relay.scene, "scene-opening-publish", payload)
    with pytest.raises(WorkflowError, match="SCENE_UNAVAILABLE"):
        relay.app.read(OUTSIDE, relay.scene, "scene-opening")
    saved = relay.app.read(PLAYER, relay.scene, "scene-opening")["opening"]
    assert saved["receipt"] == receipt["receipt"]
    assert saved["position"] == preview["position"]

    def reframe(packet):
        assert packet["opening"] == saved
        publish_opening(
            relay.app, relay.scene, FACILITATOR, intro="The crew can talk on the platform."
        )
        return WAIT

    relay.output = reframe
    assert relay.run_batch(0) == {"status": "stale", "reason": "context_changed"}
    relay.output = WAIT
    assert relay.run_batch(0)["status"] == "wait"
    assert relay.calls[-1]["opening"]["intro"] == "The crew can talk on the platform."
    assert relay.canon_and_time() == original


def test_relay_batch_rehearsal(relay):
    start = relay.canon_and_time()
    assert start[1] is not None
    relay.line("private", PLAYER, SECRET, channel="private")
    relay.line("ooc", PLAYER, SECRET, classification="ooc")
    relay.line("gm-whisper", OTHER, f"GM, {SECRET}")
    relay.reports()
    relay.output = lambda packet: (
        relay.readback(packet)
        | {
            "fiction": {"own_action": "I can't tell from here whether the relay's running."},
        }
    )
    assert relay.run_batch(119) is None
    assert not relay.calls
    draft = relay.run_batch(1)
    assert len(relay.calls) == 1 and relay.calls[0]["trigger"] == "quiet"
    _, pilot = roles(relay.app.session.observer, relay.scene)
    assert relay.app.session.dossiers.role_packet(PLAYER, relay.scene, pilot).profile is None
    listeners = {listener["label"] for listener in relay.calls[0]["eligible_listeners"]}
    assert listeners == {"SYNTH", "SYNTH_A"}
    assert draft["status"] == "draft" and draft["reason"] == "shared_report"
    assert relay.canon_and_time() == start
    review_view = relay.app.read(ADMIN, relay.scene, "handler-draft", draft["draft_id"])
    assert review_view["reply"].get("handler_action") is None
    assert review_view["heard_reports"] == [
        {"speaker": "SYNTH", "text": "Found the charged battery. It's on the shelf now."},
        {"speaker": "SYNTH_A", "text": "Same sight here. Both clips are shut."},
    ]
    assert SECRET not in json.dumps(review_view)
    with pytest.raises(WorkflowError, match="administrator"):
        relay.app.read(PLAYER, relay.scene, "handler-draft", draft["draft_id"])
    with pytest.raises(WorkflowError, match="HANDLER_DELIVERY_REVIEW"):
        relay.app.write(
            ADMIN, "unapproved", relay.scene, "handler-deliver", {"draft": draft["draft_id"]}
        )
    with pytest.raises(WorkflowError, match="administrator"):
        relay.app.read(PLAYER, relay.scene, "activity-review")
    original = relay.calls[0]["reports"][-1]
    with pytest.raises(WorkflowError, match="HANDLER_BATCH_ONLY"):
        relay.session.conversation.respond(
            OTHER,
            "parallel-direct-handler",
            relay.scene,
            original["source_id"],
            "handler",
            original["revision"],
        )

    with pytest.raises(WorkflowError, match="HANDLER_BATCH_AUDIENCE"):
        relay.app.write(
            ADMIN,
            "missing-audience",
            relay.scene,
            "handler-approve",
            {"draft": draft["draft_id"], "reason": "Check audience.", "recipients": []},
        )
    approved = relay.approve(draft["draft_id"])
    assert approved["delivery_pending"] and not approved["effects_applied"]
    payload = {"draft": draft["draft_id"]}
    with pytest.raises(WorkflowError):
        relay.app.write(PLAYER, "wrong-delivery-owner", relay.scene, "handler-deliver", payload)
    delivery = relay.app.write(ADMIN, "deliver-readback", relay.scene, "handler-deliver", payload)
    assert not delivery["effects_applied"]
    for listener in (ADMIN, PLAYER, OTHER):
        [heard] = relay.session.conversation.delivery.contributions(listener, relay.scene)
        assert heard["text"] == READBACK and heard["actor"] == relay.calls[0]["handler"]

    relay.store.engine.dispose()
    relay.connect()
    assert relay.run_batch(120) is None
    assert (
        relay.app.write(ADMIN, "deliver-readback-retry", relay.scene, "handler-deliver", payload)
        == delivery
    )
    assert len(relay.calls) == 1 and relay.canon_and_time() == start

    relay.output = WAIT
    relay.line("banter-1", PLAYER, "That's rich, coming from you.")
    relay.line("banter-2", OTHER, "You should have heard me at breakfast.")
    assert relay.run_batch() == {"status": "wait", "reason": "pilots_have_the_floor"}

    relay.output = {"kind": "complete_mission", "success": True}
    relay.line("invalid-mission", PLAYER, "Nothing new on my side.")
    assert relay.run_batch() == {"status": "rejected", "reason": "invalid_model_decision"}

    relay.output = lambda packet: relay.readback(packet) | {"text": "Mission complete."}
    relay.reports(prefix="announce-completion")
    assert relay.run_batch() == {"status": "rejected", "reason": "batch_dialogue_authority"}
    relay.output = lambda packet: relay.readback(packet) | {"text": "You gain 2 Heat."}
    relay.reports(prefix="announce-mechanics")
    assert relay.run_batch() == {"status": "rejected", "reason": "handler_rules_in_dialogue"}

    relay.output = lambda packet: relay.readback(packet) | {"text": "You decide to go inside."}
    relay.reports(prefix="pilot-choice")
    assert relay.run_batch() == {"status": "rejected", "reason": "batch_player_agency"}

    def timeout(_):
        raise TimeoutError(SECRET)

    relay.output = timeout
    relay.line("timeout", PLAYER, "Still on the outside shelf.")
    assert relay.run_batch() == {"status": "failed", "reason": "model_timeout"}
    assert relay.run_batch() is None

    def race(packet):
        relay.line("race-change", PLAYER, "Hold on. The relay is still dark.")
        return relay.readback(packet)

    relay.output = race
    relay.reports(prefix="in-flight")
    assert relay.run_batch() == {"status": "stale", "reason": "context_changed"}
    assert relay.run_batch(119) is None
    relay.output = {"kind": "NEEDS_REVIEW", "reason": "unsupported_outcome"}
    escalation = relay.run_batch(1)
    assert escalation == {
        "status": "escalated",
        "reason": "unsupported_outcome",
        "source": escalation["source"],
    }
    assert escalation["source"]
    assert relay.canon_and_time() == start
    history = records(relay.app, relay.scene)
    assert sum(batch["model_outcome"]["status"] == "draft" for batch in history) == 1
    assert any(batch["model_outcome"]["status"] == "stale" for batch in history)
    assert SECRET not in json.dumps(history) and PRIVATE not in json.dumps(history)
    assert len(relay.calls) == 9


@pytest.mark.parametrize(
    ("lines", "reply", "unknown_citation"),
    [
        (
            (
                "I can help carry the case. Who takes the other end, and where do we hand over?",
                "I'll take the other end. Outside shelf for the handover?",
            ),
            "Yes—the marked outside shelf. Once the battery is there with the clips closed, "
            "I need each of you to report that.",
            False,
        ),
        (
            (
                "I confirm the battery is on the marked outside shelf, clips closed. "
                "I can't confirm the relay is running.",
                "Confirmed: battery on the marked outside shelf, clips closed. "
                "I can't confirm the relay is running either.",
            ),
            "Both of you report the battery on the marked outside shelf, clips closed. "
            "That meets the delivery requirement. "
            "Whether the relay is running remains unconfirmed.",
            False,
        ),
        (
            ("The battery is on the outside shelf.", "I see the clips closed."),
            READBACK,
            True,
        ),
    ],
    ids=("sol-handoff", "sol-relay-readback", "unknown-citation"),
)
def test_shared_readback_separates_reports_from_citations(relay, lines, reply, unknown_citation):
    for actor, line in zip((PLAYER, OTHER), lines, strict=True):
        relay.line(f"readback-incident:{actor.user_id}", actor, line)

    def propose(packet):
        draft = relay.readback(packet)
        citations = draft["report_ids"] + draft["source_refs"]
        if unknown_citation:
            citations[1] = "unscoped-reference"
        return draft | {"text": reply, "source_refs": citations}

    relay.output = propose
    outcome = relay.run_batch()
    if unknown_citation:
        assert outcome == {"status": "rejected", "reason": "handler_citation_invalid"}
        return
    assert outcome["status"] == "draft"
    reviewed = relay.app.read(ADMIN, relay.scene, "handler-draft", outcome["draft_id"])
    assert reviewed["reply"]["text"] == reply
    assert reviewed["reply"]["source_refs"] == [
        next(ref["id"] for ref in relay.calls[0]["references"] if ref["topic"] == "completion")
    ]
    assert {item["text"] for item in reviewed["heard_reports"]} == set(lines)
    assert not relay.session.conversation.delivery.contributions(PLAYER, relay.scene)
    assert not relay.session.conversation.delivery.contributions(OTHER, relay.scene)


def test_named_handler_request_keeps_its_source_and_audience_in_a_batch(relay):
    initial = relay.canon_and_time()
    relay.line("private-name", OTHER, f"Anwen, do you know this? {SECRET}", channel="private")
    relay.line("mentions-name", PLAYER, "Did Anwen leave a note, Kite?")
    relay.line("quoted-name", PLAYER, 'The log says "Wait; Anwen, can you check the reading?"')
    relay.line("names-someone-else", OTHER, "Lark, can you see the stripe?")
    assert relay.run_batch() == {"status": "wait", "reason": "pilots_have_the_floor"}
    assert relay.calls[-1]["response_need"]["reason"] == "no_handler_need"
    assert "response_report_id" not in relay.calls[-1]

    _, question = relay.line(
        "named-question",
        PLAYER,
        "The railing’s loose. Let’s stop; Anwen, can you check whether there’s an approved way "
        "to proceed?",
    )
    _, aside = relay.line("later-aside", OTHER, "Mind the paint on the stripe.")

    def reply(packet):
        assert packet["response_need"]["action"] == "RESPOND"
        assert packet["response_need"]["reason"] == "direct_question"
        assert packet["response_report_id"] == question["source_id"]
        assert [report["source_id"] for report in packet["reports"]] == [
            question["source_id"],
            aside["source_id"],
        ]
        scope = next(ref["id"] for ref in packet["references"] if ref["topic"] == "scope")
        return {
            "kind": "NPC_DIALOGUE",
            "reason": "response_need",
            "text": "Lark, leave the door shut. Use the marked shelf outside.",
            "source_refs": [scope],
            "report_ids": [packet["response_report_id"]],
            "intended_recipients": [packet["reports"][0]["speaker"]],
        }

    relay.output = reply
    assert relay.run_batch(119) is None
    assert len(relay.calls) == 1
    outcome = relay.run_batch(1)
    assert outcome["status"] == "draft"
    draft = outcome["draft_id"]
    preview = relay.app.read(ADMIN, relay.scene, "handler-draft", draft)
    recipient = relay.calls[-1]["reports"][0]["speaker"]
    assert preview["source_actor"] == recipient
    assert "additional_listeners" not in preview
    assert relay.session.conversation.delivery.contributions(PLAYER, relay.scene) == []
    relay.app.write(
        ADMIN,
        "approve-name",
        relay.scene,
        "handler-approve",
        {
            "draft": draft,
            "reason": "Answered the original spoken question.",
            "recipients": [recipient],
        },
    )
    delivery = deliver_handler(relay, draft, "deliver-name")
    assert deliver_handler(relay, draft, "retry-name") == delivery
    [heard] = relay.session.conversation.delivery.contributions(PLAYER, relay.scene)
    assert heard["text"] == "Lark, leave the door shut. Use the marked shelf outside."
    assert relay.session.conversation.delivery.contributions(OTHER, relay.scene) == []
    assert relay.canon_and_time() == initial


@pytest.mark.parametrize("relay", ["reviewed"], indirect=True)
@pytest.mark.parametrize("result", ["generated", "invalid", "interrupted", "revoked"])
def test_handler_drafts_only_an_approved_ai_pilot_portrayal(relay, result):
    scene = relay.scene
    _, pilot = roles(relay.app.session.observer, scene)
    with relay.store.transaction() as c:
        actual = relay.app.session.dossiers._actor(c, scene, pilot)
        record = opening(c, relay.store.campaign_id)
        assert record is not None
        seed = PILOT_PORTRAYALS[0].model_copy(
            update={"girl_playbook": actual.girl, "frame_playbook": actual.frame}
        )
        planned = PlannedAIPilot(
            callsign="LANTERN", concept="Checks the winter relay.", portrayal=seed
        )
        record = record.model_copy(
            update={"seats": CampaignSeats(player_count=2, ai_pilots=(planned,))}
        )
        relay.store._audit(
            c, ADMIN.user_id, "approved-ai-seat", EVENT, record.model_dump(mode="json")
        )
    body = {
        "actor": pilot.model_dump(mode="json"),
        "origin": {"plan": record.plan, "callsign": planned.callsign},
        "version": 0,
    }
    route = "pilot-dossier-propose"
    retries = []
    portrayal = {
        "voice": "Name a check before asking a question.",
        "approach": "Look for an isolated pilot before requesting a roll call.",
        "pressure": "Keep counting people while others count equipment.",
        "repair": "Ask the person she overlooked to run the next roll call.",
        "value": "A watch is only as good as its handover.",
        "fear": "Answering for someone who never made it back.",
        "contradiction": "She wants a partner and always claims the night watch alone.",
        "goal": "Let a peer run one check without supervising it.",
        "initiative": "Speak up when a report skips over the quietest pilot.",
    }

    def post(request, _timeout):
        outgoing = json.loads(request.data)
        assert outgoing["model"] == "offline-handler" and outgoing["store"] is False
        data = json.loads(outgoing["input"][1]["content"])
        assert data["contract"]["title"] == "AIPilotPortrayalDraft"
        assert data["packet"]["pilot"] == planned.model_dump(mode="json")
        assert set(data["packet"]) == {"pilot", "playbook_guidance"}
        assert all(data["packet"]["playbook_guidance"][field] for field in ("girl", "frame"))
        for key in ("file-ai-dossier", "parallel-click"):
            receipt = app.write(PLAYER, key, scene, route, body)
            assert receipt["portrayal_status"] == "preparing"
            retries.append(receipt["id"])
        with pytest.raises(WorkflowError, match="DOSSIER_PROPOSAL_UNAVAILABLE"):
            app.read(PLAYER, scene, "dossier-review", retries[0])
        if result == "revoked":
            consent(app, scene, OTHER, revision=policy + 1, value=False)
        if result == "interrupted":
            raise RuntimeError("offline host stopped")
        # An invalid response tries to change the approved Girl playbook.
        answer = portrayal | ({"girl_playbook": "PRINCESS"} if result == "invalid" else {})
        return json.dumps({
            "status": "completed",
            "output": [{
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": json.dumps(answer)}],
            }],
        }).encode()

    model = OpenAIResponses(
        model="offline-handler",
        api_key="offline",
        limits=ModelLimits(attempts=2, output_tokens=700),
        post=post,
    )

    def connect():
        return P2Scene.reviewed_activity(
            relay.game,
            facilitator_id=ADMIN.user_id,
            opening_channel=relay.scene_channel,
            handler_batch=ModelActivityBatch(model),
        )

    app = connect()
    with pytest.raises(WorkflowError, match="OBSERVATION_DISABLED"):
        app.write(PLAYER, "disabled", scene, route, body)
    policy = app.read(ADMIN, scene, "status")["policy_revision"]
    app.write(
        ADMIN, "enable-for-draft", scene, "activity-policy-save", {"enabled": True, "revision": 0}
    )
    app.write(ADMIN, "notice-for-draft", scene, "configure", {"revision": policy})
    for viewer in (ADMIN, PLAYER):
        consent(app, scene, viewer, revision=policy + 1)
    with pytest.raises(WorkflowError, match="OBSERVATION_DISABLED"):
        app.write(PLAYER, "no-consent", scene, route, body)
    consent(app, scene, OTHER, revision=policy + 1)
    with pytest.raises(WorkflowError, match="PILOT_DOSSIER_OWNER"):
        app.write(ADMIN, "not-owner", scene, route, body)
    assert model.status()["attempts"] == 0
    baseline = state(relay.game)
    if result == "revoked":
        with pytest.raises(WorkflowError, match="OBSERVATION_DISABLED"):
            app.write(PLAYER, "file-ai-dossier", scene, route, body)
        consent(app, scene, OTHER, revision=policy + 1, key="restore-draft-consent")
        with pytest.raises(WorkflowError, match="STALE_DOSSIER"):
            app.write(PLAYER, "file-ai-dossier", scene, route, body)
        assert not app.read(PLAYER, scene, "work")["dossiers"]
        assert model.status()["attempts"] == 1
        assert state(relay.game) == baseline
        return
    if result == "interrupted":
        with pytest.raises(RuntimeError, match="offline host stopped"):
            app.write(PLAYER, "file-ai-dossier", scene, route, body)
        relay.clock.now += 121
    else:
        initial = app.write(PLAYER, "file-ai-dossier", scene, route, body)
        assert initial["id"] == retries[0]
    relay.store.engine.dispose()
    app = connect()
    receipt = app.write(PLAYER, "file-ai-dossier", scene, route, body)
    assert receipt["id"] == retries[0] == retries[1]
    assert app.write(PLAYER, "new-click-after-reopen", scene, route, body) == receipt
    assert model.status()["attempts"] == 1
    source = "handler" if result == "generated" else "approved_plan"
    assert receipt["portrayal_status"] == source
    with pytest.raises(WorkflowError, match="DOSSIER_NOT_OWNED"):
        app.read(ADMIN, scene, "dossier-review", receipt["id"])
    dossier = app.read(PLAYER, scene, "dossier-review", receipt["id"])
    assert dossier["portrayal_source"] == source
    expected = seed.model_copy(update=portrayal) if result == "generated" else seed
    assert dossier["profile"]["pilot_portrayal"] == expected.model_dump(mode="json")
    assert state(relay.game) == baseline
    decision = {"id": receipt["id"]}
    with pytest.raises(WorkflowError, match="DOSSIER_NOT_OWNED"):
        app.write(ADMIN, "cannot-confirm", scene, "dossier-confirm", decision)
    approved = app.write(PLAYER, "confirm-ai-dossier", scene, "dossier-confirm", decision)
    assert approved["effects_applied"] is False
    with relay.store.engine.connect() as c:
        assert app.session.dossiers.activity_pilots(c, scene)[pilot] == (actual.label, expected)


@pytest.mark.parametrize("relay", ["reviewed"], indirect=True)
def test_reviewed_activity_trial_has_fresh_opt_in_and_owner_scoped_play(relay):
    model = OpenAIResponses(
        model="offline-reviewed-trial",
        api_key="offline-fixture",
        limits=ModelLimits(attempts=4, output_tokens=600),
        post=relay.post,
    )
    app = P2Scene.reviewed_activity(
        relay.game,
        facilitator_id=ADMIN.user_id,
        opening_channel=relay.scene_channel,
        handler_batch=ModelActivityBatch(model),
    )
    assert relay.scene in [item["id"] for item in app.trial_scenes(PLAYER)["scenes"]]
    assert app.trial_scenes(OUTSIDE) == {"scenes": []}
    assert app.read(ADMIN, relay.scene, "activity-policy") == {"enabled": False, "revision": 0}
    with pytest.raises(WorkflowError, match="AI assistance is off for this campaign"):
        review(app, relay.scene)
    revision = app.read(ADMIN, relay.scene, "status")["policy_revision"]
    app.write(
        ADMIN,
        "live-campaign-opt-in",
        relay.scene,
        "activity-policy-save",
        {
            "enabled": True,
            "revision": 0,
        },
    )
    app.write(ADMIN, "publish-live-notice", relay.scene, "configure", {"revision": revision})
    for actor in (ADMIN, PLAYER):
        consent(app, relay.scene, actor, revision=revision + 1)
    assert not app.read(PLAYER, relay.scene, "status")["consented"]
    with pytest.raises(WorkflowError, match="OBSERVATION_DISABLED"):
        submission(app, relay.scene, PLAYER, "no-consent", "Can you hear me?")
    consent(app, relay.scene, OTHER, revision=revision + 1)
    submission(app, relay.scene, OTHER, "private-line", SECRET, channel="private")
    _, question = submission(
        app,
        relay.scene,
        PLAYER,
        "brief-line",
        "Anwen, what's the cleared route?",
    )

    def propose(packet):
        opportunity = next(item for item in packet["play_opportunities"] if item["play"] == "brief")
        assert opportunity["report_id"] == question["source_id"]
        assert opportunity["source_refs"]
        return {
            "kind": "NPC_DIALOGUE",
            "reason": "response_need",
            "text": "Leave the door shut. Use the marked shelf outside.",
            "source_refs": opportunity["source_refs"],
            "report_ids": [question["source_id"]],
            "intended_recipients": [packet["reports"][0]["speaker"]],
            "play_offer": "brief",
        }

    relay.output = propose
    relay.clock.now += 119
    assert review(app, relay.scene) is None and not relay.calls
    relay.clock.now += 1
    with pytest.raises(WorkflowError):
        app.write(OTHER, "wrong-review", relay.scene, "activity-review-run", {})
    original = relay.canon_and_time()
    result = review(app, relay.scene)["model_outcome"]
    assert result["status"] == "draft"
    assert review(app, relay.scene) is None and len(relay.calls) == 1
    private = app.read(ADMIN, relay.scene, "handler-draft", result["draft_id"])
    assert private["reply"]["handler_play_offer"] == "brief"
    with pytest.raises(WorkflowError):
        app.read(OTHER, relay.scene, "handler-draft", result["draft_id"])
    receipt = app.write(
        ADMIN,
        "approve-scoped-brief",
        relay.scene,
        "handler-approve",
        {
            "draft": result["draft_id"],
            "reason": "Grounded route for the original listener.",
            "recipients": [private["source_actor"]],
        },
    )
    assert receipt["handler_play_offer"] == "brief" and not receipt.get("delivery_pending")
    assert relay.canon_and_time() == original
    assert SECRET not in json.dumps(app.read(PLAYER, relay.scene, "timeline"))
    assert app.read(PLAYER, relay.scene, "timeline")["entries"][-1]["own_input"]
    consent(app, relay.scene, PLAYER, revision=revision + 1, value=False)
    with pytest.raises(WorkflowError, match="OBSERVATION_DISABLED"):
        app.read(PLAYER, relay.scene, "timeline")
    with pytest.raises(WorkflowError):
        app.write(
            ADMIN,
            "start-after-withdrawal",
            relay.scene,
            "handler-start-play",
            {
                "draft": result["draft_id"],
                "play": "brief",
                "game_revision": state(relay.game).revision,
            },
        )
    assert len(relay.calls) == 1 and relay.canon_and_time() == original


def test_native_play_coalesces_with_pending_dialogue(relay):
    relay.line("play-turn", PLAYER, "The battery case is rattling.")
    relay.line("play-banter", OTHER, "I can steady it from this side.")
    with relay.store.engine.connect() as c:
        revision = relay.observer._state(c, relay.scene).policy_revision
    assert revision == 1
    action = relay.game.begin(
        PLAYER,
        str(uuid4()),
        relay.scene_channel,
        state(relay.game).sheets["2"].revision,
        PlayInput(play="keep_your_head", context="Steady the case", trigger_confirmed=True, heat=0),
    )["action_id"]
    relay.tick()
    pass_tags(relay.game)
    answer(relay.game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(relay.game, ADMIN, "handler_keep", flag=True, text="SYNTHETIC_HANDLER_SECRET")
    baseline = relay.canon_and_time()
    assert relay.run_batch(0) == {"status": "wait", "reason": "pilots_have_the_floor"}
    [packet] = relay.calls
    assert packet["has_completed_play"] and packet["trigger"] == "completed_play"
    [record] = records(relay.app, relay.scene)
    assert record["items"][-1]["action"] == action
    assert record["items"][-1]["disposition"] == "assigned_to_human_gm"
    assert relay.run_batch() is None and relay.canon_and_time() == baseline


def test_revoked_consent_blocks_model_and_delivery(relay):
    relay.reports()
    relay.output = relay.readback
    consent(relay.app, relay.scene, PLAYER, value=False)
    with pytest.raises(WorkflowError, match="OBSERVATION_DISABLED"):
        relay.run_batch()
    assert not relay.calls
    consent(relay.app, relay.scene, PLAYER, key="consent-renewed")
    relay.reports(prefix="after-consent")
    draft = relay.run_batch()
    relay.approve(draft["draft_id"])
    consent(relay.app, relay.scene, PLAYER, value=False, key="consent-revoked-again")
    with pytest.raises(WorkflowError, match="(?i)(consent|disabled)"):
        relay.app.write(
            ADMIN, "revoked-delivery", relay.scene, "handler-deliver", {"draft": draft["draft_id"]}
        )
    with pytest.raises(WorkflowError, match="OBSERVATION_DISABLED"):
        records(relay.app, relay.scene)


def test_correction_to_other_report_invalidates_approved_batch(relay):
    relay.reports()
    relay.output = relay.readback
    draft = relay.run_batch()
    relay.approve(draft["draft_id"])
    report = relay.calls[-1]["reports"][0]
    relay.line(
        "revise-earlier-report",
        PLAYER,
        "Correction, I'm still holding it.",
        source_id=report["source_id"],
        expected_source_revision=report["revision"],
    )
    assert relay.app.read(ADMIN, relay.scene, "handler-draft", draft["draft_id"]) == {
        "id": draft["draft_id"],
        "status": "stale_reopen_source",
        "effects_applied": False,
    }
    with pytest.raises(WorkflowError, match="STALE_HANDLER_DRAFT|HANDLER_DELIVERY_HEARING"):
        relay.app.write(
            ADMIN, "stale-delivery", relay.scene, "handler-deliver", {"draft": draft["draft_id"]}
        )
    assert not relay.session.conversation.delivery.contributions(PLAYER, relay.scene)


def test_facilitator_world_proposal_stays_unapplied(relay):
    world = relay.session.worldbuilding
    canon = state(relay.game)
    approval = relay.store.policy.m3_approval
    assert approval is not None
    relay.store.policy = relay.store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    world.world.faction(
        ADMIN,
        "fixture-maintenance",
        canon.revision,
        Faction(id="maintenance", name="Maintenance", kind="political", cells=()),
    )
    relay.line("world-turn", PLAYER, "I wonder whether maintenance visits here.")
    baseline = relay.canon_and_time()
    relay.output = lambda packet: {
        "kind": "WORLD_EVENT_PROPOSAL",
        "action": detail(subject={"kind": "faction", "id": "maintenance"}).model_dump(mode="json"),
        "source_refs": [packet["references"][0]["id"]],
    }
    outcome = relay.run_batch()
    assert outcome["status"] == "world_review"
    assert (
        world.private(ADMIN, relay.scene, outcome["proposal_id"])["status"] == "awaiting_gm_review"
    )
    assert relay.canon_and_time() == baseline

    identity = outcome["proposal_id"]
    world.review(ADMIN, "shared-world-review", relay.scene, identity, "approve", "Set the scene.")
    committed = world.confirm(ADMIN, "shared-world-confirm", relay.scene, identity)
    [lark] = [report["speaker"] for report in relay.calls[-1]["reports"]]
    actor = relay.calls[-1]["handler"]
    lark, handler = ActorRef.model_validate(lark), ActorRef.model_validate(actor)
    world.disclose(
        ADMIN, "private-tag", relay.scene, committed["id"], "red inspection tag", (lark,)
    )
    world.disclose(
        ADMIN,
        "shared-panel",
        relay.scene,
        committed["id"],
        "beside the service panel",
        (lark, handler),
    )
    relay.line("panel-turn", PLAYER, "I'll stand over here.")
    relay.output = WAIT
    assert relay.run_batch()["status"] == "wait"
    packet = relay.calls[-1]
    assert [ref["text"] for ref in packet["scene_details"]] == [
        "Established world: beside the service panel"
    ]
    assert "red inspection tag" not in json.dumps(packet)
    assert relay.app.read(FACILITATOR, relay.scene, "scene-opening")["draft"]["suggestions"] == []
    with relay.store.engine.connect() as c:
        row = relay.context.observations._scene(c, relay.scene)
        everyone = relay.app.shadow.knowledge._actors(c, row)
    shared = world.disclose(
        ADMIN, "all-see-panel", relay.scene, committed["id"], "beside the service panel", everyone
    )
    [identity] = shared["reference_ids"]
    preview = relay.app.read(FACILITATOR, relay.scene, "scene-opening")["draft"]
    assert preview["suggestions"] == [{"id": identity, "text": "beside the service panel"}]
    relay.app.write(
        FACILITATOR,
        "share-panel-opening",
        relay.scene,
        "scene-opening-publish",
        {
            "revision": preview["revision"],
            "draft": {"location": "Relay", "intro": "", "details": [identity]},
        },
    )
    [shared_detail] = relay.app.read(OTHER, relay.scene, "scene-opening")["opening"]["details"]
    assert shared_detail == preview["suggestions"][0]


def handler_batch_line(
    packet, reason, text, *, fiction=None, cue=None, shared=False, report_id=None
):
    reports = (
        [report for report in packet["reports"] if report["source_id"] == report_id]
        if report_id is not None
        else packet["reports"][-(2 if shared else 1) :]
    )
    return {
        "kind": "NPC_DIALOGUE",
        "reason": reason,
        "text": text,
        "source_refs": [],
        "report_ids": [report["source_id"] for report in reports],
        "intended_recipients": [report["speaker"] for report in reports],
        **({"cue": cue} if cue else {}),
        **({"fiction": fiction} if fiction else {}),
    }


def deliver_handler(relay, draft, key):
    return relay.app.write(ADMIN, key, relay.scene, "handler-deliver", {"draft": draft})


@pytest.mark.parametrize("keep_reference", [True, False])
def test_reviewed_cue_survives_later_unrelated_pilot_turn(relay, keep_reference):
    line = "The clerk looked at my empty line and read out what she figured I'd say."
    _, source = relay.line("paraphrased-cue", PLAYER, line)
    relay.line("other-pilot", OTHER, "I'm still by the window.")
    svc = relay.session.conversation
    opened = relay.app.write(
        ADMIN,
        "open-paraphrase",
        relay.scene,
        "handler-need-open",
        {"source_id": source["source_id"]},
    )
    packet = svc.handler_need_packet(ADMIN, relay.scene, opened["id"])
    scope = next(x.id for x in packet.request.context.references if x.topic == "scope")
    proposal = svc.propose_handler_need(
        ADMIN,
        "propose-paraphrase",
        relay.scene,
        opened["id"],
        HandlerNeedProposal(
            request_id=opened["id"],
            action="RESPOND",
            kind="character_cue",
            cue="agency",
            speech_quote=line,
            source_refs=(scope,),
            reason="The clerk took over the Pilot's account.",
        ),
    )
    draft = relay.app.read(ADMIN, relay.scene, "handler-need", proposal["id"])
    assert draft["status"] == "awaiting_gm_review"
    with pytest.raises(WorkflowError):
        relay.app.read(OTHER, relay.scene, "handler-need", proposal["id"])
    relay.app.write(
        ADMIN,
        "review-paraphrase",
        relay.scene,
        "handler-need-review",
        {"proposal": proposal["id"], "decision": "approve", "reason": "Heard directly."},
    )
    speech = "If you want to give your own account, I'll make room."

    def respond(packet):
        if packet["response_need"]["reason"] != "reviewed_character_cue":
            return WAIT
        assert packet["response_report_id"] == source["source_id"]
        response = handler_batch_line(
            packet, "character_cue", speech, cue="agency", report_id=source["source_id"]
        )
        return response | {"source_refs": [scope] if keep_reference else []}

    before = relay.canon_and_time()
    relay.output = respond
    draft = relay.run_batch()
    if not keep_reference:
        assert draft == {"status": "rejected", "reason": "handler_required_reference"}
        assert relay.canon_and_time() == before
        return
    assert draft["status"] == "draft"
    reports = relay.calls[-1]["reports"]
    [speaker] = [item["speaker"] for item in reports if item["source_id"] == source["source_id"]]
    payload = {"draft": draft["draft_id"], "reason": "Confirm the original listener."}
    with pytest.raises(WorkflowError, match="HANDLER_BATCH_AUDIENCE"):
        relay.app.write(
            ADMIN,
            "wrong-listener-paraphrase",
            relay.scene,
            "handler-approve",
            payload | {"recipients": [item["speaker"] for item in reports]},
        )
    relay.app.write(
        ADMIN,
        "approve-paraphrase",
        relay.scene,
        "handler-approve",
        payload | {"recipients": [speaker]},
    )
    receipt = deliver_handler(relay, draft["draft_id"], "deliver-paraphrase")
    assert deliver_handler(relay, draft["draft_id"], "retry-paraphrase") == receipt
    assert speech in json.dumps(relay.app.timeline(PLAYER, relay.scene))
    assert speech not in json.dumps(relay.app.timeline(OTHER, relay.scene))
    assert relay.run_batch(0) is None and relay.canon_and_time() == before


def test_activity_update_is_acknowledged_by_delivery_to_its_actual_listener(relay):
    _, report = relay.line(
        "fresh-update", PLAYER, "Maintenance says the new gloves are on the peg."
    )
    relay.line("focus", PLAYER, "I'll put the old pair away.")
    with relay.store.engine.connect() as c:
        actors = relay.app.shadow.knowledge._actors(
            c, relay.context.observations._scene(c, relay.scene)
        )
        order = len(relay.context._references(c, relay.scene))
    ref = relay.context.record(
        ADMIN,
        "save-update",
        relay.scene,
        report["source_id"],
        order,
        known_by=tuple(actors),
        topic="debrief",
    )["id"]
    baseline = relay.canon_and_time()

    def acknowledge(packet):
        assert packet["response_need"]["reason"] == "known_update"
        assert packet["response_need"]["source_refs"] == [ref]
        return handler_batch_line(packet, "response_need", "Lark, I heard about the gloves.") | {
            "source_refs": [ref]
        }

    relay.output = acknowledge
    draft = relay.run_batch()["draft_id"]
    preview = relay.app.read(ADMIN, relay.scene, "handler-draft", draft)
    relay.app.write(
        ADMIN,
        "approve-update",
        relay.scene,
        "handler-approve",
        {"draft": draft, "reason": "Scoped readback.", "recipients": [preview["source_actor"]]},
    )
    conversation = relay.session.conversation
    with relay.store.engine.connect() as c:
        role = relay.context._handler_for_request(c, ADMIN, relay.scene)
        lark = next(actor for actor in actors if actor.entity == str(PLAYER.user_id))
        assert conversation.delivery.acknowledged_updates(c, role, lark) == ()
    receipt = deliver_handler(relay, draft, "deliver-update")
    relay.store.engine.dispose()
    assert deliver_handler(relay, draft, "retry-update") == receipt

    relay.output = WAIT
    relay.line("lark-later", PLAYER, "Mine are dry.")
    assert relay.run_batch()["status"] == "wait"
    assert relay.calls[-1]["response_need"]["reason"] == "update_already_addressed"
    relay.line("kite-later", OTHER, "I'll fetch the bucket.")
    assert relay.run_batch()["status"] == "wait"
    assert relay.calls[-1]["response_need"]["reason"] == "known_update"
    assert relay.calls[-1]["response_need"]["source_refs"] == [ref]
    relay.line("lark-question", PLAYER, "Handler, can you remind me what maintenance said?")
    assert relay.run_batch()["status"] == "wait"
    assert relay.calls[-1]["response_need"]["reason"] == "direct_question"
    assert relay.canon_and_time() == baseline


@pytest.mark.parametrize("relay", ["Advocate", "Frantic"], indirect=True)
def test_handler_capacity_cue_matches_playbook_and_follows_through(relay):
    before = relay.canon_and_time()

    def capacity(packet):
        assert not packet["recent_contributions"]
        return handler_batch_line(
            packet,
            "character_cue",
            "I can take the count, if you'd like.",
            cue="capacity",
            fiction={"own_action": "I set my clipboard down.", "offers_help": True},
        )

    relay.output = capacity
    relay.line("overloaded", PLAYER, "I can watch the stripe or keep my grip. I can't do both.")
    proposed = relay.run_batch()
    if relay.playbook == "Advocate":
        assert proposed == {"status": "rejected", "reason": "batch_cue_invalid"}
        relay.output = WAIT
        relay.line("covered", OTHER, "We can put it down before the turn.")
        assert relay.run_batch() == {"status": "wait", "reason": "pilots_have_the_floor"}
        relay.line("alarm-afterward", PLAYER, "That alarm's still in my ears.")
        relay.output = lambda packet: handler_batch_line(
            packet,
            "character_cue",
            "I can sit with you a minute, if you want.",
            cue="personal",
            fiction={"own_action": "I turn my own recorder over."},
        )
        quiet = relay.run_batch()["draft_id"]
        relay.approve(quiet, key="approve-company")
        deliver_handler(relay, quiet, "deliver-company")
        assert relay.app.timeline(PLAYER, relay.scene)["entries"][-1]["action"] == (
            "I turn my own recorder over."
        )
        assert relay.canon_and_time() == before
        return

    draft = proposed["draft_id"]
    relay.approve(draft, key="approve-support")
    offer = deliver_handler(relay, draft, "deliver-support")
    own = relay.app.timeline(PLAYER, relay.scene)["entries"][-1]
    assert own["action"] == "I set my clipboard down."
    assert not any(
        "take the count" in row["text"] for row in relay.app.timeline(OTHER, relay.scene)["entries"]
    )

    relay.line("not-a-listener", OTHER, "I have my own count.")
    relay.output = lambda packet: handler_batch_line(
        packet,
        "follow_through",
        "I'll leave that to you.",
        fiction={"follows_offer": offer["reference"]},
    )
    assert relay.run_batch() == {"status": "rejected", "reason": "fiction_offer_unavailable"}

    def handoff(packet):
        assert packet["recent_contributions"][-1]["open_offer"] is True
        return handler_batch_line(
            packet,
            "follow_through",
            "All right. Kite has the count. I'll keep the line clear.",
            fiction={"follows_offer": offer["reference"]},
        )

    _, quiet_turn = relay.line(
        "request-space",
        PLAYER,
        "Thanks. Kite and I have it here. Stay off the count line, please.",
    )
    relay.line("after-space", OTHER, "Ready from my end.")
    relay.output = handoff
    calls = len(relay.calls)
    assert relay.run_batch() == {"status": "wait", "reason": "pilot_requested_space"}
    assert len(relay.calls) == calls
    quiet_review = next(
        item
        for batch in records(relay.app, relay.scene)
        for item in batch["items"]
        if item["source"] == quiet_turn["source_id"]
    )
    assert quiet_review["decision"]["reason"] == "pilot_requested_space"
    assert len(relay.session.conversation.delivery.contributions(PLAYER, relay.scene)) == 1

    relay.line("decline-count", PLAYER, "No, Kite can count from her end. Please hold the line.")
    follow = relay.run_batch()["draft_id"]
    relay.approve(follow, key="approve-handoff")
    deliver_handler(relay, follow, "deliver-handoff")

    def wait_after_handoff(packet):
        assert not next(
            item
            for item in packet["recent_contributions"]
            if item["reference"] == offer["reference"]
        )["open_offer"]
        return WAIT

    relay.line("private-space", OTHER, "Anwen, please keep the channel clear.", channel="private")
    relay.line("back-on-task", PLAYER, "Kite, please keep the channel clear.")
    relay.output = wait_after_handoff
    assert relay.run_batch() == {"status": "wait", "reason": "pilots_have_the_floor"}
    assert relay.canon_and_time() == before


def test_handler_answers_two_questions_once_for_the_shared_listeners(relay):
    relay.output = lambda packet: handler_batch_line(
        packet,
        "response_need",
        "The shelf outside the sealed door. Use the marked stripe.",
        shared=len(packet["reports"]) == 2,
    )
    relay.line("lark-question", PLAYER, "Handler, can you confirm which shelf?")
    relay.line("kite-question", OTHER, "Handler, can you repeat where the case goes?")
    draft = relay.run_batch()["draft_id"]
    review_data = relay.app.read(ADMIN, relay.scene, "handler-draft", draft)
    actors = [report["speaker"] for report in relay.calls[-1]["reports"]]
    assert [listener["actor"] for listener in review_data["intended_listeners"]] == actors
    with pytest.raises(WorkflowError, match="HANDLER_BATCH_AUDIENCE"):
        relay.app.write(
            ADMIN,
            "shrink-shared",
            relay.scene,
            "handler-approve",
            {"draft": draft, "reason": "Only the focus Pilot.", "recipients": actors[-1:]},
        )
    relay.approve(draft, key="approve-shared")
    deliver_handler(relay, draft, "deliver-shared")

    relay.line("repeat-question", PLAYER, "Handler, can you confirm which shelf?")
    repeated = relay.run_batch()["draft_id"]
    with pytest.raises(WorkflowError, match="FICTION_ALREADY_SAID"):
        relay.approve(repeated, key="approve-repeat")
    for viewer in (PLAYER, OTHER):
        assert (
            len(
                [
                    row
                    for row in relay.app.timeline(viewer, relay.scene)["entries"]
                    if row["kind"] == "handler"
                ]
            )
            == 1
        )


def test_closeout_binds_a_handler_commitment_to_the_actual_pilot_reply(relay):
    cost = "Let the spare-parts question stand until relief arrives."
    relay.output = lambda packet: (
        handler_batch_line(
            packet,
            "character_cue",
            "Would you like me to carry both lines to the desk?",
            cue="agency",
            fiction={"offers_help": True},
        )
        | {"tradeoff": {"accepted_cost": cost, "next_move": "Offer to carry the two-line report."}}
    )
    relay.line(
        "one-box",
        PLAYER,
        "The report has one box. Delivery is confirmed but the relay is not verified.",
    )
    draft = relay.run_batch()["draft_id"]
    saved = relay.app.read(ADMIN, relay.scene, "handler-draft", draft)
    assert not any(private in json.dumps(saved) for private in (cost, "tradeoff"))
    relay.approve(draft)
    offer = deliver_handler(relay, draft, "deliver-form-offer")["reference"]
    with relay.store.engine.connect() as connection:
        roles = {
            role.controller: role.ref
            for role in relay.session.knowledge._actor_views(
                connection, relay.observer._scene(connection, relay.scene)
            )
        }
    reports = []
    for index, (speaker, text) in enumerate(
        (
            (OTHER, "Go ahead and take Lark's form."),
            (PLAYER, "Please take the form to the desk with both lines intact."),
        )
    ):
        _, source = relay.line(f"choice:{index}", speaker, text)
        with relay.store.engine.connect() as connection:
            order = len(relay.context._references(connection, relay.scene))
        ref = relay.context.record(
            ADMIN,
            f"choice-reference:{index}",
            relay.scene,
            source["source_id"],
            order,
            known_by=tuple(roles.values()),
            topic="debrief",
        )
        reports.append(ref["id"])

    view = relay.app.read(ADMIN, relay.scene, "closeout")
    assert view["offers"] == [
        {
            "reference": offer,
            "text": "Would you like me to carry both lines to the desk?",
        }
    ]
    payload = {
        "revision": view["revision"],
        "reports": reports,
        "experience": {
            "kind": "accepted_help",
            "reference_id": reports[0],
            "offer_reference": offer,
        },
    }
    with pytest.raises(WorkflowError, match="HANDLER_COMMITMENT_OFFER"):
        relay.app.write(ADMIN, "wrong-pilot-acceptance", relay.scene, "close", payload)
    payload["experience"]["reference_id"] = reports[1]
    receipt = relay.app.write(ADMIN, "close-authorized-choice", relay.scene, "close", payload)
    assert receipt["handler_experience_saved"]
    relay.store.engine.dispose()
    assert (
        relay.app.write(ADMIN, "close-authorized-choice", relay.scene, "close", payload) == receipt
    )


@pytest.mark.parametrize("relay", ["Mistress"], indirect=True)
def test_mistress_signature_reviews_actual_order_and_keeps_the_original_rewards(relay):
    def owned(viewer, kind):
        return next(
            x
            for x in relay.app.read(viewer, relay.scene, "handler-native-work")["signatures"][
                "choices"
            ]
            if x["kind"] == kind
        )

    def respond(viewer, choice, key, **reply):
        return relay.app.write(
            viewer,
            key,
            relay.scene,
            "handler-native",
            {
                "action": "signature-response",
                "id": choice["id"],
                "revision": choice["revision"],
                "answer": reply,
            },
        )

    relay.line("heard-before-hesitation", OTHER, "I'm standing at the cabinet.")
    relay.game.issue_order(
        ADMIN, "hesitant-order", relay.scene_channel, OTHER.user_id, "Check the cabinet."
    )
    relay.tick()
    answer(relay.game, OTHER, "order_response", options=("hesitant",))
    relay.tick()

    def flag(packet):
        assert packet.get("native_signatures", []) == []
        return {"kind": "REVIEW_HANDLER_SIGNATURE", "play": "catch_more_flies_with_honey"}

    relay.output = flag
    assert relay.run_batch() == {"status": "rejected", "reason": "handler_play_trigger"}
    relay.line("heard-before-obedience", OTHER, "I'm still at the cabinet.")
    opened = relay.game.issue_order(
        ADMIN, "immediate-order", relay.scene_channel, OTHER.user_id, "Check the cabinet now."
    )
    relay.tick()
    answer(relay.game, OTHER, "order_response", options=("immediate",))
    offer = owned(ADMIN, "mistress_honey_offer")

    def valid_flag(packet):
        [signature] = packet["native_signatures"]
        assert signature["play"] == "catch_more_flies_with_honey"
        assert "control" not in signature and "destination" not in signature
        return {"kind": "REVIEW_HANDLER_SIGNATURE", "play": signature["play"]}

    original = relay.canon_and_time()
    relay.output = valid_flag
    assert relay.run_batch() == {
        "status": "native_signature",
        "reason": "owned_native_work",
        "play": "catch_more_flies_with_honey",
        "control": offer["id"],
        "destination": "signature_choice",
        "target": str(OTHER.user_id),
    }
    assert relay.canon_and_time() == original
    with pytest.raises(WorkflowError):
        respond(PLAYER, offer, "not-my-choice", options=["raise_status"])
    respond(
        ADMIN,
        offer,
        "offer-private-name",
        options=["pet_name"],
        fields={"pet_name": "PRIVATE_NAME", "tag": "PRIVATE_REWARD"},
    )
    reward = owned(OTHER, "mistress_honey_reply")
    assert reward["reward"]["account"] == "PRIVATE_NAME"
    assert "PRIVATE_NAME" not in str(relay.app.read(PLAYER, relay.scene, "handler-native-work"))
    relay.store.engine.dispose()
    accepted = respond(OTHER, reward, "accept-private-name", flag=True)
    assert respond(OTHER, reward, "accept-private-name", flag=True) == accepted
    tags = [
        x for x in state(relay.game).sheets[str(OTHER.user_id)].tags if x.label == "PRIVATE_REWARD"
    ]
    assert len(tags) == 1 and set(tags[0].observers) == {ADMIN.user_id, OTHER.user_id}
    assert relay.game.inspect(OTHER, opened["action_id"])["state"] == "complete"
