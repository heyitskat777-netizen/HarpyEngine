"""Controller-confirmed actor dossiers preserve private perspectives and native state."""

import pytest
from test_director_continuity import roles
from test_director_conversation import routed as routed
from test_director_observation import observed as observed
from test_director_observation import send
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_worldbuilding_knowledge import established

from girlframe.ai.director_dossiers import (
    DossierPerspective,
    DossierProfile,
    DossierState,
    Personnel,
)
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_dossiers import DirectorDossierService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_roles import NpcRoleService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError


def propose(
    service, scene, actor, version, *, key="draft", presence="background", voice="Measured"
):
    return service.propose(
        ADMIN,
        key,
        scene,
        actor,
        version,
        DossierProfile(
            presence=presence,
            background="Private controller-authored background.",
            voice=voice,
            behavior="Pause before answering a difficult request.",
            reaction_tendencies=("Ask a question", "Offer a conditional compromise"),
            limits=("Decline personal disclosures when uncomfortable",),
            values=("Keep promises",),
            fears=("PRIVATE_SELF_FEAR",),
            contradictions=("Wants company but avoids crowds",),
        ),
        DossierState(
            beliefs=(DossierPerspective(text="I think patience earns trust."),),
            obligations=(DossierPerspective(text="I promised to return the spare seal."),),
            experiences=(DossierPerspective(text="I remember missing a training light."),),
        ),
        Personnel(public_summary="A careful pilot", mannerisms="Checks their gloves"),
    )


def test_controller_confirmation_versioned_portrayal_and_separate_gm_notes_survive_restart(routed):
    observer, context, scene, game, _ = routed
    _, pilot = roles(observer, scene)
    service = DirectorDossierService(context)
    before = state(game).model_dump(mode="json", exclude={"facts", "revision"})
    draft = propose(service, scene, pilot, 0)
    assert service.pending(PLAYER, scene)[0]["id"] == draft["id"]
    assert not service.pending(OTHER, scene)
    assert "PRIVATE_SELF_FEAR" not in str(service.pending(ADMIN, scene, gm=True))
    assert not service.role_packet(PLAYER, scene, pilot).profile
    assert state(game).model_dump(mode="json", exclude={"facts", "revision"}) == before
    with pytest.raises(WorkflowError, match="DOSSIER_NOT_OWNED"):
        service.confirm(ADMIN, "gm-cannot-confirm", scene, draft["id"])
    assert service.review(PLAYER, scene, draft["id"]).expected_version == 0
    saved = service.confirm(PLAYER, "owner-confirms", scene, draft["id"])
    assert service.confirm(PLAYER, "owner-confirms", scene, draft["id"]) == saved
    assert not service.pending(PLAYER, scene)
    notes = service.gm_notes(ADMIN, "private-notes", scene, pilot, 0, "PRIVATE_GM_AUTHOR_NOTE")
    assert notes["version"] == 1
    own = service.role_packet(PLAYER, scene, pilot)
    assert own.dossier_version == 1 and own.profile.presence == "background"
    assert len(own.profile.reaction_tendencies) == 2 and own.profile.limits
    assert own.state.obligations[0].provenance == "controller_authored_perspective"
    assert own.state.experiences[0].provenance == "controller_authored_perspective"
    assert "PRIVATE_SELF_FEAR" in own.model_dump_json()
    assert "PRIVATE_GM_AUTHOR_NOTE" not in own.model_dump_json()
    assert "SYNTHETIC_GM_SECRET_CANARY" not in own.model_dump_json()
    with observer.store.engine.connect() as c:
        assert service._role_packet(c, scene, pilot) == own
    with observer.store.engine.connect() as c:
        other = observer._authorize_input(c, OTHER, scene, "pilot")[2]
    personnel = service.personnel(OTHER, scene, other, pilot)
    assert personnel["personnel"]["public_summary"] == "A careful pilot"
    assert "PRIVATE_SELF_FEAR" not in str(personnel) and "PRIVATE_GM_AUTHOR_NOTE" not in str(
        personnel
    )
    next_draft = propose(service, scene, pilot, 1, key="recurring", presence="recurring")
    competing = propose(service, scene, pilot, 1, key="stale-recurring", voice="Quiet")
    service.confirm(PLAYER, "promote-same-actor", scene, next_draft["id"])
    with pytest.raises(WorkflowError, match="STALE_DOSSIER"):
        service.confirm(PLAYER, "reject-old-revision", scene, competing["id"])
    observer.store.engine.dispose()
    service = DirectorDossierService(DirectorContextService(observer))
    restored = service.role_packet(PLAYER, scene, pilot)
    assert restored.actor == pilot and restored.dossier_version == 2
    assert restored.profile.presence == "recurring"
    assert len(service.gm(ADMIN, scene, pilot)["history"]) == 2
    assert state(game).model_dump(mode="json", exclude={"facts", "revision"}) == before
    pending = propose(service, scene, pilot, 2, key="pending-before-correction")
    reference = restored.context.references[0]
    send(
        observer,
        scene,
        "correct-background",
        viewer=ADMIN,
        text="Corrected briefing.",
        source_id=reference.source_id,
        expected_source_revision=reference.source_revision,
    )
    metadata = next(row for row in service.pending(PLAYER, scene) if row["id"] == pending["id"])
    assert metadata["status"] == "stale_reopen_source"
    assert "PRIVATE_SELF_FEAR" not in str(metadata)


