"""An isolated Activity scene rehearses native casting, sheets, and mixed-cast dialogue."""

import json

import pytest
from scene_orders import SceneOrders
from test_activity_shadow_readiness import submission
from test_alternate_initiative import activity, setup_initiative
from test_gorgon_runtime import gorgon_source
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


@pytest.fixture
def cast_scene(ledger):
    game, _, _, _, _ = gorgon_source(
        ledger, harpy=True, npc=True, director=True, opposing=True, damaged=True, begin=False
    )
    clerk = ActorRef(kind="npc", entity="relay-clerk")
    offstage = ActorRef(kind="npc", entity="stores-clerk")
    world = WorldService(MissionService(ledger))
    for ref, name in ((clerk, "Relay clerk"), (offstage, "Stores clerk")):
        world.npc(
            ADMIN,
            "introduce-" + ref.entity,
            state(game).revision,
            Npc(
                id=ref.entity,
                name=name,
                jobs=("mechanic",),
                detail="Maintains the shift log.",
                controller=ADMIN.user_id,
                revealed=True,
                cell=(0, 0),
            ),
        )
    hidden = ActorRef(kind="gorgon", entity="opposing-gorgon")
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = update(
            canon.world,
            gorgons=tuple(
                row.model_copy(update={"revealed": False}) if row.id == hidden.entity else row
                for row in canon.world.gorgons
            ),
        )
        game.event(c, ADMIN.user_id, "undisclosed-specimen", "synthetic.visibility", canon)
        scene = game.scene(c, 900)["id"]
    return (
        game,
        scene,
        {
            "clerk": clerk,
            "offstage": offstage,
            "hidden": hidden,
            "harpy": ActorRef(kind="external_pilot", entity="actual-pitted-harpy"),
            "gorgon": ActorRef(kind="gorgon", entity="source-gorgon"),
            "director": ActorRef(kind="npc", entity="actual-director"),
            "guard": ActorRef(kind="npc", entity="actual-guard"),
        },
    )


def cast_change(game, viewer, actor, operation):
    orders = SceneOrders(game, 900)
    (card,) = orders.view(viewer, ("relay", "Relay operations"))
    control = next(item for item in card["operations"] if item["id"] == operation)
    selector = next(
        value
        for value, _ in control["fields"][0]["options"]
        if json.loads(value) == actor.model_dump(mode="json")
    )
    request = card | {"answer": {"operation": operation, "values": {"actor": selector}}}
    return orders.perform(viewer, operation + ":" + actor.token, request)


def approve_direction(app, scene, owner, actor, direction):
    ref = actor.model_dump(mode="json")
    draft = app.write(
        owner,
        "draft:" + actor.token,
        scene,
        "portrayal-draft",
        {
            "actor": ref,
            "version": 0,
            "character_setup": direction,
        },
    )
    app.write(
        owner,
        "approve:" + actor.token,
        scene,
        "portrayal-confirm",
        {
            "actor": ref,
            "id": draft["id"],
        },
    )


def test_native_cast_records_keep_engine_state_and_portrayal_under_original_owner(cast_scene):
    game, scene, roles = cast_scene
    app = activity(game, None)
    gorgon, harpy = roles["gorgon"], roles["harpy"]
    assert cast_change(game, ADMIN, gorgon, "withdraw")
    assert cast_change(game, ADMIN, gorgon, "join")
    setup_initiative(game, scene, app)

    directions = ((ADMIN, gorgon, "Listen for a name."), (PLAYER, harpy, "Keep the channel open."))
    for owner, actor, drive in directions:
        approve_direction(app, scene, owner, actor, {"drive": drive})

    game.store.engine.dispose()
    reopened = activity(game, None)

    def sheets(viewer):
        return {
            sheet["token"]: sheet
            for sheet in reopened.read(viewer, scene, "portrayal-sheets")["sheets"]
        }

    actual_gorgon = sheets(ADMIN)[gorgon.token]["native_record"]
    gorgon_body = next(row for row in state(game).world.gorgons if row.id == gorgon.entity)
    assert actual_gorgon["kind"] == "gorgon"
    assert actual_gorgon["gorgon_class"] == gorgon_body.gorgon_class
    assert actual_gorgon["types"] == list(gorgon_body.types)
    assert actual_gorgon["assets"][0]["damaged"] and actual_gorgon["core_weakness"]
    assert actual_gorgon["core_conditions"]
    actual_harpy = sheets(PLAYER)[harpy.token]["native_record"]
    assert actual_harpy["kind"] == "harpy" and actual_harpy["heat"] == 5
    assert actual_harpy["piloting"] and actual_harpy["identities"][0]["name"] == "Free"
    assert {item["name"] for item in actual_harpy["assets"]} == {
        "Actual Frame blade",
        "Actual Girl claw",
    }
    for owner, actor, drive in directions:
        preview = reopened.read(owner, scene, "portrayal-preview", actor.token)
        assert preview["profile"]["character_setup"]["drive"] == drive
    assert harpy.token not in sheets(ADMIN) and gorgon.token not in sheets(PLAYER)
    with pytest.raises(WorkflowError, match="DOSSIER_NOT_OWNED"):
        reopened.read(ADMIN, scene, "portrayal-preview", harpy.token)
    with pytest.raises(WorkflowError, match="controlled by another"):
        approve_direction(reopened, scene, ADMIN, harpy, {"drive": "Overridden"})


