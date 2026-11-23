"""Verified events can feed private planning and existing owned dialogue routes."""

import json

import pytest
from test_activity_shadow_readiness import consent, publish_opening, review, submission
from test_director_activity_scene import P2Scene
from test_director_continuity import carry
from test_ledger import ADMIN, OTHER, PLAYER
from test_m2_game import answer, pass_tags, start, state, tick
from test_m5_activity_pilots import NPC, PLOVER, attach, pilot_review
from test_m5_activity_pilots import fixture as fixture
from test_m5_activity_pilots import ledger as ledger
from test_m5_activity_pilots import rehearsal as rehearsal

from girlframe.ai.director_fronts import FrontDraft, FrontEvidence, FrontParticipant
from girlframe.ai.director_planning import DirectorPlanningDecision
from girlframe.ai.gm_outcomes import OutcomeNarration, OutcomeProposal
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_development import Subject
from girlframe.services.director_fronts import DirectorFrontService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError

GM_REASON = "PRIVATE_PLANNING_REASON: Someone wants the two crews to compete."
REPORT = "The only dry bench is occupied by the radio. The case must stay dry."
CUES = {
    NPC: "Offer to ask whether the radio can be moved safely.",
    PLOVER: "Offer to check a dry staging spot while the radio operator answers.",
}
DIALOGUE = {
    NPC: "Who has the radio lead? I can ask if we're clear to move it.",
    PLOVER: "I can look for a spare dry surface while we wait. Want me to check?",
}


class PlanningProbe:
    def __init__(self, fronts, evidence):
        self.fronts, self.evidence = fronts, evidence
        self.calls = []

    def propose(self, packet):
        self.calls.append(packet)
        assert self.evidence in packet.trigger_refs
        assert set(self.fronts.values()) <= {entry.front.id for entry in packet.fronts}
        assert set(self.fronts) <= {entry.actor for entry in packet.actors}
        return DirectorPlanningDecision.model_validate_json(
            json.dumps(
                {
                    "reasoning": GM_REASON,
                    "moves": [
                        {
                            "front": identity,
                            "actor": actor.model_dump(mode="json"),
                            "evidence": [self.evidence],
                            "text": CUES[actor],
                            "why": f"{GM_REASON} Keep {actor.entity}'s choice conditional.",
                        }
                        for actor, identity in self.fronts.items()
                    ],
                }
            )
        )


@pytest.fixture
def planning_scene(rehearsal):
    app, origin, game, clock, handler, pilot = rehearsal
    attach(app, origin)
    attach(app, origin, PLOVER, "Plover")
    context = app.session.context
    observer = app.session.observer
    with game.store.engine.connect() as c:
        lark = observer._authorize_input(c, PLAYER, origin, "pilot")[2]
    _, report = submission(app, origin, PLAYER, "shared-bench", REPORT)
    reference = context.record(
        ADMIN, "record-bench", origin, report["source_id"], 0, known_by=(lark, NPC, PLOVER)
    )["id"]
    fronts = DirectorFrontService(context)
    evidence = FrontEvidence(kind="reference", id=reference)
    topics = {NPC: "Radio and power", PLOVER: "Dry case staging"}
    identities = {
        actor: fronts.save(
            ADMIN,
            f"front:{actor.entity}",
            origin,
            state(game).revision,
            FrontDraft(
                key=f"plan-{actor.entity}",
                title=title,
                situation="The crews need the same dry bench.",
                participants=(
                    FrontParticipant(subject=Subject(kind="npc", id=actor.entity)),
                    FrontParticipant(subject=Subject(kind="location", id="base0")),
                ),
                fact_refs=(evidence,),
            ),
        )["id"]
        for actor, title in topics.items()
    }
    revision = observer.status(ADMIN, origin).scene_revision
    assert (
        app.close(ADMIN, "close-bench", origin, 900, revision, (reference,))["handler_report_count"]
        == 1
    )

    channel = 902
    scene = game.bind_scene(ADMIN, "open-follow-up", channel)["scene"]
    for viewer in (ADMIN, PLAYER, OTHER):
        game.join_scene(viewer, f"join-follow-up:{viewer.user_id}", channel)
    cast = CastService(ActorService(MissionService(game.store)))
    for owner, role in (
        (OTHER, NPC),
        (OTHER, PLOVER),
        (ADMIN, ActorRef(kind="handler", entity=str(ADMIN.user_id))),
    ):
        view = cast.view(owner, channel)
        cast.change(
            owner,
            f"cast-follow-up:{role.entity}",
            channel,
            view["game_revision"],
            view["cast_revision"],
            "join",
            role,
        )
    app.write(ADMIN, "configure-follow-up", scene, "configure", {"revision": 0})
    for viewer in (ADMIN, PLAYER, OTHER):
        consent(app, scene, viewer)
    publish_opening(app, scene, ADMIN)
    carry(context, origin, scene, (reference,), "carry-shared-bench")
    copied = next(
        ref.id
        for ref in context.build(ADMIN, scene).references
        if ref.origin_reference == reference
    )
    provider = PlanningProbe(identities, copied)
    app = P2Scene.model_fixture(
        context,
        handler.client,
        batch=handler.client,
        pilot_batch=pilot.client,
        planning_provider=provider,
    )
    return app, origin, scene, game, clock, pilot, provider, lark


