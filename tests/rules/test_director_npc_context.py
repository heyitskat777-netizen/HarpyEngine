"""Actual NPC casting/knowledge proof; no invented presence or GM context forwarding."""

import pytest
from test_actor_service import ready
from test_cast_service import change
from test_director_observation import Clock, send
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger

from girlframe.ai.observation import ObservationPolicy
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_dialogue import DirectorDialogueService
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.m3_cast import CastService
from girlframe.services.onboarding import WorkflowError


def test_actual_npc_context_requires_cast_controller_and_explicit_knowledge(
    ledger, tmp_path, monkeypatch
):
    actors, game = ready(ledger)
    cast = CastService(actors)
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    observer = DirectorObservationService(ledger, synthetic=True)
    ledger.clock = Clock()
    observer.configure_scene(
        ADMIN, "configure-observer", scene, 0, ObservationPolicy(mode="shadow")
    )
    for viewer in (ADMIN, PLAYER, OTHER):
        observer.set_consent(viewer, "consent:" + str(viewer.user_id), scene, 1, consent=True)
    _, source = send(observer, scene, "source", text="SYNTHETIC_OBSERVED_REPORT")
    context = DirectorContextService(observer)
    npc = ActorRef(kind="npc", entity="secret-npc")
    with pytest.raises(WorkflowError):
        context.record(ADMIN, "uncast-reference", scene, source.source_id, 0, known_by=(npc,))
    change(cast, PLAYER, "join", npc)
    assert not context.build(PLAYER, scene, actor=npc).references
    context.record(ADMIN, "known-reference", scene, source.source_id, 0, known_by=(npc,))
    own = context.build(PLAYER, scene, actor=npc)
    assert len(own.references) == 1
    assert "SYNTHETIC_OBSERVED_REPORT" in own.model_dump_json()
    assert "PRIVATE_NPC_NAME" not in own.model_dump_json()
    assert "PRIVATE_NPC_DETAIL" not in own.model_dump_json()
    with pytest.raises(WorkflowError):
        context.build(OTHER, scene, actor=npc)
    from test_enforcer_requisitions import approved
    from test_m2_game import state

    from girlframe.engine import m3_appearance_matrix as matrix_rules
    from girlframe.services.director_contributions import DirectorContributionService
    from girlframe.services.m3_appearance_matrix import MatrixService

    approved(ledger, game, tmp_path, monkeypatch, extra=(matrix_rules.RULE,))
    venue = MatrixService(game).record_context(
        ADMIN, "record-venue", 900, state(game).revision, "base0"
    )["id"]
    own = context.build(PLAYER, scene, actor=npc)
    dialogue = DirectorDialogueService(context)
    draft = dialogue.draft(
        PLAYER, "npc-draft", scene, npc, own.revision, tuple(x.id for x in own.references)
    )
    assert "SYNTHETIC_OBSERVED_REPORT" in dialogue.get(PLAYER, scene, draft["id"])["text"]
    with pytest.raises(WorkflowError):
        dialogue.get(OTHER, scene, draft["id"])
    reviewed = dialogue.review(PLAYER, "npc-review", scene, draft["id"], decision="approve")
    assert dialogue.review(PLAYER, "npc-review", scene, draft["id"], decision="approve") == reviewed
    assert reviewed["publication"] == reviewed["application"] == "blocked"
    contributions = DirectorContributionService(dialogue)
    with pytest.raises(WorkflowError):
        contributions.commit_synthetic_report(
            PLAYER, "unknown-venue", scene, draft["id"], "unknown"
        )
    result = contributions.commit_synthetic_report(
        PLAYER, "commit-report", scene, draft["id"], venue
    )
    assert (
        contributions.commit_synthetic_report(PLAYER, "commit-report", scene, draft["id"], venue)
        == result
    )
    projected = contributions.projections(OTHER, scene)
    assert len(projected) == 1 and "SYNTHETIC_OBSERVED_REPORT" in projected[0]["text"]
    assert "PRIVATE_NPC_NAME" not in str(projected)
    assert "secret-npc" not in str(projected)
    assert "owner_id" not in projected[0] and "actor" not in projected[0]
    ledger.safety(PLAYER, "pause-output", 0, pause=True)
    assert not contributions.projections(OTHER, scene)
    ledger.safety(PLAYER, "resume-output", ledger.status(ADMIN)["revision"], pause=False)
    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_missions import MissionService

    cast = CastService(ActorService(MissionService(ledger)))
    change(cast, PLAYER, "withdraw", npc)
    assert not contributions.projections(OTHER, scene)
    with pytest.raises(WorkflowError):
        context.build(PLAYER, scene, actor=npc)
