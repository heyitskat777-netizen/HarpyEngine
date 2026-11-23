"""Exercise the Activity JSON controls against the real scene and AI services."""

import json
from uuid import uuid4

import pytest
from test_ai_npc_reactions import ADDRESS, NPC, SPEECH, FakeGateway, enable, working_scene
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_m4_completion import book
from test_session_zero import FACILITATOR, OUTSIDE
from test_world_service import transfer_npc

from girlframe.activity.npc import ActivityNpcApi
from girlframe.scenes.campaign_time import Anchor, Cut, Position, ScenePlan
from girlframe.scenes.canon import CanonWindow
from girlframe.services.ai_npc_reactions import GUIDE_HANDOFF, RESULT, NpcReactionService
from girlframe.services.campaign_time import CampaignTimeService
from girlframe.services.canon_briefings import CanonBriefings
from girlframe.services.onboarding import WorkflowError


def call(api, viewer, scene, operation, **payload):
    return api.dispatch(viewer, {"scene_id": scene, "operation": operation, "payload": payload})


def address(api, scene, statement=ADDRESS):
    view = call(api, PLAYER, scene, "overview")
    return call(
        api,
        PLAYER,
        scene,
        "address",
        submission_id=str(uuid4()),
        window=view["targets"]["window"],
        npc_id=NPC,
        statement=statement,
    )["id"]


def review(api, scene, draft, *, approve):
    return call(
        api,
        FACILITATOR,
        scene,
        "review",
        submission_id=str(uuid4()),
        request_id=draft["id"],
        result_id=draft["result_id"],
        approve=approve,
    )


def test_address_draft_approve_and_decline_in_the_activity_json_api(ledger):
    _, game, _, _, scene = working_scene(ledger)
    enable(ledger)
    gateway = FakeGateway()
    api = ActivityNpcApi(NpcReactionService(ledger, gateway))
    before = state(game)
    saved = address(api, scene)
    assert call(api, PLAYER, scene, "overview")["addresses"][0]["id"] == saved
    assert call(api, OTHER, scene, "overview")["addresses"] == []

    with pytest.raises(WorkflowError, match="Handler"):
        call(api, PLAYER, scene, "draft", submission_id=str(uuid4()), address_id=saved)
    with pytest.raises(WorkflowError, match="unavailable in this scene"):
        call(api, ADMIN, str(uuid4()), "draft", submission_id=str(uuid4()), address_id=saved)

    first = call(api, ADMIN, scene, "draft", submission_id=str(uuid4()), address_id=saved)
    assert first["status"] == "ready" and first["proposal"]["speech"] == SPEECH
    [preview] = call(api, FACILITATOR, scene, "overview")["requests"]
    assert preview["review_audience"]["kind"] == "scene_cast"
    assert preview["review_audience"]["listeners"] == [
        state(game).sheets[str(viewer.user_id)].callsign for viewer in (PLAYER, OTHER)
    ]
    assert (preview | {"review_audience": None}) == (first | {"review_audience": None})
    assert review(api, scene, first, approve=False)["status"] == "declined"
    assert call(api, PLAYER, scene, "overview")["feed"] == []

    retried = str(uuid4())
    second = call(api, ADMIN, scene, "draft", submission_id=retried, address_id=saved)
    assert call(api, ADMIN, scene, "draft", submission_id=retried, address_id=saved) == second
    [preview, _] = call(api, FACILITATOR, scene, "overview")["requests"]
    assert preview["id"] == second["id"]
    assert "review_audience" not in call(api, ADMIN, scene, "overview")["requests"][0]
    edit = {
        "submission_id": str(uuid4()),
        "request_id": second["id"],
        "result_id": second["result_id"],
        "approve": True,
        "edited_speech": "Do you remember when the crate came in?",
    }
    with pytest.raises(WorkflowError, match="Preview the audience"):
        call(api, FACILITATOR, scene, "review", **edit)
    with pytest.raises(WorkflowError, match="STALE_AUDIENCE"):
        call(api, FACILITATOR, scene, "review", **edit, expected_audience="f" * 64)
    edit["expected_audience"] = preview["review_audience"]["receipt"]
    with pytest.raises(WorkflowError, match="mechanical effects"):
        call(api, FACILITATOR, scene, "review", **(edit | {"edited_speech": "Roll 2d6."}))
    assert call(api, PLAYER, scene, "overview")["feed"] == []
    approval = call(api, FACILITATOR, scene, "review", **edit)
    assert call(api, FACILITATOR, scene, "review", **edit) == approval
    [message] = call(api, OTHER, scene, "overview")["feed"]
    assert message["id"] == approval["reaction_id"] and message["speech"] == edit["edited_speech"]
    assert approval["proposal"]["speech"] == edit["edited_speech"]
    with game.store.engine.connect() as c:
        original = NpcReactionService(game.store)._row(c, RESULT, second["result_id"])
        assert json.loads(original["payload_json"])["proposal"]["speech"] == SPEECH
    assert call(api, OUTSIDE, scene, "overview")["feed"] == []
    assert state(game) == before and len(gateway.calls) == 2


