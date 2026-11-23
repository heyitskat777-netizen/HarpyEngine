"""Approved artwork from the GIRLFRAME review sheets."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "artwork"
CATALOG = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8"))
ARTWORK = {entry["id"]: entry for entry in CATALOG}
KINDS = {"scene", "pilot", "frame"}

if len(ARTWORK) != len(CATALOG) or any(
    not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", key)
    or entry["kind"] not in KINDS
    or entry["src"] != f"./artwork/{key}.webp"
    or not (ROOT / f"{key}.webp").is_file()
    for key, entry in ARTWORK.items()
):
    raise ValueError("Invalid Activity artwork catalog.")


def validate_selection(kind, selection):
    if selection is None:
        return
    if not isinstance(selection, str) or ARTWORK.get(selection, {}).get("kind") != kind:
        raise ValueError("Select artwork from the corresponding catalog.")


def frame_subject(character_id, playbook, runtime_id):
    return f"{character_id}:{runtime_id or playbook}"


def artwork_bytes(art_id):
    return (ROOT / f"{art_id}.webp").read_bytes()
