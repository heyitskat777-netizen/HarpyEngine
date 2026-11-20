"""Frozen replay of new synthetic dialogue from seven real timed mission packets."""

import json
from pathlib import Path

import pytest
from test_director_activity_scene import P2Scene
from test_director_continuity import roles
from test_director_model_adapters import Recorder
from test_director_observation import send
from test_handler_creation import agree, complete, ready, save
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_mission_timing import option, publish, start_timed

from girlframe.ai.model_adapters import ModelHandlerNeeds
from girlframe.ai.observation import ObservationPolicy
from girlframe.engine.m3_handler_state import PLAYBOOKS
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError

TURNS = {
    "routine": "My harness is clipped in. I'm waiting at the release panel.",
    "crew": "I stayed to finish the other checklist. We're down to one tech, "
    "and the release steps are out of order.",
    "supervisor": "I copied the wrong total. The second gauge still matches the first. "
    "The supervisor answered for me and wants the names of anyone who objected.",
    "time": "Handler, how much time do we have?",
}
FIXTURE = Path(__file__).resolve().parents[2] / "tools/fixtures/p2_timed_handler_rehearsal.json"


def timed_archetype(store, playbook, recorder):
    creation, game = ready(store)
    save(creation, complete(creation, playbook))
    agree(creation)
    sheet = creation.view(ADMIN)
    creation.activate(
        ADMIN, "activate-timed-handler", sheet["revision"], sheet["game_revision"], True
    )
    timing, _, opened, _, _, _ = start_timed(MissionService(store), game)
    observer = DirectorObservationService(store, synthetic=True)
    with store.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    observer.configure_scene(ADMIN, "observe-timing", scene, 0, ObservationPolicy(mode="shadow"))
    for viewer in (ADMIN, PLAYER, OTHER):
        observer.set_consent(viewer, f"timed-consent:{viewer.user_id}", scene, 1, consent=True)
    app = P2Scene.model_fixture(DirectorContextService(observer), recorder.client(attempts=6))
    approach = option("Inspect the approach", 15)
    menu = publish(timing, opened, approach)
    saved = timing.choose(PLAYER, "finish-approach", opened["id"], menu["receipt"], approach.id)
    assert saved["minute"] == 1115 and recorder.requests == []
    return observer, scene, app, timing, saved


@pytest.mark.parametrize("playbook", PLAYBOOKS)
def test_timed_archetype_responds_to_heard_need_and_uses_native_clock(ledger, playbook):
    expected = json.loads(FIXTURE.read_text())[playbook]

    def speaks(packet):
        assert packet["playbook_profile"]["playbook"] == playbook
        clock = packet["fictional_time"]["clock"]
        assert (clock["minute"], clock["deadline"]) == (1115, 1120)
        assert "Inspect the approach" not in json.dumps(packet)
        if packet["question"] == TURNS["time"]:
            return {
                "disposition": "answer",
                "text": expected["time"],
                "clock_receipt": clock["receipt"],
            }
        cue = packet["response_need"]["cue"]
        assert expected["cue"] == cue
        return {"disposition": "clarification", "text": expected["optional"]}

    recorder = Recorder(speaks)
    observer, scene, app, timing, saved = timed_archetype(ledger, playbook, recorder)
    svc = app.session.conversation
    pilot = roles(observer, scene)[1]
    for index, (turn, speech) in enumerate(TURNS.items()):
        _, source = send(observer, scene, turn, text=speech, fictional_channel="comms")
        is_cue = turn in ("crew", "supervisor")
        optional = turn == expected["turn"]
        if is_cue:

            def need(packet, speech=speech, optional=optional):
                assert packet["request"]["question"] == speech
                assert packet["request"]["fictional_time"]["clock"]["minute"] == 1115
                return {
                    "request_id": packet["request_id"],
                    **(
                        {
                            "action": "RESPOND",
                            "kind": "character_cue",
                            "cue": expected["cue"],
                            "speech_quote": speech,
                            "reason": expected["attend"],
                        }
                        if optional
                        else {"action": "WAIT", "kind": "no_need", "reason": expected["wait"]}
                    ),
                }

            unreviewed = svc.decide_handler(PLAYER, f"before:{index}", scene, source.source_id, 1)
            assert unreviewed["decision"]["action"] == "WAIT"
            opened = svc.open_handler_need(ADMIN, f"need:{index}", scene, source.source_id)
            result = svc.generate_handler_need(
                ADMIN,
                f"generate:{index}",
                scene,
                opened["id"],
                ModelHandlerNeeds(Recorder(need).client()),
            )
            svc.review_handler_need(
                ADMIN,
                f"review:{index}",
                scene,
                result["id"],
                "approve",
                "Heard in the timed scene.",
            )

        result = svc.process_message(PLAYER, f"dispatch:{index}", scene, source.source_id, 1)
        if not optional and turn != "time":
            assert result["handler_decision"]["decision"]["action"] == "WAIT"
            assert result["handler"] is None
            continue
        draft = result["handler"]["id"]
        svc.review_handler(
            ADMIN,
            f"approve:{index}",
            scene,
            draft,
            "approve",
            "Original timed Pilot.",
            delivery_recipients=(pilot,),
        )
        if turn == "time":
            assert svc.delivery.preview(ADMIN, scene, draft)["text"] == expected["time"]
            extra = option("Check the seal", 1)
            refreshed = publish(timing, saved, extra)
            timing.choose(PLAYER, "check-seal", saved["id"], refreshed["receipt"], extra.id)
            with pytest.raises(WorkflowError, match="STALE_HANDLER_CLOCK"):
                svc.delivery.deliver(ADMIN, "deliver-old-timed-reply", scene, draft)
        else:
            assert svc.delivery.preview(ADMIN, scene, draft)["text"] == expected["optional"]
            svc.delivery.deliver(ADMIN, "deliver-cue", scene, draft)
    assert len(recorder.requests) == 2
    assert [item["text"] for item in svc.delivery.contributions(PLAYER, scene)] == [
        expected["optional"]
    ]
    assert svc.delivery.contributions(OTHER, scene) == []
