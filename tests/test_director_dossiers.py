"""Controller-confirmed actor dossiers preserve private perspectives and native state."""

import pytest
from pydantic import ValidationError
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
from girlframe.ai.observation import ObservationPolicy
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

    app = P2Scene(DirectorSessionService(context))
    actor = npc.model_dump(mode="json")
    setup = {"drive": "PRIVATE_NPC_SETUP", "resources": ["A radio contact"]}
    draft = app.write(
        PLAYER,
        "npc-character-setup",
        "",
        "portrayal-draft",
        {"actor": actor, "version": 1, "character_setup": setup},
    )
    app.write(
        PLAYER,
        "npc-setup-confirm",
        "",
        "portrayal-confirm",
        {"actor": actor, "id": draft["id"]},
    )
    saved = service.role_packet(PLAYER, scene, npc).profile
    assert saved.character_setup.drive == setup["drive"]
    assert saved.character_setup.resources == ("A radio contact",)
    assert saved.voice == "PRIVATE_NPC_DOSSIER_VOICE"
    assert service.role_packet(PLAYER, scene, pilot).profile is None


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
    assert options["actors"] == [
        {
            "actor": npc.model_dump(mode="json"),
            "label": "Tern",
            "version": 0,
            "eligible_pilots": ["Tern"],
        }
    ]
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


def test_character_setup_is_owner_reviewed_private_and_independent_of_mechanics(routed):
    observer, context, scene, game, _ = routed
    handler, pilot = roles(observer, scene)
    app = P2Scene(DirectorSessionService(context))
    original = state(game).model_dump(exclude={"revision", "facts"})
    for owner, actor, label in ((ADMIN, handler, "HANDLER"), (PLAYER, pilot, "GIRL")):
        setup = {
            "drive": f"{label}_PRIVATE_DRIVE",
            "resources": ["Knows the welders by name"],
            "limits": ["Will not give names to command"],
            "voice_at_ease": "Ask an open question",
            "voice_under_pressure": "Count out loud",
            "voice_on_repair": "Name the mistake",
        }
        body = {"actor": actor.model_dump(mode="json"), "version": 0, "character_setup": setup}
        with pytest.raises(WorkflowError, match="another human"):
            app.write(OTHER, f"outside:{label}", "", "portrayal-draft", body)
        with pytest.raises(ValidationError):
            app.write(
                owner,
                f"bad:{label}",
                "",
                "portrayal-draft",
                body | {"character_setup": setup | {"resources": [" "]}},
            )
        draft = app.write(owner, f"setup:{label}", "", "portrayal-draft", body)
        sheet = next(
            row
            for row in app.read(owner, "", "portrayal-sheets")["sheets"]
            if row["token"] == actor.token
        )
        assert sheet["character_setup"] is None
        assert sheet["pending"]["kind"] == "character_setup"
        assert sheet["pending"]["character_setup"] == setup
        assert app.read(owner, scene, "portrayal-preview", actor.token)["profile"] is None
        assert setup["drive"] not in str(app.read(OTHER, "", "portrayal-sheets"))
        confirmation = {"actor": body["actor"], "id": draft["id"]}
        with pytest.raises(WorkflowError, match="another human"):
            app.write(OTHER, f"outside-confirm:{label}", "", "portrayal-confirm", confirmation)
        approved = app.write(owner, f"confirm:{label}", "", "portrayal-confirm", confirmation)
        assert approved["version"] == 1 and approved["effects_applied"] is False
        with pytest.raises(WorkflowError, match="STALE_DOSSIER"):
            app.write(owner, f"stale:{label}", "", "portrayal-draft", body)
        restarted = P2Scene(
            DirectorSessionService(
                DirectorContextService(DirectorObservationService(observer.store, synthetic=True))
            )
        )
        assert (
            restarted.read(owner, scene, "portrayal-preview", actor.token)["profile"][
                "character_setup"
            ]
            == setup
        )
        with pytest.raises(WorkflowError, match="DOSSIER_NOT_OWNED"):
            restarted.read(OTHER, scene, "portrayal-preview", actor.token)
    assert state(game).model_dump(exclude={"revision", "facts"}) == original