def planning_source(app, origin, scene):
    entry = next(
        source
        for source in app.read(ADMIN, scene, "gm-work")["planning"]["sources"]
        if source["kind"] == "closeout" and source["scene"] == origin
    )
    return {"kind": "closeout", "source_scene": origin, "source": entry["source"]}


def draft_linked_reaction(app, scene, clock, pilot, key):
    def choose(packet):
        actor = ActorRef.model_validate(packet["dossier"]["actor"])
        assert packet["opportunity"]["text"] == CUES[actor]
        assert packet["opportunity"]["tracked"]
        assert GM_REASON not in json.dumps(packet)
        assert all(text not in json.dumps(packet) for who, text in CUES.items() if who != actor)
        return {
            "kind": "ADDRESS",
            "recipients": [packet["report"]["speaker"]],
            "intent": {
                "tactic": "offer",
                "if_refused": "try_elsewhere",
                "move_id": packet["opportunity"]["id"],
            },
        }

    def respond(packet):
        actor = ActorRef.model_validate(packet["dossier"]["actor"])
        assert packet["opportunity"]["text"] == CUES[actor]
        assert GM_REASON not in json.dumps(packet)
        assert all(text not in json.dumps(packet) for who, text in CUES.items() if who != actor)
        return {
            "kind": "DIALOGUE",
            "text": DIALOGUE[actor],
            "source_refs": packet["opportunity"]["source_refs"],
        }

    pilot.audience_answer, pilot.answer = choose, respond
    submission(app, scene, PLAYER, key, "What can we do while the case waits?")
    clock.now += 120
    outcome = review(app, scene)["model_outcome"]
    assert outcome["status"] == "pilot_review", outcome
    return outcome["proposal_id"], ActorRef.model_validate(pilot.calls[-1]["dossier"]["actor"])


def test_reviewed_closeout_routes_one_linked_plan_to_two_owned_pilot_responses(planning_scene):
    app, origin, scene, game, clock, pilot, provider, lark = planning_scene
    source = planning_source(app, origin, scene)
    fronts = DirectorFrontService(app.session.context)
    frozen = state(game)
    with pytest.raises(WorkflowError):
        app.write(PLAYER, "untrusted-planner", scene, "plan-generate", source)
    with pytest.raises(WorkflowError):
        app.write(ADMIN, "unproved-planning", scene, "plan-generate", source | {"source": origin})
    assert not provider.calls

    proposed = app.write(ADMIN, "plan-shared-bench", scene, "plan-generate", source)
    assert app.write(ADMIN, "plan-shared-bench", scene, "plan-generate", source) == proposed
    assert proposed["effects_applied"] is False and len(provider.calls) == 1
    with pytest.raises(WorkflowError):
        app.read(OTHER, scene, "plan-review", proposed["id"])
    private = app.read(ADMIN, scene, "plan-review", proposed["id"])
    assert private["status"] == "pending"
    assert private["decision"]["reasoning"] == GM_REASON
    assert len(private["decision"]["moves"]) == 2
    assert REPORT in private["evidence"][provider.evidence]
    assert set(private["fronts"].values()) == {"Radio and power", "Dry case staging"}
    with game.store.engine.connect() as c:
        assert all(fronts.portrayal_move(c, scene, actor) is None for actor in CUES)

    approval = {"proposal": proposed["id"], "decision": "approve"}
    with pytest.raises(WorkflowError):
        app.write(OTHER, "untrusted-review", scene, "plan-review", approval)
    approved = app.write(ADMIN, "approve-shared-bench", scene, "plan-review", approval)
    assert app.write(ADMIN, "approve-shared-bench", scene, "plan-review", approval) == approved
    assert approved["status"] == "approved" and approved["effects_applied"] is False
    assert state(game) == frozen

    actors = set()
    for number in range(2):
        reaction, actor = draft_linked_reaction(app, scene, clock, pilot, f"bench-turn:{number}")
        actors.add(actor)
        pilot_review(app, scene, reaction, lark.model_dump(mode="json"))
        payload = {"proposal": reaction}
        delivered = app.write(OTHER, f"deliver-bench:{number}", scene, "npc-deliver", payload)
        assert app.write(OTHER, f"retry-bench:{number}", scene, "npc-deliver", payload) == delivered
        heard = app.npc_delivery.hearing(ADMIN, scene, delivered["id"])
        assert heard["recipients"] == [lark.model_dump(mode="json")]
        assert heard["text"] == DIALOGUE[actor]
        assert delivered["effects_applied"] is False
    assert actors == set(CUES)
    with game.store.engine.connect() as c:
        assert all(fronts.portrayal_move(c, scene, actor) is None for actor in CUES)
    assert state(game) == frozen


