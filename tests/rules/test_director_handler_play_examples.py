"""One reviewed offer and real effect per native Handler Play in the synthetic audit."""

import json
from uuid import uuid4

import pytest
from test_gm_outcome_consumers import attach, consume
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.ai.conversation import ConversationReply
from girlframe.ai.gm_outcomes import HandlerOutcome
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_play_state import BASIC, EXTRA, Effect
from girlframe.engine.m3_world_state import Npc
from girlframe.services.director_conversation import DirectorConversationService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.onboarding import WorkflowError


class Offer:
    def __init__(self, play, account):
        self.play, self.account = play, account

    def respond(self, request):
        return ConversationReply(
            route="handler",
            provider="reviewed-handler-v1",
            disposition="answer",
            text=self.account,
            source_refs=request.response_need.source_refs,
            handler_play_offer=self.play,
        )


def open_offer(service, scene, game, play, account, native_grant=None):
    from test_director_observation import send

    context = service.context
    observer = context.observations
    conversation = DirectorConversationService(
        context, handler=Offer(play, account), handler_mode="reviewed"
    )
    key = str(uuid4())
    handler, pilot = [current_ref(state(game), x) for x in (1, 2)]
    _, briefing = send(
        observer,
        scene,
        key + ":notice",
        viewer=ADMIN,
        fictional_channel="comms",
        text="The relay team has requested a decision before changing the plan.",
    )
    with game.store.engine.connect() as c:
        order = len(context._references(c, scene))
    context.record(
        ADMIN,
        key + ":briefing",
        scene,
        briefing.source_id,
        order,
        known_by=(handler, pilot),
        topic="briefing",
    )
    _, source = send(
        observer,
        scene,
        key + ":pilot",
        viewer=PLAYER,
        fictional_channel="comms",
        text="I spread the relay map and compare the routes.",
    )
    routed = conversation.process_message(PLAYER, key + ":route", scene, source.source_id, 1)
    assert routed["handler_decision"]["decision"]["reason"] == "known_update"
    draft = routed["handler"]["id"]
    review = conversation.review_handler(
        ADMIN,
        key + ":review",
        scene,
        draft,
        "approve",
        "The Handler has the actual mission context.",
    )
    assert review["handler_play_offer"] == play
    assert "handler_play_offer" not in conversation.get(PLAYER, scene, draft)["reply"]
    revision = state(game).revision
    assert conversation.handler_play_offers(ADMIN, scene)[0]["play"] == play
    if play in dict(EXTRA):
        with pytest.raises(WorkflowError, match="specialist grant"):
            conversation.start_handler_play(ADMIN, scene, draft, revision)
    result = conversation.start_handler_play(
        ADMIN, scene, draft, revision, native_grant=native_grant
    )
    assert (
        conversation.start_handler_play(ADMIN, scene, draft, revision, native_grant=native_grant)
        == result
    )
    return result["id"]


def record_example(game, identity):
    grant = next(g for g in state(game).handler_plays if g.id == identity)
    assert grant.state == "complete" and grant.effect is not None and grant.completed_event
    print(
        "HANDLER_EXAMPLE "
        + json.dumps(
            dict(
                play=grant.selected,
                effect=grant.effect.kind,
                account=grant.effect.account,
                detail=grant.effect.detail
                if grant.selected != "tracker_voyeur"
                else "Private native moment",
                state=grant.state,
                grant=grant.id,
            )
        )
    )


