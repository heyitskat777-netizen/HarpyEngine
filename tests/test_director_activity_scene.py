"""Engine-backed Activity routes over parallel native scenes and native Plays."""

import json
import os
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest
import sqlalchemy as sa
from test_director_continuity import carry, roles
from test_director_observation import observed as observed
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, start, tick

from girlframe.ai.conversation import ConversationReply, HandlerRequest
from girlframe.ai.gm_outcomes import KeepOutcome, OutcomeProposal
from girlframe.ai.gm_protocol import Assessment, Demand, TaskFrame, TraitClaim
from girlframe.ai.observation import AppendSceneInput, ObservationPolicy
from girlframe.database import tables as t
from girlframe.engine.campaign_opening import Opening
from girlframe.services.campaign_difficulty import EVENT
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.director_session import DirectorSessionService
from girlframe.services.onboarding import WorkflowError

activity_root = Path(__file__).resolve().parents[1] / "harpy-activity-lab"
bundled_adapter = activity_root / "p2_scene.py"
adapter_file = Path(os.environ.get("HARPY_ACTIVITY_TEST_ADAPTER", str(bundled_adapter)))
sys.path.insert(0, str(adapter_file.resolve().parent))
adapter_spec = spec_from_file_location("activity_p2_scene", adapter_file)
assert adapter_spec and adapter_spec.loader
activity_adapter = module_from_spec(adapter_spec)
adapter_spec.loader.exec_module(activity_adapter)
P2Scene = activity_adapter.P2Scene


class Handler:
    def __init__(self):
        self.requests = []

    def respond(self, request):
        self.requests.append(request)
        return ConversationReply(
            route="handler",
            disposition="clarification",
            provider="reviewed-handler-v1",
            text="I can wait here while you check.",
            handler_action="I turn my own report pad to a fresh page.",
            source_refs=request.response_need.source_refs if request.response_need else (),
        )


def adapter(observer):
    context = DirectorContextService(observer)
    handler = Handler()
    conversation = DirectorConversationService(context, handler=handler, handler_mode="reviewed")
    return P2Scene(DirectorSessionService(context, conversation=conversation)), handler


def input_command(observer, viewer, scene, key, text, channel="comms"):
    return AppendSceneInput(
        command_key=key,
        expected_scene_revision=observer.status(viewer, scene).scene_revision,
        speaker="pilot",
        text=text,
        fictional_channel=channel,
    )


def test_gm_rules_and_native_declaration_stay_out_of_scene_dialogue(observed):
    observer, scene, _, game, _, _, dice = observed
    app, handler = adapter(observer)
    question = "GM, does asking Kite to stop spend any Heat?"
    reply = app.session.submit(
        PLAYER, scene, input_command(observer, PLAYER, scene, "cost", question)
    )
    assert reply["conversation"]["gm"]["reply"]["gm_rule"]["status"] == "no_cost"
    assert handler.requests == []
    assert app.read(PLAYER, scene, "timeline")["entries"] == []
    assert app.read(OTHER, scene, "work")["gm_requests"] == []
    assert app.read(PLAYER, scene, "work")["gm_requests"][0]["reply"].startswith("No Heat.")

    declaration = "GM, I call Keep Your Head to brace the load before it slips."
    reply = app.session.submit(
        PLAYER, scene, input_command(observer, PLAYER, scene, "keep-declaration", declaration)
    )
    review = reply["conversation"]["gm"]["play_review_id"]
    item = next(
        row for row in app.read(PLAYER, scene, "work")["declarations"] if row["id"] == review
    )
    payload = {"review": review, "sheet_revision": item["keep"]["sheet_revision"], "heat": 0}
    assert item["keep"]["intent"] == declaration
    with pytest.raises(WorkflowError, match="declaring Pilot"):
        app.write(OTHER, "wrong-actor", scene, "open-declared-keep", payload)
    opened = app.write(PLAYER, "open-declared", scene, "open-declared-keep", payload)
    assert app.write(PLAYER, "open-declared-replay", scene, "open-declared-keep", payload) == opened
    assert dice.calls == 0
    with game.store.engine.connect() as c:
        assert game.action(c, opened["action_id"])["data"]["prepared"]["context"] == declaration