def test_origin_consent_withdrawal_hides_the_plan_and_blocks_drafted_delivery(planning_scene):
    app, origin, scene, game, clock, pilot, _, lark = planning_scene
    source = planning_source(app, origin, scene)
    proposed = app.write(ADMIN, "draft-before-consent-change", scene, "plan-generate", source)
    app.write(
        ADMIN,
        "approve-before-consent-change",
        scene,
        "plan-review",
        {"proposal": proposed["id"], "decision": "approve"},
    )
    reaction, _ = draft_linked_reaction(app, scene, clock, pilot, "draft-to-stale")
    pilot_review(app, scene, reaction, lark.model_dump(mode="json"))
    frozen = state(game)
    consent(app, origin, PLAYER, value=False)
    with pytest.raises(WorkflowError):
        app.write(OTHER, "deliver-stale-plan", scene, "npc-deliver", {"proposal": reaction})
    private = app.read(ADMIN, scene, "plan-review", proposed["id"])
    assert private["status"] == "stale"
    assert GM_REASON not in json.dumps(private)
    assert "evidence" not in private and "fronts" not in private
    assert not [entry for entry in app.timeline(PLAYER, scene)["entries"] if entry["kind"] == "npc"]
    assert state(game) == frozen


def test_confirmed_native_outcome_can_be_reviewed_without_forcing_a_cue(fixture, request):
    _, _, game, _, worker, gateway, _ = fixture
    # Keep Your Head uses pilot-only controls. Add the response cast after it completes.
    native = start(game, context="Hold the calibration needle steady.")
    tick(worker, gateway)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The needle is holding steady.")
    tick(worker, gateway, 5)
    app, scene, game, _, handler, pilot = request.getfixturevalue("rehearsal")
    attach(app, scene)
    context = app.session.context
    fronts = DirectorFrontService(context)
    outcomes = app.session.outcomes
    opened = outcomes.open(ADMIN, "open-stable-needle", scene, "completed", native)
    proposal = outcomes.propose(
        ADMIN,
        "narrate-stable-needle",
        scene,
        opened["id"],
        OutcomeProposal(
            request_id=opened["request_id"],
            decision=OutcomeNarration(
                text="The needle is holding steady.", effect_refs=("enough",)
            ),
            cited_evidence=("source", "native"),
            private_reasoning="Confirmed native outcome.",
        ),
    )
    narration = outcomes.confirm(ADMIN, "confirm-stable-needle", scene, proposal["id"])["id"]
    reference = context.record(ADMIN, "record-stable-needle", scene, narration, 0, known_by=(NPC,))[
        "id"
    ]
    fronts.save(
        ADMIN,
        "front-stable-needle",
        scene,
        state(game).revision,
        FrontDraft(
            key="steady-calibration",
            title="Calibration",
            situation="The timing of the next check depends on the needle.",
            participants=(FrontParticipant(subject=Subject(kind="npc", id=NPC.entity)),),
            fact_refs=(FrontEvidence(kind="reference", id=reference),),
        ),
    )

    class QuietPlanner:
        def propose(self, packet):
            assert packet.source.kind == "outcome" and packet.source.source == narration
            assert reference in packet.trigger_refs
            assert next(ref for ref in packet.references if ref.id == reference).classification == (
                "approved_outcome"
            )
            return DirectorPlanningDecision(reasoning="Leave the crew to their next check.")

    app = P2Scene.model_fixture(
        context,
        handler.client,
        batch=handler.client,
        pilot_batch=pilot.client,
        planning_provider=QuietPlanner(),
    )
    choices = app.read(ADMIN, scene, "gm-work")["planning"]["sources"]
    assert [(choice["kind"], choice["scene"], choice["source"]) for choice in choices] == [
        ("outcome", scene, narration)
    ]
    frozen = state(game)
    plan = app.write(
        ADMIN,
        "plan-stable-needle",
        scene,
        "plan-generate",
        {"kind": "outcome", "source_scene": scene, "source": narration},
    )
    assert app.read(ADMIN, scene, "plan-review", plan["id"])["decision"]["moves"] == []
    result = app.write(
        ADMIN,
        "approve-stable-needle",
        scene,
        "plan-review",
        {"proposal": plan["id"], "decision": "approve"},
    )
    assert result["status"] == "approved" and result["effects_applied"] is False
    with game.store.engine.connect() as c:
        assert fronts.portrayal_move(c, scene, NPC) is None
    assert state(game) == frozen
