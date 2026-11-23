"""Same-roster continuity and event-driven Handler replies over real scene sources."""

import json

import pytest
from test_director_conversation import HandlerProbe
from test_director_conversation import routed as routed
from test_director_observation import observed as observed
from test_director_observation import send
from test_director_session import command
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, pass_tags, start, state, tick

from girlframe.ai.observation import ObservationPolicy
from girlframe.delivery.m2_worker import GameWorker
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_continuity import SceneContinuityService
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.director_session import DirectorSessionService
from girlframe.services.onboarding import WorkflowError


def roles(observer, scene):
    with observer.store.engine.connect() as c:
        return (
            observer._authorize_input(c, ADMIN, scene, "handler")[2],
            observer._authorize_input(c, PLAYER, scene, "pilot")[2],
        )


def reference(context, scene, key, text, actors, topic="general", dependencies=()):
    _, source = send(context.observations, scene, key, text=text, viewer=ADMIN)
    with context.store.engine.connect() as c:
        order = len(context._references(c, scene))
    saved = context.record(
        ADMIN,
        key + ":ref",
        scene,
        source.source_id,
        order,
        known_by=actors,
        topic=topic,
        dependencies=dependencies,
    )
    return saved["id"], source


def new_scene(observer, channel=901, previous_channel=900):
    game = observer.game
    game.close_scene(ADMIN, f"close-before:{channel}", previous_channel)
    game.bind_scene(ADMIN, f"bind:{channel}", channel)
    for actor in (ADMIN, PLAYER, OTHER):
        game.join_scene(actor, f"join:{channel}:{actor.user_id}", channel)
    with observer.store.engine.connect() as c:
        scene = game.scene(c, channel)["id"]
    observer.configure_scene(
        ADMIN, f"observe:{channel}", scene, 0, ObservationPolicy(mode="shadow")
    )
    for actor in (ADMIN, PLAYER, OTHER):
        observer.set_consent(actor, f"consent:{channel}:{actor.user_id}", scene, 1, consent=True)
    return scene


def carry(context, before, after, ids, key="carry"):
    return SceneContinuityService(context).carry(
        ADMIN,
        key,
        before,
        after,
        SceneContinuityService(context).preview(ADMIN, before).revision,
        context.build(ADMIN, after).revision,
        ids,
    )


def test_known_updates_wait_for_access_then_drain_once_and_rearm(routed):
    observer, context, scene, game, _ = routed
    handler, pilot = roles(observer, scene)
    before = state(game).model_dump_json()
    private, _ = reference(
        context, scene, "private-update", "PRIVATE_TACTICAL_CANARY", (pilot,), "tactical"
    )
    service = DirectorSessionService(context)
    first = service.submit(PLAYER, scene, command(observer, scene, "quiet", "I check my harness."))
    assert first["conversation"]["handler"] is None
    brief, _ = reference(
        context,
        scene,
        "brief",
        "Relay inspection is the exercise objective.",
        (handler, pilot),
        "briefing",
    )
    tactical, _ = reference(
        context,
        scene,
        "tactical",
        "The east walkway is reported obstructed.",
        (handler,),
        "tactical",
    )
    for index, expected in enumerate((brief, tactical)):
        result = service.submit(
            PLAYER, scene, command(observer, scene, f"turn:{index}", "I listen.")
        )
        assert result["conversation"]["handler_decision"]["decision"] == {
            "action": "RESPOND",
            "reason": "known_update",
            "source_refs": [expected],
        }
        assert result["conversation"]["handler"]["reply"]["source_refs"] == [expected]
        assert "PRIVATE_TACTICAL_CANARY" not in json.dumps(result["conversation"]["handler"])
    service = DirectorSessionService(DirectorContextService(observer))
    _, source = send(observer, scene, "other-speaker", text="I check the radio.", viewer=OTHER)
    result = service.conversation.process_message(OTHER, "other-route", scene, source.source_id, 1)
    assert result["handler"] is None
    assert result["handler_decision"]["decision"]["reason"] == "update_already_addressed"
    direct = service.submit(
        PLAYER, scene, command(observer, scene, "direct", "Handler, repeat the objective?")
    )
    assert direct["conversation"]["handler"] is not None
    debrief, _ = reference(
        context,
        scene,
        "debrief",
        "Inspection report received; payment is unconfirmed.",
        (handler,),
        "debrief",
    )
    result = service.submit(PLAYER, scene, command(observer, scene, "end", "I file the report."))
    assert result["conversation"]["handler"]["reply"]["source_refs"] == [debrief]
    assert private != debrief and state(game).model_dump_json() == before


def test_failed_update_does_not_suppress_retry(routed):
    observer, context, scene, _, _ = routed
    handler, _ = roles(observer, scene)
    reference(
        context,
        scene,
        "update",
        "Check the damaged relay before approaching.",
        (handler,),
        "tactical",
    )

    class Recovering(HandlerProbe):
        attempts = 0

        def respond(self, request):
            self.attempts += 1
            if self.attempts == 1:
                raise OSError("synthetic unavailable")
            return super().respond(request)

    provider = Recovering()
    service = DirectorSessionService(
        context, conversation=DirectorConversationService(context, handler=provider)
    )
    request = command(observer, scene, "retry-update", "I check the radio.")
    with pytest.raises(WorkflowError, match="CONVERSATION_UNAVAILABLE"):
        service.submit(PLAYER, scene, request)
    result = service.submit(PLAYER, scene, request)
    assert result["conversation"]["handler"] is not None and provider.attempts == 2
    assert service.submit(PLAYER, scene, request) == result and provider.attempts == 2


