"""One offline time-sensitive Handler exchange and its original human controls."""

from dataclasses import replace
from uuid import uuid4

import pytest
from test_campaign_time import NIGHT, booked
from test_director_activity_scene import P2Scene, input_command
from test_director_continuity import roles
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_mission_timing import START, option, setup
from test_mission_timing import publish as publish_options

from girlframe.ai.conversation import ConversationReply
from girlframe.ai.observation import ObservationPolicy
from girlframe.scenes.campaign_time import ScenePlan
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.director_session import DirectorSessionService
from girlframe.services.onboarding import WorkflowError


class ClockVoice:
    def __init__(self):
        self.requests = []

    def respond(self, request):
        self.requests.append(request)
        clock = request.fictional_time.clock
        assert clock is not None
        return ConversationReply(
            route="handler",
            provider="reviewed-handler-v1",
            disposition="answer",
            clock_receipt=clock.receipt,
            text=f"{clock.minute // 60}:{clock.minute % 60:02}. Keep me posted.",
        )


def test_reviewed_clock_reply_uses_saved_time_and_original_pilot_audience(ledger):
    _, timeline, opened, _, _, game = setup(ledger)
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    observer = DirectorObservationService(ledger, synthetic=True)
    observer.configure_scene(ADMIN, "observe-clock", scene, 0, ObservationPolicy(mode="shadow"))
    for person in (ADMIN, PLAYER, OTHER):
        observer.set_consent(person, f"clock-consent:{person.user_id}", scene, 1, consent=True)
    context = DirectorContextService(observer)
    voice = ClockVoice()
    svc = DirectorConversationService(context, handler=voice, handler_mode="reviewed")
    app = P2Scene(DirectorSessionService(context, conversation=svc))
    anchor = timeline.projection(ADMIN)["anchor_receipt"]
    game.bind_scene(ADMIN, "bind-parallel-time", 901)
    parallel = booked(timeline, game, anchor, 901, (1,))
    game.join_scene(ADMIN, "join-parallel-time", 901)
    observer.configure_scene(
        ADMIN, "observe-parallel-time", parallel, 0, ObservationPolicy(mode="shadow")
    )
    observer.set_consent(ADMIN, "parallel-time-consent", parallel, 1, consent=True)
    _, pilot = roles(observer, scene)
    with ledger.engine.connect() as c:
        outsider = observer._authorize_input(c, OTHER, scene, "pilot")[2]
        gm = context._build(c, ADMIN, scene)
        assert gm.fictional_time.clock.minute == START
        parallel_gm = context._build(c, ADMIN, parallel)
        assert parallel_gm.fictional_time.clock is None
        assert context._build(c, PLAYER, scene, actor=pilot).fictional_time is None

    original = app.read(PLAYER, scene, "fictional-time")
    assert original["mission_timing"]["minute"] == START
    assert "handler_controls" not in original
    assert "mission_timing" not in app.read(OTHER, scene, "fictional-time")
    route = option("Tunnel route", 15)
    menu = app.write(
        ADMIN,
        "publish-clock",
        scene,
        "time-publish",
        {
            "id": opened["id"],
            "revision": opened["receipt"],
            "options": {"available": [route.model_dump(mode="json") | {"pilot": "2"}]},
        },
    )

    def message(key, text):
        command = input_command(observer, PLAYER, scene, key, text)
        return app.session.submit(PLAYER, scene, command)["conversation"]

    silence = message("ordinary-clock-turn", "I check my harness.")
    assert silence["handler_decision"]["decision"]["action"] == "WAIT"
    assert not voice.requests
    first = message("ask-clock", "Handler, what time is it?")["handler"]["id"]
    request = voice.requests[-1]
    assert request.fictional_time.clock.receipt == menu["receipt"]
    assert "Tunnel route" not in request.model_dump_json()
    with pytest.raises(WorkflowError, match="HANDLER_CLOCK_INVALID"):
        svc._validate_handler_draft(
            request,
            voice.respond(request).model_copy(update={"clock_receipt": str(uuid4())}),
            request.response_need,
        )
    with pytest.raises(WorkflowError, match="HANDLER_CLOCK_AUDIENCE"):
        svc.review_handler(
            ADMIN,
            "wrong-clock-audience",
            scene,
            first,
            "approve",
            "Check time",
            delivery_recipients=(pilot, outsider),
        )
    svc.review_handler(
        ADMIN, "approved-clock", scene, first, "approve", "Check time", delivery_recipients=(pilot,)
    )
    choice = {"id": opened["id"], "menu": menu["receipt"], "option": route.id}
    with pytest.raises(WorkflowError, match="joined and dispatched"):
        app.write(OTHER, "foreign-timed-choice", scene, "time-choose", choice)
    saved = app.write(PLAYER, "owned-timed-choice", scene, "time-choose", choice)
    assert saved["minute"] == 1115
    assert app.write(PLAYER, "owned-timed-choice", scene, "time-choose", choice) == saved
    with ledger.engine.connect() as c:
        current = context._build(c, ADMIN, scene)
        assert current.revision != gm.revision and current.fictional_time.clock.minute == 1115
        assert context._build(c, ADMIN, parallel) == parallel_gm
    assert app.gm_work(ADMIN, scene)["fictional_time"]["clock"]["receipt"] == saved["receipt"]
    with pytest.raises(WorkflowError, match="STALE_HANDLER_CLOCK"):
        svc.delivery.deliver(ADMIN, "deliver-old-clock", scene, first)
    draft = message("ask-current-clock", "Handler, what time is it now?")["handler"]["id"]
    svc.review_handler(
        ADMIN,
        "approved-current-clock",
        scene,
        draft,
        "approve",
        "Current time",
        delivery_recipients=(pilot,),
    )
    assert svc.delivery.preview(ADMIN, scene, draft)["text"] == "18:35. Keep me posted."
    svc.delivery.deliver(ADMIN, "deliver-current-clock", scene, draft)
    assert svc.delivery.contributions(PLAYER, scene)[0]["text"] == "18:35. Keep me posted."
    assert svc.delivery.contributions(OTHER, scene) == []

    app.write(
        ADMIN,
        "close-clock",
        scene,
        "time-close",
        {"id": opened["id"], "revision": saved["receipt"]},
    )
    with ledger.engine.connect() as c:
        revision = game.scene(c, 900)["revision"]
    timeline.schedule(
        ADMIN,
        "move-scene-to-night",
        900,
        scene,
        revision,
        anchor,
        ScenePlan(start=NIGHT, end=NIGHT, participants=(2, 3)),
    )
    with pytest.raises(WorkflowError, match="opening slot has not arrived"):
        message("premature-observation", "I try the hatch.")


