"""Actual saved Handler sheets, scoped personal cues, and source-bound follow-through."""

import json

import pytest
from test_director_activity_scene import P2Scene
from test_director_continuity import roles
from test_director_model_adapters import Recorder
from test_director_observation import observed as observed
from test_director_observation import send
from test_handler_creation import agree, complete, ready, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick

from girlframe.ai.conversation import (
    ConversationReply,
    HandlerNeedProposal,
    HandlerRequest,
    PeerResponse,
)
from girlframe.ai.observation import ObservationPolicy
from girlframe.engine.m3_handler_state import HandlerNotes
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.onboarding import WorkflowError

CUE = "The alarm is still in my ears when I close my eyes."
VOICES = {
    "Mistress": (
        "cooperation",
        "I stayed behind to finish the shared checklist.",
        "You did well. Come sit by me.",
    ),
    "Dogrunner": (
        "accountability",
        "I put the wrong totals on the report.",
        "Whose initials are on that line?",
    ),
    "Scientist": (
        "research",
        "The same result came back on the second instrument.",
        "Control conditions first. Send my assistant both readings.",
    ),
    "Frantic": (
        "capacity",
        "We only have one technician for both shifts.",
        "One technician? All right. One queue. Which check can wait?",
    ),
    "Insurgent": (
        "institution",
        "The Director wants us to name who questioned the policy.",
        "Say what you saw. Leave speculation off the record.",
    ),
    "Trainer": (
        "procedure",
        "The reset steps are in the wrong order.",
        "Mark the skipped step. We start the drill there.",
    ),
    "Advocate": (
        "agency",
        "The supervisor answered the question on my behalf.",
        "Hold on. It was your question. I want to hear your answer.",
    ),
}


class Handler:
    def __init__(self):
        self.requests = []

    def respond(self, request):
        self.requests.append(request)
        decision = request.response_need
        refs = decision.source_refs
        fields = {}
        if decision.reason == "known_update":
            text = "I can take my copy to the control desk."
            fields = dict(
                handler_action="I take my own copy to the desk.",
                handler_concern="Find out which console the control desk has assigned.",
            )
        elif decision.reason == "reviewed_follow_up":
            text = "Control says we can use the north console. I'll mark that on my copy."
            fields = dict(handler_action="I mark the north console on my copy.")
        elif request.playbook_profile:
            text = VOICES[request.playbook_profile.playbook][2]
        else:
            text = "I'm making tea. I can sit with you for a minute if you'd like."
            fields = dict(handler_action="I set a second mug beside my own.")
        return ConversationReply(
            route="handler",
            provider="reviewed-handler-v1",
            disposition="answer" if refs else "clarification",
            text=text,
            source_refs=refs,
            **fields,
        )


def service(observer):
    provider = Handler()
    return DirectorConversationService(
        DirectorContextService(observer),
        handler=provider,
        handler_mode="reviewed",
    ), provider


def propose(svc, scene, source, key, **fields):
    opened = svc.open_handler_need(ADMIN, f"{key}:open", scene, source.source_id)
    packet = svc.handler_need_packet(ADMIN, scene, opened["id"])
    proposal = HandlerNeedProposal(
        request_id=packet.request_id,
        reason="Fixture review of an actual heard moment.",
        **fields,
    )
    saved = svc.propose_handler_need(ADMIN, f"{key}:propose", scene, opened["id"], proposal)
    svc.review_handler_need(ADMIN, f"{key}:review", scene, saved["id"], "approve", "Scope checked.")
    return packet


def approve(svc, scene, draft, *recipients):
    return svc.review_handler(
        ADMIN,
        f"{draft}:approved",
        scene,
        draft,
        "approve",
        "Reviewed in-character offer.",
        delivery_recipients=recipients,
    )


def peer_actor(observer, scene):
    with observer.store.engine.connect() as c:
        return observer._authorize_input(c, OTHER, scene, "pilot")[2]