def test_handoff_preserves_private_knowledge_dependencies_and_closed_origin(routed):
    observer, context, scene, game, _ = routed
    handler, pilot = roles(observer, scene)
    first, _ = reference(
        context, scene, "brief", "A damaged antenna was reported.", (handler, pilot), "briefing"
    )
    second, _ = reference(
        context,
        scene,
        "caution",
        "Treat that report as unverified.",
        (handler,),
        "tactical",
        dependencies=(first,),
    )
    private, _ = reference(context, scene, "private", "CROSS_SCENE_PC_ONLY", (pilot,))
    target = new_scene(observer)
    with pytest.raises(WorkflowError, match="CONTINUITY_DEPENDENCY"):
        carry(context, scene, target, (second,))
    before, after = (
        SceneContinuityService(context).preview(ADMIN, scene),
        context.build(ADMIN, target),
    )
    service = SceneContinuityService(context)
    args = (
        ADMIN,
        "actual-handoff",
        scene,
        target,
        before.revision,
        after.revision,
        (first, second, private),
    )
    result = service.carry(*args)
    assert service.carry(*args) == result and not result["effects_applied"]
    refs = context.build(ADMIN, target).references
    assert refs[1].dependencies == (result["references"][first],)
    assert refs[1].origin_scene == scene and refs[1].origin_reference == second
    observer.store.engine.dispose()
    context = DirectorContextService(observer)
    visible = context.build(ADMIN, target, actor=handler).model_dump_json()
    assert "damaged antenna" in visible and "CROSS_SCENE_PC_ONLY" not in visible
    assert "CROSS_SCENE_PC_ONLY" in context.build(PLAYER, target, actor=pilot).model_dump_json()
    assert len(context.build(ADMIN, target).references) == 3


def test_handoff_rejects_stale_context_source_correction_and_revoked_consent(routed):
    observer, context, scene, _, _ = routed
    handler, _ = roles(observer, scene)
    identity, source = reference(
        context, scene, "brief", "Inspection is pending.", (handler,), "briefing"
    )
    old = SceneContinuityService(context).preview(ADMIN, scene).revision
    send(
        observer,
        scene,
        "correct",
        text="Inspection was cancelled.",
        viewer=ADMIN,
        source_id=source.source_id,
        expected_source_revision=1,
    )
    with pytest.raises(WorkflowError, match="STALE_KNOWLEDGE"):
        SceneContinuityService(context).preview(ADMIN, scene)
    with observer.store.engine.connect() as c:
        order = len(context._references(c, scene))
    revised = context.record(
        ADMIN, "reconcile", scene, source.source_id, order, known_by=(handler,), topic="briefing"
    )
    target = new_scene(observer)
    with pytest.raises(WorkflowError, match="STALE_CONTEXT"):
        SceneContinuityService(context).carry(
            ADMIN,
            "stale",
            scene,
            target,
            old,
            context.build(ADMIN, target).revision,
            (revised["id"],),
        )
    transferred = carry(context, scene, target, (revised["id"],))
    assert identity != revised["id"]
    assert "Inspection was cancelled" in context.build(ADMIN, target).model_dump_json()
    observer.set_consent(PLAYER, "revoke-origin", scene, 1, consent=False)
    with pytest.raises(WorkflowError, match="STALE_CONTINUITY"):
        context.build(ADMIN, target, actor=handler)
    review = context.archive_review(ADMIN, target)
    assert "Inspection" not in json.dumps(review)
    with pytest.raises(WorkflowError):
        context.archive_review(PLAYER, target)
    context.archive(
        ADMIN,
        "retire-revoked",
        target,
        review["revision"],
        (transferred["references"][revised["id"]],),
        "Original consent withdrawn.",
    )
    assert not context.build(ADMIN, target).references
    with pytest.raises(WorkflowError, match="SCENE_UNAVAILABLE"):
        observer.set_consent(ADMIN, "cannot-grant-for-player", scene, 1, consent=True)


def test_gm_can_review_native_owner_choice_without_taking_it_over(routed):
    observer, context, scene, game, _ = routed
    action = start(game, context="Keep the damaged antenna aligned.")
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    pass_tags(game)
    service = DirectorSessionService(context)
    work = service.work(ADMIN, scene, gm=True)
    route = next(x for x in work["decision_routes"] if x["kind"] == "actor_keep")
    assert route["owner_id"] == "2" and route["route"] == "native_owner"
    packet = service.decision_context(ADMIN, scene, route["choice_id"])
    assert packet["action"]["id"] == action and packet["application"] == "blocked"
    assert "Keep the damaged antenna aligned" in json.dumps(packet)
    assert "SYNTHETIC_GM_SECRET_CANARY" in json.dumps(packet)
    with pytest.raises(WorkflowError):
        service.decision_context(PLAYER, scene, route["choice_id"])
    assert not any(x["kind"] == "actor_keep" for x in service.work(ADMIN, scene)["decision_routes"])