def test_timing_review_survives_reconnect_and_routes_to_original_authority(ledger):
    timing, timeline, opened, _, _, game = setup(ledger, consequence=None)
    handler = replace(ADMIN, is_administrator=False)
    reviewer = replace(OTHER, is_administrator=True)
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    anchor = timeline.projection(ADMIN)["anchor_receipt"]
    game.bind_scene(ADMIN, "bind-review-parallel", 901)
    parallel = booked(timeline, game, anchor, 901, (1,))
    game.join_scene(ADMIN, "join-review-parallel", 901)
    observer = DirectorObservationService(ledger, synthetic=True)
    for identity, cast in ((scene, (ADMIN, PLAYER, OTHER)), (parallel, (ADMIN,))):
        observer.configure_scene(
            ADMIN, f"notice:{identity}", identity, 0, ObservationPolicy(mode="shadow")
        )
        for member in cast:
            observer.set_consent(
                member, f"consent:{identity}:{member.user_id}", identity, 1, consent=True
            )

    def app():
        return P2Scene(DirectorSessionService(DirectorContextService(observer)))

    adapter = app()
    uncertain = option("Blind route", None)
    menu = publish_options(timing, opened, uncertain)
    needs_duration = timing.choose(
        PLAYER, "request-duration", opened["id"], menu["receipt"], uncertain.id
    )
    (work,) = adapter.gm_work(reviewer, scene)["timing_reviews"]
    assert (work["source_receipt"], work["owner"], work["next_action"]) == (
        needs_duration["receipt"],
        "handler",
        "publish_options",
    )
    assert adapter.read(handler, scene, "fictional-time")["timing_ruling"] == work
    assert "timing_ruling" not in adapter.read(PLAYER, scene, "fictional-time")
    assert adapter.read(PLAYER, scene, "work")["timing_reviews"] == []
    assert adapter.gm_work(ADMIN, parallel)["timing_reviews"] == []
    with pytest.raises(WorkflowError):
        adapter.gm_work(handler, scene)

    route = option("Long route", 25)
    revised = {
        "id": opened["id"],
        "revision": needs_duration["receipt"],
        "options": {"available": [route.model_dump(mode="json") | {"pilot": "2"}]},
    }
    with pytest.raises(WorkflowError):
        adapter.write(reviewer, "wrong-duration-owner", scene, "time-publish", revised)
    menu = adapter.write(handler, "correct-duration", scene, "time-publish", revised)
    assert adapter.gm_work(reviewer, scene)["timing_reviews"] == []
    need_consequence = timing.choose(
        PLAYER, "request-consequence", opened["id"], menu["receipt"], route.id
    )
    (work,) = adapter.gm_work(reviewer, scene)["timing_reviews"]
    assert work["next_action"] == "define_consequence" and work["minute"] == START
    assert work["option_label"] == "Long route" and work["attempted_minute"] == 1125
    fixed = adapter.write(
        handler,
        "supply-consequence",
        scene,
        "time-consequence",
        {
            "id": opened["id"],
            "revision": need_consequence["receipt"],
            "account": "The shuttle leaves.",
        },
    )
    assert adapter.gm_work(reviewer, scene)["timing_reviews"] == []
    assert fixed["minute"] == START
    with pytest.raises(WorkflowError, match="STALE_TIMING"):
        timing.choose(PLAYER, "old-cutoff-menu", opened["id"], menu["receipt"], route.id)
    choice = (PLAYER, "cross-cutoff", opened["id"], fixed["receipt"], route.id)
    cutoff = timing.choose(*choice)
    ledger.engine.dispose()
    adapter = app()
    assert timing.choose(*choice) == cutoff
    (work,) = adapter.gm_work(reviewer, scene)["timing_reviews"]
    assert (work["source_receipt"], work["from_minute"], work["minute"], work["owner"]) == (
        cutoff["receipt"],
        START,
        1125,
        "gm",
    )
    timing.close(handler, "close-after-cutoff", opened["id"], cutoff["receipt"])
    assert adapter.gm_work(reviewer, scene)["timing_reviews"] == [work]
    manual = P2Scene(
        DirectorSessionService(DirectorContextService(DirectorObservationService(ledger))),
        facilitator_id=handler.user_id,
    )
    assert manual.read(handler, "", "fictional-time")["timing_reviews"] == [work]
    assert "timing_reviews" not in manual.read(PLAYER, "", "fictional-time")
    with pytest.raises(WorkflowError, match="select a committed cutoff"):
        adapter.write(
            ADMIN,
            "other-scene-cutoff",
            parallel,
            "time-acknowledge",
            {
                "scene": parallel,
                "source_receipt": cutoff["receipt"],
            },
        )
    data = {"scene": scene, "source_receipt": cutoff["receipt"]}
    with pytest.raises(WorkflowError):
        adapter.write(handler, "handler-cannot-ack", scene, "time-acknowledge", data)
    observer.set_consent(PLAYER, "withdraw-clock-review", scene, 1, consent=False)
    with pytest.raises(WorkflowError, match="OBSERVATION_DISABLED"):
        adapter.write(reviewer, "consent-required", scene, "time-acknowledge", data)
    observer.set_consent(PLAYER, "renew-clock-review", scene, 1, consent=True)
    revision = observer.status(ADMIN, scene).scene_revision
    adapter.close(ADMIN, "close-scene-after-cutoff", scene, 900, revision, ())
    assert adapter.read(reviewer, scene, "timing-review")["items"] == [work]
    first = adapter.write(reviewer, "acknowledge-cutoff", scene, "time-acknowledge", data)
    assert first["effects_applied"] is False
    assert adapter.write(reviewer, "repeat-cutoff-review", scene, "time-acknowledge", data) == first
    assert adapter.read(reviewer, scene, "timing-review")["items"] == []
