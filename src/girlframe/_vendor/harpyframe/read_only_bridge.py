"""Adapted from supplied HarpyFrame v1.3.10 integrations/read_only_bridge.py.

See docs/ENGINE_SOURCE_INVENTORY.md for provenance and changes. This bridge is
not authorization, a bot, or rules certification. It never writes or executes code.
"""

import json
from pathlib import Path

MAX_SNAPSHOT_BYTES = 4 * 1024 * 1024


def load_public_status(path: str | Path) -> dict[str, int | bool]:
    """Project two validated fields, with a bounded read of the source snapshot."""
    with Path(path).open("rb") as source:
        data = source.read(MAX_SNAPSHOT_BYTES + 1)
    if len(data) > MAX_SNAPSHOT_BYTES:
        raise ValueError("Campaign snapshot exceeds size limit")
    state = json.loads(data.decode("utf-8"))
    if not isinstance(state, dict):
        raise ValueError("Campaign state must be a JSON object")
    turn = state.get("turn")
    paused = state.get("paused")
    if type(turn) is not int or turn < 0:
        raise ValueError("Campaign turn must be a nonnegative integer")
    if type(paused) is not bool:
        raise ValueError("Campaign paused field must be boolean")
    return {"turn": turn, "paused": paused}
