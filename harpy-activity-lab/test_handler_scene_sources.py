"""Synthetic Handler source forms, with the original native filing and audience."""

import json
from types import SimpleNamespace

import pytest
from girlframe.engine import m3_tracker_implants
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_advancements import awards
from girlframe.engine.m3_handler_ordinary import RULE as ORDINARY
from girlframe.services.m2_game import GameService
from girlframe.services.m3_access import load_registry
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_tracker_implants import TrackerService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import FacilitatorService
from handler_award_scenario import ordinary_pr_award
from test_cast_service import change
from test_contaminant_zone import acquire, quarantine_native
from test_contaminant_zone import setup as zone_setup
from test_doctor_npc_nanobot import roll_nanobot
from test_doctor_npc_nanobot import setup as legacy_doctor
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state, tick
from test_strain_service import D6
from test_tracker_implants import native_acquire

import mission_lab  # noqa: F401
from ai_native_plays import ActivityNativePlays
from handler_playbook import HandlerPlaybook
from native_scene_forms import HANDLER_WARP, TRACKER_MOMENT
from off_duty_followups import OffDutyFollowups
from specialist_scene import SpecialistScene
from test_identity_specialists import option, popup, respond, scoped

ledger = ledger_fixture
CHANNEL = 900
ROOM = ("relay", "Relay")


def join_handler(ledger, game):
    handler = current_ref(state(game), ADMIN.user_id)
    change(CastService(ActorService(MissionService(ledger))), ADMIN, "join", handler)
    return handler


def book_for(game):
    return HandlerPlaybook(game.store, load_registry(), OffDutyFollowups(game).periods)


def options(game, handler):
    setup = SimpleNamespace(
        game=game, handler=ADMIN, play_registry=load_registry(), handler_playbook=book_for(game),
        handler_rooms=lambda: {CHANNEL: ROOM},
    )
    with game.store.engine.connect() as connection:
        return ActivityNativePlays(setup, None)(
            connection, game.scene(connection, CHANNEL), handler,
        )


def action(form, operation, values):
    return form[0] | {"answer": {"operation": operation, "values": values}}


def effect(book, key, grant, play, fields, *, viewer=ADMIN):
    return book.perform(viewer, key, "handler-play-submit", {
        "id": grant["id"], "revision": grant["game_revision"], "play": play,
        "account": "I carry out the actual original effect.", "detail": "", "stakes": "",
        "fields": fields,
    })


def test_tracker_form_reopens_original_grant_and_keeps_moment_private(ledger, tmp_path, monkeypatch):
    game, _, _ = ordinary_pr_award(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ORDINARY, m3_tracker_implants.RULE))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(update={
        "m3_approval": approval.model_copy(update={"subsystems": approval.subsystems | {"world", "plays"}}),
    })
    handler = join_handler(ledger, game)
    tracker = TrackerService(ledger)
    held = next(row for row in awards(state(game)) if row.phase == "held")
    native_acquire(tracker, game, held)
    original = m3_tracker_implants.acquisitions(state(game))[0]
    implant = original.implants[0]
    tracker.record_initial_presence(
        ADMIN, "real-handler-position", original.id, state(game).revision, implant.id,
        "My body is initially present here.",
    )
    native = SpecialistScene(game, CHANNEL)
    intercept, voyeur = "handler_tracker_intercept", "handler_tracker_voyeur"
    assert intercept in {row["id"] for row in options(game, handler)}
    assert voyeur not in {row["id"] for row in options(game, handler)}
    for viewer in (PLAYER, OTHER):
        assert TRACKER_MOMENT in {row["id"] for row in native.view(viewer, ROOM)}
        assert {intercept, voyeur}.isdisjoint(row["id"] for row in native.view(viewer, ROOM))
    moment = "PRIVATE_MOMENT_I mend my old radio."
    form = popup(native, PLAYER, TRACKER_MOMENT)
    native.perform(PLAYER, "own-moment", action(form, TRACKER_MOMENT, {"context": moment}))
    for play in (intercept, voyeur):
        form = popup(native, ADMIN, play)
        sources = form[1]["fields"][0]["options"]
        source = next(value for value, _ in sources if json.loads(value)[0] == implant.id)
        payload = action(form, play, {"source": source})
        with pytest.raises(WorkflowError):
            native.perform(OTHER, "foreign-" + play, payload)
        prepared = native.perform(ADMIN, "prepare-" + play, payload)
        ledger.engine.dispose()
        fresh = GameService(ledger)
        offer = options(fresh, handler)
        assert any(row["destination"] == "handler_effect" and row["control"] == prepared["id"]
                   for row in offer)
        book = book_for(fresh)
        first = effect(book, play, prepared, prepared["handler_effect"], {"target": implant.actor.token})
        assert effect(book, play, prepared, prepared["handler_effect"], {"target": implant.actor.token}) == first
        assert native.perform(ADMIN, "prepare-" + play, payload) == prepared
    book = book_for(fresh)
    assert book.service.notice(ADMIN, prepared["id"])["detail"] == moment
    for viewer in (PLAYER, OTHER):
        assert moment not in json.dumps(book.notices(viewer))


