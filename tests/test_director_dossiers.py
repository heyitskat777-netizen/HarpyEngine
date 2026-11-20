"""Controller-confirmed actor dossiers preserve private perspectives and native state."""

import pytest
from test_director_activity_scene import P2Scene
from test_director_continuity import carry, new_scene, reference, roles
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
from girlframe.engine.campaign_opening import CampaignSeats, Opening, PlannedAIPilot
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Npc
from girlframe.engine.pilot_portrayal import PILOT_PORTRAYALS
from girlframe.services.campaign_difficulty import EVENT
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_dossiers import DirectorDossierService
from girlframe.services.director_observation import DirectorObservationService
from girlframe.services.director_session import DirectorSessionService
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


def test_generated_pilot_uses_the_approved_plan_and_actual_npc_controller(routed):
    observer, context, scene, game, _ = routed
    _, human_pilot = roles(observer, scene)
    established(routed)
    world = WorldService(MissionService(observer.store))
    native_roles = NpcRoleService(world)
    offer = native_roles.offer(
        ADMIN,
        "offer-pilot-npc",
        state(game).revision,
        Npc(
            id="trainee",
            name="Tern",
            jobs=("pilot_candidate",),
            detail="Uses the training bay.",
            controller=PLAYER.user_id,
            cell=(0, 0),
        ),
    )
    native_roles.respond(PLAYER, "accept-trainee", offer["id"], state(game).revision, "accept")
    npc = ActorRef(kind="npc", entity="trainee")
    cast = CastService(ActorService(world.missions))
    view = cast.view(PLAYER, 900)
    cast.change(
        PLAYER, "cast-trainee", 900, view["game_revision"], view["cast_revision"], "join", npc
    )
    portrayal = PILOT_PORTRAYALS[0].model_copy(update={"voice": "PRIVATE_MIXED_VOICE"})
    record = Opening(
        scene="approved-introduction",
        channel=901,
        handler=ADMIN.user_id,
        audience=(ADMIN.user_id, PLAYER.user_id),
        plan="approved-plan",
        goals="Share handoffs.",
        difficulty="normal",
        introduction="Check in.",
        first_mission_day=4,
        seats=CampaignSeats(
            player_count=2,
            ai_pilots=(
                PlannedAIPilot(
                    callsign="Tern", concept="From the training wing.", portrayal=portrayal
                ),
            ),
        ),
    )
    with observer.store.transaction() as c:
        observer.store._audit(
            c, ADMIN.user_id, "approved-pilot-plan", EVENT, record.model_dump(mode="json")
        )
    app = P2Scene(DirectorSessionService(context))
    assert app.read(OTHER, scene, "pilot-dossiers") == {"pilots": [], "actors": []}
    options = app.read(PLAYER, scene, "pilot-dossiers")
    assert options["pilots"] == ["Tern"]
    assert options["actors"] == [{"actor": npc.model_dump(mode="json"), "label": "Tern"}]
    route = "pilot-dossier-propose"
    data = {
        "actor": npc.model_dump(mode="json"),
        "origin": {"plan": options["plan"], "callsign": "Tern"},
    }
    with pytest.raises(WorkflowError, match="PILOT_DOSSIER_OWNER"):
        app.write(ADMIN, "wrong-owner", scene, route, data)
    with pytest.raises(WorkflowError, match="PILOT_DOSSIER_PLAN"):
        app.write(
            PLAYER,
            "stale-plan",
            scene,
            route,
            data | {"origin": {"plan": "old", "callsign": "Tern"}},
        )
    original = state(game)
    draft = app.write(PLAYER, "prepare", scene, route, data)
    assert app.write(PLAYER, "prepare", scene, route, data) == draft
    assert app.session.dossiers.role_packet(PLAYER, scene, npc).profile is None
    review = app.read(PLAYER, scene, "dossier-review", draft["id"])
    assert review["pilot_origin"] == data["origin"]
    assert "PRIVATE_MIXED_VOICE" == review["profile"]["voice"]
    with pytest.raises(WorkflowError, match="DOSSIER_NOT_OWNED"):
        app.read(ADMIN, scene, "dossier-review", draft["id"])
    saved = app.write(PLAYER, "accept-dossier", scene, "dossier-confirm", {"id": draft["id"]})
    assert saved["version"] == 1 and saved["effects_applied"] is False
    assert state(game).model_dump(exclude={"revision", "facts"}) == original.model_dump(
        exclude={"revision", "facts"}
    )
    assert app.read(PLAYER, scene, "pilot-dossiers")["pilots"] == []
    assert app.session.dossiers.role_packet(PLAYER, scene, human_pilot).profile is None
    _, source = send(
        observer, scene, "pilot-turn", text="What did you find?", fictional_channel="comms"
    )
    reaction = app.session.reactions.open(ADMIN, "reaction", scene, npc, source.source_id)
    dossier = app.session.reactions.packet(ADMIN, scene, reaction["id"])["role"]["dossier"]
    assert dossier["profile"]["voice"] == "PRIVATE_MIXED_VOICE"
    assert dossier["profile"]["reaction_tendencies"] == [portrayal.pressure]
    assert dossier["context"]["actor"] == npc.model_dump(mode="json")
    sheet = next(
        item
        for item in app.read(PLAYER, "", "portrayal-sheets")["sheets"]
        if item["actor"] == npc.model_dump(mode="json")
    )
    assert sheet["portrayal"]["archetype"] == portrayal.archetype
    assert sheet["portrayal"]["repair"] == portrayal.repair
    edited = sheet["portrayal"] | {"voice": "Use practical examples and a little dry humor."}
    edit = {"actor": sheet["actor"], "version": sheet["version"], "portrayal": edited}
    manual = P2Scene(
        DirectorSessionService(DirectorContextService(DirectorObservationService(observer.store)))
    )
    draft = manual.write(PLAYER, "edit-from-sheet", "", "portrayal-draft", edit)
    assert manual.write(PLAYER, "edit-from-sheet", "", "portrayal-draft", edit) == draft
    assert (
        "PRIVATE_MIXED_VOICE"
        == app.read(PLAYER, scene, "portrayal-preview", npc.token)["profile"]["pilot_portrayal"][
            "voice"
        ]
    )
    with pytest.raises(WorkflowError):
        app.read(OTHER, scene, "portrayal-preview", npc.token)
    assert (
        manual.write(
            PLAYER,
            "approve-sheet",
            "",
            "portrayal-confirm",
            {"actor": sheet["actor"], "id": draft["id"]},
        )["version"]
        == 2
    )
    history = app.session.dossiers._records(state(game), npc)
    assert history[0].pilot_origin == history[1].pilot_origin
    next_reaction = app.session.reactions.open(
        ADMIN, "edited-reaction", scene, npc, source.source_id
    )
    packet = app.session.reactions.packet(ADMIN, scene, next_reaction["id"])["role"]["dossier"]
    assert packet["profile"]["pilot_portrayal"] == edited
    assert packet["profile"]["voice"] == edited["voice"]
    assert "PRIVATE_MIXED_VOICE" not in str(packet)


