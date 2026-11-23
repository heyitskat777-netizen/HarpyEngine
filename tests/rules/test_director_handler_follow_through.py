"""The same open concern branches on a Pilot's actual delivered response."""

import pytest
from test_director_continuity import carry, new_scene, roles
from test_director_conversation import routed as routed
from test_director_observation import observed as observed
from test_director_observation import send
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.ai.conversation import ConversationReply, HandlerNeedProposal
from girlframe.ai.gm_outcomes import HandlerOutcome
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.engine.m3_world_state import Npc
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.director_session import DirectorSessionService
from girlframe.services.onboarding import WorkflowError


class FollowThrough:
    def respond(self, request):
        decision = request.response_need
        common = dict(
            route="handler",
            disposition="answer",
            provider="reviewed-handler-v1",
            source_refs=decision.source_refs,
        )
        if decision.reason == "known_update":
            return ConversationReply(
                **common,
                text="Could you verify the reflection from the public platform?",
                handler_action="I pencil a question mark next to the reflection.",
                handler_concern="Determine what the reflection represents.",
            )
        assert decision.reason == "reviewed_follow_up" and request.open_concerns
        if "decline" in request.question:
            return ConversationReply(
                **common,
                text="Understood. I can call Venn if you want another option.",
                handler_play_offer="support",
            )
        return ConversationReply(
            **common,
            text="Copy your identification. I mark the reflection as reported.",
            handler_action="I write the pilot's identification next to the earlier report.",
        )


def learn(context, scene, source, known_by, topic="general"):
    with context.store.engine.connect() as c:
        order = len(context._references(c, scene))
    return context.record(
        ADMIN, "ref:" + source, scene, source, order, known_by=known_by, topic=topic
    )["id"]


