"""A scoped intervention can propose Handler action and hand off an actual briefing."""

import pytest
from m3_policy_scenario import configure_m3_fixture
from test_director_continuity import roles
from test_director_conversation import routed as routed
from test_director_observation import observed as observed
from test_director_observation import send
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.ai.conversation import ConversationReply
from girlframe.ai.director_dossiers import DossierProfile, DossierState
from girlframe.ai.gm_outcomes import HandlerOutcome, OutcomeProposal
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.director_session import DirectorSessionService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.onboarding import WorkflowError


class HandlerFixture:
    def __init__(self):
        self.requests = []

    def respond(self, request):
        self.requests.append(request)
        return ConversationReply(
            route="handler",
            disposition="answer",
            source_refs=request.response_need.source_refs,
            text="The public platform is open. Use your own check before moving.",
            handler_action="I mark the public platform on my copy of the map.",
            handler_play_offer="brief",
            provider="reviewed-handler-v1",
        )


def test_handler_proactive_action_and_native_brief_preserve_authority_and_scope(routed):
    observer, context, scene, game, _ = routed
    configure_m3_fixture(observer.store)
    policy = observer.store.policy
    observer.store.policy = policy.model_copy(
        update={
            "m3_approval": policy.m3_approval.model_copy(
                update={"subsystems": policy.m3_approval.subsystems | {"plays"}}
            )
        }
    )
    handler, pilot = roles(observer, scene)
    provider = HandlerFixture()
    service = DirectorConversationService(context, handler=provider, handler_mode="reviewed")
    session = DirectorSessionService(context, conversation=service)
    for persona, owner, voice in (
        (handler, ADMIN, "Careful, clipped"),
        (pilot, PLAYER, "PRIVATE_PILOT_VOICE"),
    ):
        dossier = session.dossiers.propose(
            owner,
            f"dossier-{voice}",
            scene,
            persona,
            0,
            DossierProfile(voice=voice),
            DossierState(),
        )
        session.dossiers.confirm(owner, f"confirm-{voice}", scene, dossier["id"])
    session.dossiers.gm_notes(ADMIN, "hidden-note", scene, handler, 0, "PRIVATE_GM_NOTE")
    _, quiet = send(observer, scene, "quiet", text="I finish my tea.", fictional_channel="comms")
    assert (
        service.process_message(PLAYER, "quiet-route", scene, quiet.source_id, 1)["handler"] is None
    )
    _, briefing = send(
        observer,
        scene,
        "brief",
        text="The public platform is open.",
        viewer=ADMIN,
        fictional_channel="comms",
    )
    with observer.store.engine.connect() as c:
        order = len(context._references(c, scene))
    context.record(
        ADMIN,
        "known-brief",
        scene,
        briefing.source_id,
        order,
        known_by=(handler, pilot),
        topic="briefing",
    )
    assert (
        service.process_message(ADMIN, "no-self-reply", scene, briefing.source_id, 1)["handler"]
        is None
    )
    _, trigger = send(
        observer, scene, "turn-start", text="I unfold my map.", fictional_channel="comms"
    )
    native_before = state(game).model_dump_json()
    result = service.process_message(PLAYER, "turn-route", scene, trigger.source_id, 1)
    assert result["handler_decision"]["decision"]["reason"] == "known_update"
    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert request.persona.profile.voice == "Careful, clipped"
    assert "PRIVATE_PILOT_VOICE" not in request.model_dump_json()
    assert "PRIVATE_GM_NOTE" not in request.model_dump_json()
    assert "SYNTHETIC_PC_ONLY_REFERENCE" not in request.model_dump_json()
    draft = result["handler"]["id"]
    revision = state(game).revision
    with pytest.raises(WorkflowError, match="HANDLER_PLAY_REVIEW"):
        service.start_handler_brief(ADMIN, scene, draft, revision)
    service.review_handler(
        ADMIN, "review", scene, draft, "approve", "Grounded own action and briefing."
    )
    assert state(game).model_dump_json() == native_before
    assert not service.handler_play_offers(PLAYER, scene)
    assert session.work(ADMIN, scene)["handler_play_offers"][0]["id"] == draft
    exchange = service.get(PLAYER, scene, draft)
    assert exchange["reply"]["handler_action"]
    with pytest.raises(WorkflowError, match="HANDLER_PLAY_OWNER"):
        service.start_handler_brief(PLAYER, scene, draft, revision)
    grant = service.start_handler_brief(ADMIN, scene, draft, revision)
    assert service.start_handler_brief(ADMIN, scene, draft, revision) == grant
    assert not service.handler_play_offers(ADMIN, scene)
    native = HandlerPlayService(observer.store)
    with pytest.raises(WorkflowError, match="reviewed briefing"):
        native.submit(
            ADMIN,
            "unrelated-effect",
            grant["id"],
            grant["game_revision"],
            "expectation",
            Effect(
                kind="expectation",
                account="Invented",
                detail="Invented duty",
                stakes="Invented cost",
            ),
        )
    opened = session.outcomes.open(ADMIN, "open", scene, "handler_grant", grant["id"])
    packet = session.outcomes.packet(ADMIN, scene, opened["id"])
    account = exchange["reply"]["text"]
    proposal = session.outcomes.propose(
        ADMIN,
        "propose",
        scene,
        opened["id"],
        OutcomeProposal(
            request_id=packet.request_id,
            decision=HandlerOutcome(play="brief", effect=Effect(kind="brief", account=account)),
            cited_evidence=("source", "native"),
            private_reasoning="Exact reviewed briefing.",
        ),
    )
    assert state(game).handler_plays[-1].state == "pending"
    session.outcomes.confirm(ADMIN, "confirm", scene, proposal["id"])
    assert native.notice(PLAYER, grant["id"])["account"] == account
    with pytest.raises(WorkflowError):
        native.notice(OTHER, grant["id"])
    assert state(game).handler_plays[-1].state == "complete"
    _, repeat = send(
        observer, scene, "more-quiet", text="I check the strap.", fictional_channel="comms"
    )
    assert (
        service.process_message(PLAYER, "no-repetition", scene, repeat.source_id, 1)["handler"]
        is None
    )
