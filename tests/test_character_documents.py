"""Portable starting choices stay distinct from authority and display snapshots."""

import json

import pytest

from girlframe.engine.character_documents import (
    MAX_DOCUMENT_BYTES,
    CharacterSheetDocument,
    DocumentError,
    encode_document,
    parse_draft,
)
from girlframe.serialization.character_sheet_html import render_sheet


def document():
    return {
        "format": "harpyengine.character-draft",
        "schema_version": 1,
        "profile": {
            "callsign": "SYNTHETIC ☃",
            "girl_playbook": "Mockingbird",
            "frame_playbook": "JANUS",
        },
        "creation": {
            "girl_assets": [
                {"name": "Adaptive Restraints", "description": "Player text: 雪 & <tag>"}
            ],
            "girl_appearance": "An incomplete draft can still be exchanged.",
        },
    }


def test_creation_json_roundtrip_preserves_owner_text_and_omitted_private_notes():
    parsed = parse_draft(json.dumps(document(), ensure_ascii=False).encode())
    assert parsed.profile.girl_playbook == "MOCKINGBIRD"
    assert parsed.profile.as_profile("PRIVATE_EXISTING").notes == "PRIVATE_EXISTING"
    assert parsed.creation.girl_assets[0].description == "Player text: 雪 & <tag>"
    assert parse_draft(encode_document(parsed)) == parsed
    draft = parsed.to_creation(shared_tokens=("actual-server-context",))
    assert draft.shared_tokens == ("actual-server-context",) and draft.missing()
    assert draft.starting_bond_id is None and draft.additional_starting_bond_id is None
    clearing = document()
    clearing["profile"]["notes"] = ""
    assert (
        parse_draft(json.dumps(clearing).encode()).profile.as_profile("PRIVATE_EXISTING").notes
        == ""
    )


def test_untrusted_import_rejects_authority_duplicate_nonfinite_and_snapshot_formats_safely():
    canary = "PRIVATE_UPLOADED_CANARY_DO_NOT_ECHO"
    wrong_asset = document()
    wrong_asset["creation"]["girl_assets"] = [{"name": canary}]
    authority = document() | {"owner": canary}
    token = document()
    token["creation"]["starting_bond_id"] = canary
    bad_version = document() | {"schema_version": 2}
    inputs = [json.dumps(x).encode() for x in (wrong_asset, authority, token, bad_version)] + [
        b'{"format":"harpyengine.character-draft","format":"ignored"}',
        b'{"format":"harpyengine.character-draft","schema_version":NaN}',
        b'{"format":"harpyengine.character-sheet","schema_version":1}',
        b" " * (MAX_DOCUMENT_BYTES + 1),
    ]
    for raw in inputs:
        with pytest.raises(DocumentError) as caught:
            parse_draft(raw)
        assert canary not in str(caught.value)


def test_printable_snapshot_escapes_known_sections_and_resolves_names_without_id_fallback():
    owner, peer = "100000000000000001", "100000000000000002"
    private = "PRIVATE_NOTE <script>alert('x')</script>"
    snapshot = CharacterSheetDocument(
        engine_version="test",
        audience="owner",
        owner_id=owner,
        revision=3,
        display_name="Current nickname <&>",
        members={peer: "Current partner <img>"},
        sheet={
            "callsign": "<svg onload=alert(1)>",
            "girl": "MOCKINGBIRD",
            "frame": "JANUS",
            "heat": 2,
            "private_notes": private,
            "identities": [{"name": "<Identity>", "marked": True}],
            "assets": [{"name": "<Asset>", "description": "Full text\n雪", "damaged": True}],
            "bonds": [
                {"counterpart_id": peer, "depth": "Personal", "context": "<context>"},
                {"counterpart_id": "100000000000000003", "depth": "Personal"},
            ],
            "unrendered_engine_history": "HIDDEN_INTERNAL_CANARY",
        },
    )
    rendered = render_sheet(snapshot)
    assert "<script>" not in rendered and "<svg onload" not in rendered and "<img>" not in rendered
    assert "&lt;script&gt;" in rendered and "Full text\n雪" in rendered
    assert "Current partner &lt;img&gt;" in rendered and "Unavailable member" in rendered
    assert owner not in rendered and peer not in rendered and "100000000000000003" not in rendered
    assert "HIDDEN_INTERNAL_CANARY" not in rendered
    public = snapshot.model_copy(update={"audience": "public", "sheet": {"callsign": "Shared"}})
    assert "PRIVATE_NOTE" not in render_sheet(public) and "<script>" not in render_sheet(public)
    with pytest.raises(DocumentError):
        parse_draft(encode_document(snapshot))
