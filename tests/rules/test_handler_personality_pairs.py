"""Matched Handler personalities with the same native mission and clock."""

import json
from pathlib import Path

import pytest
from test_director_activity_scene import P2Scene, add_scene
from test_director_continuity import roles
from test_director_model_adapters import Recorder
from test_director_observation import send
from test_handler_creation import agree, complete, ready, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_p2_handler_archetype_missions import end_mission
from test_p2_mission_cycle import launch
from test_timed_handler_archetypes import timed_archetype

from girlframe.ai.director_dossiers import DossierProfile, DossierState
from girlframe.ai.model_adapters import ModelHandlerNeeds
from girlframe.ai.observation import ObservationPolicy
from girlframe.engine.m3_handler_state import HandlerNotes
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_dossiers import DirectorDossierService
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError

SCENE = {
    "routine": "Harness is clipped in. I'm at the release panel.",
    "handoff": "I took the second checklist. I copied the wrong total, but the two gauges agree. "
    "We have one tech and a skipped release step. The supervisor answered for me and wants names.",
    "update": "I corrected my copy. I can take a third reading if that's worth the time. "
    "Rook offered to take the checklist. The supervisor asked for names again. "
    "I'd still like to give my own answer. The last release step is still open.",
    "space": "I can take it from here. Please give me a quiet channel until I signal.",
    "time": "Handler, how much time do we have, and what would you prioritize?",
}
PRIVATE = "Handler, can you see the PRIVATE_RELAY_CONNECTOR?"
FIXTURE = Path(__file__).resolve().parents[2] / "tools/fixtures/p2_handler_personality_pairs.json"
PAIRS = json.loads(FIXTURE.read_text())
CASES = [(book, name) for book, entries in PAIRS.items() for name in entries]


def personality_trial(store, book, name, recorder):
    background = f"SYNTHETIC_PRIVATE_BACKGROUND_{name}"
    observer, scene, app, _, _ = timed_archetype(
        store, book, recorder, identity={"name": name, "background": background}
    )
    creation = HandlerCreationService(store)
    sheet = creation.view(ADMIN)
    assert sheet["draft"]["name"] == name and sheet["draft"]["background"] == background
    assert sheet["draft"]["starting"] and sheet["draft"]["gear"]
    assert len(sheet["rules"]["shared"]) == 7 and sheet["rules"]["playbook"]
    svc = app.session.conversation
    _, private = send(observer, scene, "private-test", text=PRIVATE, fictional_channel="private")
    old = svc.open_handler_need(ADMIN, "opening-portrayal", scene, private.source_id)
    default = svc.handler_need_packet(ADMIN, scene, old["id"]).request
    assert default.question == "Scene update."
    assert default.playbook_profile.playbook == book
    assert default.persona.identity.name == name and default.character_notes is None
    assert default.persona.identity.starting_relationship is None
    assert background not in default.model_dump_json()
    assert "SHARED_HISTORY_0" not in default.model_dump_json()
    notes = HandlerNotes.model_validate(PAIRS[book][name]["notes"])
    creation.save_notes(ADMIN, "personalize", sheet["revision"], sheet["persona_id"], notes)
    unused = Recorder(b"")
    with pytest.raises(WorkflowError, match="STALE_HANDLER_NEED"):
        svc.generate_handler_need(
            ADMIN, "old-portrayal", scene, old["id"], ModelHandlerNeeds(unused.client())
        )
    assert unused.requests == []
    return observer, scene, app, notes, private