def test_native_pilot_seat_requires_matching_sheet_and_owner_confirmation(routed):
    observer, context, scene, game, _ = routed
    _, pilot = roles(observer, scene)
    app = P2Scene(DirectorSessionService(context))
    dossiers = app.session.dossiers
    with observer.store.engine.connect() as c:
        actual = dossiers._actor(c, scene, pilot)
    portrayal = PILOT_PORTRAYALS[0].model_copy(
        update={"girl_playbook": actual.girl, "frame_playbook": actual.frame}
    )
    mismatch = "JANUS" if actual.frame != "JANUS" else "WYVERN 0.4"
    different_girl = "PRINCESS" if actual.girl != "PRINCESS" else "MOCKINGBIRD"
    record = Opening(
        scene="native-introduction",
        channel=901,
        handler=ADMIN.user_id,
        audience=(ADMIN.user_id, PLAYER.user_id),
        plan="native-plan",
        goals="Keep the native sheet.",
        difficulty="normal",
        introduction="Check in.",
        first_mission_day=4,
        seats=CampaignSeats(
            player_count=2,
            ai_pilots=(
                PlannedAIPilot(callsign="Matching seat", portrayal=portrayal),
                PlannedAIPilot(
                    callsign="Wrong frame",
                    portrayal=portrayal.model_copy(update={"frame_playbook": mismatch}),
                ),
                PlannedAIPilot(
                    callsign="Wrong Girl",
                    portrayal=portrayal.model_copy(update={"girl_playbook": different_girl}),
                ),
                PlannedAIPilot(callsign=actual.label),
            ),
        ),
    )
    with observer.store.transaction() as c:
        observer.store._audit(
            c, ADMIN.user_id, "native-plan", EVENT, record.model_dump(mode="json")
        )
        assert pilot not in dossiers.activity_pilots(c, scene)
    actor = pilot.model_dump(mode="json")
    setup = app.write(
        PLAYER,
        "native-setup",
        "",
        "portrayal-draft",
        {
            "actor": actor,
            "version": 0,
            "character_setup": {"drive": "Keep the watch"},
        },
    )
    app.write(
        PLAYER, "approve-native-setup", "", "portrayal-confirm", {"actor": actor, "id": setup["id"]}
    )
    options = app.read(PLAYER, scene, "pilot-dossiers")
    option = next(item for item in options["actors"] if item["actor"] == actor)
    assert option["eligible_pilots"] == ["Matching seat"]
    assert option["version"] == 1
    body = {
        "actor": actor,
        "version": option["version"],
        "origin": {
            "plan": options["plan"],
            "callsign": "Matching seat",
        },
    }
    with pytest.raises(WorkflowError, match="PILOT_DOSSIER_OWNER"):
        app.write(ADMIN, "native-wrong-owner", scene, "pilot-dossier-propose", body)
    for callsign in ("Wrong frame", "Wrong Girl", actual.label):
        with pytest.raises(WorkflowError, match="PILOT_DOSSIER_SHEET"):
            app.write(
                PLAYER,
                f"no:{callsign}",
                scene,
                "pilot-dossier-propose",
                body | {"origin": body["origin"] | {"callsign": callsign}},
            )
    draft = app.write(PLAYER, "native-draft", scene, "pilot-dossier-propose", body)
    with observer.store.engine.connect() as c:
        assert pilot not in dossiers.activity_pilots(c, scene)
    with pytest.raises(WorkflowError, match="DOSSIER_NOT_OWNED"):
        app.write(ADMIN, "native-forged-confirm", scene, "dossier-confirm", {"id": draft["id"]})
    original = state(game).model_dump(exclude={"revision", "facts"})
    approved = app.write(PLAYER, "native-confirm", scene, "dossier-confirm", {"id": draft["id"]})
    assert approved["version"] == 2 and approved["effects_applied"] is False
    assert state(game).model_dump(exclude={"revision", "facts"}) == original
    with observer.store.engine.connect() as c:
        assert dossiers.activity_pilots(c, scene)[pilot] == (actual.label, portrayal)
    assert (
        dossiers.role_packet(PLAYER, scene, pilot).profile.character_setup.drive == "Keep the watch"
    )
    assert not app.read(PLAYER, scene, "pilot-dossiers")["actors"]
    with pytest.raises(WorkflowError, match="PILOT_DOSSIER_USED"):
        app.write(PLAYER, "native-duplicate", scene, "pilot-dossier-propose", body | {"version": 2})
    superseded = record.model_copy(update={"plan": "revised-plan"})
    with observer.store.transaction() as c:
        observer.store._audit(
            c, ADMIN.user_id, "revised-plan", EVENT, superseded.model_dump(mode="json")
        )
        assert pilot not in dossiers.activity_pilots(c, scene)
    assert app.read(PLAYER, scene, "pilot-dossiers")["actors"][0]["version"] == 2


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


