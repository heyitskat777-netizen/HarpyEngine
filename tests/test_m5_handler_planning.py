"""A reviewed Handler plan becomes one scoped action through normal Activity delivery."""

import json

import pytest
from test_activity_shadow_readiness import consent, publish_opening
from test_director_continuity import carry
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_m5_activity_batch import WAIT, RelayRehearsal, deliver_handler, handler_batch_line
from test_m5_director_planning import planning_source
from test_p2_handler_archetype_missions import end_mission
from test_session_zero import FACILITATOR

from girlframe.ai.director_fronts import FrontDraft, FrontEvidence, FrontMove, FrontParticipant
from girlframe.ai.director_planning import DirectorPlanningDecision, PlannedMove
from girlframe.engine.m3_world_development import Subject
from girlframe.engine.m3_world_state import Faction
from girlframe.services.director_fronts import DirectorFrontService
from girlframe.services.onboarding import WorkflowError

CUE = "Put a dry pad under the borrowed thermos before the table is cleared."
RATIONALE = "PRIVATE_TACTIC: Anwen wants the owner to see she takes care of borrowed things."
ACTION = "I slide the spare dry pad under the thermos."
SPEECH = "There. It can stay on this end while we clear the table."


class HandlerPlanner:
    def __init__(self, handler, front, evidence):
        self.handler, self.front, self.evidence = handler, front, evidence

    def propose(self, packet):
        assert self.evidence in packet.trigger_refs
        assert {item.front.id for item in packet.fronts} == {self.front}
        assert len(packet.fronts) == 1 and packet.fronts[0].actors == (self.handler,)
        return DirectorPlanningDecision(
            moves=(
                PlannedMove(
                    actor=self.handler,
                    front=self.front,
                    evidence=(self.evidence,),
                    text=CUE,
                    why="The table has space for her to care for the borrowed thermos.",
                ),
            ),
            reasoning=RATIONALE,
        )


@pytest.fixture
def handler_plan(ledger, request):
    from run_m5_model_campaign import Campaign

    relay = RelayRehearsal(ledger, "Advocate")
    relay.calls = []
    relay.output = WAIT
    zero, approved = relay.setup()
    mission = relay.dispatch(zero, approved)
    publish_opening(relay.app, relay.scene, FACILITATOR)
    assert zero.view(ADMIN)["opening"]["handler_control"] == "ai"
    approval = ledger.policy.m3_approval
    assert approval is not None
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    origin = relay.scene
    context = relay.context
    with ledger.engine.connect() as connection:
        handler = relay.observer._authorize_input(connection, ADMIN, origin, "handler")[2]
        lark = relay.observer._authorize_input(connection, PLAYER, origin, "pilot")[2]
        order = len(context._references(connection, origin))
    _, report = relay.line("thermos", PLAYER, "Your borrowed thermos has left a ring on the table.")
    known_by = (handler,) if getattr(request, "param", None) == "handler-only" else (handler, lark)
    ref = context.record(
        ADMIN, "remember-thermos", origin, report["source_id"], order, known_by=known_by
    )["id"]
    evidence = FrontEvidence(kind="reference", id=ref)
    relay.session.worldbuilding.world.faction(
        ADMIN,
        "stores-faction",
        state(relay.game).revision,
        Faction(id="stores", name="Stores", kind="political", cells=()),
    )
    subject = Subject(kind="faction", id="stores")
    fronts = DirectorFrontService(context)
    front = fronts.save(
        ADMIN,
        "thermos-front",
        origin,
        state(relay.game).revision,
        FrontDraft(
            key="borrowed-thermos",
            title="Get the thermos back in good condition",
            situation="Anwen borrowed a thermos and wants to return it in good condition.",
            participants=(FrontParticipant(subject=subject),),
            fact_refs=(evidence,),
            possible_moves=(
                FrontMove(
                    id="protect-thermos",
                    subject=subject,
                    text=CUE,
                    portrayed_by=handler,
                    evidence_refs=(evidence,),
                ),
            ),
        ),
    )["id"]
    fronts.save(
        ADMIN,
        "unassigned-front",
        origin,
        state(relay.game).revision,
        FrontDraft(
            key="unassigned-thermos",
            title="Find other table supplies",
            situation="A drawer in the table may hold spare supplies.",
            participants=(FrontParticipant(subject=subject),),
            fact_refs=(evidence,),
        ),
    )
    end_mission(relay.game, mission)
    revision = relay.observer.status(ADMIN, origin).scene_revision
    relay.app.close(ADMIN, "close-thermos", origin, relay.scene_channel, revision, (ref,))
    Campaign.bind(relay, 902, "thermos-follow-up")
    target = relay.scene
    publish_opening(relay.app, target, FACILITATOR)
    carry(context, origin, target, (ref,), "carry-thermos")
    copied = next(
        item.id for item in context.build(ADMIN, target).references if item.origin_reference == ref
    )
    relay.app.planning.provider = HandlerPlanner(handler, front, copied)
    return relay, origin, copied


