"""Synthetic atomic sheet exchange; files never grant game state or consent."""

import json
from dataclasses import replace

import pytest
import sqlalchemy as sa
from test_creation import selected
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import setup_game, state

from girlframe.database import tables as t
from girlframe.engine.character_documents import (
    CharacterDraftDocument,
    PortableChoices,
    encode_document,
    parse_draft,
)
from girlframe.engine.drafts import DraftInput
from girlframe.engine.npc_bonds import NpcBond
from girlframe.serialization.character_sheet_html import render_sheet
from girlframe.services.character_transfer import CharacterTransferService
from girlframe.services.creation import CreationService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

PRIVATE = "SYNTHETIC_PRIVATE_IMPORT_NOTES"


def document(notes=PRIVATE):
    source = selected("MOCKINGBIRD", "JANUS-B").model_dump(mode="json")
    source["npc_bonds"] = [
        NpcBond(
            slot=0, name="SYNTHETIC_STARTING_NPC", feelings="Owner starting context"
        ).model_dump(mode="json")
    ]
    return CharacterDraftDocument.model_validate_json(
        json.dumps(
            {
                "format": "harpyengine.character-draft",
                "schema_version": 1,
                "profile": {
                    "callsign": "SYNTH_IMPORT",
                    "girl_playbook": "MOCKINGBIRD",
                    "frame_playbook": "JANUS-B",
                    "notes": notes,
                },
                "creation": {key: source[key] for key in PortableChoices.model_fields},
            }
        )
    )


def counts(store):
    with store.engine.connect() as c:
        return {
            table.name: c.scalar(sa.select(sa.func.count()).select_from(table))
            for table in (
                t.characters,
                t.creation_drafts,
                t.events,
                t.snapshots,
                t.commands,
                t.character_sync,
            )
        }


def test_file_preview_atomic_import_retry_roundtrip_and_printable_draft(ledger):
    ledger.join(PLAYER, "transfer-join")
    service = CharacterTransferService(ledger)
    before = counts(ledger)
    preview = service.preview(PLAYER, encode_document(document()))
    assert counts(ledger) == before
    assert preview.profile_revision == preview.creation_revision == 0
    outcome = service.apply(PLAYER, "import-confirm", preview)
    after = counts(ledger)
    assert service.apply(PLAYER, "import-confirm", preview) == outcome
    assert counts(ledger) == after
    assert outcome["profile_revision"] == outcome["creation_revision"] == 1
    assert CreationService(ledger).get(PLAYER).draft.girl_assets == document().creation.girl_assets
    with ledger.engine.connect() as c:
        assert not load_state(c, ledger.campaign_id).sheets
        audits = "\n".join(c.scalars(sa.select(t.events.c.payload_json)))
        outcomes = "\n".join(c.scalars(sa.select(t.commands.c.outcome_json)))
        assert PRIVATE not in audits + outcomes
    template = service.template(PLAYER)
    assert template.profile.notes is None
    assert parse_draft(encode_document(template)) == template
    second = service.preview(PLAYER, encode_document(template))
    service.apply(PLAYER, "import-template-again", second)
    assert service.template(PLAYER, include_private=True).profile.notes == PRIVATE
    assert service.template(PLAYER).to_creation().starting_bond_id is None
    owned = service.snapshot(PLAYER, include_private=True)
    assert owned.sheet["state"] == "draft_rules_unverified"
    assert owned.sheet["private_notes"] == PRIVATE and "heat" not in owned.sheet
    assert owned.sheet["starting_setup"]["npc_bonds"][0]["name"] == "SYNTHETIC_STARTING_NPC"
    printable = render_sheet(owned)
    assert "Draft — not activated" in printable and "Still needed before activation" in printable
    assert "SYNTHETIC_STARTING_NPC" in printable
    public = service.snapshot(PLAYER, audience="public")
    assert PRIVATE not in encode_document(public).decode()
    assert "SYNTHETIC_STARTING_NPC" not in encode_document(public).decode()
    assert "assets" not in public.sheet and "identities" not in public.sheet