def test_handler_roleplay_rejects_rules_phrasing_and_retains_ordinary_heat(observed):
    observer, scene, _, game, *_ = observed
    app, _ = adapter(observer)
    with game.store.engine.connect() as c:
        context = app.session.context._handler_for_request(c, PLAYER, scene)
    request = HandlerRequest(question="Handler, is that the relay vent?", context=context)
    reply = ConversationReply(
        route="handler",
        provider="reviewed-handler-v1",
        disposition="clarification",
        text="The heat from that vent is reaching my boots too.",
    )
    app.session.conversation._validate_handler_draft(request, reply)
    mechanical = reply.model_copy(update={"handler_action": "I tell her to spend 2 Heat."})
    with pytest.raises(WorkflowError, match="HANDLER_RULES_IN_DIALOGUE"):
        app.session.conversation._validate_handler_draft(request, mechanical)


def add_scene(observer, channel, roster):
    observer.game.bind_scene(ADMIN, f"bind:{channel}", channel)
    for viewer in roster:
        observer.game.join_scene(viewer, f"join:{channel}:{viewer.user_id}", channel)
    with observer.store.engine.connect() as c:
        scene = observer.game.scene(c, channel)["id"]
    observer.configure_scene(ADMIN, f"config:{channel}", scene, 0, ObservationPolicy(mode="shadow"))
    for viewer in roster:
        observer.set_consent(viewer, f"consent:{channel}:{viewer.user_id}", scene, 1, consent=True)
    return scene


def test_opening_draft_previews_only_each_cast_members_facts(observed):
    observer, scene, _, game, *_ = observed
    app, handler = adapter(observer)
    handler_role, pilot = roles(observer, scene)
    data = {
        "revision": 0,
        "draft": {
            "location": "Relay service hall",
            "situation": "Maintenance wants to shut down the relay.",
            "first_choice": "Ask for a delay or check in elsewhere?",
            "gm_pressure": "GM_PRIVATE_PLAN",
            "facts": [
                {
                    "text": "Maintenance requested a delay.",
                    "learned_from": "Shift briefing",
                    "known_by": [handler_role.token],
                },
                {
                    "text": "PILOT_ONLY_LIGHT",
                    "learned_from": "Sole witness",
                    "known_by": [pilot.token],
                },
                {"text": "GM_ONLY_CAUSE", "learned_from": "Planning note", "known_by": []},
            ],
        },
    }
    assert app.read(ADMIN, scene, "opening")["draft"] is None
    saved = app.write(ADMIN, "save-opening", scene, "opening-save", data)
    assert app.write(ADMIN, "save-opening", scene, "opening-save", data) == saved == {"revision": 1}
    with pytest.raises(WorkflowError, match="STALE_OPENING"):
        app.write(ADMIN, "old-opening", scene, "opening-save", data)
    with pytest.raises(WorkflowError, match="administrator"):
        app.read(PLAYER, scene, "opening")
    with pytest.raises(WorkflowError, match="administrator"):
        app.write(PLAYER, "other-editor", scene, "opening-save", data)
    preview = app.read(ADMIN, scene, "opening")
    facts = {role["id"]: role["facts"] for role in preview["previews"]}
    assert facts[handler_role.token] == ["Maintenance requested a delay."]
    assert facts[pilot.token] == ["PILOT_ONLY_LIGHT"]
    assert "GM_ONLY_CAUSE" not in json.dumps(facts)
    with observer.store.engine.connect() as c:
        for table, column in (
            (t.events, t.events.c.payload_json),
            (t.commands, t.commands.c.outcome_json),
        ):
            bodies = json.dumps(
                list(
                    c.scalars(
                        sa.select(column).where(table.c.campaign_id == observer.store.campaign_id)
                    )
                )
            )
            assert "GM_PRIVATE_PLAN" not in bodies and "PILOT_ONLY_LIGHT" not in bodies
    app.submit(
        PLAYER,
        scene,
        input_command(observer, PLAYER, scene, "query", "Handler, can you repeat the scope?"),
    )
    assert "PILOT_ONLY_LIGHT" not in handler.requests[-1].model_dump_json()
    assert "Maintenance requested a delay." not in handler.requests[-1].model_dump_json()
    game.leave_scene(PLAYER, "pilot-leaves-opening", 900)
    assert app.read(ADMIN, scene, "opening")["stale_audience"]
    with pytest.raises(WorkflowError, match="STALE_OPENING"):
        app.write(ADMIN, "stale-launch", scene, "opening-launch", {"review": preview["review"]})
    with pytest.raises(WorkflowError, match="OPENING_AUDIENCE"):
        app.write(ADMIN, "stale-cast", scene, "opening-save", data | {"revision": 1})