# Authored lines stand in for a provider so the rehearsal can exercise exact review and delivery.
ROUNDS = (
    (
        "clerk",
        "The return column is empty. Should I close the log?",
        "Leave it blank a minute. If they call back, I'll need to hear the whole name.",
        "Keep a place for a missing worker.",
        "Bureaucratic shorthand with flashes of concern.",
    ),
    (
        "harpy",
        "The tapping stopped when I said Juno. I don't know who it is.",
        "Say it once more. Then wait. If you hear my name too, leave it for me to answer.",
        "Find out who is still on comms.",
        "Clipped, practical directions. Leave room for an answer.",
    ),
    (
        "gorgon",
        "I called it an alarm. I should have asked what you heard.",
        "The Gorgon stills its head. "
        "One forelimb withdraws from the threshold, slow enough to follow.",
        "Leave room for a genuine question.",
        "Patient and precise. Drops its guard on an apology.",
    ),
    (
        "director",
        "They haven't checked in. Whose name goes into the report?",
        "Leave the field open. When they check in, let them say it themselves.",
        "Keep an unconfirmed report from becoming a finding.",
        "Measured and direct under pressure.",
    ),
)


def test_facilitator_rehearses_mixed_cast_with_exact_audience_and_owned_follow_through(cast_scene):
    game, scene, roles = cast_scene
    owners = {"clerk": ADMIN, "gorgon": ADMIN, "harpy": PLAYER, "director": OTHER, "guard": OTHER}
    active = {}
    attempts = []
    clerk_line = ROUNDS[0][2]

    class RehearsalModel:
        def generate(self, instructions, packet, response):
            name, line, reply, drive, voice = active["round"]
            role = packet["role"]
            attempts.append(name)
            assert ("third-person" if name == "gorgon" else "voice cue") in instructions
            assert role["question"] == line
            assert role["actor"] == roles[name].model_dump(mode="json")
            setup = role["dossier"]["profile"]["character_setup"]
            assert setup["drive"] == drive and voice in setup.values()
            assert not role["native_plays"] and "PRIVATE_LOG" not in str(role)
            if name == "harpy":
                assert clerk_line in str(role["references"])
            if name == "gorgon":
                assert clerk_line not in str(role["references"])
            cited = tuple(item["id"] for item in role["references"] if clerk_line in item["text"])
            return response(
                kind="NARRATION" if name == "gorgon" else "DIALOGUE",
                text=reply,
                cited_references=cited,
                rationale="PRIVATE_REHEARSAL_REASON",
            )

    model = RehearsalModel()
    app = activity(game, model)
    cast_change(game, ADMIN, roles["clerk"], "join")
    setup_initiative(game, scene, app)
    for name, _, _, drive, voice in ROUNDS:
        cue = {"clerk": "voice_at_ease", "gorgon": "voice_on_repair"}.get(
            name, "voice_under_pressure"
        )
        approve_direction(app, scene, owners[name], roles[name], {"drive": drive, cue: voice})

    def control(who, name):
        return app.write(
            who,
            "control:" + name,
            scene,
            "scene-alternate-control",
            {
                "actor": roles[name].model_dump(mode="json"),
                "enabled": True,
                "revision": None,
            },
        )

    for name in ("harpy", "guard", "director", "offstage"):
        with pytest.raises(WorkflowError, match="INITIATIVE_CONTROL_OWNER"):
            control(ADMIN, name)
    for name, owner in owners.items():
        control(owner, name)

    submission(app, scene, PLAYER, "private-log", "PRIVATE_LOG", channel="private")
    before = state(game)
    receipts = []
    pilot = current_ref(before, PLAYER.user_id)
    for name, line, reply, drive, voice in ROUNDS:
        active["round"] = (name, line, reply, drive, voice)
        _, source = submission(app, scene, PLAYER, "inbound:" + name, line)
        choices = app.read(ADMIN, scene, "scene-initiative")["options"]
        comms = {
            item["actor"]["entity"]: item for item in choices if item["source"]["kind"] == "comms"
        }
        assert set(comms) == {roles[name].entity for name in owners}
        option = comms[roles[name].entity]
        assert option["source"]["id"] == source["source_id"]
        request = app.write(
            ADMIN, "open:" + name, scene, "scene-initiative-open", {"option": option["id"]}
        )
        proposal = app.write(
            ADMIN,
            "draft-reply:" + name,
            scene,
            "reaction-generate",
            {
                "request": request["id"],
            },
        )["id"]
        controller = owners[name]
        if controller != ADMIN:
            with pytest.raises(WorkflowError, match="REACTION_NOT_OWNED"):
                app.read(ADMIN, scene, "npc-owner-review", proposal)
        review = app.read(controller, scene, "npc-owner-review", proposal)
        assert review["source_quote"] == line and review["proposal"]["text"] == reply
        candidates = [item["actor"]["entity"] for item in review["delivery_candidates"]]
        if controller != ADMIN:
            assert roles["hidden"].entity not in candidates
        listeners = [pilot]
        if name in ("clerk", "gorgon"):
            listeners.append(roles["harpy"])
        if name == "harpy":
            listeners.append(roles["clerk"])
            assert roles["gorgon"].entity not in candidates
            with pytest.raises(WorkflowError, match="NPC_DELIVERY_KNOWLEDGE"):
                app.write(
                    controller,
                    "other-listener",
                    scene,
                    "npc-review",
                    {
                        "proposal": proposal,
                        "decision": "approve",
                        "reason": "Try to widen the audience for the clerk's line.",
                        "recipients": [roles["gorgon"].model_dump(mode="json")],
                    },
                )
        app.write(
            controller,
            "approved:" + name,
            scene,
            "npc-review",
            {
                "proposal": proposal,
                "decision": "approve",
                "reason": "The exact line was heard.",
                "recipients": [actor.model_dump(mode="json") for actor in listeners],
            },
        )
        receipt = app.write(
            controller, "delivered:" + name, scene, "npc-deliver", {"proposal": proposal}
        )
        receipts.append(receipt)

    game.store.engine.dispose()
    reopened = activity(game, model)
    entries = reopened.timeline(PLAYER, scene)["entries"]
    assert [item["text"] for item in entries if item["id"] in {x["id"] for x in receipts}] == [
        reply for _, _, reply, _, _ in ROUNDS
    ]
    assert clerk_line not in str(reopened.timeline(OTHER, scene))
    assert attempts == [row[0] for row in ROUNDS] and state(game) == before and game.dice.calls == 0
    harpy = roles["harpy"]
    preview = reopened.read(PLAYER, scene, "portrayal-preview", harpy.token)
    subjects = [item["actor"]["entity"] for item in preview["continuity_subjects"]]
    assert roles["gorgon"].entity in subjects and roles["hidden"].entity not in subjects
    reference = receipts[2]["reference"]
    assert reference in [item["id"] for item in preview["continuity_sources"]]
    change = reopened.write(
        PLAYER,
        "relationship",
        scene,
        "portrayal-continuity",
        {
            "actor": harpy.model_dump(mode="json"),
            "version": 1,
            "updates": [
                {
                    "kind": "relationship",
                    "subject": roles["gorgon"].model_dump(mode="json"),
                    "text": "The Gorgon left the threshold clear after an apology.",
                    "knowledge_refs": [reference],
                }
            ],
        },
    )
    reopened.write(
        PLAYER,
        "approve-relationship",
        scene,
        "portrayal-confirm",
        {
            "actor": harpy.model_dump(mode="json"),
            "id": change["id"],
        },
    )
    game.store.engine.dispose()
    preview = activity(game, model).read(PLAYER, scene, "portrayal-preview", harpy.token)
    assert preview["state"]["continuity"][0]["subject"] == roles["gorgon"].model_dump(mode="json")
