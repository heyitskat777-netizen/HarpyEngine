"""Owner review of a native Girl's suggested Play uses her current sheet and scene."""

import json

import pytest
from test_activity_shadow_readiness import configure, opt, publish_opening
from test_activity_shadow_readiness import fixture as fixture
from test_director_activity_scene import P2Scene, activity_adapter
from test_director_continuity import roles
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import start, state

from girlframe.ai.model_transport import ModelLimits, OpenAIResponses
from girlframe.engine.campaign_opening import CampaignSeats, Opening, PlannedAIPilot
from girlframe.engine.pilot_portrayal import PILOT_PORTRAYALS
from girlframe.services.campaign_difficulty import EVENT
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError


def test_native_ai_girl_play_suggestion_survives_reopen_and_requires_its_owner(fixture):
    trial, scene, game, _, _, _, dice = fixture
    context = trial.session.context
    opt(trial, scene)
    configure(trial, scene)
    _, pilot = roles(trial.session.observer, scene)
    sheet = state(game).sheets[str(PLAYER.user_id)]
    portrayal = PILOT_PORTRAYALS[0].model_copy(
        update={"girl_playbook": sheet.girl, "frame_playbook": sheet.frame}
    )
    plan = Opening(
        scene="native-introduction",
        channel=901,
        handler=ADMIN.user_id,
        handler_control="player",
        audience=(ADMIN.user_id, PLAYER.user_id, OTHER.user_id),
        plan="native-ai-plan",
        goals="Keep the relief pump staffed.",
        difficulty="normal",
        introduction="Check in.",
        first_mission_day=4,
        seats=CampaignSeats(
            player_count=2,
            ai_pilots=(PlannedAIPilot(callsign="Pump watch", portrayal=portrayal),),
        ),
    )
    with game.store.transaction() as c:
        game.store._audit(c, ADMIN.user_id, "native-plan", EVENT, plan.model_dump(mode="json"))
    opening = publish_opening(trial, scene, ADMIN)
    assert trial.read(ADMIN, scene, "scene-initiative") == {"options": []}

    actor = pilot.model_dump(mode="json")
    sheet_draft = trial.write(
        PLAYER,
        "native-setup",
        "",
        "portrayal-draft",
        {"actor": actor, "version": 0, "character_setup": {"drive": "Hold the pump on pressure."}},
    )
    trial.write(
        PLAYER,
        "own-character-setup",
        "",
        "portrayal-confirm",
        {"actor": actor, "id": sheet_draft["id"]},
    )
    link = trial.write(
        PLAYER,
        "native-seat",
        scene,
        "pilot-dossier-propose",
        {
            "actor": actor,
            "version": 1,
            "origin": {"plan": plan.plan, "callsign": "Pump watch"},
        },
    )
    assert trial.read(ADMIN, scene, "scene-initiative") == {"options": []}
    trial.write(PLAYER, "confirm-native-seat", scene, "dossier-confirm", {"id": link["id"]})

    play = {
        "id": "keep_your_head",
        "label": "Keep Your Head",
        "destination": "scene",
        "trigger": "When you try to endure.",
        "control": "keep_your_head",
        "room": "relay",
    }

    def project(c, row, owner):
        active = load_state(c, game.store.campaign_id).sheets.get(owner.entity)
        if owner != pilot or active is None or active.character_id != owner.incarnation:
            return ()
        view = game.scene_info(PLAYER, int(row["channel_id"]))
        lock = view["lock"]
        return (play,) if view["joined"] and (lock is None or lock["state"] == "released") else ()

    requests = []

    def respond(request, timeout):
        body = json.loads(request.data)
        assert body["store"] is False
        packet = json.loads(body["input"][1]["content"])["packet"]
        assert "request_id" not in packet
        requests.append(packet)
        options = packet["role"]["native_plays"]
        candidate = {
            "kind": "SCENE_OFFER" if options else "WAIT",
            "text": "I brace the pump handle against my knee." if options else "",
            "rationale": "Stay on the relief pump until another pilot takes over.",
            "play_id": options[0]["id"] if options else None,
        }
        return json.dumps(
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": json.dumps(candidate)}],
                    }
                ],
            }
        ).encode()

    client = OpenAIResponses(
        model="synthetic-native-girl",
        api_key="synthetic",
        limits=ModelLimits(attempts=3, output_tokens=500),
        post=respond,
    )
    context.native_play_projection = project
    app = P2Scene.model_fixture(context, handler=client, pilot_batch=client)
    (option,) = app.read(ADMIN, scene, "scene-initiative")["options"]
    assert option["source"] == {"kind": "opening", "id": opening["receipt"]}
    assert option["actor"] == actor and option["label"] == sheet.callsign
    before = state(game)
    request = app.write(
        ADMIN, "native-initiative", scene, "scene-initiative-open", {"option": option["id"]}
    )
    saved = app.write(
        ADMIN, "native-proposal", scene, "reaction-generate", {"request": request["id"]}
    )
    assert requests[0]["role"]["native_plays"] == [play]
    assert (
        requests[0]["role"]["initiative"]["agenda"]["plan"]["stake"] == "Hold the pump on pressure."
    )
    assert not saved["effects_applied"] and app.timeline(OTHER, scene)["entries"] == []
    decision = {
        "proposal": saved["id"],
        "decision": "approve",
        "reason": "My character is holding the pump.",
        "recipients": [],
    }
    for other in (ADMIN, OTHER):
        with pytest.raises(WorkflowError, match="REACTION_NOT_OWNED"):
            app.read(other, scene, "npc-owner-review", saved["id"])
        with pytest.raises(WorkflowError, match="REACTION_NOT_OWNED"):
            app.write(other, f"wrong-owner:{other.user_id}", scene, "npc-review", decision)
    approval = app.write(PLAYER, "owner-approval", scene, "npc-review", decision)
    assert not approval["effects_applied"]
    assert dice.calls == 0 and state(game) == before

    game.store.engine.dispose()
    restored = activity_adapter.local_fixture_director(game, activity_shadow=True)
    restored.session.context.native_play_projection = project
    reopened = P2Scene.model_fixture(restored.session.context, handler=client, pilot_batch=client)
    preview = reopened.read(PLAYER, scene, "npc-owner-review", saved["id"])
    assert preview["native_play"] == play and preview["native_play_approved"]
    (pending,) = reopened.read(PLAYER, scene, "work")["reactions"]
    assert pending["status"] == "approved_native_suggestion"
    assert saved["id"] not in [x["id"] for x in reopened.read(OTHER, scene, "work")["reactions"]]

    start(game, context="Hold the relief pump handle while the pressure rises.")
    assert reopened.read(PLAYER, scene, "npc-owner-review", saved["id"]) == {
        "id": saved["id"],
        "status": "stale_reopen_source",
        "effects_applied": False,
    }
    revised = reopened.write(
        ADMIN, "fresh-initiative", scene, "scene-initiative-open", {"option": option["id"]}
    )
    assert revised["id"] != request["id"]
    reopened.write(ADMIN, "new-proposal", scene, "reaction-generate", {"request": revised["id"]})
    assert requests[1]["role"]["native_plays"] == []
