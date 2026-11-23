"""Front attention is persistent evidence-backed review, never an automatic consequence."""

import json

import pytest
import sqlalchemy as sa
from pydantic import ValidationError
from test_director_adjudication import prepare
from test_director_continuity import roles
from test_director_conversation import routed as routed
from test_director_observation import observed as observed
from test_director_observation import send
from test_director_worldbuilding import detail, propose, ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, start, state, tick

from girlframe.ai.director_fronts import (
    FrontAdvance,
    FrontClock,
    FrontDraft,
    FrontEvidence,
    FrontHypothesis,
    FrontParticipant,
)
from girlframe.ai.gm_outcomes import OutcomeNarration, OutcomeProposal
from girlframe.database import tables as t
from girlframe.engine.m3_world_development import Subject
from girlframe.engine.m3_world_state import Npc
from girlframe.services.director_fronts import DirectorFrontService, records
from girlframe.services.gm_outcomes import GMOutcomeService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.onboarding import WorkflowError


def fixture(routed):
    world = ready(routed)
    observer, context, scene, game, _ = routed
    ref = next(
        value.id for value in context.build(ADMIN, scene).references if value.topic == "objective"
    )
    return DirectorFrontService(context), world, FrontEvidence(kind="reference", id=ref)


def draft(evidence, **changes):
    return FrontDraft(
        **(
            {
                "key": "relay-dispute",
                "title": "PRIVATE_FRONT_TITLE",
                "situation": "PRIVATE_FRONT_SITUATION: competing maintenance priorities.",
                "fact_refs": (evidence,),
                "participants": (
                    FrontParticipant(
                        subject=Subject(kind="location", id="base0"), resource_refs=(evidence,)
                    ),
                ),
                "hypotheses": (
                    FrontHypothesis(
                        id="rumour",
                        text="PRIVATE_FRONT_HYPOTHESIS: an uncertain explanation.",
                        support_refs=(evidence,),
                    ),
                ),
                "unresolved_consequences": (
                    "An unanswered maintenance dispute may need later review.",
                ),
            }
            | changes
        )
    )


def test_front_world_sources_disclose_only_known_fragments_and_preserve_retry_history(routed):
    fronts, world, _ = fixture(routed)
    observer, context, scene, game, dice = routed
    action = detail(text="A red inspection tag hangs beside the service panel.")
    _, proposed, _ = propose(world, scene, action)
    world.review(ADMIN, "review", scene, proposed["id"], "approve", "Finite setting detail only.")
    committed = world.confirm(ADMIN, "commit", scene, proposed["id"])
    evidence = FrontEvidence(kind="world_development", id=committed["native"]["id"])
    value, expected = draft(evidence, clock=FrontClock(limit=2)), state(game).revision
    saved = fronts.save(ADMIN, "front", scene, expected, value)
    assert fronts.save(ADMIN, "front", scene, expected, value) == saved
    assert len(records(state(game))) == 1
    assert "PRIVATE_FRONT_HYPOTHESIS" in json.dumps(fronts.view(ADMIN, scene))
    dormant = draft(evidence, key="paused-maintenance", status="dormant")
    fronts.save(ADMIN, "dormant", scene, state(game).revision, dormant)
    _, source = send(observer, scene, "next-world-source", text="GM, frame the next choice.")
    request = world.open(ADMIN, "front-world-context", scene, source.source_id)
    packet = world.packet(ADMIN, scene, request["id"])
    assert [front.id for front in packet.current_fronts] == [saved["id"]]
    handler, pilot = roles(observer, scene)
    assert fronts.view(ADMIN, scene, actor=handler)["fragments"] == []
    assert fronts.view(PLAYER, scene, actor=pilot)["fragments"] == []
    disclosed = world.disclose(
        ADMIN, "teach-handler", scene, committed["id"], action.development.text, (handler,)
    )
    visible = fronts.view(ADMIN, scene, actor=handler)
    assert visible["fragments"][0]["id"] == disclosed["reference_ids"][0]
    assert visible["fragments"][0]["classification"] == "established_world"
    encoded = json.dumps(visible)
    assert action.development.text in encoded and "PRIVATE_FRONT" not in encoded
    assert "clock" not in encoded and saved["id"] not in encoded
    assert fronts.view(PLAYER, scene, actor=pilot)["fragments"] == []
    with observer.store.engine.connect() as c:
        assert fronts._actor_view(c, scene, handler) == visible
        assert "PRIVATE_FRONT" not in " ".join(c.scalars(sa.select(t.events.c.payload_json)))
        assert "PRIVATE_FRONT" not in " ".join(c.scalars(sa.select(t.commands.c.outcome_json)))
    with pytest.raises(WorkflowError):
        fronts.view(PLAYER, scene)
    with pytest.raises(WorkflowError):
        fronts.view(PLAYER, scene, actor=handler)
    game.rebuild()
    assert DirectorFrontService(context).view(ADMIN, scene, actor=handler) == visible
    assert dice.calls == 0


