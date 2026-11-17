"""Role-filtered natural reactions reuse actual batch claims and preserve engine authority."""

import json

import pytest
from pydantic import ValidationError
from test_director_continuity import roles
from test_director_conversation import routed as routed
from test_director_observation import observed as observed
from test_director_observation import send
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.ai.director_reactions import ReactionProposal
from girlframe.services.director_reactions import DirectorReactionService
from girlframe.services.director_session import DirectorSessionService
from girlframe.services.onboarding import WorkflowError


def opened(routed, key="source", *, private=False, actor=None):
    observer, context, scene, _, _ = routed
    handler, _ = roles(observer, scene)
    _, source = send(
        observer,
        scene,
        key,
        text="Handler, what is in scope?",
        fictional_channel="private" if private else "comms",
    )
    service = DirectorReactionService(context)
    request = service.open(ADMIN, key + ":open", scene, actor or handler, source.source_id)
    return service, request["id"], source


def draft(service, scene, request, *, kind="SCENE_OFFER", key="proposal"):
    return service.propose(
        ADMIN,
        key,
        scene,
        request,
        ReactionProposal(
            request_id=request,
            kind=kind,
            text="Observe accessible areas; report what you see.",
            rationale="PRIVATE_MODEL_REASON: use only the role's briefing.",
        ),
    )


def test_filtered_provider_natural_reply_review_and_retry_never_apply_mechanics(routed):
    from test_director_worldbuilding import ready

    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_world_state import Npc
    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_cast import CastService
    from girlframe.services.m3_npc_roles import NpcRoleService

    observer, context, scene, game, dice = routed
    world = ready(routed).world
    handler, pilot = roles(observer, scene)
    npc_roles = NpcRoleService(world)
    invitation = npc_roles.offer(
        ADMIN,
        "offer",
        state(game).revision,
        Npc(
            id="reaction-contact",
            name="Mora",
            jobs=("mechanic",),
            detail="Keeps notes.",
            controller=3,
            cell=(0, 0),
        ),
    )
    npc_roles.respond(OTHER, "accept", invitation["id"], state(game).revision, "accept")
    npc = ActorRef(kind="npc", entity="reaction-contact")
    cast = CastService(ActorService(world.missions))
    current = cast.view(OTHER, 900)
    cast.change(OTHER, "join", 900, current["game_revision"], current["cast_revision"], "join", npc)
    for controller, actor in ((ADMIN, handler), (PLAYER, pilot)):
        current = cast.view(controller, 900)
        if any(role["ref"] == actor.model_dump(mode="json") for role in current["roles"]):
            continue
        cast.change(
            controller,
            "join:" + actor.kind,
            900,
            current["game_revision"],
            current["cast_revision"],
            "join",
            actor,
        )
    service, request, _ = opened(routed, actor=npc)
    before = state(game).model_dump_json()

    class Fixture:
        calls = 0

        def propose(self, packet):
            self.calls += 1
            encoded = json.dumps(packet)
            assert "SYNTHETIC_GM_SECRET_CANARY" not in encoded
            assert "SYNTHETIC_PC_ONLY_REFERENCE" not in encoded
            assert "what is in scope" in packet["role"]["question"]
            return ReactionProposal(
                request_id=packet["request_id"],
                kind="COMPROMISE",
                text="I can review your report after the watch changes.",
                rationale="PRIVATE_MODEL_REASON",
            )

    fixture = Fixture()
    saved = service.generate(ADMIN, "generate", scene, request, fixture)
    assert service.generate(ADMIN, "generate", scene, request, fixture) == saved
    assert fixture.calls == 1
    assert service.pending(PLAYER, scene) == []
    assert service.pending(OTHER, scene)[0]["id"] == saved["id"]
    assert "PRIVATE_MODEL_REASON" not in str(
        DirectorSessionService(context).work(ADMIN, scene, gm=True)
    )
    assert "PRIVATE_MODEL_REASON" not in str(service.owner_review(OTHER, scene, saved["id"]))
    with pytest.raises(WorkflowError, match="REACTION_NOT_OWNED"):
        service.review(PLAYER, "wrong-owner", scene, saved["id"], "approve", "Looks fine.")
    accepted = service.review(OTHER, "review", scene, saved["id"], "approve", "Reviewed.")
    assert accepted["publication"] == "private_review_only"
    assert accepted["kind"] == "COMPROMISE" and accepted["text"]
    assert service.pending(OTHER, scene) == []
    assert service.review(OTHER, "review", scene, saved["id"], "approve", "Reviewed.") == accepted
    reopened = DirectorSessionService(context)
    assert reopened.reactions.private(ADMIN, scene, saved["id"])["request"] == request
    assert state(game).model_dump_json() == before and dice.calls == 0


def test_private_pilot_sighting_never_enters_handler_reaction_packet(routed):
    _, _, scene, _, _ = routed
    service, request, _ = opened(routed, private=True)
    packet = service.packet(ADMIN, scene, request)
    assert packet["role"]["question"] == "No newly heard speech."
    assert "what is in scope" not in json.dumps(packet)
    with pytest.raises(WorkflowError, match="REACTION_SCOPE"):
        draft(service, scene, request, kind="DIALOGUE")
    saved = draft(service, scene, request, kind="WAIT")
    result = service.review(ADMIN, "silent", scene, saved["id"], "approve", "No known need.")
    assert result["text"] == "" and result["next_step"] == "silent"


