"""Only Pilot turns are scripted; GM and Handler replies come from separate providers."""

import json
from html import escape
from pathlib import Path

import pytest
import sqlalchemy as sa
from test_director_observation import observed as observed
from test_director_observation import send
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.ai.conversation import ConversationReply, SyntheticGM, SyntheticHandler
from girlframe.database import tables as t
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.onboarding import WorkflowError


@pytest.fixture
def routed(observed):
    observer, scene, clock, game, _, _, dice = observed
    with observer.store.engine.connect() as c:
        _, _, handler = observer._authorize_input(c, ADMIN, scene, "handler")
        _, _, pilot = observer._authorize_input(c, PLAYER, scene, "pilot")
    # Background is fixture state, not prewritten Handler dialogue in the test exchange.
    with observer.store.transaction() as c:
        canon = state(game)
        canon.facts.append({"kind": "synthetic_gm_only", "body": "SYNTHETIC_GM_SECRET_CANARY"})
        game.event(c, ADMIN.user_id, "gm-background", "synthetic.gm_background", canon)
    context = DirectorContextService(observer)
    backgrounds = [
        (
            "objective",
            "Training brief objective: inspect the relay site and report observed conditions.",
            (handler, pilot),
        ),
        (
            "scope",
            "Training brief scope: observe accessible areas only; forced entry is not authorised.",
            (handler, pilot),
        ),
        (
            "status",
            "Training brief status: planning only; no mission has been accepted.",
            (handler, pilot),
        ),
        ("general", "SYNTHETIC_PC_ONLY_REFERENCE", (pilot,)),
    ]
    for index, (topic, text, actors) in enumerate(backgrounds):
        _, source = send(observer, scene, f"background:{index}", text=text, viewer=ADMIN)
        context.record(
            ADMIN,
            f"background-ref:{index}",
            scene,
            source.source_id,
            index,
            known_by=actors,
            topic=topic,
        )
    return observer, context, scene, game, dice


class GMProbe(SyntheticGM):
    def __init__(self):
        self.requests = []

    def respond(self, request):
        self.requests.append(request)
        return super().respond(request)


class HandlerProbe(SyntheticHandler):
    def __init__(self):
        self.requests = []

    def respond(self, request):
        self.requests.append(request)
        return super().respond(request)