def launch_opening(app, scene, *, facts=()):
    app.write(
        ADMIN,
        "opening-draft",
        scene,
        "opening-save",
        {
            "revision": 0,
            "draft": {
                "location": "Relay hall",
                "situation": "Check the main relay circuit.",
                "first_choice": "Inspect the panel or wait for the technician?",
                "gm_pressure": "GM_ONLY_MAINTENANCE_PLAN",
                "facts": facts,
                "session_zero": {
                    "tone": "Quiet operational drama",
                    "human_fallback": "Facilitator",
                },
            },
        },
    )
    payload = {"review": app.read(ADMIN, scene, "opening")["review"]}
    with pytest.raises(WorkflowError, match="administrator"):
        app.write(OTHER, "opening-impersonation", scene, "opening-launch", payload)
    receipt = app.write(ADMIN, "opening-confirm", scene, "opening-launch", payload)
    assert app.write(ADMIN, "opening-confirm", scene, "opening-launch", payload) == receipt
    assert receipt == {"launched": True, "revision": 1}
    with pytest.raises(WorkflowError, match="OPENING_LAUNCHED"):
        app.write(ADMIN, "opening-repeat", scene, "opening-launch", payload)


def test_manual_activity_opening_publishes_role_briefs_without_observation(ledger, monkeypatch):
    from test_m2_game import setup_game

    from girlframe.services.m2_game import GameService
    from girlframe.services.m3_handler_creation import HandlerCreationService

    activate = GameService.activate

    def check_intermediate_cast(game, viewer, *args):
        result = activate(game, viewer, *args)
        if viewer == PLAYER:
            mid_creation = HandlerCreationService(ledger).view(ADMIN)
            assert len(mid_creation["pilots"]) == 1
            assert mid_creation["pilots"][0]["ref"]["entity"] == str(PLAYER.user_id)
        return result

    monkeypatch.setattr(GameService, "activate", check_intermediate_cast)
    game, _, _, _ = setup_game(ledger)
    observer = DirectorObservationService(ledger)
    observer.game = game
    app, _ = adapter(observer)
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
        pilot = next(
            actor.ref
            for actor in app.session.knowledge._actor_views(c, observer._scene(c, scene))
            if actor.controller == PLAYER.user_id
        )
    assert app.read(PLAYER, scene, "opening-brief") == {"launched": False}
    launch_opening(
        app,
        scene,
        facts=[
            {
                "text": "Red inspection tag",
                "learned_from": "Private inspection",
                "known_by": [pilot.token],
            }
        ],
    )
    brief = app.read(PLAYER, scene, "opening-brief")
    assert brief["roles"][0]["facts"] == ["Red inspection tag"]
    assert brief["session_zero"]["tone"] == "Quiet operational drama"
    assert app.read(ADMIN, scene, "opening-brief")["roles"][0]["facts"] == []
    assert "GM_ONLY_MAINTENANCE_PLAN" not in json.dumps(brief)
    with ledger.engine.connect() as c:
        assert app.session.context._references(c, scene) == ()


