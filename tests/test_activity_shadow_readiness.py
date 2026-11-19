"""Offline Activity intake, scoped review and simulated delivery against native fixtures."""

import json

import pytest
from test_director_activity_scene import activity_adapter, input_command, launch_opening
from test_director_observation import Clock, complete_keep
from test_director_worldbuilding import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, setup_game, start, state, tick

from girlframe.ai.director_reactions import ReactionProposal
from girlframe.engine.m2 import QUESTIONS
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.onboarding import WorkflowError


@pytest.fixture
def fixture(ledger):
    game, worker, gateway, dice = setup_game(ledger)
    ledger.clock = Clock()
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    app = activity_adapter.local_fixture_director(game, activity_shadow=True)
    return app, scene, game, ledger.clock, worker, gateway, dice


def configure(app, scene, actors=(ADMIN, PLAYER, OTHER), revision=0):
    app.write(
        ADMIN,
        f"config:{scene}:{revision}",
        scene,
        "configure",
        {
            "revision": revision,
            "policy": {"mode": "shadow", "quiet_seconds": 2, "min_interval_seconds": 1},
        },
    )
    for actor in actors:
        consent(app, scene, actor, revision=revision + 1)


def opt(app, scene, revision=0, enabled=True):
    return app.write(
        ADMIN,
        f"campaign:{revision}",
        scene,
        "activity-policy-save",
        {"revision": revision, "enabled": enabled},
    )


def consent(app, scene, actor, *, revision=1, value=True, key=None):
    return app.write(
        actor,
        key or f"consent:{scene}:{revision}:{actor.user_id}:{value}",
        scene,
        "consent",
        {"policy_revision": revision, "consent": value},
    )


def submission(app, scene, actor, key, text, *, channel="comms", **change):
    cmd = input_command(app.session.observer, actor, scene, key, text, channel).model_copy(
        update=change
    )
    return cmd, app.submit(actor, scene, cmd)["input"]


def review(app, scene):
    return app.write(ADMIN, "review-eligible-batch", scene, "activity-review-run", {})["batch"]


def records(app, scene):
    return app.read(ADMIN, scene, "activity-review")["batches"]


def test_campaign_opt_in_native_commit_order_and_restart(fixture):
    app, scene, game, clock, worker, gateway, dice = fixture
    with pytest.raises(ValueError):
        DirectorObservationService(game.store, activity_shadow=True)
    assert app.read(ADMIN, scene, "activity-policy") == {"revision": 0, "enabled": False}
    with pytest.raises(WorkflowError, match="OPT_IN"):
        configure(app, scene)
    with pytest.raises(WorkflowError, match="administrator"):
        app.write(
            PLAYER, "wrong-staff", scene, "activity-policy-save", {"enabled": True, "revision": 0}
        )
    assert opt(app, scene) == opt(app, scene) == {"revision": 1, "enabled": True}
    configure(app, scene)
    _, ooc = submission(
        app, scene, PLAYER, "out-of-character", "Keep this outside.", classification="ooc"
    )
    assert ooc["status"] == "ignored_ooc"
    cmd, before = submission(app, scene, PLAYER, "before-commit", "We check the dials.")
    assert app.submit(PLAYER, scene, cmd)["input"] == before and before["sequence"] == 1
    assert review(app, scene) is None
    action = complete_keep(game, worker, gateway)
    tick(worker, gateway, 5)
    sensors = start(game, play="check_sensors")
    tick(worker, gateway)
    pass_tags(game)
    answer(game, PLAYER, "actor_sensors", options=QUESTIONS[:2])
    answer(
        game, ADMIN, "handler_sensors", fields={"a1": "PRIVATE_SENSOR_ANSWER", "a2": "Other answer"}
    )
    tick(worker, gateway, 5)
    _, after = submission(app, scene, PLAYER, "after-native", "Handler, what is the scope?")
    assert after["sequence"] == 4
    canonical = state(game)
    assert review(app, scene)["reason"] == "completed_play"
    batch = records(app, scene)[0]["items"]
    assert [x["kind"] for x in batch] == [
        "message",
        "completed_play",
        "completed_play",
        "message",
    ]
    assert [batch[1]["action"], batch[2]["action"]] == [action, sensors]
    assert "PRIVATE_SENSOR_ANSWER" not in json.dumps(batch)
    assert app.read(ADMIN, scene, "status")["reviewed_sequence"] == 4
    assert state(game) == canonical and dice.calls == 2
    game.store.engine.dispose()
    reopened = activity_adapter.local_fixture_director(game, activity_shadow=True)
    assert reopened.submit(PLAYER, scene, cmd)["input"] == before
    assert review(reopened, scene) is None and records(reopened, scene) == records(app, scene)
    with pytest.raises(WorkflowError, match="administrator"):
        reopened.read(PLAYER, scene, "activity-review")