@pytest.mark.parametrize("play", [play for play, _ in BASIC])
def test_every_basic_handler_play_runs_through_review_to_native_completion(ledger, play):
    from test_handler_plays import ready
    from test_off_duty_cycle import activate, call, finish_routine, movement, prepared, recover_both
    from test_role_punishments import change

    from girlframe.engine.m3_punishments import Details
    from girlframe.engine.m3_role_punishment_state import Instruction
    from girlframe.services.m3_role_punishments import RolePunishmentService

    if play == "off_duty":
        cycle, game, period = prepared(ledger)
    else:
        _, game = ready(ledger)
        period = None
    service, scene = attach(game)
    before = state(game)
    pilot, handler = (current_ref(before, n) for n in (2, 1))
    examples = {
        "brief": Effect(kind="brief", account="The relay team will use the checked public route."),
        "punish": Effect(
            kind="punish",
            target=pilot,
            executor=handler,
            account="The Handler opens formal review of the missed check-in.",
        ),
        "escalate": Effect(
            kind="escalate",
            account="The warning bell is accelerating.",
            detail="The relay warning changes to the short interval.",
            stakes="Continuing would cost the remaining inspection window.",
        ),
        "support": Effect(
            kind="support",
            account="I call in a mechanic who can check the panel.",
            npc=Npc(
                id="relay-mechanic",
                name="Venn",
                jobs=("mechanic",),
                detail="Public relay technician",
                controller=1,
                cell=before.world.locations[0].cell,
                revealed=True,
                employment="foundation",
            ),
        ),
        "mess": Effect(
            kind="tag",
            target=pilot,
            tag="Held the relay under pressure",
            account="I record the pilot's composure during the relay handoff.",
        ),
        "expectation": Effect(
            kind="expectation",
            detail="Report before leaving the checked route.",
            stakes="An unreported departure goes to Handler review.",
            account="The next check-in now has a stated expectation.",
        ),
    }
    effect = (
        Effect(kind="off_duty", account="I join the Cadre's return to base.", off_duty=period)
        if play == "off_duty"
        else examples[play]
    )
    grant = open_offer(service, scene, game, play, effect.account)
    native = HandlerPlayService(game.store)
    assert tuple(x[0] for x in native.get(ADMIN, grant)["plays"]) == (play,)
    assert state(game).handler_plays[-1].state == "pending"
    resolution = consume(
        service, scene, "handler_grant", grant, HandlerOutcome(play=play, effect=effect)
    )
    if play == "punish":
        assert resolution["state"] == "awaiting_effect"
        case = state(game).handler_plays[-1].followups[0]
        punishments = RolePunishmentService(game)
        details = Details(kind="stimulant_injection")
        change(
            punishments,
            ADMIN,
            case,
            instruction=Instruction(kind=details.kind, details_json=details.model_dump_json()),
        )
        change(punishments, ADMIN, case, scene="The Handler explains the recorded discipline.")
        with pytest.raises(WorkflowError):
            change(punishments, ADMIN, case, execute=True, account="No assumed attendance")
        change(punishments, PLAYER, case, attest=True)
        change(punishments, ADMIN, case, execute=True, account="Actual owned scene consequence.")
    if play == "off_duty":
        assert resolution["state"] == "awaiting_effect"
        activate(cycle, game, period)
        recover_both(cycle, game, period)
        finish_routine(cycle, game, period)
        call(cycle, game, ADMIN, period, "finish", movement(game))
    if play == "support":
        assert any(n.id == "relay-mechanic" and n.controller == 1 for n in state(game).world.npcs)
    if play == "mess":
        assert any(t.label == effect.tag for t in state(game).sheets["2"].tags)
    assert native.notice(PLAYER, grant)["account"] == effect.account
    with pytest.raises(WorkflowError):
        native.notice(OTHER, grant)
    record_example(game, grant)


def test_mess_routes_status_and_real_asset_effects(ledger):
    from test_handler_plays import ready
    from test_physical_service import decide, propose

    from girlframe.services.m3_physical import PhysicalService

    _, game = ready(ledger)
    physical = PhysicalService(ledger)
    decide(physical, propose(physical)["id"])
    service, scene = attach(game)
    before = state(game)
    pilot = current_ref(before, 2)
    asset = next(a for a in before.sheets["2"].assets if a.family == "frame" and not a.damaged)
    effects = (
        Effect(
            kind="status",
            target=pilot,
            status=-1,
            account="The Handler records a drop in standing after the relay review.",
        ),
        Effect(
            kind="damage",
            target=pilot,
            asset=asset.id,
            account="The Handler records damage to the pilot's actual Frame Asset.",
        ),
    )
    for effect in effects:
        grant = open_offer(service, scene, game, "mess", effect.account)
        consumed = consume(
            service, scene, "handler_grant", grant, HandlerOutcome(play="mess", effect=effect)
        )
        assert consumed["state"] == "complete"
        record_example(game, grant)
    after = state(game)
    assert after.order == tuple(reversed(before.order))
    assert next(a for a in after.sheets["2"].assets if a.id == asset.id).damaged
