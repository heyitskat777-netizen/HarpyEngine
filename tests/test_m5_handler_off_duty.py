"""Native sheet notes and a scoped, optional Off-Duty Handler contribution."""

import json

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m5_activity_batch import WAIT, deliver_handler, handler_batch_line
from test_m5_activity_batch import relay as relay
from test_session_zero import FACILITATOR

from girlframe.ai.handler_initiative import OFF_DUTY_PERSONAL, off_duty_initiative
from girlframe.engine.m3_handler_state import HandlerNotes
from girlframe.scenes.opening import SceneOpening


@pytest.mark.parametrize("relay", ["Scientist"], indirect=True)
def test_scoped_off_duty_hook_uses_own_saved_notes_and_can_be_declined_by_wait(relay):
    assert HandlerNotes.model_validate({"voice": "Quiet."}).model_dump() == {"voice": "Quiet."}
    notes = HandlerNotes(
        personal_habit="I play a tin whistle on nights I can't sleep.",
        obligation="I have promised to fix my sister's whistle.",
        relationship_tension="I want to ask Lark if we can play together, but I dread the answer.",
        off_duty_cue="tin whistle",
    )
    sheet = relay.app.read(ADMIN, relay.scene, "persona-setup")["sheet"]
    relay.app.write(
        ADMIN,
        "save-off-duty-notes",
        relay.scene,
        "persona-notes",
        {
            "revision": sheet["revision"],
            "persona_id": sheet["persona_id"],
            "notes": notes.model_dump(),
        },
    )
    relay.store.engine.dispose()
    assert relay.app.read(ADMIN, relay.scene, "persona-setup")["sheet"]["draft"]["notes"] == (
        notes.model_dump()
    )
    assert relay.app.read(PLAYER, relay.scene, "persona-setup")["sheet"] is None

    relay.line("mission-whistle", PLAYER, "I brought a tin whistle in my pocket.")
    assert relay.run_batch()["status"] == "wait"
    assert "initiative" not in relay.calls[-1]

    def open_barracks(key, *, off_duty=None, intro="The overflow kettle is off."):
        opening = relay.app.read(FACILITATOR, relay.scene, "scene-opening")["draft"]
        relay.app.write(
            FACILITATOR,
            key,
            relay.scene,
            "scene-opening-publish",
            {
                "revision": opening["revision"],
                "draft": {
                    "location": "Barracks",
                    "intro": intro,
                    "details": [],
                    **({"off_duty": off_duty} if off_duty is not None else {}),
                },
            },
        )

    open_barracks("mark-off-duty", off_duty=True)
    open_barracks("existing-client-update")
    opening = relay.app.read(PLAYER, relay.scene, "scene-opening")["opening"]
    assert opening["off_duty"] is True
    room = SceneOpening.model_validate_json(json.dumps(opening)).model_copy(
        update={"intro": "A tin whistle is hanging from the peg."}
    )
    assert off_duty_initiative(notes, room, "source-from-actual-pilot", "The kettle's off.")

    relay.line("private-whistle", OTHER, "One tin whistle tucked in my pocket.", channel="private")
    relay.line("barracks-banter", PLAYER, "Should we put another kettle on, Kite?")
    assert relay.run_batch()["status"] == "wait"
    assert "initiative" not in relay.calls[-1]

    relay.line("shared-whistle", PLAYER, "I thought I heard a tin whistle in the hall.")
    assert relay.run_batch()["status"] == "wait"
    packet = relay.calls[-1]
    assert packet["initiative"]["prompt"] == OFF_DUTY_PERSONAL
    assert packet["character_notes"]["personal_habit"] == notes.personal_habit
    assert "tucked in my pocket" not in str(packet)

    def answer(packet):
        assert packet["initiative"]["prompt"] == OFF_DUTY_PERSONAL
        return handler_batch_line(
            packet,
            "character_cue",
            "Three notes like this? I keep one for nights I can't sleep.",
            cue="personal",
            fiction={"own_action": "I hum three notes."},
        )

    relay.output = answer
    relay.line("shared-whistle-again", PLAYER, "The tin whistle just started up again.")
    draft = relay.run_batch()["draft_id"]
    relay.approve(draft)
    deliver_handler(relay, draft, "deliver-personal-hook")
    assert "I hum three notes." in str(relay.app.timeline(PLAYER, relay.scene))
    assert "I hum three notes." not in str(relay.app.timeline(OTHER, relay.scene))

    relay.output = WAIT
    relay.line("another-listener", OTHER, "I hear the tin whistle too.")
    assert relay.run_batch()["status"] == "wait"
    assert "initiative" not in relay.calls[-1]