@pytest.mark.parametrize("playbook", VOICES)
def test_all_printed_types_shape_the_saved_sheet_prompt_and_intervention(ledger, playbook):
    creation, game = ready(ledger)
    notes = HandlerNotes(voice="Speak softly between check-ins.", concern="PRIVATE_PORTRAYAL_CUE")
    save(creation, complete(creation, playbook).model_copy(update={"notes": notes}))
    agree(creation)
    preview = creation.view(ADMIN)
    assert preview["draft"]["playbook"] == preview["playbook_profile"]["playbook"] == playbook
    assert all(preview["playbook_profile"]["behavior"].values())
    assert len(preview["rules"]["shared"]) == 7
    assert len(preview["rules"]["advancement_triggers"]) == 4
    assert any(x["kind"] == "Signature Play" for x in preview["rules"]["playbook"])
    assert all(x["access"] == "draft" for x in preview["rules"]["playbook"])
    creation.activate(
        ADMIN, "activate-character", preview["revision"], preview["game_revision"], True
    )
    observer = DirectorObservationService(ledger, synthetic=True)
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    observer.configure_scene(ADMIN, "configure", scene, 0, ObservationPolicy(mode="shadow"))
    for viewer in (ADMIN, PLAYER, OTHER):
        observer.set_consent(viewer, f"consent:{viewer.user_id}", scene, 1, consent=True)

    performer = Handler()

    def reply(packet):
        request = HandlerRequest.model_validate_json(json.dumps(packet))
        return performer.respond(request).model_dump(
            mode="json",
            exclude={
                "route",
                "provider",
                "schema_version",
                "gm_decision",
                "play_id",
                "application",
            },
        )

    recorder = Recorder(reply)
    app = P2Scene.model_fixture(DirectorContextService(observer), recorder.client())
    svc = app.session.conversation
    saved_sheet = app.read(ADMIN, scene, "handler-sheet")
    assert saved_sheet["playbook_profile"] == preview["playbook_profile"]
    assert saved_sheet["draft"]["notes"] == notes.model_dump()
    assert saved_sheet["notes_editable"]
    assert "PRIVATE_PORTRAYAL_CUE" not in state(game).model_dump_json()
    assert app.read(PLAYER, scene, "persona-setup")["sheet"] is None
    with pytest.raises(WorkflowError):
        app.read(PLAYER, scene, "handler-sheet")
    cue, speech, expected = VOICES[playbook]
    _, source = send(observer, scene, "cue", text=speech, fictional_channel="comms")
    assert (
        svc.process_message(PLAYER, "before-review", scene, source.source_id, 1)["handler"] is None
    )
    with pytest.raises(WorkflowError, match="HANDLER_PLAYBOOK_CUE"):
        propose(
            svc,
            scene,
            source,
            "unrelated",
            kind="character_cue",
            cue="capacity" if cue != "capacity" else "agency",
            speech_quote=speech,
            action="RESPOND",
        )
    packet = propose(
        svc,
        scene,
        source,
        "known",
        kind="character_cue",
        cue=cue,
        speech_quote=speech,
        action="RESPOND",
    )
    route = svc.process_message(PLAYER, "after-review", scene, source.source_id, 1)
    assert route["handler_decision"]["decision"]["reason"] == "reviewed_character_cue"
    handler, pilot = roles(observer, scene)
    assert packet.request.context.actor == handler
    assert packet.request.character_notes == notes
    assert all("PRIVATE_PORTRAYAL_CUE" not in x.text for x in packet.request.context.references)
    assert len(recorder.requests) == 1
    assert (
        performer.requests[-1].playbook_profile.model_dump(mode="json")
        == preview["playbook_profile"]
    )
    assert "PRIVATE_BACKGROUND" not in performer.requests[-1].model_dump_json()
    assert performer.requests[-1].character_notes == notes
    draft = route["handler"]["id"]
    approve(svc, scene, draft, pilot)
    assert svc.delivery.preview(ADMIN, scene, draft)["text"] == expected
    svc.delivery.deliver(ADMIN, "send-character", scene, draft)
    assert svc.delivery.contributions(PLAYER, scene)[0]["text"] == expected
    assert not svc.delivery.contributions(OTHER, scene)
    print(f"HANDLER_CHARACTER {playbook}: {expected}")


@pytest.mark.parametrize("case", ("heard", "private", "peer-first", "peer-before-delivery"))
def test_personal_offer_when_heard_wait_when_private_or_peer_takes_the_turn(observed, case):
    observer, scene, _, game, *_ = observed
    svc, performer = service(observer)
    _, pilot = roles(observer, scene)
    before = state(game)
    _, source = send(
        observer,
        scene,
        "personal",
        text=CUE,
        fictional_channel="private" if case == "private" else "comms",
    )
    fields = dict(kind="character_cue", cue="personal", speech_quote=CUE, action="RESPOND")
    if case == "private":
        with pytest.raises(WorkflowError, match="HANDLER_NEED_SPEECH"):
            propose(svc, scene, source, "private-cue", **fields)
        route = svc.process_message(PLAYER, "route", scene, source.source_id, 1)
        assert route["handler"] is None and not performer.requests
        return

    def covered():
        words = "I can sit here with you until you're ready."
        _, peer = send(observer, scene, "peer", text=words, viewer=OTHER, fictional_channel="comms")
        proof = PeerResponse(source_id=peer.source_id, source_revision=1, quote=words)
        propose(
            svc, scene, source, "covered", **(fields | {"action": "WAIT", "peer_response": proof})
        )

    propose(svc, scene, source, "personal-cue", **fields)
    if case == "peer-first":
        covered()
        route = svc.process_message(PLAYER, "route", scene, source.source_id, 1)
        assert route["handler_decision"]["decision"]["reason"] == "peer_response"
        assert route["handler"] is None and not performer.requests
        return
    draft = svc.process_message(PLAYER, "route", scene, source.source_id, 1)["handler"]["id"]
    second_pilot = peer_actor(observer, scene)
    with pytest.raises(WorkflowError, match="HANDLER_DELIVERY_AUDIENCE"):
        approve(svc, scene, draft, pilot, second_pilot)
    approve(svc, scene, draft, pilot)
    if case == "peer-before-delivery":
        covered()
        route = svc.process_message(PLAYER, "recheck", scene, source.source_id, 1)
        assert route["handler_decision"]["decision"]["reason"] == "peer_response"
        assert route["handler"] is None and len(performer.requests) == 1
        assert not svc.delivery.pending(ADMIN, scene)
        with pytest.raises(WorkflowError, match="HANDLER_PEER_RESPONSE"):
            svc.delivery.deliver(ADMIN, "do-not-interrupt", scene, draft)
    else:
        receipt = svc.delivery.deliver(ADMIN, "send-personal", scene, draft)
        assert svc.delivery.deliver(ADMIN, "retry", scene, draft) == receipt
        _, repeated = send(observer, scene, "repeat", text=CUE, fictional_channel="comms")
        propose(svc, scene, repeated, "repeat-review", **fields)
        assert (
            svc.process_message(PLAYER, "repeat-route", scene, repeated.source_id, 1)["handler"]
            is None
        )
    assert state(game) == before


