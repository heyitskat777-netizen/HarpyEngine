"""Pure core operations for M3; services must persist effects and required follow-ups together."""

from typing import Literal

from pydantic import Field

from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.m2 import AssetState, IdentityState, Model, PilotSheet
from girlframe.engine.m3_identity_slots import replacement_slot


class Followup(Model):
    kind: Literal[
        "defeat", "helpless", "girl_void_threshold", "frame_void_threshold", "mockingbird_resist"
    ]
    owner: int
    source_pdf: int


class Result(Model):
    sheet: PilotSheet
    followups: tuple[Followup, ...] = ()


class RepairSelection(Model):
    girl: tuple[str, ...] = ()
    frame: tuple[str, ...] = ()


class Recovery(Model):
    unmark_identity: str | None = None
    embrace_tag: str | None = None
    replace_identity: str | None = None
    replacement_id: str | None = None
    repair_assets: bool = True
    allow_duplicate_labels: bool = False
    sedation_locked: frozenset[str] = frozenset()
    repair_limit: int | None = Field(default=None, ge=0)
    repairs: RepairSelection | None = None


def clone(sheet: PilotSheet) -> PilotSheet:
    return PilotSheet.model_validate_json(sheet.model_dump_json())


def owned_asset(sheet: PilotSheet, identity: str) -> AssetState:
    asset = next((x for x in sheet.assets if x.id == identity), None)
    if asset is None:
        raise ValueError("Choose an owned Asset")
    return asset


def damage(sheet: PilotSheet, asset_id: str, *, piloting: bool) -> Result:
    updated = clone(sheet)
    asset = owned_asset(updated, asset_id)
    if asset.damaged:
        raise ValueError("An already damaged Asset cannot be damaged again")
    asset.damaged = True
    required: list[Followup] = []
    if not any(x.family == "frame" and not x.damaged for x in updated.assets) and piloting:
        required.append(Followup(kind="defeat", owner=sheet.owner, source_pdf=29))
    elif not any(x.family == "girl" and not x.damaged for x in updated.assets) and not piloting:
        required.append(Followup(kind="helpless", owner=sheet.owner, source_pdf=15))
    updated.revision += 1
    return Result(sheet=updated, followups=tuple(required))


def install(sheet: PilotSheet, asset: AssetState, *, replace: str | None = None) -> Result:
    updated = clone(sheet)
    if any(x.id == asset.id for x in updated.assets):
        raise ValueError("Asset IDs must be distinct")
    family = [x for x in updated.assets if x.family == asset.family]
    maximum = 4 if asset.family == "girl" else 5
    if len(family) >= maximum:
        candidate = next((x for x in family if x.id == replace), None)
        if candidate is None or candidate.void:
            raise ValueError("At the Asset cap, explicitly replace a non-Void Asset of that family")
        updated.assets = [x for x in updated.assets if x.id != candidate.id]
    elif replace is not None:
        raise ValueError("Do not erase an Asset when no cap replacement is needed")
    updated.assets.append(AssetState.model_validate_json(asset.model_dump_json()))
    updated.revision += 1
    return Result(sheet=updated)


def corrupt(sheet: PilotSheet, asset_id: str, description: str, *, piloting: bool) -> Result:
    if not description.strip() or len(description) > 1200:
        raise ValueError("Describe the chosen Asset's Void alteration")
    updated = clone(sheet)
    asset = owned_asset(updated, asset_id)
    if asset.void:
        raise ValueError("Void must alter an uncorrupted Asset")
    asset.void = True
    asset.description = description
    required: list[Followup] = []
    girls = [x for x in updated.assets if x.family == "girl"]
    frames = [x for x in updated.assets if x.family == "frame"]
    if updated.girl == "MOCKINGBIRD":
        if piloting and frames and all(x.void for x in frames):
            required.append(Followup(kind="mockingbird_resist", owner=sheet.owner, source_pdf=35))
    else:
        if girls and all(x.void for x in girls):
            required.append(Followup(kind="girl_void_threshold", owner=sheet.owner, source_pdf=19))
        if frames and all(x.void for x in frames):
            required.append(Followup(kind="frame_void_threshold", owner=sheet.owner, source_pdf=19))
    updated.revision += 1
    return Result(sheet=updated, followups=tuple(required))


