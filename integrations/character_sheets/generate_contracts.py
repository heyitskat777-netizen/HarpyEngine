"""Regenerate public portable contracts; no campaign, PDF or credential access."""

import hashlib
import json
from pathlib import Path

from girlframe.engine.character_documents import (
    CharacterDraftDocument,
    CharacterSheetDocument,
    PortableChoices,
    PortableProfile,
    encode_document,
)
from girlframe.engine.creation import AssetChoice
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.creation_details import BODY_PARTS, DESIRES, MAXIMS, STANDARDS
from girlframe.engine.fanbase import DEMOGRAPHICS, QUALITIES
from girlframe.engine.npc_bonds import NPC_ROLES, NpcBond
from girlframe.engine.playbooks import FRAME_TYPES, GIRL_TYPES
from girlframe.serialization.character_sheet_html import render_sheet


def generate(destination: Path) -> None:
    for name, model in (
        ("character-draft-v1.schema.json", CharacterDraftDocument),
        ("character-sheet-v1.schema.json", CharacterSheetDocument),
    ):
        schema = model.model_json_schema()
        schema["required"] = sorted(set(schema.get("required", ())) | {"format", "schema_version"})
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = "urn:harpyengine:" + name.removesuffix(".schema.json")
        (destination / name).write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    catalog = {
        "format": "harpyengine.creation-catalog",
        "schema_version": 1,
        "rules_status": "RULES_SUBSET",
        "campaign_defaults_require_engine": True,
        "girl_types": GIRL_TYPES,
        "frame_types": FRAME_TYPES,
        "frame_rules_aliases": {"JANUS-B": "JANUS"},
        "playbooks": CATALOG,
        "npc_roles": NPC_ROLES,
        "standards": STANDARDS,
        "maxims": MAXIMS,
        "investor_desires": DESIRES,
        "body_parts": BODY_PARTS,
        "fanbase": {"demographics": DEMOGRAPHICS, "qualities": QUALITIES},
    }
    canonical = json.dumps(catalog, sort_keys=True, separators=(",", ":")).encode()
    catalog["catalog_sha256"] = hashlib.sha256(canonical).hexdigest()
    (destination / "creation-catalog-v1.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    girl_assets = tuple(
        AssetChoice(name=x, description="Synthetic example description")
        for x in CATALOG["MOCKINGBIRD"]["assets"][:2]
    )
    frame_assets = tuple(
        AssetChoice(name=x, description="Synthetic example description")
        for x in CATALOG["JANUS"]["assets"][:2]
    )
    example = CharacterDraftDocument(
        profile=PortableProfile(
            callsign="SYNTHETIC_DEMO", girl_playbook="MOCKINGBIRD", frame_playbook="JANUS-B"
        ),
        creation=PortableChoices(
            girl_assets=girl_assets,
            frame_assets=frame_assets,
            void_asset=girl_assets[0].name,
            girl_appearance="Synthetic appearance",
            frame_name="Synthetic Frame",
            frame_appearance="Synthetic Frame appearance",
            npc_bonds=(
                NpcBond(slot=0, name="Synthetic NPC A", feelings="Synthetic relationship"),
                NpcBond(slot=1, name="Synthetic NPC B", feelings="Synthetic relationship"),
            ),
        ),
    )
    (destination / "example-mockingbird-janus-b.json").write_bytes(encode_document(example))
    owner, peer = "100000000000000001", "100000000000000002"
    sheet = CharacterSheetDocument(
        engine_version="synthetic-example",
        audience="owner",
        owner_id=owner,
        revision=0,
        display_name="Synthetic Pilot",
        members={peer: "Synthetic partner"},
        sheet={
            "callsign": example.profile.callsign,
            "girl_playbook": "MOCKINGBIRD",
            "frame_playbook": "JANUS-B",
            "heat": 0,
            "permissions": 0,
            "girl_appearance": example.creation.girl_appearance,
            "frame_name": example.creation.frame_name,
            "frame_appearance": example.creation.frame_appearance,
            "identities": [
                {"name": name, "marked": False} for name in CATALOG["MOCKINGBIRD"]["identities"]
            ],
            "assets": [
                {
                    "name": choice.name,
                    "description": choice.description,
                    "family": family,
                    "damaged": False,
                }
                for family, choices in (("girl", girl_assets), ("frame", frame_assets))
                for choice in choices
            ],
            "bonds": [
                {
                    "counterpart_id": peer,
                    "depth": "Personal",
                    "context": "Synthetic display example; grants no live agreement.",
                }
            ],
            "private_notes": "Synthetic sample only. No live state or consent is imported.",
        },
    )
    (destination / "example-read-only-sheet.json").write_bytes(encode_document(sheet))
    (destination / "example-printable-sheet.html").write_text(render_sheet(sheet))


if __name__ == "__main__":
    generate(Path(__file__).resolve().parent)