def test_pilot_only_script_gets_discrete_scoped_engine_replies(routed):
    observer, context, scene, game, dice = routed
    gm, handler = GMProbe(), HandlerProbe()
    service = DirectorConversationService(context, gm=gm, handler=handler)
    before = state(game).model_dump_json()
    # Framing labels only: these do not assert engine travel or mission acceptance.
    chapters = {
        "Barracks, before the exercise": [
            ("handler", "Handler, what is the objective?", "answer"),
            ("handler", "Handler, what is included in scope?", "answer"),
            ("handler", "Handler, who funds the relay?", "clarification"),
            ("handler", "Handler, are we already committed?", "answer"),
            (
                "gm",
                "GM, can you resolve Keep Your Head and spend Heat?",
                "requires_engine_workflow",
            ),
            ("gm", "GM, can you summarise the briefing?", "answer"),
            ("handler", "Handler, please repeat the objective.", "answer"),
            ("handler", "Handler, does the scope permit forced entry?", "answer"),
            ("handler", "Handler, what is the status of mission acceptance?", "answer"),
            ("handler", "Handler, which bunk belongs to the relay technician?", "clarification"),
        ],
        "Hallway encounter": [
            ("handler", "Handler, before you go, what is our goal?", "answer"),
            ("handler", "Handler, remind me of the boundaries.", "answer"),
            ("handler", "Handler, who left that sealed envelope?", "clarification"),
            ("gm", "GM, does asking a question spend Heat?", "requires_engine_workflow"),
            ("handler", "Handler, are we committed just by talking here?", "answer"),
            ("handler", "Handler, is there an access code for the relay door?", "clarification"),
            ("handler", "Handler, give me the objective once more.", "answer"),
            ("gm", "GM, what is established about the objective?", "answer"),
            ("handler", "Handler, what limits are in the training brief?", "answer"),
            ("handler", "Handler, has the mission been accepted?", "answer"),
        ],
        "Simulation briefing room": [
            ("handler", "Handler, state the exercise objective.", "answer"),
            ("handler", "Handler, outline the authorised scope.", "answer"),
            ("gm", "GM, I want to roll Keep Your Head.", "requires_engine_workflow"),
            ("handler", "Handler, can you resolve that roll for me?", "requires_engine_workflow"),
            ("handler", "Handler, are there hostile units at the relay?", "clarification"),
            ("handler", "Handler, confirm the planning status.", "answer"),
            ("handler", "Handler, does the scope include forcing the door?", "answer"),
            ("gm", "GM, remind me of the mission scope.", "answer"),
            ("handler", "Handler, what weather should I expect?", "clarification"),
            ("handler", "Handler, is reporting conditions the goal?", "answer"),
        ],
        "Simulated cockpit communications": [
            ("handler", "Handler, comms check: repeat the objective.", "answer"),
            ("handler", "Handler, repeat the access limits.", "answer"),
            ("gm", "GM, resolve Keep Your Head using my chosen Heat.", "requires_engine_workflow"),
            ("handler", "Handler, who is on the other radio channel?", "clarification"),
            ("handler", "Handler, have we accepted a real mission?", "answer"),
            ("handler", "Handler, what is the extraction frequency?", "clarification"),
            ("handler", "Handler, what does the brief say about the objective?", "answer"),
            ("gm", "GM, what is the current acceptance status?", "answer"),
            ("handler", "Handler, confirm the scope before I proceed.", "answer"),
            ("handler", "Handler, where is the emergency landing pad?", "clarification"),
        ],
        "Barracks debrief": [
            ("handler", "Handler, what was the stated objective?", "answer"),
            ("handler", "Handler, remind me of the scope boundaries.", "answer"),
            ("gm", "GM, can the conversation resolve a Play?", "requires_engine_workflow"),
            ("handler", "Handler, did the relay owner pay us?", "clarification"),
            ("handler", "Handler, what mission status is established?", "answer"),
            (
                "handler",
                "Handler, can you spend Heat for my next attempt?",
                "requires_engine_workflow",
            ),
            ("handler", "Handler, what is tomorrow's timetable?", "clarification"),
            ("gm", "GM, restate the authorised scope.", "answer"),
            ("handler", "Handler, repeat the goal for my notes.", "answer"),
            (
                "handler",
                "Handler, confirm we have not committed through this discussion.",
                "answer",
            ),
        ],
    }
    turns = [(chapter, *turn) for chapter, dialogue in chapters.items() for turn in dialogue]
    transcript = []
    for index, (chapter, route, text, expected) in enumerate(turns):
        _, source = send(observer, scene, f"pilot:{index}", text=text)
        bundle = service.dispatch(
            PLAYER, f"address:{index}", scene, source.source_id, 1, addressed_to=route
        )
        result = bundle[route]
        assert result["reply"]["route"] == route and result["reply"]["disposition"] == expected
        assert "SYNTHETIC_GM_SECRET_CANARY" not in result["reply"]["text"]
        if route == "handler":
            assert "SYNTHETIC_PC_ONLY_REFERENCE" not in json.dumps(result)
        calls = len(gm.requests) + len(handler.requests)
        assert (
            service.dispatch(
                PLAYER, f"address:{index}", scene, source.source_id, 1, addressed_to=route
            )
            == bundle
        )
        assert len(gm.requests) + len(handler.requests) == calls
        assert service.get(PLAYER, scene, result["id"]) == result
        with pytest.raises(WorkflowError):
            service.get(OTHER, scene, result["id"])
        transcript.append(
            {
                "chapter": chapter,
                "pilot": text,
                "route": route,
                "reply": result["reply"],
                "gm_reply": bundle["gm"]["reply"],
            }
        )
    assert len(gm.requests) == 50 and len(handler.requests) == 40
    assert all("SYNTHETIC_GM_SECRET_CANARY" in x.model_dump_json() for x in gm.requests)
    assert all("SYNTHETIC_GM_SECRET_CANARY" not in x.model_dump_json() for x in handler.requests)
    assert all("SYNTHETIC_PC_ONLY_REFERENCE" not in x.model_dump_json() for x in handler.requests)
    assert all(
        "canonical_state" not in x.model_dump() and "engine_records" not in x.model_dump()
        for x in handler.requests
    )
    assert all(
        "m3_missions" in x.engine_records and "m2_choices" in x.engine_records for x in gm.requests
    )
    assert transcript[4]["reply"]["play_id"] == "keep_your_head"
    assert "inspect the relay site" in transcript[0]["reply"]["text"]
    assert "forced entry is not authorised" in transcript[1]["reply"]["text"]
    assert "do not have established information" in transcript[2]["reply"]["text"]
    assert state(game).model_dump_json() == before and dice.calls == 0
    output = Path("var/gm-handler-conversation.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "pilot_turns": 50,
                "engine_handler_replies": 40,
                "engine_gm_replies": 50,
                "scripted_speakers": ["pilot"],
                "framing": "Five narrative settings; no engine travel or mission acceptance.",
                "external_tokens": 0,
                "external_cost": 0,
                "transcript": transcript,
            },
            indent=2,
        )
        + "\n"
    )
    paragraphs = []
    for index, turn in enumerate(transcript, start=1):
        paragraphs.append(
            f"<article><h2>{index}. {escape(turn['chapter'])}</h2>"
            f"<p><b>Pilot (scripted):</b> {escape(turn['pilot'])}</p>"
            f"<p><b>Engine GM:</b> {escape(turn['gm_reply']['text'])}</p>"
            + (
                f"<p><b>Engine Handler:</b> {escape(turn['reply']['text'])}</p>"
                if turn["route"] == "handler"
                else ""
            )
            + "</article>"
        )
    output.with_suffix(".html").write_text(
        "<!doctype html><html lang='en'><meta charset='utf-8'>"
        "<title>GM and Handler synthetic trial</title>"
        "<style>body{max-width:900px;margin:40px auto;padding:0 20px;"
        "font:17px/1.6 system-ui;background:#f7f5f0;color:#242424}"
        "article{border-top:1px solid #ccc;margin-top:30px}h2{font-size:20px}</style>"
        "<h1>GM and Handler: engine-generated replies</h1>"
        "<p>50 scripted Pilot messages; 50 engine GM replies; 40 engine Handler replies. "
        "Deterministic local templates, external tokens/cost: 0. Background brief facts "
        "are seeded before dialogue. Narrative settings do not assert engine travel. "
        "No mission acceptance, rolls, expenditure or live publication.</p>"
        + "".join(paragraphs)
        + "</html>"
    )