def test_handler_agenda_follows_a_witnessed_refusal_into_later_scene(routed):
    observer, context, scene, game, _ = routed
    handler, pilot = roles(observer, scene)
    app = P2Scene(DirectorSessionService(context))
    actor = handler.model_dump(mode="json")
    lead = {
        "stake": "Keep incoming lights off the test bench.",
        "next_step": "Ask the pilot to trade the late watch.",
        "blocker": "The pilot owns the decision.",
        "trigger": "The current watch must end.",
        "fallback": "Ask supply to cover the last hour.",
    }
    original = state(game).model_dump(exclude={"revision", "facts"})

    def draft(key, version, memory, viewer=ADMIN):
        return app.write(
            viewer,
            key,
            scene,
            "portrayal-memory",
            {"actor": actor, "version": version, "memory": memory},
        )

    def confirm(key, revision, viewer=ADMIN):
        return app.write(
            viewer, key, "", "portrayal-confirm", {"actor": actor, "id": revision["id"]}
        )

    first = {"kind": "pressures", "text": "Cover the late watch.", "pressure": lead}
    pending = draft("late-watch-draft", 0, first)
    with pytest.raises(WorkflowError):
        confirm("foreign-late-watch-confirm", pending, viewer=PLAYER)
    confirm("late-watch-confirm", pending)
    plan = app.read(ADMIN, scene, "portrayal-preview", handler.token)["state"]["pressures"][0]
    revised = first | {
        "pressure_id": plan["pressure_id"],
        "pressure": lead
        | {
            "next_step": lead["fallback"],
            "consequence": "The pilot kept her assigned watch. The Handler will ask supply.",
        },
    }
    with pytest.raises(WorkflowError, match="PRESSURE_EVIDENCE"):
        draft("no-refusal-evidence", 1, revised)

    _, refusal = send(
        observer,
        scene,
        "refuse-switch",
        "I am keeping my assigned watch.",
        viewer=PLAYER,
        fictional_channel="comms",
    )
    with observer.store.engine.connect() as c:
        order = len(context._references(c, scene))
    proof = context.record(
        ADMIN, "refusal-proof", scene, refusal.source_id, order, known_by=(handler, pilot)
    )["id"]
    confirm("confirm-fallback", draft("refusal-fallback", 1, revised | {"knowledge_refs": [proof]}))
    term = {
        "kind": "terms",
        "subject": pilot.model_dump(mode="json"),
        "term": "refusal",
        "text": "The watch transfer was refused.",
        "knowledge_refs": [proof],
    }
    confirm("confirm-refusal-term", draft("remember-refusal", 2, term))
    assert state(game).model_dump(exclude={"revision", "facts"}) == original

    later = new_scene(observer)
    game.store.engine.dispose()
    recovered = P2Scene(DirectorSessionService(context))
    own = recovered.read(ADMIN, later, "portrayal-preview", handler.token)
    assert own["state"]["pressures"][0]["pressure"]["next_step"] == lead["fallback"]
    assert (
        own["state"]["pressures"][0]["pressure"]["consequence"]
        == revised["pressure"]["consequence"]
    )
    assert own["state"]["terms"][0]["text"] == term["text"]
    assert proof not in str(own["context"]["references"])
    counterpart = recovered.read(PLAYER, later, "portrayal-preview", pilot.token)
    assert lead["stake"] not in str(counterpart)
    assert term["text"] not in str(counterpart)
    with observer.store.engine.connect() as c:
        dossiers = recovered.session.dossiers
        one_to_one = dossiers._role_packet(c, later, handler, subjects=(pilot,))
        generic = dossiers._role_packet(c, later, handler, subjects=())
        assert one_to_one.state and one_to_one.state.terms[0].text == term["text"]
        assert generic.state and not generic.state.terms
    observer.set_consent(PLAYER, "withdraw-refusal-origin", scene, 1, consent=False)
    recalled = recovered.read(ADMIN, later, "portrayal-preview", handler.token)["state"]
    assert recalled["pressures"] == [] and "terms" not in recalled


