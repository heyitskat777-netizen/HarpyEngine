"""Human-readable card labels without importing UI/service modules."""

from typing import Any


def entity_label(row: dict[str, Any]) -> str:
    name = str(row.get("label", row.get("name", "Choice")))
    slot = row.get("slot")
    return name + f" (Identity {slot + 1})" if type(slot) is int else name