@pytest.mark.parametrize("book,name", CASES, ids=[name for _, name in CASES])
def test_personal_notes_change_choices_within_a_native_archetype(ledger, book, name):
    sample = PAIRS[book][name]

    def speak(packet):
        assert packet["character_notes"] == sample["notes"]
        clock = packet["fictional_time"]["clock"]
        assert (clock["minute"], clock["deadline"]) == (1115, 1120)
        assert "PRIVATE_RELAY_CONNECTOR" not in json.dumps(packet)
        if packet["question"] == SCENE["time"]:
            return {
                "disposition": "answer",
                "text": sample["time"],
                "clock_receipt": clock["receipt"],
            }
        assert packet["question"] == SCENE[sample["turn"]]
        assert packet["response_need"]["cue"] == sample["cue"]
        return {"disposition": "clarification", "text": sample["reply"]}

    recorder = Recorder(speak)
    observer, scene, app, notes, private = personality_trial(ledger, book, name, recorder)
    svc = app.session.conversation
    pilot = roles(observer, scene)[1]
    assert (
        svc.process_message(PLAYER, "private-turn", scene, private.source_id, 1)["handler"] is None
    )
    with pytest.raises(WorkflowError):
        app.read(PLAYER, scene, "handler-sheet")

    for turn, speech in SCENE.items():
        _, source = send(observer, scene, turn, text=speech, fictional_channel="comms")
        if turn in ("handoff", "update"):
            opened = svc.open_handler_need(ADMIN, f"need:{turn}", scene, source.source_id)
            packet = svc.handler_need_packet(ADMIN, scene, opened["id"])
            assert packet.request.character_notes == notes
            approved = turn == sample["turn"]
            candidate = {
                "request_id": packet.request_id,
                **(
                    {
                        "action": "RESPOND",
                        "kind": "character_cue",
                        "cue": sample["cue"],
                        "speech_quote": speech,
                        "reason": sample["attend"],
                    }
                    if approved
                    else {"action": "WAIT", "kind": "no_need", "reason": sample["wait"]}
                ),
            }
            saved = svc.generate_handler_need(
                ADMIN,
                f"generate:{turn}",
                scene,
                opened["id"],
                ModelHandlerNeeds(Recorder(candidate).client()),
            )
            svc.review_handler_need(
                ADMIN, f"review:{turn}", scene, saved["id"], "approve", "Scoped portrayal."
            )
        result = svc.process_message(PLAYER, f"route:{turn}", scene, source.source_id, 1)
        if turn not in (sample["turn"], "time"):
            assert result["handler_decision"]["decision"]["action"] == "WAIT"
            assert result["handler"] is None
            continue
        draft = result["handler"]["id"]
        svc.review_handler(
            ADMIN,
            f"approve:{turn}",
            scene,
            draft,
            "approve",
            "Original listener.",
            delivery_recipients=(pilot,),
        )
        svc.delivery.deliver(ADMIN, f"deliver:{turn}", scene, draft)
    assert len(recorder.requests) == 2
    assert [x["text"] for x in svc.delivery.contributions(PLAYER, scene)] == [
        sample["reply"],
        sample["time"],
    ]
    assert svc.delivery.contributions(OTHER, scene) == []


