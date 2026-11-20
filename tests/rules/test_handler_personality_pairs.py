"""Matched Handler personalities with the same native mission and clock."""

import json
from pathlib import Path

import pytest
from test_director_continuity import roles
from test_director_model_adapters import Recorder
from test_director_observation import send
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_timed_handler_archetypes import timed_archetype

from girlframe.ai.model_adapters import ModelHandlerNeeds
from girlframe.engine.m3_handler_state import HandlerNotes
from girlframe.services.m3_handler_creation import HandlerCreationService
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
    assert default.persona is None and default.character_notes is None
    assert name not in default.model_dump_json() and background not in default.model_dump_json()
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
