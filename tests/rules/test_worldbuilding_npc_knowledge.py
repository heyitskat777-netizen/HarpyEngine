"""An actual cast NPC retains selected world knowledge across a closed origin."""

import pytest
from test_actor_service import pc_ref, ready
from test_cast_service import change
from test_director_continuity import carry, new_scene
from test_director_observation import Clock, send
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state

from girlframe.ai.observation import ObservationPolicy
from girlframe.ai.worldbuilding import DevelopmentAction, WorldbuildingProposal
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_development import DevelopmentDraft, Subject
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.director_worldbuilding import DirectorWorldbuildingService
from girlframe.services.m3_cast import CastService
from girlframe.services.onboarding import WorkflowError


def test_native_cast_npc_disclosure_survives_closed_origin_and_new_explicit_cast(ledger):
    actors, game = ready(ledger)
    cast, npc = CastService(actors), ActorRef(kind="npc", entity="secret-npc")
    change(cast, PLAYER, "join", npc, key="npc-origin-cast")
    with ledger.engine.connect() as c:
        scene = game.scene(c, 900)["id"]
    ledger.clock = Clock()
    observer = DirectorObservationService(ledger, synthetic=True)
    observer.game = game
    observer.configure_scene(ADMIN, "npc-observe", scene, 0, ObservationPolicy(mode="shadow"))
    for viewer in (ADMIN, PLAYER, OTHER):
        observer.set_consent(viewer, f"npc-consent:{viewer.user_id}", scene, 1, consent=True)
    context = DirectorContextService(observer)
    service = DirectorWorldbuildingService(context)
    _, source = send(observer, scene, "npc-world-source", text="GM, establish the relay desk.")
    request = service.open(ADMIN, "npc-world-open", scene, source.source_id)
    detail = "The relay desk has an amber lamp."
    hidden = "PRIVATE_WORLD_DESK_COMPARTMENT"
    proposal = service.propose(
        ADMIN,
        "npc-world-propose",
        scene,
        request["id"],
        WorldbuildingProposal(
            request_id=request["id"],
            action=DevelopmentAction(
                development=DevelopmentDraft(
                    key="relay-desk",
                    kind="detail",
                    subject=Subject(kind="location", id="base0"),
                    title="Relay desk",
                    text=detail + " " + hidden,
                )
            ),
            cited_evidence=("source", "native"),
            private_reasoning="Bounded fixture detail.",
        ),
    )
    service.review(
        ADMIN,
        "npc-world-review",
        scene,
        proposal["id"],
        "approve",
        "The source supports a bounded location detail without mechanics.",
    )
    committed = service.confirm(ADMIN, "npc-world-confirm", scene, proposal["id"])
    disclosed = service.disclose(
        ADMIN, "npc-world-disclose", scene, committed["id"], detail, (npc,), topic="briefing"
    )
    identity = disclosed["reference_ids"][0]
    own = context.build(PLAYER, scene, actor=npc)
    assert detail in own.model_dump_json() and hidden not in own.model_dump_json()
    assert detail not in context.build(PLAYER, scene, actor=pc_ref(actors, game)).model_dump_json()
    with pytest.raises(WorkflowError):
        context.build(OTHER, scene, actor=npc)

    target = new_scene(observer)
    original = next(value for value in state(game).scene_casts if value.id == scene)
    assert not original.open and any(role.actor == npc for role in original.roles)
    change(cast, PLAYER, "join", npc, key="npc-target-cast", channel=901)
    copied = carry(context, scene, target, (identity,), key="npc-world-handoff")
    ledger.engine.dispose()
    context = DirectorContextService(observer)
    recalled = context.build(PLAYER, target, actor=npc)
    ref = next(value for value in recalled.references if value.id == copied["references"][identity])
    assert ref.origin_scene == scene and ref.origin_reference == identity
    assert ref.classification == "established_world" and ref.text == "Established world: " + detail
    assert hidden not in recalled.model_dump_json()
    assert detail not in context.build(PLAYER, target, actor=pc_ref(actors, game)).model_dump_json()
