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


def test_actual_npc_context_requires_cast_controller_and_explicit_knowledge(ledger):
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
    change(cast, PLAYER, "withdraw", npc)
    with pytest.raises(WorkflowError):
        context.build(PLAYER, scene, actor=npc)