def test_source_correction_abandons_leased_work_and_revokes_pending_draft(fixture):
    app, scene, game, clock, *_ = fixture
    opt(app, scene)
    configure(app, scene)
    observer = app.session.observer
    _, original = submission(app, scene, PLAYER, "original", "Handler, what is the scope?")
    clock.now += 3
    abandoned = observer.claim_review(scene)
    assert abandoned is not None
    game.store.engine.dispose()
    app = activity_adapter.local_fixture_director(game, activity_shadow=True)
    assert review(app, scene) is None  # the durable lease survived the restart
    _, updated = submission(
        app,
        scene,
        PLAYER,
        "correction",
        "I put the spare cables away.",
        source_id=original["source_id"],
        expected_source_revision=1,
    )
    clock.now += 3
    assert review(app, scene)["frontier"] == 2
    batch = records(app, scene)[0]
    assert len(batch["items"]) == 1 and batch["items"][0]["decision"]["action"] == "WAIT"
    assert batch["items"][0]["revision"] == 2 and updated["source_revision"] == 2
    with pytest.raises(WorkflowError, match="STALE_CLAIM"):
        observer.acknowledge_review(abandoned.run_id, abandoned.lease_token, success=True)
    submission(
        app,
        scene,
        PLAYER,
        "correction-again",
        "The equipment is secure.",
        source_id=original["source_id"],
        expected_source_revision=2,
    )
    assert records(app, scene)[0]["items"][0]["status"] == "stale"
    _, source = submission(app, scene, PLAYER, "draft-source", "Handler, can you repeat the scope?")
    # An explicit local rehearsal using the original provider adapter creates a
    # pending draft. Intake and batched readiness never call that adapter.
    current = app.session.conversation.process_message(
        PLAYER, "manual-draft", scene, source["source_id"], 1
    )
    draft = current["handler"]["id"]
    assert app.read(ADMIN, scene, "handler-draft", draft)["reply"]
    submission(
        app,
        scene,
        PLAYER,
        "correct-after-draft",
        "I rack the cable.",
        source_id=source["source_id"],
        expected_source_revision=1,
    )
    assert app.read(ADMIN, scene, "handler-draft", draft) == {
        "id": draft,
        "status": "stale_reopen_source",
        "effects_applied": False,
    }
    assert app.gm_work(ADMIN, scene)["handler_drafts"][0]["status"] == "stale_reopen_source"
    _, pending = submission(
        app, scene, PLAYER, "withdrawn-source", "WITHDRAWN_PRIVATE", channel="private"
    )
    consent(app, scene, PLAYER, value=False)
    with pytest.raises(WorkflowError, match="consent"):
        app.read(ADMIN, scene, "activity-review")
    consent(app, scene, PLAYER, key="reconsent-after-withdrawal")
    assert app.timeline(PLAYER, scene)["entries"] == []
    with pytest.raises(WorkflowError, match="SOURCE_UNAVAILABLE"):
        submission(
            app,
            scene,
            PLAYER,
            "revive-old",
            "Changed",
            source_id=pending["source_id"],
            expected_source_revision=1,
            channel="private",
        )
    opt(app, scene, 1, False)
    opt(app, scene, 2, True)
    with pytest.raises(WorkflowError, match="OPT_IN_REQUIRED"):
        consent(app, scene, ADMIN, key="old-notice-after-restart")
    configure(app, scene, revision=1)
    assert records(app, scene) == []