def test_zone_warp_prepares_native_scene_effect_and_rejects_a_foreign_cell(ledger, tmp_path, monkeypatch):
    game, control, _, _ = zone_setup(ledger, tmp_path, monkeypatch)
    handler = join_handler(ledger, game)
    strain = StrainService(OffDutyService(MissionService(ledger)), dice=D6(1))
    strain.configure(ADMIN, "actual-strain", state(game).revision, "business_as_usual", frozenset())
    original = acquire(control, game)
    zone = quarantine_native(control, original.id)
    native = SpecialistScene(game, CHANNEL)
    form = popup(native, ADMIN, HANDLER_WARP)
    assert option(form, "zone") == zone.id
    assert HANDLER_WARP in {row["id"] for row in options(game, handler)}
    assert HANDLER_WARP not in {row["id"] for row in native.view(PLAYER, ROOM)}
    payload = action(form, HANDLER_WARP, {"zone": zone.id})
    with pytest.raises(WorkflowError):
        native.perform(PLAYER, "wrong-warp-owner", payload)
    prepared = native.perform(ADMIN, "prepare-warp", payload)
    ledger.engine.dispose()
    fresh = GameService(ledger)
    assert any(row["destination"] == "handler_effect" and row["control"] == prepared["id"]
               for row in options(fresh, handler))
    book = book_for(fresh)
    play = prepared["handler_effect"]
    fields = {"cell": "9,9", "feature": "Boundary", "description": "The ground forms a spiral."}
    with pytest.raises(WorkflowError):
        effect(book, "foreign-warp-cell", prepared, play, fields)
    fields["cell"] = "0,0"
    saved = effect(book, "actual-warp", prepared, play, fields)
    assert effect(book, "actual-warp", prepared, play, fields) == saved
    assert book.service.get(ADMIN, prepared["id"])["grant"]["state"] == "complete"
    assert native.perform(ADMIN, "prepare-warp", payload) == prepared


def test_missing_npc_resource_only_goes_to_facilitator_after_owner_files_it(ledger, tmp_path, monkeypatch):
    game, worker, gateway, patient, _ = legacy_doctor(ledger, tmp_path, monkeypatch)
    review = FacilitatorService(game)
    review.configure(ADMIN, "actual-facilitator", "user", OTHER.user_id)
    game.dice.faces = (6, 6)
    action = roll_nanobot(game, patient, 1, worker=worker, gateway=gateway)
    tick(worker, gateway, 3)
    saved = game.inspect(PLAYER, action)["receipt"]
    assigned = scoped(game, ADMIN, "doctor_patient")
    assert assigned[1]["action"] == "native_choice_review"
    assert review.tasks(ADMIN) == []
    with pytest.raises(WorkflowError):
        respond(assigned, OTHER, "doctor_patient", {})
    filed = respond(assigned, ADMIN, "doctor_patient", {}, key="actual-blocked-referral")
    ledger.engine.dispose()
    fresh = GameService(ledger, dice=game.dice)
    request = FacilitatorService(fresh).view(OTHER, filed["review_id"])["request"]
    assert request["source"] == action and request["rule"] == "choice:doctor_patient"
    assert request["mandatory"] and request["status"] == "awaiting_ruling"
    assert respond(assigned, ADMIN, "doctor_patient", {}, key="actual-blocked-referral") == filed
    assert fresh.inspect(PLAYER, action)["state"] != "complete"
    assert fresh.inspect(PLAYER, action)["receipt"] == saved and game.dice.calls == 1
    assert patient.entity not in state(fresh).sheets