def test_parallel_scenes_file_only_approved_reports_after_native_close(observed):
    observer, source, _, _, *_ = observed
    app, handler = adapter(observer)
    session = app.session
    observer.game.leave_scene(OTHER, "other-leaves-source", 900)
    target = add_scene(observer, 901, (ADMIN, OTHER))
    with observer.store.engine.connect() as c:
        handler_role = observer._authorize_input(c, ADMIN, target, "handler")[2]
        target_pilot = observer._authorize_input(c, OTHER, target, "pilot")[2]
    launch_opening(
        app,
        target,
        facts=[
            {
                "text": "HANDLER_APPROVED_BRIEF",
                "learned_from": "Shift report",
                "known_by": [handler_role.token],
            },
            {
                "text": "TARGET_PILOT_ONLY_NOTE",
                "learned_from": "Personal note",
                "known_by": [target_pilot.token],
            },
        ],
    )
    pilot = roles(observer, source)[1]
    text, secret = "We found a loose cover on the east rail.", "UNREPORTED_CELLAR_ENTRY"
    posted = []
    for i, (speech, channel) in enumerate(((text, "comms"), (secret, "private"))):
        item = app.submit(
            PLAYER, source, input_command(observer, PLAYER, source, f"post:{i}", speech, channel)
        )
        posted.append(
            session.context.record(
                ADMIN,
                f"know:{i}",
                source,
                item["input"]["source_id"],
                i,
                known_by=(pilot,),
                topic="tactical",
            )["id"]
        )
    assert secret in json.dumps(app.timeline(PLAYER, source))
    assert secret not in json.dumps(app.timeline(ADMIN, source))
    assert not app.timeline(OTHER, target)["entries"]
    assert not session.handler_reports(ADMIN, target)["reports"]

    def question(key):
        cmd = input_command(observer, OTHER, target, key, "Handler, can you repeat the scope?")
        app.submit(OTHER, target, cmd)
        return handler.requests[-1]

    before_close = question("before-close")
    assert not before_close.closed_scene_reports
    prompt = before_close.model_dump_json()
    assert "HANDLER_APPROVED_BRIEF" in prompt
    assert all(
        hidden not in prompt
        for hidden in (secret, text, "TARGET_PILOT_ONLY_NOTE", "GM_ONLY_MAINTENANCE_PLAN")
    )
    with pytest.raises(WorkflowError, match="SCENE_REPORT_OPEN"):
        carry(session.context, source, target, (posted[0],), key="early-carry")
    revision = observer.status(ADMIN, source).scene_revision
    with pytest.raises(WorkflowError, match="SCENE_REPORT_SCOPE"):
        app.close(ADMIN, "bad-close", source, 900, revision, tuple(posted))
    assert app.timeline(PLAYER, source)["open"]
    with pytest.raises(WorkflowError):
        app.close(OTHER, "wrong-owner", source, 900, revision, (posted[0],))
    receipt = app.close(ADMIN, "manual-close", source, 900, revision, (posted[0],))
    assert receipt["closed"] and receipt["handler_report_count"] == 1
    assert app.close(ADMIN, "manual-close", source, 900, revision, (posted[0],)) == receipt
    assert app.timeline(PLAYER, source)["open"] is False
    expected = ["Reported claim: " + text]
    assert [ref.text for ref in question("after-close").closed_scene_reports] == expected
    assert secret not in json.dumps(session.handler_reports(ADMIN, target))
    with pytest.raises(WorkflowError):
        session.handler_reports(OTHER, target)
    observer.game.bind_scene(ADMIN, "reuse-channel", 900)
    assert [ref.text for ref in question("after-rebind").closed_scene_reports] == expected
    observer.set_consent(PLAYER, "withdraw-origin", source, 1, consent=False)
    assert not question("after-withdrawal").closed_scene_reports


def test_room_without_handler_records_input_without_an_interjection(observed):
    observer, scene, *_ = observed
    observer.game.leave_scene(ADMIN, "handler-leaves", 900)
    app, handler = adapter(observer)
    alone = input_command(observer, OTHER, scene, "away", "I survey the other room.")
    outcome = app.session.submit(OTHER, scene, alone)["conversation"]
    assert outcome["handler_decision"]["decision"]["reason"] == "handler_absent"
    assert outcome["handler"] is None and not handler.requests