def test_parallel_activity_review_only_learns_approved_closeout(fixture):
    app, scene, game, clock, *_ = fixture
    game.leave_scene(OTHER, "other-departs", 900)
    game.bind_scene(ADMIN, "parallel-bind", 901)
    for viewer in (ADMIN, OTHER):
        game.join_scene(viewer, f"parallel-join:{viewer.user_id}", 901)
    observer = app.session.observer
    with game.store.engine.connect() as c:
        parallel = game.scene(c, 901)["id"]
    opt(app, scene)
    configure(app, scene, (ADMIN, PLAYER))
    configure(app, parallel, (ADMIN, OTHER))
    with game.store.engine.connect() as c:
        handler = observer._authorize_input(c, ADMIN, parallel, "handler")[2]
        pilot = observer._authorize_input(c, PLAYER, scene, "pilot")[2]
    launch_opening(
        app,
        parallel,
        facts=[
            {
                "text": "APPROVED_HANDLER_BRIEF",
                "learned_from": "Manual",
                "known_by": [handler.token],
            }
        ],
    )
    _, private = submission(
        app, scene, PLAYER, "private-see", "PRIVATE_DISCOVERY", channel="private"
    )
    _, public = submission(app, scene, PLAYER, "comms-report", "APPROVED_PILOT_REPORT")
    refs = [
        app.session.context.record(
            ADMIN, "record-" + key, scene, item["source_id"], i, known_by=(pilot,), topic="tactical"
        )["id"]
        for i, (key, item) in enumerate((("private", private), ("public", public)))
    ]
    submission(app, parallel, OTHER, "ask-before", "Handler, what is our scope?")
    clock.now += 3
    assert review(app, parallel)
    before = json.dumps(records(app, parallel))
    assert "APPROVED_HANDLER_BRIEF" in before
    assert all(
        text not in before
        for text in ("APPROVED_PILOT_REPORT", "PRIVATE_DISCOVERY", "GM_ONLY_MAINTENANCE_PLAN")
    )
    revision = observer.status(ADMIN, scene).scene_revision
    with pytest.raises(WorkflowError, match="SCENE_REPORT_SCOPE"):
        app.close(ADMIN, "bad-report", scene, 900, revision, (refs[0],))
    assert (
        app.close(ADMIN, "approved-report", scene, 900, revision, (refs[1],))[
            "handler_report_count"
        ]
        == 1
    )
    submission(app, parallel, OTHER, "ask-after", "Handler, what is our updated scope?")
    clock.now += 3
    assert review(app, parallel)
    after = json.dumps(records(app, parallel)[0])
    assert "APPROVED_PILOT_REPORT" in after and "PRIVATE_DISCOVERY" not in after