def test_only_explicit_time_or_native_sources_advance_attention_never_consequences(routed):
    fronts, _, evidence = fixture(routed)
    observer, _, scene, game, dice = routed
    value = draft(evidence, clock=FrontClock(limit=2))
    first = fronts.save(ADMIN, "clock-front", scene, state(game).revision, value)
    deadline = draft(evidence, key="deadline-front", deadline_tick=2)
    fronts.save(ADMIN, "deadline-front", scene, state(game).revision, deadline)
    before = state(game)
    send(observer, scene, "ordinary-chat", text="We keep talking without advancing fictional time.")
    observer.store.clock.now += 50_000
    assert state(game) == before
    with pytest.raises(WorkflowError, match="FRONT_ADVANCE_REQUIRED"):
        fronts.save(
            ADMIN,
            "no-trigger",
            scene,
            before.revision,
            value.model_copy(
                update={"supersedes": first["id"], "clock": FrontClock(mark=1, limit=2)}
            ),
        )
    time_one = fronts.fictional_time(
        ADMIN, "time-one", scene, before.revision, 1, "One fictional interval passes."
    )
    assert not time_one["ready"]
    second_draft = value.model_copy(
        update={"supersedes": first["id"], "clock": FrontClock(mark=1, limit=2)}
    )
    second = fronts.save(
        ADMIN,
        "clock-one",
        scene,
        state(game).revision,
        second_draft,
        advance=FrontAdvance(kind="fictional_time", id=time_one["id"]),
    )
    assert second["status"] == "active"
    third_draft = value.model_copy(
        update={"supersedes": second["id"], "clock": FrontClock(mark=2, limit=2)}
    )
    with pytest.raises(WorkflowError, match="FRONT_ADVANCE_USED"):
        fronts.save(
            ADMIN,
            "same-trigger",
            scene,
            state(game).revision,
            third_draft,
            advance=FrontAdvance(kind="fictional_time", id=time_one["id"]),
        )
    expected = state(game).revision
    time_two = fronts.fictional_time(
        ADMIN, "time-two", scene, expected, 1, "A second fictional interval passes."
    )
    assert (
        fronts.fictional_time(
            ADMIN, "time-two", scene, expected, 1, "A second fictional interval passes."
        )
        == time_two
    )
    assert len(time_two["ready"]) == 1
    final = fronts.save(
        ADMIN,
        "clock-full",
        scene,
        state(game).revision,
        third_draft,
        advance=FrontAdvance(kind="fictional_time", id=time_two["id"]),
    )
    assert final["status"] == "ready" and all(
        record.status == "ready" for record in records(state(game))
    )
    after = state(game)
    assert after.model_dump(exclude={"facts", "revision"}) == before.model_dump(
        exclude={"facts", "revision"}
    )
    assert dice.calls == 0
    assert len(records(after, current=False)) == 5
    assert records(after, current=False)[0].clock.mark == 0
    time_three = fronts.fictional_time(
        ADMIN, "time-three", scene, after.revision, 1, "An explicit review interval passes."
    )
    with pytest.raises(WorkflowError, match="FRONT_RESOLUTION_REQUIRED"):
        fronts.save(
            ADMIN,
            "time-is-not-resolution",
            scene,
            state(game).revision,
            third_draft.model_copy(update={"supersedes": final["id"], "status": "resolved"}),
            advance=FrontAdvance(kind="fictional_time", id=time_three["id"]),
        )


def native_outcome(routed):
    _, context, scene, game, _ = routed
    _, _, native, worker, gateway = prepare(routed, "Hold the calibration needle steady.", "native")
    answer(game, ADMIN, "handler_keep", flag=True, text="The needle remains steady.")
    tick(worker, gateway, 5)
    outcomes = GMOutcomeService(context)
    opened = outcomes.open(ADMIN, "narration-open", scene, "completed", native)
    packet = outcomes.packet(ADMIN, scene, opened["id"])
    saved = outcomes.propose(
        ADMIN,
        "narration-propose",
        scene,
        opened["id"],
        OutcomeProposal(
            request_id=packet.request_id,
            decision=OutcomeNarration(
                text="The native calibration attempt completed.", effect_refs=("tier",)
            ),
            cited_evidence=("source", "native"),
            private_reasoning="Actual completed native source.",
        ),
    )
    return outcomes.confirm(ADMIN, "narration-confirm", scene, saved["id"])["id"]