def test_stale_pause_revoke_and_foreign_source_reject(routed):
    observer, context, scene, game, dice = routed
    service = DirectorConversationService(context)
    _, source = send(observer, scene, "question", text="Handler, what is the objective?")
    with pytest.raises(WorkflowError, match="SOURCE_UNAVAILABLE"):
        service.respond(OTHER, "foreign", scene, source.source_id, "handler", 1)
    with pytest.raises(WorkflowError, match="STALE_SOURCE"):
        service.respond(PLAYER, "stale", scene, source.source_id, "handler", 2)
    observer.store.safety(PLAYER, "pause", 0, pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.respond(PLAYER, "paused", scene, source.source_id, "handler", 1)
    observer.store.safety(PLAYER, "resume", observer.store.status(ADMIN)["revision"], pause=False)
    observer.set_consent(OTHER, "withdraw", scene, 1, consent=False)
    with pytest.raises(WorkflowError, match="OBSERVATION_DISABLED"):
        service.respond(PLAYER, "revoked", scene, source.source_id, "handler", 1)


def test_provider_cannot_leak_or_commit_stale_reply(routed):
    observer, context, scene, game, dice = routed
    _, source = send(observer, scene, "question", text="Handler, what is the objective?")

    class Leaky:
        def respond(self, request):
            return ConversationReply(
                route="handler", disposition="answer", text="SYNTHETIC_GM_SECRET_CANARY"
            )

    with pytest.raises(WorkflowError, match="CONVERSATION_UNAVAILABLE"):
        DirectorConversationService(context, handler=Leaky()).respond(
            PLAYER, "leaky", scene, source.source_id, "handler", 1
        )

    class Concurrent(SyntheticHandler):
        def respond(self, request):
            send(observer, scene, "new-input", text="New source arrived.")
            return super().respond(request)

    with pytest.raises(WorkflowError, match="STALE_CONTEXT"):
        DirectorConversationService(context, handler=Concurrent()).respond(
            PLAYER, "raced", scene, source.source_id, "handler", 1
        )
    with observer.store.engine.connect() as c:
        assert not list(c.scalars(sa.select(t.director_context["shadow"].c.id)))


def test_request_schemas_cannot_cross_gm_handler_boundary(routed):
    from pydantic import ValidationError

    from girlframe.ai.conversation import HandlerRequest

    observer, context, scene, game, dice = routed
    gm = context.build(ADMIN, scene)
    with pytest.raises(ValidationError):
        HandlerRequest(question="What is the objective?", context=gm)


def test_route_intent_retry_and_pause_before_commit_are_safe(routed):
    observer, context, scene, game, dice = routed
    _, source = send(observer, scene, "question", text="Handler, what is the objective?")
    service = DirectorConversationService(context)
    result = service.respond(PLAYER, "stable", scene, source.source_id, "handler", 1)
    with pytest.raises(WorkflowError, match="IDEMPOTENCY_CONFLICT"):
        service.respond(PLAYER, "stable", scene, source.source_id, "gm", 1)

    class Pause(SyntheticHandler):
        def respond(self, request):
            observer.store.safety(PLAYER, "pause-during-inference", 0, pause=True)
            return super().respond(request)

    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        DirectorConversationService(context, handler=Pause()).respond(
            PLAYER, "pause-race", scene, source.source_id, "handler", 1
        )
    assert service.get(PLAYER, scene, result["id"]) == result


def test_gm_and_handler_retry_independently_after_handler_outage(routed):
    observer, context, scene, game, dice = routed
    _, source = send(observer, scene, "question", text="Handler, what is the objective?")
    gm = GMProbe()

    class Recovering(SyntheticHandler):
        calls = 0

        def respond(self, request):
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("SYNTHETIC_PRIVATE_PROVIDER_FAILURE")
            return super().respond(request)

    handler = Recovering()
    service = DirectorConversationService(context, gm=gm, handler=handler)
    with pytest.raises(WorkflowError, match="CONVERSATION_UNAVAILABLE"):
        service.dispatch(PLAYER, "both", scene, source.source_id, 1, addressed_to="handler")
    result = service.dispatch(PLAYER, "both", scene, source.source_id, 1, addressed_to="handler")
    assert len(gm.requests) == 1 and handler.calls == 2
    assert result["handler"]["reply"]["disposition"] == "answer"
    assert "SYNTHETIC_PRIVATE_PROVIDER_FAILURE" not in json.dumps(result)


def test_direct_gm_reply_deduplicates_observer_without_losing_other_input(routed):
    observer, context, scene, game, dice = routed
    _, source = send(observer, scene, "question", text="GM, what is the objective?")
    observer.store.clock.now += 120
    frozen = observer.claim_review(scene)
    service = DirectorConversationService(context)
    service.dispatch(PLAYER, "direct", scene, source.source_id, 1)
    assert (
        observer.status(PLAYER, scene).pending_messages == 4
    )  # setup references still require review
    with pytest.raises(WorkflowError, match="STALE_CLAIM"):
        observer.acknowledge_review(frozen.run_id, frozen.lease_token, success=True)
    send(
        observer,
        scene,
        "edit-question",
        text="GM, what is included in scope?",
        source_id=source.source_id,
        expected_source_revision=1,
    )
    assert observer.status(PLAYER, scene).pending_messages == 5
    service.respond(PLAYER, "edited-question", scene, source.source_id, "gm", 2)
    assert observer.status(PLAYER, scene).pending_messages == 4


def test_engine_decides_handler_need_and_persists_silence_and_grounded_warning(routed):
    observer, context, scene, game, dice = routed
    gm, handler = GMProbe(), HandlerProbe()
    service = DirectorConversationService(context, gm=gm, handler=handler)
    before = state(game).model_dump_json()
    cases = [
        ("The objective is on the table. I am talking to the other Pilot.", "no_handler_need"),
        ("The Handler was mentioned on the noticeboard.", "no_handler_need"),
        ("Handler, what is the objective?", "direct_question"),
        ("I will force the sealed door and go inside.", "scope_boundary"),
        ("I am not going to force the door.", "no_handler_need"),
        ("GM, resolve Keep Your Head.", "gm_request"),
    ]
    for index, (text, reason) in enumerate(cases):
        _, source = send(observer, scene, f"need-input:{index}", text=text)
        bundle = service.process_message(PLAYER, f"need:{index}", scene, source.source_id, 1)
        assert bundle["handler_decision"]["decision"]["reason"] == reason
        assert (bundle["handler"] is not None) == (reason in ("direct_question", "scope_boundary"))
        assert (
            service.process_message(PLAYER, f"need:{index}", scene, source.source_id, 1) == bundle
        )
        if reason == "scope_boundary":
            assert "conflicts with the scope" in bundle["handler"]["reply"]["text"]
            assert bundle["handler"]["reply"]["source_refs"]
        if reason == "no_handler_need":
            with pytest.raises(WorkflowError, match="STALE_HANDLER_DECISION"):
                service.respond(
                    PLAYER,
                    f"forced:{index}",
                    scene,
                    source.source_id,
                    "handler",
                    1,
                    handler_decision_id=bundle["handler_decision"]["id"],
                )
    assert len(gm.requests) == 6 and len(handler.requests) == 2
    assert state(game).model_dump_json() == before and dice.calls == 0
    _, source = send(observer, scene, "decision-before-change", text="Handler, what is the scope?")
    decision = service.decide_handler(PLAYER, "old-decision", scene, source.source_id, 1)
    send(observer, scene, "subsequent-input", text="Another source has arrived.")
    with pytest.raises(WorkflowError, match="STALE_HANDLER_DECISION"):
        service.respond(
            PLAYER,
            "stale-decision-reply",
            scene,
            source.source_id,
            "handler",
            1,
            handler_decision_id=decision["id"],
        )
    assert len(handler.requests) == 2
