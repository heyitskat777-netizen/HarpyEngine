"""Request the real Handler adapter through a no-network Activity fixture."""

import json
from uuid import uuid4

import pytest
from m3_policy_scenario import configure_m3_fixture
from test_activity_shadow_readiness import configure, consent, opt, submission
from test_activity_shadow_readiness import fixture as fixture
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m4_completion import book, with_canon
from test_session_zero import FACILITATOR, OUTSIDE

from girlframe.ai.conversation import ConversationReply, HandlerRequest
from girlframe.scenes.campaign_time import Anchor, Position, ScenePlan
from girlframe.services.campaign_time import CampaignTimeService
from girlframe.services.onboarding import WorkflowError


def test_canon_handler_wire_payload_in_parallel_scenes(fixture, monkeypatch, tmp_path):
    app, first, game, *_ = fixture
    store = game.store
    configure_m3_fixture(store)
    with_canon(store)
    game.leave_scene(OTHER, "move-to-tower", 900)
    game.bind_scene(ADMIN, "bind-tower", 901)
    for viewer in (ADMIN, OTHER):
        game.join_scene(viewer, f"join-tower-{viewer.user_id}", 901)
    time = CampaignTimeService(store)
    position = Position(day=1, slot="morning")
    anchor = time.initialize(ADMIN, "calendar", Anchor(chapter="Relay test", position=position))[
        "receipt"
    ]
    for channel, pilot in ((900, PLAYER), (901, OTHER)):
        booked = book(
            time,
            f"schedule-{channel}",
            channel,
            anchor,
            ScenePlan(start=position, end=position, participants=(ADMIN.user_id, pilot.user_id)),
        )
        if channel == 901:
            second = booked
        else:
            assert booked == first

    def establish(statement, *, public=False):
        pilot_window = app.read(PLAYER, first, "canon-window")
        proposal = app.write(
            PLAYER,
            str(uuid4()),
            first,
            "canon-submit",
            {"window": pilot_window, "statement": statement},
        )
        return app.write(
            FACILITATOR,
            str(uuid4()),
            first,
            "canon-review",
            {**proposal, "approve": True, "public": public},
        )["id"]

    def witness(fact):
        return app.write(
            FACILITATOR,
            str(uuid4()),
            first,
            "canon-witness",
            {
                "window": app.read(FACILITATOR, first, "canon-review-window"),
                "fact": fact,
                "pilot": str(PLAYER.user_id),
            },
        )

    def report(fact):
        app.write(
            PLAYER,
            str(uuid4()),
            first,
            "canon-report",
            {"window": app.read(PLAYER, first, "canon-window"), "fact": fact},
        )

    pre_opt_in = "The practice aerial is painted brass."
    old_fact = establish(pre_opt_in)
    witness(old_fact)
    report(old_fact)
    opt(app, first)
    configure(app, first, (ADMIN, PLAYER))
    configure(app, second, (ADMIN, OTHER))
    disclosed = "The west relay battery can be collected at Dock Seven."
    stale = "The spare beacon is labelled Cobalt."
    pilot_only = "Pilot Echo saw a silver light below the relay floor."
    public = "The depot plaque dates from the Year of Glass."
    shared_fact = establish(disclosed)
    stale_fact = establish(stale)
    for fact in (shared_fact, stale_fact, establish(pilot_only)):
        witness(fact)
    establish(public, public=True)
    report(shared_fact)
    report(stale_fact)

    with pytest.raises(WorkflowError, match="facilitator"):
        app.read(OUTSIDE, first, "canon-review")
    with pytest.raises(WorkflowError, match="actual Pilot or Handler"):
        app.read(OTHER, first, "canon-window")
    assert pilot_only not in json.dumps(app.read(ADMIN, first, "canon-known"))

    client = app.session.conversation.handler.client
    fixture_post = client._post
    packets = []

    def capture(request, timeout):
        envelope = json.loads(request.data)
        packets.append(json.loads(envelope["input"][1]["content"])["packet"])
        return fixture_post(request, timeout)

    monkeypatch.setattr(client, "_post", capture)

    def ask(viewer, scene, case):
        _, source = submission(
            app, scene, viewer, case, "Handler, what is confirmed about the relay supplies?"
        )
        result = app.session.conversation.process_message(
            viewer, f"ask:{case}", scene, source["source_id"], 1
        )
        assert result["handler_decision"]["decision"]["action"] == "RESPOND"
        assert result["handler"]["reply"] is None  # private draft awaiting GM review
        return source, result["handler"]["id"], packets[-1]

    _, _, before = ask(OTHER, second, "before-closeout")
    assert disclosed not in json.dumps(before)
    _, _, local = ask(PLAYER, first, "local-report")
    assert disclosed in json.dumps(local["context"]["references"])

    replacement = "The spare beacon is labelled Amber."
    app.write(
        FACILITATOR,
        "correct-beacon",
        first,
        "canon-correct",
        {"fact": stale_fact, "statement": replacement},
    )
    closeout = app.read(ADMIN, first, "closeout")
    app.close(ADMIN, "approved-close", first, 900, closeout["revision"], ())
    game.bind_scene(ADMIN, "reuse-channel-with-new-scene", 900)
    store.engine.dispose()  # Reopen the same synthetic database.
    _, draft, after = ask(OTHER, second, "after-closeout")
    assert [ref["text"] for ref in after["closed_scene_reports"]] == [disclosed]
    assert disclosed not in json.dumps(after["context"]["references"])
    with pytest.raises(WorkflowError, match="HANDLER_CITATION_INVALID"):
        app.session.conversation._validate_handler_draft(
            HandlerRequest.model_validate_json(json.dumps(after)),
            ConversationReply(
                route="handler",
                provider="reviewed-handler-v1",
                disposition="answer",
                text=disclosed,
                source_refs=(after["closed_scene_reports"][0]["id"],),
            ),
        )
    with store.engine.connect() as c:
        _, _, recipient = app.session.observer._authorize_input(c, OTHER, second, "pilot")
    app.approve_handler(ADMIN, "approve-draft", second, draft, "Reviewed", (recipient,))

    consent(app, first, PLAYER, value=False)
    with pytest.raises(WorkflowError, match="STALE_HANDLER_DRAFT"):
        app.deliver_handler(ADMIN, "stale-after-withdrawal", second, draft)
    _, _, withdrawn = ask(OTHER, second, "after-withdrawal")
    assert disclosed not in json.dumps(withdrawn)
    assert disclosed in json.dumps(app.read(ADMIN, second, "canon-known"))
    for packet in packets:
        for forbidden in (pre_opt_in, pilot_only, public, replacement):
            assert forbidden not in json.dumps(packet)
    assert stale not in json.dumps(after)
    assert stale not in json.dumps(withdrawn)
    (tmp_path / "m4-handler-packets.json").write_text(json.dumps(packets, indent=2))