def test_guide_offer_uses_a_legal_destination_and_owned_pilot_choices(ledger):
    world, game, _, _, scene = working_scene(ledger)
    enable(ledger)
    gateway = FakeGateway()
    api = ActivityNpcApi(NpcReactionService(ledger, gateway))
    saved = address(api, scene, "Can you guide us to the drop-off?")
    with pytest.raises(WorkflowError, match="operational destination"):
        call(
            api,
            ADMIN,
            scene,
            "draft",
            submission_id=str(uuid4()),
            address_id=saved,
            guide_destination_id="invented",
        )

    [destination, *_] = call(api, ADMIN, scene, "overview")["destinations"]
    gateway.speech = f"I can guide you to {destination['name']}."
    draft = call(
        api,
        ADMIN,
        scene,
        "draft",
        submission_id=str(uuid4()),
        address_id=saved,
        guide_destination_id=destination["id"],
    )
    assert draft["guide"] == destination
    assert gateway.calls[-1][1].guide_destination == destination["name"]
    assert call(api, PLAYER, scene, "overview")["feed"] == []
    before = state(game)
    approved = review(api, scene, draft, approve=True)
    reaction = approved["reaction_id"]
    [offer] = call(api, PLAYER, scene, "overview")["feed"]
    assert offer["guide"] == destination | {"open": True, "response": None}
    with pytest.raises(WorkflowError, match="unavailable to your Pilot"):
        call(
            api,
            OUTSIDE,
            scene,
            "guide_response",
            submission_id=str(uuid4()),
            reaction_id=reaction,
            choice="follow",
        )
    response_id = str(uuid4())
    answer = call(
        api,
        PLAYER,
        scene,
        "guide_response",
        submission_id=response_id,
        reaction_id=reaction,
        choice="follow",
    )
    assert (
        call(
            api,
            PLAYER,
            scene,
            "guide_response",
            submission_id=response_id,
            reaction_id=reaction,
            choice="follow",
        )
        == answer
    )
    assert call(api, PLAYER, scene, "overview")["feed"][0]["guide"]["response"] == "follow"
    assert call(api, OTHER, scene, "overview")["feed"][0]["guide"]["response"] is None
    declined = call(
        api,
        OTHER,
        scene,
        "guide_response",
        submission_id=str(uuid4()),
        reaction_id=reaction,
        choice="decline",
    )
    assert declined["choice"] == "decline"
    assert call(api, ADMIN, scene, "overview")["requests"][0]["guide_responses"] == {
        "follow": 1,
        "decline": 1,
    }
    assert state(game) == before

    next_address = address(api, scene, "Are you still able to show us the way?")
    next_draft = call(
        api,
        ADMIN,
        scene,
        "draft",
        submission_id=str(uuid4()),
        address_id=next_address,
        guide_destination_id=destination["id"],
    )
    next_offer = review(api, scene, next_draft, approve=True)["reaction_id"]
    assert call(api, OTHER, scene, "overview")["feed"][-1]["guide"]["open"]
    transfer_npc(world, ADMIN, OTHER, NPC)
    assert not call(api, OTHER, scene, "overview")["feed"][-1]["guide"]["open"]
    with pytest.raises(WorkflowError, match="STALE_GUIDE"):
        call(
            api,
            OTHER,
            scene,
            "guide_response",
            submission_id=str(uuid4()),
            reaction_id=next_offer,
            choice="decline",
        )
    assert call(api, ADMIN, scene, "overview")["requests"][-1]["guide_responses"] == {
        "follow": 1,
        "decline": 1,
    }