def test_actual_listener_can_report_back_after_handler_takes_an_action(observed):
    observer, scene, _, game, *_ = observed
    svc, performer = service(observer)
    handler, original = roles(observer, scene)
    other = peer_actor(observer, scene)
    request = "The briefing copy still has an empty console assignment."
    _, source = send(observer, scene, "problem", text=request, fictional_channel="comms")
    svc.context.record(
        ADMIN,
        "known-problem",
        scene,
        source.source_id,
        0,
        known_by=(handler, original, other),
        topic="tactical",
    )
    first = svc.process_message(PLAYER, "first", scene, source.source_id, 1)["handler"]["id"]
    approve(svc, scene, first, original, other)
    initial = svc.delivery.deliver(ADMIN, "send-action", scene, first)

    answer = "The control desk assigned us the north console."
    _, report = send(
        observer, scene, "report", viewer=OTHER, text=answer, fictional_channel="comms"
    )
    proof = svc.context.record(
        ADMIN,
        "actual-report",
        scene,
        report.source_id,
        2,
        known_by=(handler, original, other),
        topic="general",
    )["id"]
    propose(
        svc,
        scene,
        report,
        "follow-up",
        kind="follow_up",
        action="RESPOND",
        speech_quote=answer,
        source_refs=(proof,),
        concern_id=initial["id"],
    )
    follow = svc.process_message(OTHER, "reply", scene, report.source_id, 1)
    assert follow["handler_decision"]["decision"]["reason"] == "reviewed_follow_up"
    draft = follow["handler"]["id"]
    with pytest.raises(WorkflowError, match="HANDLER_CONCERN_AUDIENCE"):
        approve(svc, scene, draft, other)
    approve(svc, scene, draft, original, other)
    svc.delivery.deliver(ADMIN, "result", scene, draft)
    assert "north console" in svc.delivery.contributions(PLAYER, scene)[-1]["text"]
    assert svc.process_message(OTHER, "again", scene, report.source_id, 1)["handler"] is None
    assert "north console" not in performer.requests[0].model_dump_json()
    assert not state(game).handler_plays


def test_gm_heat_answers_have_actual_owned_cost_states_and_no_fiction(observed):
    from test_m2_game import start

    observer, scene, _, game, worker, gateway, dice = observed
    svc, performer = service(observer)
    _, explanation = send(
        observer,
        scene,
        "heat-rule",
        fictional_channel="comms",
        text="GM, can you explain whether that correction costs Heat?",
    )
    before = state(game)
    decision = svc.process_message(PLAYER, "explain", scene, explanation.source_id, 1)
    assert decision["gm"]["reply"]["gm_rule"]["status"] == "no_cost"
    assert decision["gm"]["reply"]["gm_rule"]["amount"] == 0
    assert not performer.requests and dice.calls == 0 and state(game) == before
    _, unclear = send(
        observer,
        scene,
        "heat-unclear",
        fictional_channel="comms",
        text="GM, did I spend Heat on the last thing?",
    )
    clarification = svc.process_message(PLAYER, "clarify", scene, unclear.source_id, 1)
    assert clarification["gm"]["reply"]["gm_rule"]["status"] == "needs_source"

    with observer.store.transaction() as c:
        native = state(game)
        native.sheets["2"].heat = 3
        game.event(c, 1, "heat-fixture", "synthetic.heat", native)
    action = start(game, heat=2)
    pending = svc.action_heat(PLAYER, scene, action)
    assert pending.status == "pending" and pending.amount == 2 and dice.calls == 0
    assert svc.action_heat(OTHER, scene, action).status == "needs_source"
    tick(worker, gateway)
    result = svc.action_heat(PLAYER, scene, action)
    assert result.status == "committed" and result.amount == 2 and result.receipt_id
    assert dice.calls == 1 and state(game).sheets["2"].heat == 1