def test_player_speech_unknown_sources_and_arbitrary_effects_are_rejected(routed):
    observer, _, scene, game, dice = routed
    _, pilot = roles(observer, scene)
    service, request, _ = opened(routed, actor=pilot)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="REACTION_SCOPE"):
        draft(service, scene, request, kind="DIALOGUE")
    with pytest.raises(WorkflowError, match="REACTION_SCOPE"):
        service.propose(
            ADMIN,
            "unknown",
            scene,
            request,
            ReactionProposal(
                request_id=request, kind="WAIT", cited_references=("secret-id",), rationale="Wait."
            ),
        )
    with pytest.raises(ValidationError):
        ReactionProposal(request_id=request, kind="WAIT", rationale="Wait.", effects=({"heat": 9},))
    with pytest.raises(WorkflowError, match="NATIVE_ROUTE_UNAVAILABLE"):
        service.propose(
            ADMIN,
            "fake-route",
            scene,
            request,
            ReactionProposal(
                request_id=request,
                kind="REQUEST_ACTION",
                text="Review a choice.",
                rationale="Ask the actual owner.",
                route="native_choice",
                source_work_id="invented",
            ),
        )
    assert state(game).model_dump_json() == before and dice.calls == 0


def test_existing_quiet_batch_can_finish_with_wait_and_cannot_be_replayed(routed):
    observer, context, scene, game, dice = routed
    handler, _ = roles(observer, scene)
    _, source = send(observer, scene, "last", text="We sit quietly.", fictional_channel="comms")
    assert observer.claim_review(scene) is None
    observer.store.clock.now += 120
    batch = observer.claim_review(scene)
    assert batch is not None and batch.reason == "quiet"
    service = DirectorReactionService(context)
    request = service.open(
        ADMIN, "batch-open", scene, handler, source.source_id, run_id=batch.run_id
    )
    saved = draft(service, scene, request["id"], kind="WAIT")
    before = state(game).model_dump_json()
    result = service.review(ADMIN, "wait", scene, saved["id"], "approve", "Allow a quiet interval.")
    assert result["next_step"] == "silent"
    assert observer.status(PLAYER, scene).pending_messages == 0
    assert observer.claim_review(scene) is None
    assert (
        service.review(ADMIN, "wait", scene, saved["id"], "approve", "Allow a quiet interval.")
        == result
    )
    assert state(game).model_dump_json() == before and dice.calls == 0


def test_source_edits_and_withdrawn_consent_prevent_acceptance_but_allow_rejection(routed):
    observer, _, scene, game, _ = routed
    service, request, source = opened(routed)
    saved = draft(service, scene, request)
    send(
        observer,
        scene,
        "edit",
        text="I changed my question.",
        source_id=source.source_id,
        expected_source_revision=source.source_revision,
        fictional_channel="comms",
    )
    with pytest.raises(WorkflowError, match="STALE_REACTION"):
        service.review(ADMIN, "stale", scene, saved["id"], "approve", "Old question.")
    service.review(ADMIN, "reject-stale", scene, saved["id"], "reject", "Source changed.")
    service, request, _ = opened(routed, "fresh")
    saved = draft(service, scene, request, key="new-proposal")
    observer.set_consent(OTHER, "withdraw", scene, 1, consent=False)
    with pytest.raises(WorkflowError, match="OBSERVATION_DISABLED"):
        service.review(ADMIN, "no-consent", scene, saved["id"], "approve", "Cannot proceed.")
    assert not service.review(ADMIN, "reject", scene, saved["id"], "reject", "Consent withdrawn.")[
        "text"
    ]


def test_scene_offers_preserve_player_decisions_and_episode_suppression(routed):
    observer, _, scene, game, _ = routed
    _, pilot = roles(observer, scene)
    service, request, _ = opened(routed, actor=pilot)
    first = draft(service, scene, request, kind="SCENE_OFFER")
    second = draft(service, scene, request, key="second", kind="SCENE_OFFER")
    before = state(game).model_dump_json()
    result = service.review(PLAYER, "offer", scene, first["id"], "approve", "Keep as invitation.")
    assert result["next_step"] == "native_service_or_scene_invitation"
    with pytest.raises(WorkflowError, match="REACTION_ADDRESSED"):
        service.review(PLAYER, "repeat", scene, second["id"], "approve", "Duplicate.")
    assert state(game).model_dump_json() == before


def test_native_handoffs_remain_pending_and_recheck_shadow_review_status(routed):
    from test_director_worldbuilding import detail, propose, ready

    world = ready(routed)
    observer, _, scene, game, _ = routed
    handler, _ = roles(observer, scene)
    world_request, world_proposal, _ = propose(world, scene, detail())
    source = world.packet(ADMIN, scene, world_request["id"]).source.id
    service = DirectorReactionService(routed[1])
    request = service.open(ADMIN, "native-open", scene, handler, source)
    proposal = ReactionProposal(
        request_id=request["id"],
        kind="REQUEST_ACTION",
        text="Review the proposed setting detail.",
        rationale="Actual world-owner work remains separate.",
        route="worldbuilding",
        source_work_id=world_proposal["id"],
    )
    first = service.propose(ADMIN, "native-first", scene, request["id"], proposal)
    second = service.propose(ADMIN, "native-second", scene, request["id"], proposal)
    before = state(game).model_dump_json()
    accepted = service.review(ADMIN, "native-review", scene, first["id"], "approve", "Review only.")
    assert accepted["source_work_id"] == world_proposal["id"]
    assert not accepted["effects_applied"] and state(game).model_dump_json() == before
    world.review(ADMIN, "world-reject", scene, world_proposal["id"], "reject", "Wrong tone.")
    with pytest.raises(WorkflowError, match="NATIVE_ROUTE_UNAVAILABLE"):
        service.review(
            ADMIN, "closed-native-review", scene, second["id"], "approve", "Already rejected."
        )
    assert state(game).model_dump_json() == before