@pytest.mark.parametrize("change", ["none", "cast", "corruption", "later_corruption"])
def test_simulated_npc_delivery_binds_controller_and_hearing(fixture, change):
    app, scene, game, _, _, _, dice = fixture
    opt(app, scene)
    configure(app, scene)
    observer, context = app.session.observer, app.session.context
    world = ready((observer, context, scene, game, dice)).world
    with game.store.engine.connect() as c:
        handler = observer._authorize_input(c, ADMIN, scene, "handler")[2]
        pilot = observer._authorize_input(c, PLAYER, scene, "pilot")[2]
    npc = ActorRef(kind="npc", entity="npc-scene-mechanic")
    npc_roles = NpcRoleService(world)
    offer = npc_roles.offer(
        ADMIN,
        "offer-mechanic",
        state(game).revision,
        Npc(
            id=npc.entity,
            name="Mora",
            jobs=("mechanic",),
            detail="Tests radios.",
            controller=OTHER.user_id,
            cell=(0, 0),
        ),
    )
    npc_roles.respond(OTHER, "accept-mechanic", offer["id"], state(game).revision, "accept")
    if change in ("corruption", "later_corruption"):
        from test_physical_operations import place
        from test_world import gorgon

        from girlframe.engine.m3_sentinel import corrupt
        from girlframe.engine.m3_world import update

        with game.store.transaction() as c:
            original = place(state(game), PLAYER.user_id, cell=(2, 0), mode="outside_frame")
            sentinel = gorgon("erratic", "signal-sentinel", types=("sentinel",))
            original.world = update(original.world, gorgons=(*original.world.gorgons, sentinel))
            if change == "corruption":
                original.world = corrupt(
                    original.world,
                    sentinel,
                    sentinel.cell,
                    "synthetic-action",
                    scene,
                    "start-effect",
                )
            game.event(c, 1, "position-recipients", "synthetic.original_positions", original)
    _, early = submission(
        app, scene, PLAYER, "before-npc-joins", "This was said before Mora arrived."
    )
    cast = CastService(ActorService(world.missions))
    for owner, role in ((OTHER, npc), (PLAYER, pilot), (ADMIN, handler)):
        current = cast.view(owner, 900)
        if not any(x["ref"] == role.model_dump(mode="json") for x in current["roles"]):
            cast.change(
                owner,
                "join-" + role.kind,
                900,
                current["game_revision"],
                current["cast_revision"],
                "join",
                role,
            )
    with game.store.engine.connect() as c:
        assert app.session.knowledge.heard(c, scene, early["source_id"], npc) == ()
    _, source = submission(app, scene, PLAYER, "greet-mechanic", "Is the panel ready?")
    req = app.write(
        ADMIN,
        "npc-request",
        scene,
        "reaction-open",
        {
            "actor": npc.model_dump(mode="json"),
            "source_id": source["source_id"],
        },
    )["id"]
    text = "The spare panel is ready for inspection."
    proposal = app.write(
        ADMIN,
        "npc-proposal",
        scene,
        "reaction-propose",
        {
            "request": req,
            "proposal": ReactionProposal(
                request_id=req, kind="DIALOGUE", text=text, rationale="PRIVATE_GM_REASON"
            ).model_dump(mode="json"),
        },
    )["id"]
    selection = {
        "proposal": proposal,
        "decision": "approve",
        "reason": "Verified dialogue only.",
        "recipients": [pilot.model_dump(mode="json")],
    }
    with pytest.raises(WorkflowError, match="NOT_OWNED"):
        app.write(PLAYER, "wrong-reviewer", scene, "npc-review", selection)
    app.write(OTHER, "npc-reviewer", scene, "npc-review", selection)
    delivery = {"proposal": proposal}
    with pytest.raises(WorkflowError, match="NOT_OWNED"):
        app.write(ADMIN, "wrong-speaker", scene, "npc-deliver", delivery)
    if change == "cast":
        current = cast.view(PLAYER, 900)
        cast.change(
            PLAYER,
            "leave-listener",
            900,
            current["game_revision"],
            current["cast_revision"],
            "withdraw",
            pilot,
        )
        with pytest.raises(WorkflowError, match="STALE_NPC_DELIVERY|DISABLED"):
            app.write(OTHER, "removed-listener", scene, "npc-deliver", delivery)
        return
    if change == "later_corruption":
        from girlframe.engine.m3_sentinel import corrupt

        with game.store.transaction() as c:
            original = state(game)
            sentinel = next(x for x in original.world.gorgons if x.id == "signal-sentinel")
            original.world = corrupt(
                original.world,
                sentinel,
                sentinel.cell,
                "synthetic-action",
                scene,
                "synthetic-effect",
            )
            game.event(c, 1, "terrain-now-corrupted", "synthetic.corrupted_after_review", original)
        with pytest.raises(WorkflowError, match="STALE_REACTION"):
            app.write(OTHER, "blocked-hearing", scene, "npc-deliver", delivery)
        assert text not in json.dumps(app.timeline(PLAYER, scene))
        return
    if change == "corruption":
        with pytest.raises(WorkflowError, match="No verified communication route"):
            app.write(OTHER, "blocked-hearing", scene, "npc-deliver", delivery)
        assert text not in json.dumps(app.timeline(PLAYER, scene))
        return
    before = state(game)
    delivered = app.write(OTHER, "deliver-synthetic", scene, "npc-deliver", delivery)
    assert app.write(OTHER, "deliver-synthetic", scene, "npc-deliver", delivery) == delivered
    assert app.write(OTHER, "deliver-again", scene, "npc-deliver", delivery) == delivered
    record = app.read(ADMIN, scene, "npc-hearing", delivered["id"])
    assert (
        record["actor"] == npc.model_dump(mode="json")
        and record["recipients"] == selection["recipients"]
    )
    assert record["controllers"] == {npc.token: OTHER.user_id, pilot.token: PLAYER.user_id}
    assert len([x for x in app.timeline(PLAYER, scene)["entries"] if x["text"] == text]) == 1
    assert text not in json.dumps(app.timeline(ADMIN, scene))
    assert delivered["reference"] in {
        ref.id for ref in context.build(PLAYER, scene, actor=pilot).references
    }
    assert delivered["reference"] not in {
        ref.id for ref in context.build(ADMIN, scene, actor=handler).references
    }
    with pytest.raises(WorkflowError, match="administrator"):
        app.read(PLAYER, scene, "npc-hearing", delivered["id"])
    assert "PRIVATE_GM_REASON" not in json.dumps(record)
    assert state(game) == before and dice.calls == 0