@pytest.mark.parametrize("control", ("player", "ai"))
def test_opening_handler_control_gates_reviewed_drafts(observed, control):
    observer, scene, *_ = observed
    app, handler = adapter(observer)
    record = Opening(
        scene="approved-introduction",
        channel=901,
        handler=ADMIN.user_id,
        audience=(ADMIN.user_id, PLAYER.user_id),
        plan="approved-session-zero",
        goals="Inspect the relay",
        difficulty="normal",
        introduction="Check in.",
        first_mission_day=4,
        handler_control=control,
    )
    with observer.store.transaction() as c:
        observer.store._audit(
            c, ADMIN.user_id, "test-control", EVENT, record.model_dump(mode="json")
        )
    question = input_command(observer, PLAYER, scene, "question", "Handler, can you clarify?")
    outcome = app.session.submit(PLAYER, scene, question)["conversation"]
    if control == "player":
        assert outcome["handler_decision"]["decision"]["reason"] == "player_handler"
        assert outcome["handler"] is None and not handler.requests
    else:
        assert outcome["handler_decision"]["decision"]["action"] == "RESPOND"
        assert outcome["handler"] and len(handler.requests) == 1


def test_activity_timeline_shows_one_scoped_delivery_on_reopen(observed):
    observer, scene, *_ = observed
    app, _ = adapter(observer)
    pilot = roles(observer, scene)[1]
    cmd = input_command(observer, PLAYER, scene, "input", "Handler, can you say what you saw?")
    assert app.submit(PLAYER, scene, cmd) == app.submit(PLAYER, scene, cmd)
    draft = app.gm_work(ADMIN, scene)["handler_drafts"][0]["id"]
    app.approve_handler(ADMIN, "review", scene, draft, "Scoped fixture reply.", (pilot,))
    assert [x["kind"] for x in app.timeline(PLAYER, scene)["entries"]] == ["input"]
    delivered = app.deliver_handler(ADMIN, "deliver", scene, draft)
    assert app.deliver_handler(ADMIN, "deliver", scene, draft) == delivered
    reopened, _ = adapter(observer)
    assert [x["kind"] for x in reopened.timeline(PLAYER, scene)["entries"]] == ["input", "handler"]
    assert [x["kind"] for x in reopened.timeline(OTHER, scene)["entries"]] == ["input"]
    observer.set_consent(OTHER, "withdraw-destination", scene, 1, consent=False)
    with pytest.raises(WorkflowError, match="OBSERVATION_DISABLED"):
        reopened.timeline(PLAYER, scene)


def test_native_play_creates_gm_work_without_a_conversation_source(observed):
    observer, scene, _, game, worker, gateway, dice = observed
    app, _ = adapter(observer)
    action = start(game, context="Hold the relay needle on the marked limit.")
    tick(worker, gateway)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    work = next(x for x in app.gm_work(ADMIN, scene)["outcome_sources"] if x["action_id"] == action)
    assert work["operation"] == "keep" and work["frame_required"]
    assert not app.timeline(PLAYER, scene)["entries"]
    with pytest.raises(WorkflowError):
        app.gm_work(OTHER, scene)

    frame = TaskFrame(
        stakes="The needle stays within the marked limit.",
        demands=(Demand(id="control", question="Did the pilot maintain control?"),),
        response_scope="self",
    )
    opened = app.open_ruling(ADMIN, "open", scene, work["source_kind"], work["source_id"], frame)
    packet = app.ruling_packet(ADMIN, scene, opened["id"])
    proposal = OutcomeProposal(
        request_id=packet["request_id"],
        decision=KeepOutcome(
            verdict="enough",
            narration="The needle stayed within the mark.",
            assessments=(
                Assessment(
                    demand_id="control",
                    sufficient=True,
                    evidence_ids=("traits", "source", "native"),
                    traits=(TraitClaim(trait="in_control", polarity="are"),),
                    private_reason="The saved trait matches the declared approach.",
                ),
            ),
        ),
        cited_evidence=("source", "native"),
        private_reasoning="Fixture reviewed saved native traits.",
    )
    pending = app.propose_ruling(ADMIN, "propose", scene, opened["id"], proposal)
    with pytest.raises(WorkflowError):
        app.confirm_ruling(OTHER, "wrong-ruling-owner", scene, pending["id"])
    done = app.confirm_ruling(ADMIN, "confirm", scene, pending["id"])
    assert app.confirm_ruling(ADMIN, "confirm", scene, pending["id"]) == done
    assert app.play_results(PLAYER, scene, action)["state"] == "complete"
    assert dice.calls == 1