@pytest.mark.parametrize("accept", [True, False], ids=["confirms-contact", "declines-check"])
def test_handler_follows_actual_choice_and_preserves_recipient_memory(routed, accept):
    from rules.m3_policy_scenario import configure_m3_fixture
    from rules.test_world import initial

    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_world import WorldService

    observer, context, scene, game, _ = routed
    configure_m3_fixture(observer.store)
    policy = observer.store.policy
    observer.store.policy = policy.model_copy(
        update={
            "m3_approval": policy.m3_approval.model_copy(
                update={"subsystems": policy.m3_approval.subsystems | {"plays", "world"}}
            )
        }
    )
    world = WorldService(MissionService(observer.store))
    base = initial()
    world.initialize(
        ADMIN, "world", state(game).revision, base.board, base.locations, base.gorgons[0]
    )
    handler, pilot = roles(observer, scene)
    service = DirectorConversationService(context, handler=FollowThrough(), handler_mode="reviewed")
    session = DirectorSessionService(context, conversation=service)

    def turn(key, text):
        _, source = send(observer, scene, key, text=text, fictional_channel="comms")
        return source

    origin = turn("reflection", "An amber reflection is visible from the public platform.")
    learn(context, scene, origin.source_id, (pilot, handler), "tactical")
    before = state(game).revision
    first = service.process_message(PLAYER, "first", scene, origin.source_id, 1)["handler"]["id"]
    with pytest.raises(WorkflowError, match="HANDLER_CONCERN_DELIVERY"):
        service.review_handler(ADMIN, "no-audience", scene, first, "approve", "Review")
    service.review_handler(
        ADMIN,
        "first-review",
        scene,
        first,
        "approve",
        "Verified audience",
        delivery_recipients=(pilot,),
    )
    assert service.get(PLAYER, scene, first)["reply"] is None
    assert not session.contributions(PLAYER, scene)
    assert session.work(ADMIN, scene)["handler_deliveries"][0]["id"] == first
    assert not session.work(PLAYER, scene)["handler_deliveries"]
    assert service.delivery.preview(ADMIN, scene, first)["action"].startswith("I pencil")
    with pytest.raises(WorkflowError, match="HANDLER_DELIVERY_OWNER"):
        service.delivery.preview(PLAYER, scene, first)
    with pytest.raises(WorkflowError, match="HANDLER_DELIVERY_OWNER"):
        service.delivery.deliver(PLAYER, "wrong-controller", scene, first)
    delivered = service.delivery.deliver(ADMIN, "first-delivery", scene, first)
    assert service.delivery.deliver(ADMIN, "first-delivery", scene, first) == delivered
    assert service.delivery.deliver(ADMIN, "retry-another-key", scene, first) == delivered
    assert len(session.contributions(PLAYER, scene)) == 1
    assert session.contributions(PLAYER, scene)[0]["action"].startswith("I pencil")
    assert not session.contributions(OTHER, scene)
    assert state(game).revision == before
    assert any(
        r.reported_by == handler and "pencil" in r.text
        for r in context.build(PLAYER, scene, actor=pilot).references
    )
    quiet = turn("quiet", "I finish folding my spare gloves.")
    assert (
        service.process_message(PLAYER, "quiet-route", scene, quiet.source_id, 1)["handler"] is None
    )

    answer = (
        "I confirm the reflection is from a service mirror."
        if accept
        else "I decline to leave my current position to check it."
    )
    update = turn("answer", answer)
    ref = learn(
        context, scene, update.source_id, (pilot, handler), "tactical" if accept else "general"
    )
    opened = service.open_handler_need(ADMIN, "follow-needed", scene, update.source_id)
    packet = service.handler_need_packet(ADMIN, scene, opened["id"])
    assert [x.id for x in packet.request.open_concerns] == [delivered["id"]]
    need = HandlerNeedProposal(
        request_id=packet.request_id,
        action="RESPOND",
        kind="follow_up",
        concern_id=delivered["id"],
        speech_quote=answer,
        source_refs=(ref,),
        reason="The Pilot has answered the actual open concern.",
    )
    saved = service.propose_handler_need(ADMIN, "follow-propose", scene, opened["id"], need)
    service.review_handler_need(
        ADMIN, "follow-approve", scene, saved["id"], "approve", "Heard answer"
    )
    routed = service.process_message(PLAYER, "second", scene, update.source_id, 1)
    assert routed["handler_decision"]["decision"]["reason"] == "reviewed_follow_up"
    draft = routed["handler"]["id"]
    service.review_handler(
        ADMIN,
        "second-review",
        scene,
        draft,
        "approve",
        "Grounded follow-through",
        delivery_recipients=(pilot,),
    )
    repeated = service.process_message(PLAYER, "repeat-second", scene, update.source_id, 1)
    assert repeated["handler"] is None
    receipt = service.delivery.deliver(ADMIN, "second-delivery", scene, draft)
    lines = session.contributions(PLAYER, scene)
    assert len(lines) == 2 and not session.contributions(OTHER, scene)
    if accept:
        assert "identification" in lines[-1]["text"]
    else:
        assert "call Venn" in lines[-1]["text"]
        # The reviewed offer still resolves after its own contribution enters scene memory.
        from test_gm_outcome_consumers import consume

        grant = service.start_handler_play(ADMIN, scene, draft, state(game).revision)
        result = consume(
            session.outcomes,
            scene,
            "handler_grant",
            grant["id"],
            HandlerOutcome(
                play="support",
                effect=Effect(
                    kind="support",
                    account="Venn is available at the public platform.",
                    npc=Npc(
                        id="venn",
                        name="Venn",
                        jobs=("mechanic",),
                        detail="Relay technician",
                        controller=1,
                        cell=base.locations[0].cell,
                        revealed=True,
                        employment="foundation",
                    ),
                ),
            ),
        )
        assert result["state"] == "complete"
        assert any(n.id == "venn" for n in state(game).world.npcs)
    final = turn("done", "I finish my notes.")
    assert (
        service.process_message(PLAYER, "done-route", scene, final.source_id, 1)["handler"] is None
    )
    final_need = service.open_handler_need(ADMIN, "after", scene, final.source_id)
    assert not service.handler_need_packet(ADMIN, scene, final_need["id"]).request.open_concerns
    next_scene = new_scene(observer)
    carry(context, scene, next_scene, (receipt["reference"],), "actual-memory")
    assert any(
        r.reported_by == handler and r.origin_reference == receipt["reference"]
        for r in context.build(PLAYER, next_scene, actor=pilot).references
    )
    _, other = roles(observer, next_scene)
    assert other == pilot
    print(f"HANDLER_FOLLOW_THROUGH {('confirmed' if accept else 'declined')} {lines[-1]['text']}")