@pytest.mark.parametrize("withdraw_origin", [False, True], ids=["deliver", "origin-consent"])
def test_reviewed_handler_move_waits_for_approval_and_exact_listener(handler_plan, withdraw_origin):
    relay, origin, copied = handler_plan
    source = planning_source(relay.app, origin, relay.scene)
    proposed = relay.app.write(ADMIN, "draft-thermos", relay.scene, "plan-generate", source)
    assert proposed["effects_applied"] is False
    with pytest.raises(WorkflowError):
        relay.app.read(PLAYER, relay.scene, "plan-review", proposed["id"])
    assert "handler_moves" not in relay.app.read(PLAYER, relay.scene, "work")

    def private_move(status):
        review = relay.app.read(ADMIN, relay.scene, "plan-review", proposed["id"])
        assert review["status"] == status
        [move] = review["handler_moves"].values()
        return move

    pending_move = private_move("pending")
    assert pending_move["status"] == "pending"
    [listener] = pending_move["eligible_listeners"]
    assert listener["actor"]["entity"] == str(PLAYER.user_id)
    assert listener["label"] == state(relay.game).sheets[str(PLAYER.user_id)].callsign

    def turn(key, speaker=PLAYER):
        relay.line(key, speaker, "There's a moment before cleanup.")
        return relay.run_batch()

    frozen = relay.canon_and_time()
    assert turn("pending-plan")["status"] == "wait"
    assert "opportunity" not in relay.calls[-1]
    payload = {"proposal": proposed["id"], "decision": "approve"}
    with pytest.raises(WorkflowError):
        relay.app.write(OTHER, "wrong-plan-reviewer", relay.scene, "plan-review", payload)
    approved = relay.app.write(ADMIN, "review-thermos", relay.scene, "plan-review", payload)
    assert relay.app.write(ADMIN, "review-thermos", relay.scene, "plan-review", payload) == approved
    assert approved["status"] == "approved"
    assert private_move("approved") == {"status": "waiting", "eligible_listeners": [listener]}
    assert turn("wrong-listener", OTHER)["status"] == "wait"
    assert "opportunity" not in relay.calls[-1]
    assert CUE not in json.dumps(relay.calls[-1])

    assert turn("legitimate-wait")["status"] == "wait"
    assert relay.calls[-1]["opportunity"]["text"] == CUE
    assert relay.run_batch(0) is None

    def answer(packet):
        assert RATIONALE not in json.dumps(packet)
        assert packet["opportunity"]["text"] == CUE
        assert packet["opportunity"]["tracked"]
        assert packet["response_need"]["reason"] == "planned_handler_move"
        return handler_batch_line(
            packet,
            "response_need",
            SPEECH,
            fiction={"own_action": ACTION},
            report_id=packet["response_report_id"],
        ) | {"source_refs": [copied]}

    relay.output = answer
    draft = turn("enact-plan")["draft_id"]
    relay.approve(draft, "approve-thermos")
    assert SPEECH not in json.dumps(relay.app.timeline(PLAYER, relay.scene))
    if withdraw_origin:
        consent(relay.app, origin, PLAYER, value=False)
        with pytest.raises(WorkflowError, match="STALE_HANDLER_DRAFT|HANDLER_PLAN_STALE"):
            deliver_handler(relay, draft, "block-origin-withdrawal")
        pending = relay.app.read(ADMIN, relay.scene, "plan-review", proposed["id"])
        assert pending == {"id": proposed["id"], "status": "stale"}
        assert SPEECH not in json.dumps(relay.app.timeline(PLAYER, relay.scene))
        relay.output = WAIT
        assert turn("no-withdrawn-move")["status"] == "wait"
        assert "opportunity" not in relay.calls[-1]
        assert CUE not in json.dumps(relay.calls[-1])
        assert relay.canon_and_time() == frozen
        return
    receipt = deliver_handler(relay, draft, "deliver-thermos")
    relay.store.engine.dispose()
    assert deliver_handler(relay, draft, "retry-thermos") == receipt
    delivery = [
        entry
        for entry in relay.app.timeline(PLAYER, relay.scene)["entries"]
        if entry["id"] == receipt["id"]
    ]
    assert len(delivery) == 1 and delivery[0]["text"] == SPEECH and delivery[0]["action"] == ACTION
    assert SPEECH not in json.dumps(relay.app.timeline(OTHER, relay.scene))
    assert private_move("approved") == {"status": "delivered", "eligible_listeners": []}

    relay.output = WAIT
    assert turn("no-repeated-move")["status"] == "wait"
    assert "opportunity" not in relay.calls[-1]
    assert relay.canon_and_time() == frozen


@pytest.mark.parametrize("handler_plan", ["handler-only"], indirect=True)
def test_reviewed_handler_move_waits_when_no_pilot_shares_the_evidence(handler_plan):
    relay, origin, _ = handler_plan
    source = planning_source(relay.app, origin, relay.scene)
    proposal = relay.app.write(ADMIN, "draft-private-thermos", relay.scene, "plan-generate", source)
    payload = {"proposal": proposal["id"], "decision": "approve"}
    relay.app.write(ADMIN, "review-private-thermos", relay.scene, "plan-review", payload)
    approved = relay.app.read(ADMIN, relay.scene, "plan-review", proposal["id"])
    [move] = approved["handler_moves"].values()
    assert move == {"status": "waiting", "eligible_listeners": []}

    for listener in (PLAYER, OTHER):
        relay.line(f"private-thermos:{listener.user_id}", listener, "There's room at this table.")
        assert relay.run_batch()["status"] == "wait"
        assert "opportunity" not in relay.calls[-1]
