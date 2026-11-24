"""An offline encounter with two approved AI Pilots and both alternate opponents."""

from types import SimpleNamespace

import pytest
from ai_native_plays import ActivityNativePlays
from test_activity_shadow_readiness import publish_opening, submission
from test_alternate_initiative import activity, native_case, setup_initiative, submit_choice
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_scene_beneath_followups import adapter

from girlframe.engine.campaign_opening import CampaignSeats, Opening, PlannedAIPilot
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.pilot_portrayal import PILOT_PORTRAYALS
from girlframe.services.campaign_difficulty import EVENT
from girlframe.services.m3_access import load_registry
from girlframe.services.onboarding import WorkflowError


def test_ai_pilots_meet_a_harpy_and_a_silent_gorgon(ledger):
    game, worker, gateway, _, gorgon, _, _ = native_case(ledger, "gorgon", harpy=True)
    harpy = ActorRef(kind="external_pilot", entity="actual-pitted-harpy")
    pilot, wing = (current_ref(state(game), viewer.user_id) for viewer in (PLAYER, OTHER))
    description = (
        "The Gorgon hooks one forelimb over the hatch lip. Its other limbs stay low, "
        "raking white dust off the threshold in a short fan."
    )
    harpy_line = "Leave me the light. When I can see your hands, I'll tell you what I saw."
    wing_line = "The left rail's clear. I can mark a way out if the shutter jams."
    drives = {
        gorgon: "Hold the threshold while it can feel the air moving.",
        harpy: "Stay in the light until the pilots show their hands.",
    }
    selections = {}
    modeled = []

    class EncounterModel:
        def generate(self, instructions, packet, response):
            role = packet["role"]
            actor = ActorRef.model_validate(role["actor"])
            if actor in drives:
                assert role["dossier"]["profile"]["character_setup"]["drive"] == drives[actor]
            if "NARRATION" in role["available_actions"]:
                assert actor == gorgon and "Omit speech" in instructions
                modeled.append((actor, "narration"))
                return response(kind="NARRATION", text=description, rationale="A silent warning.")
            if "DIALOGUE" in role["available_actions"]:
                assert actor == harpy and "leave the emergency light" in role["question"]
                modeled.append((actor, "dialogue"))
                return response(
                    kind="DIALOGUE", text=harpy_line, rationale="The Harpy asks for time."
                )
            identities = {play["id"] for play in role["native_plays"]}
            assert selections[actor] in identities
            modeled.append((actor, selections[actor]))
            text = {
                pilot: "Wing, look under the shutter. If it drops, I'm keeping this channel open.",
                wing: wing_line,
                gorgon: (
                    "The Gorgon lowers its shoulder and brings its forelimb around the hatch edge."
                ),
                harpy: "I'm coming through the gap on the left. Give me room.",
            }[actor]
            return response(
                kind="SCENE_OFFER", text=text, play_id=selections[actor], rationale="Actual action."
            )

    model = EncounterModel()
    app = activity(game, model)
    native = adapter(game)
    app.session.context.native_play_projection = ActivityNativePlays(
        SimpleNamespace(
            game=game,
            handler=ADMIN,
            play_registry=load_registry(),
            scene_plays=native,
            handler_rooms=lambda: {900: ("relay", "Relay operations")},
        ),
        None,
    )
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    setup_initiative(game, scene, app)

    directions = ("Keep the hatch usable.", "Keep the exit lane in view.")
    seats = []
    for idx, ref in enumerate((pilot, wing)):
        sheet = state(game).sheets[ref.entity]
        seats.append(
            PlannedAIPilot(
                callsign=f"Hatch watch {idx + 1}",
                portrayal=PILOT_PORTRAYALS[idx].model_copy(
                    update={"girl_playbook": sheet.girl, "frame_playbook": sheet.frame}
                ),
            )
        )
    plan = Opening(
        scene="hatch-opening",
        channel=901,
        handler=ADMIN.user_id,
        handler_control="player",
        audience=(ADMIN.user_id, PLAYER.user_id, OTHER.user_id),
        plan="hatch-watch",
        goals="Hold the emergency exit.",
        difficulty="normal",
        introduction="Hold the hatch.",
        first_mission_day=4,
        seats=CampaignSeats(player_count=2, ai_pilots=tuple(seats)),
    )
    with ledger.transaction() as c:
        ledger._audit(c, ADMIN.user_id, "approved-hatch-plan", EVENT, plan.model_dump(mode="json"))
    publish_opening(
        app, scene, ADMIN, intro="An open shutter separates the watch from two approaching bodies."
    )
    for viewer, ref, seat, drive in zip(
        (PLAYER, OTHER), (pilot, wing), seats, directions, strict=True
    ):
        role = ref.model_dump(mode="json")
        draft = app.write(
            viewer,
            "direction:" + ref.token,
            scene,
            "portrayal-draft",
            {
                "actor": role,
                "version": 0,
                "character_setup": {"drive": drive},
            },
        )["id"]
        app.write(
            viewer,
            "direction-approval:" + ref.token,
            scene,
            "portrayal-confirm",
            {"actor": role, "id": draft},
        )
        draft = app.write(
            viewer,
            "seat:" + ref.token,
            scene,
            "pilot-dossier-propose",
            {
                "actor": role,
                "version": 1,
                "origin": {"plan": plan.plan, "callsign": seat.callsign},
            },
        )["id"]
        app.write(viewer, "seat-approval:" + ref.token, scene, "dossier-confirm", {"id": draft})
    for viewer, ref in ((ADMIN, gorgon), (PLAYER, harpy)):
        role = ref.model_dump(mode="json")
        direction = app.write(
            viewer,
            "direction:" + ref.token,
            scene,
            "portrayal-draft",
            {
                "actor": role,
                "version": 0,
                "character_setup": {"drive": drives[ref]},
            },
        )["id"]
        app.write(
            viewer,
            "direction-approval:" + ref.token,
            scene,
            "portrayal-confirm",
            {
                "actor": role,
                "id": direction,
            },
        )
        app.write(
            viewer,
            "control:" + ref.token,
            scene,
            "scene-alternate-control",
            {
                "actor": role,
                "enabled": True,
                "revision": None,
            },
        )

    def ask(ref, owner, kind, recipients=()):
        option = next(
            x
            for x in app.read(ADMIN, scene, "scene-initiative")["options"]
            if x["actor"] == ref.model_dump(mode="json") and x["source"]["kind"] == kind
        )
        request = app.write(
            ADMIN, "open:" + option["id"], scene, "scene-initiative-open", {"option": option["id"]}
        )
        proposal = app.write(
            ADMIN,
            "generate:" + option["id"],
            scene,
            "reaction-generate",
            {"request": request["id"]},
        )["id"]
        app.write(
            owner,
            "review:" + proposal,
            scene,
            "npc-review",
            {
                "proposal": proposal,
                "decision": "approve",
                "reason": "Review the exact portrayal and action.",
                "recipients": [x.model_dump(mode="json") for x in recipients],
            },
        )
        return proposal

    selections[pilot] = "keep_your_head"
    selections[wing] = "keep_your_head"
    initiative = ask(pilot, PLAYER, "opening")
    pilot_account = app.read(PLAYER, scene, "npc-owner-review", initiative)["proposal"]["text"]
    wing_initiative = ask(wing, OTHER, "opening")
    wing_account = app.read(OTHER, scene, "npc-owner-review", wing_initiative)["proposal"]["text"]
    submission(app, scene, OTHER, "wing-turn", wing_account)
    submission(
        app,
        scene,
        PLAYER,
        "pilot-turn",
        pilot_account + " Harpy, I'll leave the emergency light on.",
    )
    for ref, owner in ((gorgon, ADMIN), (harpy, PLAYER)):
        request = ask(ref, owner, "comms", (pilot, wing))
        app.write(owner, "deliver:" + request, scene, "npc-deliver", {"proposal": request})
    assert game.dice.calls == 0

    selections[gorgon] = "gorgon_attack:" + pilot.token
    proposal = ask(gorgon, ADMIN, "native")
    asset = next(
        iter(
            app.read(ADMIN, scene, "npc-owner-review", proposal)["native_play"]["alternate"][
                "choices"
            ]["asset"]
        )
    )
    attack = app.write(
        ADMIN,
        "gorgon-attack",
        scene,
        "scene-alternate-start",
        {"proposal": proposal, "choices": {"asset": asset}},
    )["action_id"]
    tick(worker, gateway, 3)
    app.write(ADMIN, "advance-attack", scene, "scene-alternate-advance", {"id": attack})
    submit_choice(
        app, scene, PLAYER, "gorgon_defend", options=["play"], text="I hold my post and brace."
    )
    decision = next(
        x
        for x in app.read(PLAYER, scene, "scene-alternate-choices")["choices"]
        if x["kind"] == "gorgon_response_play"
    )
    reply = {
        "id": decision["id"],
        "revision": decision["revision"],
        "heat": 0,
        "play": "keep_your_head",
        "account": pilot_account,
    }
    with pytest.raises(WorkflowError, match="no longer available"):
        app.write(OTHER, "take-over", scene, "scene-alternate-response", reply)
    game.dice.faces = (2, 3)
    child = app.write(PLAYER, "pilot-defends", scene, "scene-alternate-response", reply)[
        "action_id"
    ]
    tick(worker, gateway, 3)
    app.write(PLAYER, "pilot-roll", scene, "scene-alternate-advance", {"id": child})
    for viewer in (ADMIN, PLAYER, OTHER):
        submit_choice(app, scene, viewer, "tag_window", options=["pass"])
    submit_choice(app, scene, PLAYER, "actor_keep", options=["in_control"])
    submit_choice(app, scene, ADMIN, "handler_keep", flag=True, text="The Pilot holds the hatch.")
    assert game.inspect(PLAYER, child)["state"] == "complete"
    tick(worker, gateway, 5)

    selections[harpy] = "harpy_engage:" + wing.token
    proposal = ask(harpy, PLAYER, "native")
    game.dice.faces = (1, 2)
    charge = app.write(
        PLAYER,
        "harpy-engage",
        scene,
        "scene-alternate-start",
        {"proposal": proposal, "choices": {"heat": 5}},
    )["action_id"]
    tick(worker, gateway, 3)
    app.write(PLAYER, "harpy-roll", scene, "scene-alternate-advance", {"id": charge})
    for viewer in (ADMIN, PLAYER, OTHER):
        submit_choice(app, scene, viewer, "tag_window", options=["pass"])
    maneuver = next(
        x
        for x in app.read(PLAYER, scene, "scene-alternate-choices")["choices"]
        if x["kind"] == "engage_maneuvers"
    )
    weapon = next(
        field["options"][0][0] for field in maneuver["fields"] if field["key"] == "fields.pin"
    )
    submit_choice(
        app,
        scene,
        PLAYER,
        "engage_maneuvers",
        options=["pin", "cover"],
        fields={x: weapon for x in ("pin", "cover")},
        text="The Harpy bars the hatch and covers the approach with the same weapon.",
    )
    assert game.inspect(PLAYER, charge)["state"] == "complete", [
        (viewer.user_id, [x["kind"] for x in game.choices(viewer)])
        for viewer in (ADMIN, PLAYER, OTHER)
    ]
    assert game.dice.calls == 2
    ledger.engine.dispose()
    reopened = activity(game, model)
    assert any(
        x["text"] == description and x["narration"]
        for x in reopened.timeline(OTHER, scene)["entries"]
    )
    assert any(x["text"] == harpy_line for x in reopened.timeline(OTHER, scene)["entries"])
    assert game.inspect(ADMIN, attack)["receipt"] is None
    assert game.inspect(PLAYER, child)["receipt"]["faces"] == [2, 3]
    assert game.inspect(PLAYER, charge)["receipt"]["faces"] == [1, 2]
    assert any(x["text"] == wing_line for x in reopened.timeline(PLAYER, scene)["entries"])
    assert {item[0] for item in modeled} == {pilot, wing, harpy, gorgon}
