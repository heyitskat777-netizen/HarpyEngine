"""Authoritative controls, scoped specialist admission and owned archived reset."""

import pytest
import sqlalchemy as sa
from test_career_service import draft
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_service import service

from girlframe.database import tables as t
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_access import Access, digest
from girlframe.services.m3_careers import CareerService
from girlframe.services.m3_mission_control import MissionControlService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.player_reset import awaiting_replacement, purge_sheet

ledger = ledger_fixture


def test_mission_controls_share_dispatch_blockers_are_private_and_never_write(ledger):
    missions, game = service(ledger)
    controls = MissionControlService(missions)
    assert controls.view(ADMIN)["desk"]["can_offer"]
    first = missions.offer(ADMIN, "first-offer", "SYNTHETIC_OBJECTIVE", (2, 3))
    row = controls.view(ADMIN)["offers"][0]
    assert row["actions"] == ["cancel"] and row["blocked"]["dispatch"]
    pilot = controls.view(PLAYER)
    assert pilot["desk"] is None and "actions" not in pilot["offers"][0]
    assert "blocked" not in pilot["offers"][0]
    yes = missions.respond(PLAYER, "yes-2", first["id"], 1, "accept")
    yes = missions.respond(OTHER, "yes-3", first["id"], yes["revision"], "accept")
    with ledger.engine.connect() as c:
        before = c.scalar(sa.select(sa.func.count()).select_from(t.events))
    row = controls.view(ADMIN)["offers"][0]
    assert row["actions"] == ["cancel", "dispatch"]
    assert row["revision"] == yes["revision"]
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(t.events)) == before
    missions.start(ADMIN, "first-dispatch", first["id"], yes["revision"])
    second = missions.offer(ADMIN, "second-offer", "OVERLAPPING_OBJECTIVE", (2,))
    accepted = missions.respond(PLAYER, "second-yes", second["id"], 1, "accept")
    row = next(x for x in controls.view(ADMIN)["offers"] if x["id"] == second["id"])
    assert "dispatch" not in row["actions"]
    assert "unfinished mission" in row["blocked"]["dispatch"]
    with pytest.raises(WorkflowError, match="unfinished mission"):
        missions.start(ADMIN, "blocked-dispatch", second["id"], accepted["revision"])
    ledger.policy = ledger.policy.model_copy(update={"m3_approval": None})
    reopened = controls.view(ADMIN)
    assert all(not x["actions"] for x in reopened["offers"])
    assert not reopened["desk"]["can_begin_off_duty"]
    assert not reopened["desk"]["can_offer"]
    assert state(game).sheets["2"].permissions == 0


def test_specialist_scope_is_default_empty_exact_and_digest_bound(ledger):
    missions, _ = service(ledger)
    registry = missions.access.registry
    rule = "frame.changeling.blank-slate"
    original = registry.model_dump_json()
    access = Access(ledger, registry)
    assert not access.activity_specialist_enabled(rule)
    approval = ledger.policy.m3_approval
    assert "activity_specialist_rules" not in approval.model_dump(mode="json")
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={
                    "subsystems": approval.subsystems | {"plays"},
                    "activity_specialist_rules": frozenset({rule}),
                }
            )
        }
    )
    access.require_specialist_rule(rule)
    assert not access.activity_specialist_enabled("frame.changeling.fingers-in-the-brain")
    assert registry.model_dump_json() == original and not registry.entry(rule).verified
    assert ledger.policy.m3_approval.registry_sha256 == digest(registry)
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={"registry_sha256": "0" * 64}
            )
        }
    )
    assert not access.activity_specialist_enabled(rule)
    with pytest.raises(ValueError):
        access.require_specialist_rule(rule)


def test_owner_reset_preserves_original_receipts_and_starts_clean_replacement(ledger):
    _, game = service(ledger)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"playbooks"}}
            )
        }
    )
    original = current_ref(state(game), PLAYER.user_id)
    sheet = state(game).sheets["2"]
    payload = dict(
        callsign=sheet.callsign,
        confirmed=True,
        character=sheet.character_id,
        revision=sheet.revision,
    )
    receipt = ledger.roll_basic(PLAYER, "original-receipt", ledger.status(PLAYER)["revision"])
    with pytest.raises(ValueError, match="Approve"):
        purge_sheet(game, PLAYER, "unconfirmed-reset", payload | {"confirmed": False})
    for index, (actor, invalid) in enumerate(
        (
            (OTHER, payload),
            (ADMIN, payload),
            (PLAYER, payload | {"callsign": "WRONG"}),
            (PLAYER, payload | {"revision": sheet.revision + 1}),
        )
    ):
        with pytest.raises(WorkflowError):
            purge_sheet(game, actor, "invalid-reset-" + str(index), invalid)
    reset = purge_sheet(game, PLAYER, "owner-reset", payload)
    assert purge_sheet(game, PLAYER, "owner-reset", payload) == reset
    assert "2" not in state(game).sheets
    archive = awaiting_replacement(state(game), PLAYER.user_id)
    assert archive is not None and archive.actor == original
    assert archive.id == reset["archive_id"] and archive.ending == "player_reset"
    ledger.engine.dispose()
    careers = CareerService(ledger)
    preview = careers.get(PLAYER, archive.id)
    new = careers.begin_replacement(
        PLAYER, "new-character", archive.id, preview["game_revision"], draft()
    )
    assert new["character"] != original.incarnation
    assert ledger.get_roll_receipt(PLAYER, receipt.id).id == receipt.id
    from girlframe.services.creation import CreationService

    creation = CreationService(ledger).get(PLAYER)
    assert not creation.draft.girl_assets and not creation.draft.frame_assets
    assert careers.get(PLAYER, archive.id)["sheet"]["callsign"] == sheet.callsign