def test_import_failure_rolls_back_profile_creation_audit_snapshot_and_sync(ledger, monkeypatch):
    ledger.join(PLAYER, "transfer-join")
    service = CharacterTransferService(ledger)
    preview = service.preview(PLAYER, encode_document(document()))
    before = counts(ledger)
    original = service.creation._save_in_transaction

    def fail(*args, **kwargs):
        raise RuntimeError("Synthetic failure after profile/snapshot/sync staging")

    monkeypatch.setattr(service.creation, "_save_in_transaction", fail)
    with pytest.raises(RuntimeError, match="Synthetic failure"):
        service.apply(PLAYER, "atomic-import", preview)
    assert counts(ledger) == before
    monkeypatch.setattr(service.creation, "_save_in_transaction", original)
    result = service.apply(PLAYER, "atomic-import", preview)
    assert result["profile_revision"] == result["creation_revision"] == 1


def test_stale_owner_binding_revocation_and_changed_preview_do_not_overwrite(ledger):
    ledger.join(PLAYER, "transfer-join")
    ledger.join(OTHER, "other-join")
    service = CharacterTransferService(ledger)
    preview = service.preview(PLAYER, encode_document(document()))
    before = counts(ledger)
    with pytest.raises(WorkflowError, match="another owner"):
        service.apply(OTHER, "foreign-import", preview)
    with pytest.raises(WorkflowError, match="IMPORT_CHANGED"):
        service.apply(PLAYER, "changed-import", replace(preview, digest="wrong"))
    assert counts(ledger) == before
    ledger.save_draft(
        PLAYER,
        "newer-profile",
        0,
        DraftInput(callsign="KEEP_NEWER", girl_playbook="MOCKINGBIRD", frame_playbook="JANUS-B"),
    )
    newer = counts(ledger)
    with pytest.raises(WorkflowError, match="STALE_IMPORT"):
        service.apply(PLAYER, "stale-import", preview)
    assert counts(ledger) == newer
    current = service.preview(PLAYER, encode_document(document()))
    with ledger.engine.begin() as c:
        c.execute(
            t.members.update()
            .where(
                t.members.c.campaign_id == ledger.campaign_id,
                t.members.c.user_id == str(PLAYER.user_id),
            )
            .values(active=False)
        )
    with pytest.raises(WorkflowError):
        service.apply(PLAYER, "revoked-import", current)
    wrong = GuildViewer(PLAYER.user_id, 201, True, False)
    with pytest.raises(WorkflowError):
        service.preview(wrong, encode_document(document()))


def test_active_snapshot_public_owner_projection_and_active_import_protection(ledger):
    game, _, _, _ = setup_game(ledger)
    with ledger.transaction() as c:
        prior = state(game)
        prior.sheets["2"].heat = 3
        prior.sheets["2"].permissions = 2
        prior.sheets["2"].public_fields = ()
        prior.sheets["2"].assets[0].description = PRIVATE
        game.event(c, 1, "synthetic.export-facts", "synthetic.export-facts", prior)
    service = CharacterTransferService(ledger)
    public = service.snapshot(PLAYER, audience="public")
    assert (
        not {"heat", "permissions", "assets", "identities", "bonds", "private_notes"}
        & public.sheet.keys()
    )
    assert PRIVATE not in encode_document(public).decode()
    owner = service.snapshot(PLAYER)
    assert owner.sheet["heat"] == 3 and owner.sheet["permissions"] == 2
    assert owner.sheet["assets"][0]["description"] == PRIVATE
    assert owner.sheet["bonds"][0]["counterpart_id"] == str(OTHER.user_id)
    with pytest.raises(WorkflowError, match="actual owner"):
        service.snapshot(OTHER, owner=PLAYER.user_id, audience="owner")
    before = counts(ledger)
    with pytest.raises(WorkflowError, match="ACTIVE_CHARACTER"):
        service.preview(PLAYER, encode_document(document()))
    assert counts(ledger) == before