def test_private_continuity_requires_owner_review_and_survives_scene_close(routed):
    observer, context, scene, game, _ = routed
    handler, pilot = roles(observer, scene)
    app = P2Scene(DirectorSessionService(context))
    _, heard = send(
        observer,
        scene,
        "relay-exchange",
        "Let me try first.",
        viewer=PLAYER,
        fictional_channel="comms",
    )
    with observer.store.engine.connect() as c:
        order = len(context._references(c, scene))
    source = context.record(
        ADMIN, "relay-reference", scene, heard.source_id, order, known_by=(handler,)
    )
    unheard, _ = reference(context, scene, "unheard-thought", "I wish she would leave.", (handler,))
    actor = handler.model_dump(mode="json")
    update = {
        "kind": "relationship",
        "subject": pilot.model_dump(mode="json"),
        "text": "I can give her room without leaving her to do this alone.",
        "knowledge_refs": [source["id"]],
    }
    draft_body = {"actor": actor, "version": 0, "updates": [update]}
    original = state(game).model_dump(exclude={"revision", "facts"})
    preview = app.read(ADMIN, scene, "portrayal-preview", handler.token)
    eligible = {item["id"] for item in preview["continuity_sources"]}
    assert source["id"] in eligible and unheard not in eligible
    with pytest.raises(WorkflowError, match="CONTINUITY_SOURCE"):
        app.write(
            ADMIN,
            "unheard-continuity",
            scene,
            "portrayal-continuity",
            draft_body
            | {
                "updates": [update | {"knowledge_refs": [unheard]}],
            },
        )
    with pytest.raises(WorkflowError):
        app.write(OTHER, "foreign-continuity", scene, "portrayal-continuity", draft_body)
    draft = app.write(ADMIN, "draft-continuity", scene, "portrayal-continuity", draft_body)
    preview = app.read(ADMIN, scene, "portrayal-preview", handler.token)
    assert preview["pending_continuity"]["entries"][0]["text"] == update["text"]
    assert update["text"] not in str(preview["state"])
    confirmation = {"actor": actor, "id": draft["id"]}
    with pytest.raises(WorkflowError):
        app.write(PLAYER, "foreign-confirmation", "", "portrayal-confirm", confirmation)
    saved = app.write(ADMIN, "approve-continuity", "", "portrayal-confirm", confirmation)
    assert app.write(ADMIN, "approve-continuity", "", "portrayal-confirm", confirmation) == saved
    assert state(game).model_dump(exclude={"revision", "facts"}) == original

    game.bind_scene(ADMIN, "bind-concurrent-scene", 901)
    game.join_scene(ADMIN, "join-concurrent", 901)
    with observer.store.engine.connect() as c:
        later = game.scene(c, 901)["id"]
    observer.configure_scene(ADMIN, "notice-concurrent", later, 0, ObservationPolicy(mode="shadow"))
    observer.set_consent(ADMIN, "consent-concurrent", later, 1, consent=True)
    concurrent = app.read(ADMIN, later, "portrayal-preview", handler.token)
    assert not concurrent["state"].get("continuity")
    game.close_scene(ADMIN, "close-continuity-origin", 900)
    for viewer in (PLAYER, OTHER):
        game.join_scene(viewer, f"join-later:{viewer.user_id}", 901)
        observer.set_consent(viewer, f"consent-later:{viewer.user_id}", later, 1, consent=True)
    restarted = P2Scene(
        DirectorSessionService(
            DirectorContextService(DirectorObservationService(observer.store, synthetic=True))
        )
    )
    recalled = restarted.read(ADMIN, later, "portrayal-preview", handler.token)
    assert recalled["state"]["continuity"][0]["text"] == update["text"]
    assert recalled["context"]["references"] == []
    assert update["text"] not in str(
        restarted.read(PLAYER, later, "portrayal-preview", pilot.token)
    )
    with pytest.raises(WorkflowError, match="DOSSIER_NOT_OWNED"):
        restarted.read(OTHER, later, "portrayal-preview", handler.token)
    observer.set_consent(PLAYER, "withdraw-origin", scene, 1, consent=False)
    revoked = restarted.read(ADMIN, later, "portrayal-preview", handler.token)
    assert not (revoked["state"] or {}).get("continuity")


def test_corrected_evidence_cannot_support_drafted_or_approved_continuity(routed):
    observer, context, scene, _, _ = routed
    _, pilot = roles(observer, scene)
    app = P2Scene(DirectorSessionService(context))
    _, heard = send(
        observer,
        scene,
        "heard-term",
        "I'll bring a different cable.",
        viewer=ADMIN,
        fictional_channel="comms",
    )
    with observer.store.engine.connect() as c:
        order = len(context._references(c, scene))
    source = context.record(
        ADMIN, "cable-reference", scene, heard.source_id, order, known_by=(pilot,)
    )
    actor = pilot.model_dump(mode="json")
    update = {
        "kind": "commitment",
        "text": "I'll leave connector selection to her until she asks me.",
        "knowledge_refs": [source["id"]],
    }
    body = {"actor": actor, "version": 0, "updates": [update]}
    draft = app.write(PLAYER, "draft-provenance", scene, "portrayal-continuity", body)
    app.write(
        PLAYER,
        "confirm-provenance",
        "",
        "portrayal-confirm",
        {
            "actor": actor,
            "id": draft["id"],
        },
    )
    next_draft = app.write(
        PLAYER,
        "draft-again",
        scene,
        "portrayal-continuity",
        body
        | {
            "version": 1,
            "updates": [update | {"kind": "intention"}],
        },
    )
    send(
        observer,
        scene,
        "correct-heard-words",
        "I can't find the cable.",
        viewer=ADMIN,
        fictional_channel="comms",
        source_id=heard.source_id,
        expected_source_revision=1,
    )
    with pytest.raises(WorkflowError, match="STALE_KNOWLEDGE"):
        app.write(
            PLAYER,
            "accept-stale-provenance",
            "",
            "portrayal-confirm",
            {
                "actor": actor,
                "id": next_draft["id"],
            },
        )
    later = new_scene(observer)
    preview = app.read(PLAYER, later, "portrayal-preview", pilot.token)
    assert not (preview["state"] or {}).get("continuity")