def test_sheet_experiences_follow_the_owned_scoped_source(routed):
    observer, context, scene, _, _ = routed
    handler, pilot = roles(observer, scene)
    app = P2Scene(DirectorSessionService(context))
    npc_voice = {"voice": "Wait before offering help."}
    actor = pilot.model_dump(mode="json")
    draft = app.write(
        PLAYER,
        "pilot-portrayal",
        "",
        "portrayal-draft",
        {"actor": actor, "version": 0, "portrayal": npc_voice},
    )
    assert app.read(PLAYER, scene, "portrayal-preview", pilot.token)["profile"] is None
    app.write(
        PLAYER,
        "apply-pilot-portrayal",
        "",
        "portrayal-confirm",
        {"actor": actor, "id": draft["id"]},
    )
    seen, _ = reference(context, scene, "pause", "Wait for my signal.", (pilot,))
    private, _ = reference(context, scene, "unheard", "PRIVATE_HANDLER_NOTE", (handler,))
    attempt = {"actor": actor, "version": 1, "reference": private, "text": "Do not take over."}
    with pytest.raises(WorkflowError, match="DOSSIER_UNKNOWN_SOURCE"):
        app.write(PLAYER, "fabricated-experience", scene, "portrayal-experience", attempt)
    saved = app.write(
        PLAYER, "actual-experience", scene, "portrayal-experience", attempt | {"reference": seen}
    )
    before = app.read(PLAYER, scene, "portrayal-preview", pilot.token)
    assert before["pending_experience"]["entry"]["text"] == attempt["text"]
    assert before["state"]["experiences"] == []
    done = {"actor": actor, "id": saved["id"]}
    accepted = app.write(PLAYER, "file-experience", "", "portrayal-confirm", done)
    assert app.write(PLAYER, "file-experience", "", "portrayal-confirm", done) == accepted
    with pytest.raises(WorkflowError, match="STALE_DOSSIER"):
        app.write(PLAYER, "file-same-experience-again", "", "portrayal-confirm", done)
    target = new_scene(observer)
    shown = app.read(PLAYER, target, "portrayal-preview", pilot.token)
    assert shown["state"]["experiences"] == []
    assert shown["profile"]["pilot_portrayal"]["voice"] == npc_voice["voice"]
    carry(context, scene, target, (seen,), "approved-lesson")
    shown = app.read(PLAYER, target, "portrayal-preview", pilot.token)
    assert [entry["text"] for entry in shown["state"]["experiences"]] == [attempt["text"]]
    assert "PRIVATE_HANDLER_NOTE" not in str(shown)
    recalled = next(
        ref["id"] for ref in shown["context"]["references"] if ref["origin_reference"] == seen
    )
    new_draft = app.write(
        PLAYER,
        "more-lessons",
        target,
        "portrayal-experience",
        {"actor": actor, "version": 2, "reference": recalled, "text": "Ask which signal they use."},
    )
    observer.set_consent(PLAYER, "withdraw", target, 1, consent=False)
    with pytest.raises(WorkflowError, match="OBSERVATION_DISABLED"):
        app.write(
            PLAYER,
            "withdrawn-experience",
            "",
            "portrayal-confirm",
            {"actor": actor, "id": new_draft["id"]},
        )
