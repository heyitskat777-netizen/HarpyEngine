"""Original source-bound Girl Play swaps; a borrowed rule does not change playbook identity."""

import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal

from pydantic import Field

from girlframe.engine.creation_details import StandardChoice
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_girl_transition_state import GirlSetup

if TYPE_CHECKING:
    from girlframe.engine.m2 import PilotSheet


class PlaySwap(Model):
    removed_rule: str = Field(min_length=1, max_length=180)
    acquired_rule: str = Field(min_length=1, max_length=180)
    source_playbook: str = Field(min_length=1, max_length=80)
    source_event: str = Field(min_length=1)


class StandardGrant(Model):
    role: Literal["own", "peer", "handler"]
    choice: StandardChoice
    chooser: ActorRef
    source_event: str = Field(min_length=1)
    appointment: str | None = None


class GirlRuntime(Model):
    baseline_event: str | None = None
    setup: GirlSetup | None = None
    swaps: tuple[PlaySwap, ...] = ()
    retained_rules: tuple[str, ...] = ()
    standards: tuple[StandardGrant, ...] = ()


def has_rule(sheet: object, identity: str, native_playbook: str) -> bool:
    if isinstance(sheet, Mapping):
        raw = sheet.get("girl_runtime")
        try:
            runtime = GirlRuntime.model_validate_json(json.dumps(raw)) if raw is not None else None
        except (ValueError, TypeError):
            return False
        book = sheet.get("girl")
    else:
        runtime = getattr(sheet, "girl_runtime", None)
        book = getattr(sheet, "girl", None)
    active = book == native_playbook or (identity in runtime.retained_rules if runtime else False)
    for swap in runtime.swaps if runtime else ():
        if swap.removed_rule == identity:
            active = False
        if swap.acquired_rule == identity:
            active = True
    return active


def keep_automatic(sheet: object) -> frozenset[str]:
    automatic = set()
    if has_rule(sheet, "girl.princess.objectively-beautiful", "PRINCESS"):
        automatic.add("sexy")
    if has_rule(sheet, "girl.alpha.itching-for-a-fight", "ALPHA"):
        automatic.add("vicious")
    return frozenset(automatic)


def change_playbook_runtime(
    original: "PilotSheet",
    new_book: str,
    source_event: str,
) -> tuple["PilotSheet", dict[str, str]]:
    """A new native baseline retains explicitly acquired rules, never old removal masks."""
    from girlframe.engine.m2 import PilotSheet
    from girlframe.engine.playbooks import GIRL_TYPES

    if new_book not in GIRL_TYPES or new_book == original.girl or not source_event:
        raise ValueError("Choose a different base Girl playbook with an actual source")
    sheet = PilotSheet.model_validate_json(original.model_dump_json())
    runtime = sheet.girl_runtime or GirlRuntime()
    retained = set(runtime.retained_rules)
    for swap in runtime.swaps:
        retained.discard(swap.removed_rule)
        retained.add(swap.acquired_rule)
    fact = dict(
        kind="girl_playbook_changed",
        original_character=sheet.character_id or "",
        old_book=sheet.girl,
        new_book=new_book,
        source_event=source_event,
        prior_runtime=runtime.model_dump_json(),
    )
    sheet.girl = new_book
    sheet.girl_runtime = GirlRuntime(
        baseline_event=source_event,
        setup=runtime.setup,
        retained_rules=tuple(sorted(retained)),
        standards=runtime.standards,
    )
    sheet.revision += 1
    return sheet, fact


def relation_current(sheet: object, relation: Literal["mentor", "pair"], state: object) -> bool:
    """A runtime relationship never transfers from an original person to their replacement."""
    runtime = getattr(sheet, "girl_runtime", None)
    setup = runtime.setup if runtime else None
    actual = getattr(setup, relation, None) if setup else None
    if actual is None:
        return True  # Legacy setup remains subject to its existing lifecycle guards.
    other = getattr(state, "sheets", {}).get(actual.entity)
    return bool(other and other.character_id == actual.incarnation)


def mentor_tag(sheet: object, tag: object, state: object) -> bool:
    if (
        not has_rule(sheet, "girl.newgirl.mentor", "NEWGIRL")
        or not relation_current(sheet, "mentor", state)
        or getattr(tag, "giver", None) != getattr(sheet, "mentor", None)
    ):
        return False
    runtime = getattr(sheet, "girl_runtime", None)
    ref = runtime.setup.mentor if runtime and runtime.setup else None
    actual = getattr(tag, "giver_actor", None)
    if ref is not None and actual is not None:
        return bool(ref == actual)
    original = getattr(tag, "giver_character", None)
    return bool(ref is None or original is None or ref.incarnation == original)