def test_resolution_requires_actual_accepted_native_outcome_and_remains_source_bound(routed):
    fronts, _, evidence = fixture(routed)
    _, _, scene, game, dice = routed
    value = draft(evidence)
    saved = fronts.save(ADMIN, "initial-front", scene, state(game).revision, value)
    resolved = value.model_copy(update={"supersedes": saved["id"], "status": "resolved"})
    with pytest.raises(WorkflowError):
        fronts.save(
            ADMIN,
            "fabricated-outcome",
            scene,
            state(game).revision,
            resolved,
            advance=FrontAdvance(kind="outcome", id="gm-narration:invented"),
        )
    outcome = native_outcome(routed)
    before = state(game)
    result = fronts.save(
        ADMIN,
        "native-resolution",
        scene,
        before.revision,
        resolved,
        advance=FrontAdvance(kind="outcome", id=outcome),
    )
    assert result["status"] == "resolved" and dice.calls == 1
    assert state(game).model_dump(exclude={"facts", "revision"}) == before.model_dump(
        exclude={"facts", "revision"}
    )
    assert len(records(state(game), current=False)) == 2


def test_front_writes_retain_world_owner_consent_controller_and_pending_play_guards(routed):
    fronts, world, evidence = fixture(routed)
    observer, _, scene, game, _ = routed
    world.world.npc(
        ADMIN,
        "npc",
        state(game).revision,
        Npc(
            id="front-npc",
            name="Mechanic",
            jobs=("mechanic",),
            detail="A careful person.",
            cell=(0, 0),
            controller=1,
        ),
    )
    value = draft(
        evidence, participants=(FrontParticipant(subject=Subject(kind="npc", id="front-npc")),)
    )
    with pytest.raises(WorkflowError):
        fronts.save(OTHER, "wrong-owner", scene, state(game).revision, value)
    initial = fronts.save(ADMIN, "initial", scene, state(game).revision, value)
    manual_time = fronts.fictional_time(
        ADMIN, "manual-time", scene, state(game).revision, 1, "A declared interval."
    )
    observer.set_consent(PLAYER, "withdraw", scene, 1, consent=False)
    with pytest.raises(WorkflowError, match="OBSERVATION_DISABLED"):
        fronts.fictional_time(
            ADMIN, "withdrawn-time", scene, state(game).revision, 1, "No consent."
        )
    observer.set_consent(PLAYER, "renew", scene, 1, consent=True)
    revised = value.model_copy(update={"supersedes": initial["id"]})
    with pytest.raises(WorkflowError, match="STALE_FRONT_ADVANCE"):
        fronts.save(
            ADMIN,
            "old-time",
            scene,
            state(game).revision,
            revised,
            advance=FrontAdvance(kind="fictional_time", id=manual_time["id"]),
        )
    npc_roles = NpcRoleService(world.world)
    offered = npc_roles.offer_transfer(
        ADMIN, "offer-front-npc", state(game).revision, "front-npc", OTHER.user_id
    )
    npc_roles.respond(OTHER, "accept-front-npc", offered["id"], state(game).revision, "accept")
    fresh_time = fronts.fictional_time(
        ADMIN, "fresh-time", scene, state(game).revision, 1, "A fresh declared interval."
    )
    with pytest.raises(WorkflowError, match="STALE_FRONT_CONTROLLER"):
        fronts.save(
            ADMIN,
            "changed-controller",
            scene,
            state(game).revision,
            revised,
            advance=FrontAdvance(kind="fictional_time", id=fresh_time["id"]),
        )
    start(game)
    before = state(game)
    with pytest.raises(WorkflowError, match="finish pending Plays"):
        fronts.fictional_time(ADMIN, "pending-time", scene, before.revision, 1, "Pending Play.")
    assert state(game) == before


def test_front_contract_has_references_not_balances_or_unrestricted_effects(routed):
    fronts, _, evidence = fixture(routed)
    scene, game = routed[2:4]
    raw = draft(evidence).model_dump(mode="json")
    raw["effects"] = [{"permissions": -1}]
    with pytest.raises(ValidationError):
        FrontDraft.model_validate_json(json.dumps(raw))
    with pytest.raises(ValidationError):
        FrontAdvance(kind="message", id="ordinary-chat")
    with pytest.raises(WorkflowError, match="STALE_FRONT_EVIDENCE"):
        fronts.save(
            ADMIN,
            "unknown-evidence",
            scene,
            state(game).revision,
            draft(FrontEvidence(kind="reference", id="invented")),
        )
