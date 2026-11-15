"""Escaped printable views of an already-authorized sheet projection."""

from html import escape
from typing import Any

from girlframe.engine.character_documents import CharacterSheetDocument
from girlframe.engine.creation_details import DESIRES, MAXIMS, STANDARDS
from girlframe.engine.npc_bonds import NPC_ROLES


def _text(value: Any) -> str:
    return escape(str(value), quote=True)


def _rows(title: str, entries: list[str]) -> str:
    if not entries:
        return ""
    return (
        "<section><h2>"
        + _text(title)
        + "</h2><ul>"
        + "".join("<li>" + value + "</li>" for value in entries)
        + "</ul></section>"
    )


def _entries(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def render_sheet(document: CharacterSheetDocument) -> str:
    """Never adds missing/private fields; public filtering belongs to the service.

    Render known display sections rather than dumping arbitrary internal JSON.
    Discord IDs remain wire metadata and are not used as display-name fallbacks.
    """
    sheet = document.sheet
    name = sheet.get("callsign") or document.display_name or "Unnamed character"
    owner = document.display_name or document.members.get(document.owner_id, "Unavailable member")
    state_label = {
        "draft_rules_unverified": "Draft — not activated",
        "active_m2_subset": "Active character",
    }.get(str(sheet.get("state", "")), "Read-only snapshot")
    parts = [
        "<header><p>HarpyEngine · "
        + _text(document.audience)
        + " sheet · v"
        + _text(document.engine_version)
        + "</p><h1>"
        + _text(name)
        + "</h1><p>Player: "
        + _text(owner)
        + "</p><p>"
        + _text(sheet.get("girl_playbook", sheet.get("girl", "Unspecified Girl")))
        + " / "
        + _text(sheet.get("frame_playbook", sheet.get("frame", "Unspecified Frame")))
        + "</p><p>State: "
        + _text(state_label)
        + "</p></header>",
    ]
    resources = []
    for key, label in (
        ("rank", "Status"),
        ("heat", "Heat"),
        ("permissions", "Permissions"),
        ("obsolescence_marked", "Obsolescence"),
        ("medical_state", "Medical state"),
        ("frame_scrapped", "Frame scrapped"),
        ("status_marked", "Status marked"),
    ):
        if key in sheet:
            resources.append("<strong>" + label + ":</strong> " + _text(sheet[key]))
    parts.append(_rows("Resources", resources))
    appearance = []
    for key, label in (
        ("appearance", "Girl"),
        ("girl_appearance", "Girl"),
        ("frame_name", "Frame name"),
        ("frame_appearance", "Frame"),
    ):
        if sheet.get(key):
            appearance.append("<strong>" + label + ":</strong> " + _text(sheet[key]))
    parts.append(_rows("Appearance", appearance))
    identities = []
    for item in _entries(sheet.get("identities")):
        if isinstance(item, dict):
            identities.append(
                ("☑ " if item.get("marked") else "☐ ") + _text(item.get("name", "Identity"))
            )
        else:
            identities.append(_text(item))
    parts.append(_rows("Identities", identities))
    assets = []
    for item in _entries(sheet.get("assets")):
        if isinstance(item, dict):
            flags = [
                label
                for key, label in (("damaged", "damaged"), ("void", "Void-altered"))
                if item.get(key)
            ]
            assets.append(
                "<strong>"
                + _text(item.get("name", "Asset"))
                + "</strong>"
                + (" (" + ", ".join(flags) + ")" if flags else "")
                + (": " + _text(item["description"]) if item.get("description") else "")
            )
        else:
            assets.append(_text(item))
    parts.append(_rows("Assets", assets))
    bonds = []
    for item in _entries(sheet.get("bonds")):
        if not isinstance(item, dict):
            continue
        counterpart = str(item.get("counterpart_id", item.get("counterpart", "")))
        label = document.members.get(counterpart, "Unavailable member")
        if item.get("role") in ("handler", "pilot"):
            label += " (" + str(item["role"]).capitalize() + ")"
        bonds.append(
            "<strong>"
            + _text(item.get("depth", "Bond"))
            + " — "
            + _text(label)
            + "</strong>"
            + (": " + _text(item["context"]) if item.get("context") else "")
        )
    parts.append(_rows("Bonds", bonds))
    setup = sheet.get("starting_setup", {})
    if isinstance(setup, dict):
        npc_rows = []
        book = setup.get("girl_playbook", "")
        roles = NPC_ROLES.get(book, ()) if isinstance(book, str) else ()
        for npc in _entries(setup.get("npc_bonds")):
            if not isinstance(npc, dict):
                continue
            slot = npc.get("slot")
            role = roles[slot] if type(slot) is int and 0 <= slot < len(roles) else "NPC"
            npc_rows.append(
                "<strong>"
                + _text(npc.get("name") or role)
                + "</strong> ("
                + _text(role)
                + "): "
                + _text(npc.get("feelings", ""))
            )
        parts.append(_rows("Starting NPC context — not current world Bond depth", npc_rows))
        details_rows = []
        if setup.get("dna_basis"):
            details_rows.append("DNA basis: " + _text(setup["dna_basis"]))
        details = setup.get("girl_details")
        if isinstance(details, dict):
            standard = details.get("own_standard")
            if isinstance(standard, dict):
                slot = standard.get("slot")
                if type(slot) is int and 0 <= slot < len(STANDARDS):
                    label = standard.get("custom", "") if slot == 9 else STANDARDS[slot]
                    details_rows.append("Own standard: " + _text(label))
            for index in _entries(details.get("maxims")):
                if type(index) is int and 0 <= index < len(MAXIMS):
                    details_rows.append("Maxim: " + _text(MAXIMS[index]))
            for investor in _entries(details.get("investors")):
                if isinstance(investor, dict):
                    selection = investor.get("desires", {})
                    slots = selection.get("slots", []) if isinstance(selection, dict) else []
                    labels = [DESIRES[x] for x in slots if type(x) is int and 0 <= x < len(DESIRES)]
                    details_rows.append(
                        "NPC investor starting desires: " + _text(", ".join(labels))
                    )
        fanbase = setup.get("fanbase")
        if isinstance(fanbase, dict):
            for key in ("demographics", "demanded", "rejected"):
                if fanbase.get(key):
                    labels = [
                        fanbase.get("custom_demographic", "")
                        if key == "demographics" and x == "custom:1"
                        else fanbase.get("custom_quality_" + str(x)[-1], "")
                        if x in ("custom:1", "custom:2")
                        else str(x)
                        for x in _entries(fanbase[key])
                    ]
                    details_rows.append("Fanbase " + key + ": " + _text(", ".join(labels)))
        parts.append(_rows("Starting playbook choices — reference only", details_rows))
    if sheet.get("creation_requirements"):
        parts.append(
            _rows(
                "Still needed before activation",
                [_text(value) for value in _entries(sheet["creation_requirements"])],
            )
        )
    tags = []
    for item in _entries(sheet.get("tags")):
        tags.append(
            _text(item.get("label", item.get("name", "Tag")))
            if isinstance(item, dict)
            else _text(item)
        )
    parts.append(_rows("Tags", tags))
    if document.audience == "owner" and sheet.get("private_notes"):
        parts.append(_rows("Private notes", [_text(sheet["private_notes"])]))
    parts.append(
        "<footer>Read-only snapshot · "
        + _text(document.rules_status)
        + " · revision "
        + _text(document.revision)
        + ". Importing this view does not grant gameplay state or consent.</footer>"
    )
    return (
        """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HarpyEngine character sheet</title><style>
*{box-sizing:border-box}body{font:16px/1.5 system-ui,sans-serif;color:#242638;
background:#e9e9f0;max-width:960px;margin:2rem auto;padding:1.5rem}
header,section{background:white;padding:1rem 1.4rem;margin-bottom:1rem;border:1px solid #c8c6df}
h1{margin:.3rem 0;font-size:2rem}h2{font-size:1.15rem;color:#514980}
ul{padding-left:1.4rem}li{white-space:pre-wrap;overflow-wrap:anywhere;margin:.35rem 0}
footer{font-size:.8rem;color:#555}@media print{body{background:white;margin:0;max-width:none}
header,section{break-inside:avoid}footer{margin-top:1rem}}
</style></head><body>"""
        + "".join(parts)
        + "</body></html>"
    )