def test_unknown_fact_citations_and_revoked_consent_cannot_enter_self_packet(routed):
    observer, context, scene, _, _ = routed
    _, pilot = roles(observer, scene)
    with observer.store.engine.connect() as c:
        other = observer._authorize_input(c, OTHER, scene, "pilot")[2]
        order = len(context._references(c, scene))
    _, source = send(
        observer,
        scene,
        "other-private",
        viewer=OTHER,
        text="PRIVATE_OTHER_ROLE_OBSERVATION",
        fictional_channel="private",
    )
    hidden = context.record(
        ADMIN, "other-private-memory", scene, source.source_id, order, known_by=(other,)
    )
    service = DirectorDossierService(context)
    with pytest.raises(WorkflowError, match="DOSSIER_UNKNOWN_SOURCE"):
        service.propose(
            ADMIN,
            "cannot-attribute-hidden",
            scene,
            pilot,
            0,
            DossierProfile(),
            DossierState(
                beliefs=(
                    DossierPerspective(
                        text="I somehow know another role's secret.", knowledge_refs=(hidden["id"],)
                    ),
                )
            ),
        )
    draft = propose(service, scene, pilot, 0)
    observer.set_consent(PLAYER, "withdraw-dossier", scene, 1, consent=False)
    with pytest.raises(WorkflowError, match="OBSERVATION_DISABLED"):
        service.confirm(PLAYER, "no-consent-confirm", scene, draft["id"])
    with pytest.raises(WorkflowError, match="OBSERVATION_DISABLED"):
        service.role_packet(PLAYER, scene, pilot)


def test_same_human_npc_and_pilot_self_fields_do_not_cross_roles_or_native_visibility(routed):
    observer, context, scene, game, _ = routed
    _, pilot = roles(observer, scene)
    established(routed)
    world = WorldService(MissionService(observer.store))
    roles_service = NpcRoleService(world)
    offered = roles_service.offer(
        ADMIN,
        "offer-dossier-npc",
        state(game).revision,
        Npc(
            id="dossier-npc",
            name="PRIVATE_NPC_NAME",
            jobs=("guard",),
            detail="PRIVATE_NPC_NATIVE_DETAIL",
            controller=PLAYER.user_id,
            cell=(0, 0),
        ),
    )
    roles_service.respond(
        PLAYER, "accept-dossier-npc", offered["id"], state(game).revision, "accept"
    )
    npc = ActorRef(kind="npc", entity="dossier-npc")
    cast = CastService(ActorService(world.missions))
    view = cast.view(PLAYER, 900)
    cast.change(
        PLAYER, "cast-dossier-npc", 900, view["game_revision"], view["cast_revision"], "join", npc
    )
    service = DirectorDossierService(context)
    npc_draft = propose(service, scene, npc, 0, voice="PRIVATE_NPC_DOSSIER_VOICE")
    service.confirm(PLAYER, "confirm-dossier-npc", scene, npc_draft["id"])
    npc_packet = service.role_packet(PLAYER, scene, npc)
    pilot_packet = service.role_packet(PLAYER, scene, pilot)
    assert "PRIVATE_NPC_DOSSIER_VOICE" in npc_packet.model_dump_json()
    assert "PRIVATE_NPC_DOSSIER_VOICE" not in pilot_packet.model_dump_json()
    assert pilot_packet.profile is None
    with pytest.raises(WorkflowError, match="DOSSIER_IDENTITY_UNKNOWN"):
        service.personnel(PLAYER, scene, pilot, npc)
    with pytest.raises(WorkflowError, match="DOSSIER_NOT_OWNED"):
        service.role_packet(OTHER, scene, npc)
