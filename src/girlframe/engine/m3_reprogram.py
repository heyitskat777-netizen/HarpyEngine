"""Observation's actual Identity reset, with protected extras and Sedation slots."""

from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.m2 import IdentityState, PilotSheet
from girlframe.engine.m3_core import reprogram_labels
from girlframe.engine.m3_identity_slots import bind


def apply(
    sheet: PilotSheet, retain: str, slot: str | None, source: str, *, allow_duplicate_labels: bool
) -> PilotSheet:
    if not source.strip():
        raise ValueError("Reprogramming needs its actual source outcome")
    updated = bind(sheet)
    labels = reprogram_labels(updated, retain, slot, allow_duplicates=allow_duplicate_labels)
    defaults = CATALOG[sheet.girl]["identities"]
    extras = [x for x in updated.identities if x.protected and not x.paired]
    paired = next((x for x in updated.identities if x.paired), None)
    locked = {
        x.slot for x in updated.identities if x.id in updated.sedation_locked and x.slot is not None
    }
    if updated.sedation_locked and not updated.sedation_period:
        raise ValueError("Resolve unscoped Sedation before resetting Identities")
    identities = []
    for index, label in enumerate(labels[: len(defaults)]):
        if paired is not None and defaults[index] == "Hers":
            identities.append(paired)
        else:
            identities.append(
                IdentityState(
                    id=str(uuid5(NAMESPACE_URL, source + ":identity:" + str(index))),
                    name=label,
                    slot=index,
                    marked=index in locked,
                )
            )
    updated.identities = identities + extras
    updated.sedation_locked = tuple(
        x.id
        for x in updated.identities
        if x.id in updated.sedation_locked or (x.slot is not None and x.slot in locked)
    )
    updated.revision = sheet.revision + 1
    return PilotSheet.model_validate_json(updated.model_dump_json())
