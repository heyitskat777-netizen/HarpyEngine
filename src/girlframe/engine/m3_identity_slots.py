"""Stable ordinary slots for replacement and reset; no new Identity or unmark grant."""

from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.m2 import PilotSheet


def bind(sheet: PilotSheet) -> PilotSheet:
    if CATALOG.get(sheet.girl, {}).get("family") != "girl":
        raise ValueError("Identity slots require an actual base Girl playbook")
    updated = PilotSheet.model_validate_json(sheet.model_dump_json())
    ordinary = [x for x in updated.identities if not x.protected or x.paired or x.am_limiter]
    occupied = {x.slot for x in ordinary if x.slot is not None}
    pair = next((x for x in ordinary if x.paired), None)
    if pair is not None:
        defaults = CATALOG[sheet.girl]["identities"]
        if "Hers" not in defaults:
            raise ValueError("The Paired slot needs its actual Bonded starting playbook")
        reserved = defaults.index("Hers")
        if pair.slot is None:
            if reserved in occupied:
                raise ValueError("Recover the inconsistent protected Paired slot explicitly")
            pair.slot = reserved
            occupied.add(reserved)
        elif pair.slot != reserved:
            raise ValueError("Do not silently move the protected Paired slot")
    for identity in ordinary:
        if identity.slot is None:
            identity.slot = next(x for x in range(4) if x not in occupied)
            occupied.add(identity.slot)
    if updated != sheet:
        updated.revision += 1
    return PilotSheet.model_validate_json(updated.model_dump_json())


def replacement_slot(sheet: PilotSheet, replaced: str | None) -> int | None:
    ordinary = [x for x in sheet.identities if not x.protected or x.paired or x.am_limiter]
    if replaced is not None:
        return next(x.slot for x in ordinary if x.id == replaced)
    if any(x.slot is None for x in ordinary):
        return None  # Legacy M2 remains ID-bound until actual M3 period normalization.
    occupied = {x.slot for x in ordinary}
    return next((x for x in range(4) if x not in occupied), None)