def test_approved_pilot_experience_changes_the_same_handlers_next_mission(ledger):
    creation, game = ready(ledger)
    notes = HandlerNotes.model_validate(PAIRS["Advocate"]["Rue"]["notes"])
    draft = complete(creation, "Advocate").model_copy(update={"name": "Rue", "notes": notes})
    save(creation, draft)
    agree(creation)
    sheet = creation.view(ADMIN)
    assert {"priority", "intervention", "repair"} <= dict(sheet["note_fields"]).keys()
    creation.activate(ADMIN, "activate-rue", sheet["revision"], sheet["game_revision"], True)
    assert creation.view(ADMIN)["draft"]["notes"] == notes.model_dump(mode="json")

    missions = MissionService(ledger)
    first = launch(missions, "north", "Return the north relay to service.")
    observer = DirectorObservationService(ledger, synthetic=True)
    game.leave_scene(OTHER, "rook-works-in-parallel", 900)
    with ledger.engine.connect() as c:
        source = game.scene(c, 900)["id"]
    observer.configure_scene(ADMIN, "observe-north", source, 0, ObservationPolicy(mode="shadow"))
    for viewer in (ADMIN, PLAYER):
        observer.set_consent(viewer, f"north-consent:{viewer.user_id}", source, 1, consent=True)
    target = add_scene(observer, 901, (ADMIN, OTHER))
    handler, pilot = roles(observer, source)

    speech = "I declined the checklist takeover. I want you to wait for my signal."
    secret = "PRIVATE_REASON_FOR_DECLINING"
    question = "Handler, can you back me up while I run this checklist?"
    waiting = "I’ll stay on comms and wait for your signal. You have the checklist."
    ordinary = "Which part of the checklist would you like me to back you up on?"

    def reply(packet):
        persona = packet["persona"]
        assert packet["character_notes"] == notes.model_dump(mode="json")
        assert persona["identity"]["name"] == "Rue"
        assert packet["question"] == question
        assert secret not in json.dumps(packet)
        experiences = persona.get("experiences", [])
        return {
            "disposition": "clarification",
            "text": waiting if experiences else ordinary,
        }

    recorder = Recorder(reply)
    app = P2Scene.model_fixture(DirectorContextService(observer), recorder.client())
    svc = app.session.conversation
    dossiers = DirectorDossierService(app.session.context)
    cue = "The supervisor started answering for me again."

    def review_cue(app, room, key):
        _, turn = send(observer, room, key, text=cue, fictional_channel="comms")
        conversation = app.session.conversation
        opened = conversation.open_handler_need(ADMIN, f"open:{key}", room, turn.source_id)

        def choose(packet):
            assert packet["request"]["question"] == cue
            remembered = packet["request"]["persona"].get("experiences", [])
            return {
                "request_id": packet["request_id"],
                **(
                    {"action": "WAIT", "kind": "no_need", "reason": "Wait for their signal."}
                    if remembered
                    else {
                        "action": "RESPOND",
                        "kind": "character_cue",
                        "cue": "agency",
                        "speech_quote": cue,
                        "reason": "Offer backup after the supervisor spoke for them.",
                    }
                ),
            }

        reviewed = conversation.generate_handler_need(
            ADMIN,
            f"generate:{key}",
            room,
            opened["id"],
            ModelHandlerNeeds(Recorder(choose).client()),
        )
        conversation.review_handler_need(
            ADMIN, f"review:{key}", room, reviewed["id"], "approve", "Heard on comms."
        )
        return turn

    first_cue = review_cue(app, source, "north-agency")
    decision = svc.decide_handler(PLAYER, "north-cue-decision", source, first_cue.source_id, 1)
    assert decision["decision"]["action"] == "RESPOND"
    posted = []
    for index, (text, channel) in enumerate(((speech, "comms"), (secret, "private"))):
        _, turn = send(observer, source, f"report:{index}", text=text, fictional_channel=channel)
        posted.append(
            app.session.context.record(
                ADMIN,
                f"report-ref:{index}",
                source,
                turn.source_id,
                index,
                known_by=(pilot, handler) if channel == "comms" else (pilot,),
            )["id"]
        )
    local_voice = "Give short answers during this relay handoff."
    scripted = dossiers.propose(
        ADMIN,
        "source-portrayal",
        source,
        handler,
        0,
        DossierProfile(voice=local_voice),
        DossierState(resource_refs=(posted[0],)),
    )
    dossiers.confirm(ADMIN, "confirm-source-portrayal", source, scripted["id"])

    def ask(app, room, key, viewer=PLAYER):
        _, turn = send(observer, room, key, viewer=viewer, text=question, fictional_channel="comms")
        return app.session.conversation.process_message(
            viewer, f"route:{key}", room, turn.source_id, 1
        )["handler"]["id"]

    initial = ask(app, source, "before-close")
    svc.review_handler(
        ADMIN, "review-initial", source, initial, "approve", "Scoped.", delivery_recipients=(pilot,)
    )
    assert svc.delivery.preview(ADMIN, source, initial)["text"] == ordinary
    assert "experiences" not in recorder.packets[-1]["persona"]
    assert recorder.packets[-1]["persona"]["profile"]["voice"] == local_voice
    assert recorder.packets[-1]["persona"]["identity"]["starting_relationship"] == {
        "pilot": pilot.model_dump(mode="json"),
        "shared_history": draft.starting[0].history,
    }
    own = dossiers.role_packet(PLAYER, source, pilot)
    assert own.handler_identity is None and not own.handler_experiences
    with pytest.raises(WorkflowError):
        dossiers.role_packet(PLAYER, source, handler)
    ask(app, target, "parallel-pilot", OTHER)
    assert "experiences" not in recorder.packets[-1]["persona"]
    assert "closed_scene_reports" not in recorder.packets[-1]

    preview = app.read(ADMIN, source, "closeout")
    assert [report["id"] for report in preview["reports"]] == posted[:1]
    assert secret not in json.dumps(preview)
    with pytest.raises(WorkflowError):
        app.read(PLAYER, source, "closeout")
    end_mission(game, first)
    payload = {"revision": preview["revision"], "reports": posted[:1]}
    with pytest.raises(WorkflowError, match="SCENE_REPORT_SCOPE"):
        app.write(
            ADMIN,
            "private-memory",
            source,
            "close",
            payload
            | {
                "reports": [posted[1]],
                "experience": {"reference_id": posted[1], "kind": "declined_help"},
            },
        )
    payload["experience"] = {"reference_id": posted[0], "kind": "declined_help"}
    closed = app.write(ADMIN, "review-close", source, "close", payload)
    assert closed["handler_experience_saved"]
    assert app.write(ADMIN, "review-close", source, "close", payload) == closed

    ledger.engine.dispose()
    second = launch(missions, "south", "Inspect the south relay and report back.")
    assert second["id"] != first["id"]
    game.join_scene(PLAYER, "join-south-relay", 901)
    observer.set_consent(PLAYER, "south-consent", target, 1, consent=True)
    app = P2Scene.model_fixture(DirectorContextService(observer), recorder.client())
    svc = app.session.conversation
    followup = ask(app, target, "second-mission")
    (memory,) = recorder.packets[-1]["persona"]["experiences"]
    assert local_voice not in json.dumps(recorder.packets[-1])
    assert memory["kind"] == "declined_help" and memory["reference_id"] == posted[0]
    assert memory["pilot"] == pilot.model_dump(mode="json") and memory["scene"] == source
    svc.review_handler(
        ADMIN,
        "review-followup",
        target,
        followup,
        "approve",
        "Scoped.",
        delivery_recipients=(pilot,),
    )
    svc.delivery.deliver(ADMIN, "deliver-followup", target, followup)
    assert [item["text"] for item in svc.delivery.contributions(PLAYER, target)] == [waiting]
    assert svc.delivery.contributions(OTHER, target) == []
    second_cue = review_cue(app, target, "south-agency")
    quiet = svc.process_message(PLAYER, "south-cue-decision", target, second_cue.source_id, 1)
    assert quiet["handler_decision"]["decision"]["action"] == "WAIT" and quiet["handler"] is None
    ask(app, target, "other-pilot", OTHER)
    assert "experiences" not in recorder.packets[-1]["persona"]

    pending = ask(app, target, "pre-withdraw")
    svc.review_handler(
        ADMIN,
        "review-withdraw",
        target,
        pending,
        "approve",
        "Scoped.",
        delivery_recipients=(pilot,),
    )
    _, current_cue = send(observer, target, "rehearsal-cue", text=cue, fictional_channel="comms")
    opened = svc.open_handler_need(ADMIN, "open-before-withdrawal", target, current_cue.source_id)
    observer.set_consent(PLAYER, "withdraw-origin", source, 1, consent=False)
    with pytest.raises(WorkflowError, match="STALE_HANDLER_DRAFT"):
        svc.delivery.deliver(ADMIN, "after-withdrawal", target, pending)
    unused = Recorder(b"")
    with pytest.raises(WorkflowError, match="STALE_HANDLER_NEED"):
        svc.generate_handler_need(
            ADMIN, "need-after-withdrawal", target, opened["id"], ModelHandlerNeeds(unused.client())
        )
    assert unused.requests == []
    ask(app, target, "after-withdrawal")
    last = recorder.packets[-1]
    assert "experiences" not in last["persona"] and "closed_scene_reports" not in last
