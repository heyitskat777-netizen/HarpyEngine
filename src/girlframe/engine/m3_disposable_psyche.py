"""Actual Disposable Psyche removal and bounded, source-owned Tag rebuilding."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m2 import GameState, IdentityState, PilotSheet, TagState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_identity_slots import replacement_slot
from girlframe.engine.m3_leviathan_obsession import require_unlocked

RULE = "girl.stim-blissed.disposable-psyche"
KIND = "disposable_psyche"


class Disposal(Model):
    id: str
    actor: ActorRef
    identity: IdentityState
    gain: int = Field(ge=1, le=3)
    extra: Literal[3, 4]
    heat_before: int = Field(ge=0)
    heat_after: int = Field(ge=0)
    spent: int = Field(ge=0)
    receipt: str
    event: str


class Trigger(Model):
    id: str
    actor: ActorRef
    period: str
    action: str
    event: str
    tags: tuple[str, ...]


class TagSelection(Model):
    tag: str
    replace: str | None = None


class Conversion(Model):
    id: str
    trigger: Trigger
    selections: tuple[TagSelection, ...]
    tags: tuple[TagState, ...]
    replaced: tuple[IdentityState, ...]
    created: tuple[IdentityState, ...]
    event: str


def disposals(state: GameState) -> tuple[Disposal, ...]:
    return tuple(
        Disposal.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "disposable_disposal"
    )


def conversions(state: GameState) -> tuple[Conversion, ...]:
    return tuple(
        Conversion.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "disposable_conversion"
    )


def put(state: GameState, value: Disposal | Conversion) -> None:
    kind = "disposable_disposal" if isinstance(value, Disposal) else "disposable_conversion"
    if any(x.get("kind") == kind and x.get("id") == value.id for x in state.facts):
        raise ValueError("Preserve the immutable original Disposable Psyche source")
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))


def removable(sheet: PilotSheet, identity: IdentityState) -> None:
    if (
        not has_rule(sheet, RULE, "STIM-BLISSED")
        or identity.protected
        or identity.paired
        or identity.am_limiter is not None
        or identity.id in sheet.sedation_locked
    ):
        raise ValueError(
            "SOURCE_PORT_REQUIRED: preserve the actual protected Identity and its obligations"
        )
    require_unlocked(sheet.identities, (identity.id,))


def admit_removal(state: GameState, sheet: PilotSheet, identity: IdentityState) -> None:
    removable(sheet, identity)
    if sheet.frame == "PROJECT ANKOU":
        from girlframe.engine.m3_clone_am import additional_identities

        effective = (*sheet.identities, *additional_identities(state, sheet.owner))
        if all(x.marked or x.id == identity.id for x in effective):
            raise ValueError(
                "SOURCE_ANKOU_FEEDBACK_REQUIRED: complete the actual Feedback consumer first"
            )


def convert(
    original: PilotSheet,
    selections: tuple[TagSelection, ...],
    source: str,
) -> tuple[PilotSheet, tuple[TagState, ...], tuple[IdentityState, ...], tuple[IdentityState, ...]]:
    if not has_rule(original, RULE, "STIM-BLISSED"):
        raise ValueError("Use the original source-owned Disposable Psyche Girl")
    if not 1 <= len(selections) <= 4 or len({x.tag for x in selections}) != len(selections):
        raise ValueError("Choose one to four distinct actual owned Tags")
    state = PilotSheet.model_validate_json(original.model_dump_json())
    selected_tags: list[TagState] = []
    replaced: list[IdentityState] = []
    created: list[IdentityState] = []
    # Additions before replacements let a batch identify only the cap-required old slots.
    needed = max(
        0,
        len([x for x in state.identities if not x.protected or x.paired or x.am_limiter])
        + len(selections)
        - 4,
    )
    replacements = [x.replace for x in selections if x.replace is not None]
    if len(replacements) != needed or len(set(replacements)) != len(replacements):
        raise ValueError(
            "Select exactly the distinct original Identities required by the four-slot cap"
        )
    old_slots: dict[str, int | None] = {}
    for replaced_id in replacements:
        old = next((x for x in state.identities if x.id == replaced_id), None)
        if old is None:
            raise ValueError("Replace an actual original owned Identity")
        removable(state, old)
        old_slots[old.id] = old.slot
        replaced.append(old.model_copy(deep=True))
    state.identities = [x for x in state.identities if x.id not in replacements]
    reserved = {x for x in old_slots.values() if x is not None}
    for selection in selections:
        tag = next((x for x in state.tags if x.id == selection.tag), None)
        if tag is None or tag.rejection_pending:
            raise ValueError("Finish actual Tag rejection work; select a current owned Tag")
        slot = old_slots[selection.replace] if selection.replace else replacement_slot(state, None)
        if selection.replace is None and slot in reserved:
            occupied = reserved | {x.slot for x in state.identities if x.slot is not None}
            slot = next((x for x in range(4) if x not in occupied), None)
        identity = IdentityState(
            id=str(uuid5(NAMESPACE_URL, source + ":tag:" + tag.id)), name=tag.label, slot=slot
        )
        if identity.id in (
            {x.id for x in original.identities}
            | {x.id for x in original.tags}
            | {x.id for x in original.assets}
        ):
            raise ValueError("A new Identity must retain a distinct source-derived ID")
        state.identities.append(identity)
        selected_tags.append(tag.model_copy(deep=True))
        created.append(identity)
        state.tags = [x for x in state.tags if x.id != tag.id]
    state.revision += 1
    return (
        PilotSheet.model_validate_json(state.model_dump_json()),
        tuple(selected_tags),
        tuple(replaced),
        tuple(created),
    )