def test_guide_books_actual_attendance_only_for_pilots_who_followed(ledger, monkeypatch):
    _, game, _, _, source = working_scene(ledger)
    enable(ledger)
    api = ActivityNpcApi(NpcReactionService(ledger, FakeGateway()))
    timeline = CampaignTimeService(ledger)
    target = game.bind_scene(ADMIN, "bind-guide-destination", 902)["scene"]
    saved = address(api, source)
    destination = call(api, ADMIN, source, "overview")["destinations"][0]
    draft = call(
        api,
        ADMIN,
        source,
        "draft",
        submission_id=str(uuid4()),
        address_id=saved,
        guide_destination_id=destination["id"],
    )
    offer = review(api, source, draft, approve=True)["reaction_id"]
    before = state(game)
    [binding] = call(api, ADMIN, source, "overview")["guide_bookings"]["scenes"]
    assert binding["id"] == target
    position = Position(day=1, slot="afternoon")
    body = {
        "submission_id": str(uuid4()),
        "reaction_id": offer,
        "destination_scene_id": target,
        "destination_revision": binding["revision"],
        "position": position.model_dump(),
    }
    with pytest.raises(WorkflowError):
        call(api, PLAYER, source, "guide_handoff", **body)
    with pytest.raises(WorkflowError, match="must choose Follow"):
        call(api, ADMIN, source, "guide_handoff", **body)
    call(
        api,
        PLAYER,
        source,
        "guide_response",
        submission_id=str(uuid4()),
        reaction_id=offer,
        choice="follow",
    )
    audit = api.reactions._audit

    def fail_handoff(c, viewer, key, kind, data, **kwargs):
        if kind == GUIDE_HANDOFF:
            raise RuntimeError("synthetic receipt failure")
        return audit(c, viewer, key, kind, data, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(api.reactions, "_audit", fail_handoff)
        with pytest.raises(RuntimeError, match="synthetic receipt failure"):
            call(api, ADMIN, source, "guide_handoff", **body)
    assert call(api, ADMIN, source, "overview")["guide_bookings"]["scenes"] == [binding]

    handoff = call(api, ADMIN, source, "guide_handoff", **body)
    assert handoff["scene"] == target and handoff["followers"] == 1
    assert call(api, ADMIN, source, "guide_handoff", **body) == handoff
    with pytest.raises(WorkflowError, match="already booked"):
        call(api, ADMIN, source, "guide_handoff", **(body | {"submission_id": str(uuid4())}))
    with pytest.raises(WorkflowError, match="already booked"):
        call(
            api,
            OTHER,
            source,
            "guide_response",
            submission_id=str(uuid4()),
            reaction_id=offer,
            choice="follow",
        )
    [line] = call(api, PLAYER, source, "overview")["feed"]
    assert line["guide"]["booking"] == {"scene": target, "position": position.model_dump()}
    [line] = call(api, OTHER, source, "overview")["feed"]
    assert "booking" not in line["guide"] and not line["guide"]["open"]
    calendar_view = timeline.projection(PLAYER)
    [booked] = [item for item in calendar_view["scenes"] if item["id"] == target]
    assert booked["location"] == destination["name"]
    assert booked["scheduled_participants"] == [str(PLAYER.user_id)] and not booked["joined"]
    assert target not in {item["id"] for item in timeline.projection(OTHER)["scenes"]}
    assert state(game) == before

    with pytest.raises(WorkflowError, match="opening slot has not arrived"):
        game.join_scene(PLAYER, "early-guide-arrival", 902)
    game.close_scene(ADMIN, "close-guide-source", 900)
    cut = Cut(target=Anchor(chapter="Relay", position=position))
    preview = timeline.preview_cut(ADMIN, cut)
    timeline.commit_cut(ADMIN, "cut-to-guide-destination", cut, preview["token"])
    with pytest.raises(WorkflowError, match="schedule this Pilot"):
        game.join_scene(OTHER, "unscheduled-guide-arrival", 902)
    game.join_scene(PLAYER, "guide-arrival", 902)
    [booked] = [item for item in timeline.projection(PLAYER)["scenes"] if item["id"] == target]
    assert booked["joined"]


def test_private_npc_lead_requires_witness_and_explicit_report_for_briefings(ledger):
    _, game, canon, _, source = working_scene(ledger)
    enable(ledger)
    gateway = FakeGateway()
    api = ActivityNpcApi(NpcReactionService(ledger, gateway))
    timeline = CampaignTimeService(ledger)
    briefings = CanonBriefings(ledger)
    witness = call(api, FACILITATOR, source, "overview")["lead_witness"]
    window = CanonWindow.model_validate(witness["window"])
    secret = "A spare battery is in the relay cupboard."
    fact = canon.establish(FACILITATOR, "lead-fact", window, secret)
    private = "A hidden flare is missing."
    unrelated = canon.establish(FACILITATOR, "unwitnessed-fact", window, private)
    saved = address(api, source)
    payload = {"address_id": saved, "submission_id": str(uuid4()), "lead_fact_id": fact}
    with pytest.raises(WorkflowError, match="this NPC witnessed"):
        call(api, ADMIN, source, "draft", **payload)
    assert gateway.calls == []

    witness = call(api, FACILITATOR, source, "overview")["lead_witness"]
    record = {
        "npc_id": NPC,
        "fact_id": fact,
        "window": witness["window"],
        "submission_id": str(uuid4()),
    }
    with pytest.raises(WorkflowError, match="designated canon facilitator"):
        call(api, ADMIN, source, "npc_witness", **record)
    receipt = call(api, FACILITATOR, source, "npc_witness", **record)
    assert call(api, FACILITATOR, source, "npc_witness", **record) == receipt
    assert call(api, ADMIN, source, "overview")["leads"] == {
        NPC: [{"fact_id": fact, "statement": secret}],
    }

    gateway.speech = secret
    first = call(api, ADMIN, source, "draft", **payload)
    assert first["lead"] == {"fact_id": fact, "statement": secret}
    assert gateway.calls[-1][1].lead_fact == secret
    assert unrelated not in str(gateway.calls[-1]) and private not in str(gateway.calls[-1])
    assert review(api, source, first, approve=False)["status"] == "declined"
    assert canon.known(PLAYER) == ()
    draft = call(api, ADMIN, source, "draft", **(payload | {"submission_id": str(uuid4())}))
    [lead_preview, _] = call(api, FACILITATOR, source, "overview")["requests"]
    audience = lead_preview["review_audience"]
    assert audience["kind"] == "private_lead"
    assert audience["listeners"] == [state(game).sheets[str(PLAYER.user_id)].callsign]
    approved = call(
        api,
        FACILITATOR,
        source,
        "review",
        submission_id=str(uuid4()),
        request_id=draft["id"],
        result_id=draft["result_id"],
        approve=True,
        expected_audience=audience["receipt"],
        edited_speech="There's a spare battery in the relay cupboard.",
    )
    [line] = call(api, PLAYER, source, "overview")["feed"]
    assert line["id"] == approved["reaction_id"] and line["lead"] == draft["lead"]
    assert line["speech"] == approved["proposal"]["speech"]
    assert call(api, OTHER, source, "overview")["feed"] == []
    assert call(api, ADMIN, source, "overview")["feed"] == []
    [known] = canon.known(PLAYER)
    assert known.method == "told" and known.fact_id == fact
    assert canon.known(OTHER) == canon.known(ADMIN) == ()
    with ledger.engine.connect() as c:
        [(_, grant)] = canon._grants_for(c, PLAYER.user_id, canon.principal(c, PLAYER.user_id))
        assert grant.source_grant_id == receipt["id"]
    with pytest.raises(WorkflowError, match="Handler has learned"):
        briefings.draft(ADMIN, "guess-private-lead", (fact,))

    game.close_scene(ADMIN, "close-lead-source", 900)
    next_scene = game.bind_scene(ADMIN, "bind-report-scene", 903)["scene"]
    position = Position(day=1, slot="afternoon")
    current = timeline.projection(ADMIN)["anchor_receipt"]
    book(
        timeline,
        "book-report-scene",
        903,
        current,
        ScenePlan(start=position, end=position, participants=(ADMIN.user_id, PLAYER.user_id)),
    )
    cut = Cut(target=Anchor(chapter="Relay", position=position))
    preview = timeline.preview_cut(ADMIN, cut)
    timeline.commit_cut(ADMIN, "cut-to-report-scene", cut, preview["token"])
    game.join_scene(PLAYER, "join-as-reporting-pilot", 903)
    assert call(api, PLAYER, next_scene, "overview")["lead_reports"] is None
    game.join_scene(ADMIN, "join-as-listening-handler", 903)
    reports = call(api, PLAYER, next_scene, "overview")["lead_reports"]
    assert reports["facts"] == [line["lead"]]
    payload = {"submission_id": str(uuid4()), "window": reports["window"], "fact_id": fact}
    assert call(api, PLAYER, next_scene, "report_lead", **payload)["id"]
    assert call(api, PLAYER, next_scene, "overview")["lead_reports"] is None
    assert canon.known(ADMIN)[0].method == "reported"
    assert briefings.draft(ADMIN, "cite-reported-lead", (fact,))


def test_corrected_fact_cannot_be_published_from_a_ready_npc_lead(ledger):
    _, _, canon, _, scene = working_scene(ledger)
    enable(ledger)
    api = ActivityNpcApi(NpcReactionService(ledger, FakeGateway()))
    witness = call(api, FACILITATOR, scene, "overview")["lead_witness"]
    window = CanonWindow.model_validate(witness["window"])
    fact = canon.establish(FACILITATOR, "lead-fact", window, "The relay is open.")
    call(
        api,
        FACILITATOR,
        scene,
        "npc_witness",
        npc_id=NPC,
        fact_id=fact,
        window=witness["window"],
        submission_id=str(uuid4()),
    )
    draft = call(
        api,
        ADMIN,
        scene,
        "draft",
        address_id=address(api, scene),
        lead_fact_id=fact,
        submission_id=str(uuid4()),
    )
    assert draft["status"] == "ready"
    canon.correct(FACILITATOR, "lead-corrected", fact, "The relay is closed.")
    with pytest.raises(WorkflowError, match="STALE_REACTION"):
        review(api, scene, draft, approve=True)
    assert call(api, ADMIN, scene, "overview")["leads"] == {}
    assert call(api, PLAYER, scene, "overview")["feed"] == []
    assert canon.known(PLAYER) == ()