def recover_off_duty(sheet: PilotSheet, choice: Recovery) -> Result:
    updated = clone(sheet)
    locks = choice.sedation_locked | frozenset(updated.sedation_locked)
    if not locks <= {x.id for x in updated.identities}:
        raise ValueError("Sedation locks must reference current owned Identities")
    if choice.embrace_tag is not None:
        tag = next((x for x in updated.tags if x.id == choice.embrace_tag), None)
        if (
            tag is None
            or not choice.replacement_id
            or choice.replacement_id
            in {x.id for x in updated.identities}
            | {x.id for x in updated.assets}
            | {x.id for x in updated.tags}
        ):
            raise ValueError("Embrace an owned current Tag with a distinct new Identity ID")
        ordinary = [x for x in updated.identities if not x.protected or x.paired]
        replaced = next(
            (x for x in updated.identities if x.id == choice.replace_identity and not x.protected),
            None,
        )
        if (len(ordinary) >= 4 and replaced is None) or (
            len(ordinary) < 4 and choice.replace_identity is not None
        ):
            raise ValueError(
                "Replace an ordinary unprotected Identity only when the four-slot cap requires it"
            )
        if not choice.allow_duplicate_labels and any(
            x.name.casefold() == tag.label.casefold() for x in updated.identities
        ):
            raise ValueError("Choose a Tag that does not duplicate a current Identity label")
        marked = replaced is not None and replaced.id in locks
        if replaced is not None:
            updated.identities = [x for x in updated.identities if x.id != replaced.id]
            if marked:
                locks = frozenset(x for x in locks if x != replaced.id) | {choice.replacement_id}
                updated.sedation_locked = tuple(sorted(locks))
        updated.identities.append(
            IdentityState(
                id=choice.replacement_id,
                name=tag.label,
                marked=marked,
                slot=replaced.slot if replaced else replacement_slot(updated, None),
            )
        )
        updated.tags = [x for x in updated.tags if x.id != tag.id]
    elif choice.replace_identity is not None or choice.replacement_id is not None:
        raise ValueError("Identity replacement requires an actual embraced Tag")
    if choice.unmark_identity:
        selected = next((x for x in updated.identities if x.id == choice.unmark_identity), None)
        if selected is None or not selected.marked or selected.id in locks:
            raise ValueError("Choose a marked Identity that off-duty Sedation does not lock")
        selected.marked = False
    if not choice.repair_assets:
        if choice.repairs is not None:
            raise ValueError("Do not select repairs when declining Asset recovery")
    elif choice.repair_limit is None:
        if choice.repairs is not None:
            raise ValueError("Ordinary recovery repairs all Assets, without a restricted selection")
        for asset in updated.assets:
            asset.damaged = False
    else:
        if choice.repairs is None:
            raise ValueError("The owner must select the Assets repaired under a shortage")
        for family, selected_ids in (
            ("girl", choice.repairs.girl),
            ("frame", choice.repairs.frame),
        ):
            available = [x for x in updated.assets if x.family == family and x.damaged]
            if len(set(selected_ids)) != len(selected_ids) or len(selected_ids) != min(
                choice.repair_limit, len(available)
            ):
                raise ValueError("Select the exact available repair quota for each Asset family")
            if not set(selected_ids) <= {x.id for x in available}:
                raise ValueError("Select damaged owned Assets of the requested family")
            for asset in available:
                if asset.id in selected_ids:
                    asset.damaged = False
    updated.revision += 1
    return Result(sheet=updated)


def reprogram_labels(
    sheet: PilotSheet, retain_id: str, slot: str | None = None, *, allow_duplicates: bool = False
) -> tuple[str, ...]:
    """Resolve labels; applying marks and reset follow-ups is a separate effect."""
    default = list(CATALOG[sheet.girl]["identities"])
    current = next((x for x in sheet.identities if x.id == retain_id and not x.protected), None)
    if current is None:
        raise ValueError(
            "Retain an ordinary current Identity; protected extras are preserved separately"
        )
    replacement = "Malfunctioning" if "Malfunctioning" in default else slot
    if replacement is None or replacement not in default:
        raise ValueError(
            "Choose an ordinary starting slot for the owner-approved reprogramming fallback"
        )
    if slot is not None and slot != replacement:
        raise ValueError("Use the printed Malfunctioning slot when it exists")
    paired = next((x for x in sheet.identities if x.paired), None)
    if paired and "Hers" in default:
        if replacement == "Hers":
            raise ValueError("Reprogramming cannot replace the protected Paired Identity")
        default[default.index("Hers")] = paired.name
    default[default.index(replacement)] = current.name
    default.extend(x.name for x in sheet.identities if x.protected and not x.paired)
    if not allow_duplicates and len(set(x.casefold() for x in default)) != len(default):
        raise ValueError(
            "Choose a retained Identity and slot that do not create duplicate Identities"
        )
    return tuple(default)
