"""Published creation labels."""

import json
from typing import Any

# The previous deployment emitted a suffixed label. Only saved/imported
# selections need translation; the catalog and all output use the printed name.
_RETIRED_FRAME_LABEL = "JANUS" + "-B"

GIRL_TYPES: dict[str, str] = {
    "PRINCESS": "Princess",
    "MOCKINGBIRD": "Mockingbird",
    "STIM-BLISSED": "Stim-Blissed",
    "NEWGIRL": "Newgirl",
    "CASUALTY": "Casualty",
    "OLDGEN": "Oldgen",
    "VATGROWN": "Vatgrown",
    "ALPHA": "Alpha",
    "AM": "AM (Artificial Mind)",
    "BONDED": "Bonded",
}
FRAME_TYPES: dict[str, str] = {
    "THE PRINCE": "The Prince",
    "CONSUME": "CONSUME",
    "JANUS": "JANUS",
    "DOCTORDOCTOR MK. II": "DoctorDoctor Mk. II",
    "WYVERN 0.4": "Wyvern 0.4",
    "THE ENFORCER": "The Enforcer",
    "CHANGELING": "CHANGELING",
    "PROJECT ANKOU": "Project Ankou",
    "THE RED QUEEN": "The Red Queen",
}


def canonical_girl(value: str) -> str:
    key = value.strip().upper()
    if key == "AM (ARTIFICIAL MIND)":
        key = "AM"
    if key not in GIRL_TYPES:
        raise ValueError("Select a listed Girl type")
    return key


def canonical_frame(value: str) -> str:
    key = normalize_frame_name(value.strip().upper())
    if key not in FRAME_TYPES:
        raise ValueError("Select a listed Frame type")
    return key


def normalize_frame_name(value: str) -> str:
    return "JANUS" if value == _RETIRED_FRAME_LABEL else value


def normalize_frame_fields(value: Any) -> Any:
    """Translate structured Frame fields in persisted projections, leaving prose alone."""
    if isinstance(value, dict):
        return {
            key: normalize_frame_name(item)
            if isinstance(key, str)
            and isinstance(item, str)
            and (key in {"frame", "frame_playbook"} or key.endswith("_frame"))
            else normalize_frame_fields(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [normalize_frame_fields(item) for item in value]
    return value


def normalize_saved_frame_json(data: str | bytes | bytearray) -> str | bytes | bytearray:
    """Keep strict JSON validation in the state reader and fast-path current data."""
    if isinstance(data, str):
        contains_old_name = _RETIRED_FRAME_LABEL in data
    else:
        contains_old_name = _RETIRED_FRAME_LABEL.encode() in data
    if not contains_old_name:
        return data
    try:
        return json.dumps(normalize_frame_fields(json.loads(data)))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return data  # The typed reader reports invalid JSON.
