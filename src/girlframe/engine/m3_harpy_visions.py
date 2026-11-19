"""Source-owned Visions choices and the original recipient's actual consequences."""

import hashlib
from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState, IdentityState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_hallucinations import Roll
from girlframe.engine.m3_harpy_defeat import harpy, update
from girlframe.engine.m3_void_state import HarpyIdentity, HarpyState

KIND = "harpy_visions"


class Adjustment(Model):
    effect: Literal["identity", "tag", "deepen", "weaken", "remove"]
    name: str = Field(default="", max_length=120)
    slot: int | None = Field(default=None, ge=0, le=3)


class Plan(Model):
    event: str
    baseline: str
    choices: tuple[Adjustment, ...]


class Vision(Model):
    id: str
    scene: str
    channel: int
    harpy: ActorRef
    controller: int
    advancement: str
    subject: ActorRef
    account: str
    consent: str | None = None
    roll: Roll | None = None
    low_identities: tuple[HarpyIdentity, ...] = ()
    plans: tuple[Plan, ...] = ()
    returned: tuple[str, ...] = ()
    resolved: str | None = None

    @property
    def proposed(self) -> Plan | None:
        last = self.plans[-1] if self.plans else None
        return last if last and last.event not in self.returned else None


def records(state: GameState) -> tuple[Vision, ...]:
    return tuple(
        Vision.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def put(state: GameState, value: Vision) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.id)]
    state.facts.append(dict(kind=KIND, id=value.id, body=value.model_dump_json()))


def can_replace(state: GameState, case: Vision) -> bool:
    sheet = state.sheets.get(case.subject.entity)
    if sheet is None or sheet.character_id != case.subject.incarnation:
        return False
    from girlframe.engine.m3_clone_am import additional_identities
    from girlframe.engine.m3_parasite_infection import controls_identity

    return (
        0 < len(case.low_identities) <= 4
        and not sheet.obsession_sources
        and sheet.frame != "PROJECT ANKOU"
        and not additional_identities(state, sheet.owner)
        and not any(
            x.protected
            or x.paired
            or x.am_limiter
            or x.obsession_sources
            or x.id in sheet.sedation_locked
            or controls_identity(state, case.subject, x.id)
            for x in sheet.identities
        )
        and not any(x.paired or x.obsession_sources for x in case.low_identities)
    )


def replace_low(state: GameState, case: Vision, event: str) -> GameState:
    if not can_replace(state, case) or harpy(state, case.harpy).identities != case.low_identities:
        raise ValueError("Recover the actual source Identities and unprotected original recipient")
    source = harpy(state, case.harpy)
    if isinstance(source, HarpyState):
        state = update(state, case.harpy, exposed=True)
    elif state.world is not None and any(
        x.id == case.harpy.entity and x.alive for x in state.world.pilots
    ):
        state.world = state.world.model_copy(
            update=dict(
                pilots=tuple(
                    x.model_copy(update=dict(exposed=True)) if x.id == case.harpy.entity else x
                    for x in state.world.pilots
                ),
            )
        )
    else:
        raise ValueError("Recover the original living Harpy Core")
    sheet = state.sheets[case.subject.entity]
    sheet.identities = [
        IdentityState(id=f"{event}:{slot}", name=original.name, slot=slot)
        for slot, original in enumerate(case.low_identities)
    ]
    sheet.revision += 1
    put(state, case.model_copy(update=dict(resolved=event)))
    return state


def baseline(state: GameState, case: Vision, choices: tuple[Adjustment, ...]) -> str:
    from girlframe.engine.m3_actor_bonds import depth

    sheet = state.sheets[case.subject.entity]
    material = []
    if any(x.effect in {"identity", "tag"} for x in choices):
        material.append(sheet.model_dump_json(include={"identities", "sedation_locked", "frame"}))
    if any(x.effect in {"deepen", "weaken", "remove"} for x in choices):
        material.append(str(depth(state, case.subject, case.harpy)))
    return hashlib.sha256("\0".join(material).encode()).hexdigest()


def preview(
    original: GameState, case: Vision, choices: tuple[Adjustment, ...], event: str
) -> tuple[GameState, tuple[str, ...]]:
    require_choice_count(case, choices)
    state = GameState.model_validate_json(original.model_dump_json())
    labels = []
    for offset, item in enumerate(choices):
        state, label = _apply_adjustment(state, case, item, event, offset)
        labels.append(label)
    return state, tuple(labels)


def require_choice_count(case: Vision, choices: tuple[Adjustment, ...]) -> None:
    if case.roll is None or not (
        (case.roll.result == "mid" and len(choices) <= 4)
        or (case.roll.result == "high" and len(choices) == 8)
    ):
        raise ValueError("Choose up to four effects on 8–10, or exactly eight on 11+")


def _apply_adjustment(
    state: GameState, case: Vision, item: Adjustment, event: str, offset: int
) -> tuple[GameState, str]:
    from girlframe.engine.m3_actor_bonds import change, depth
    from girlframe.engine.m3_clone_am import additional_identities
    from girlframe.engine.m3_harpy_defeat import give_tag
    from girlframe.engine.m3_identity_slots import bind, replacement_slot
    from girlframe.engine.m3_parasite_infection import controls_identity

    sheet = state.sheets[case.subject.entity]
    if item.effect in {"identity", "tag"}:
        if sheet.frame == "PROJECT ANKOU" or additional_identities(state, sheet.owner):
            raise ValueError("This original Identity adjustment needs lifecycle review")
        sheet = bind(sheet)
        state.sheets[case.subject.entity] = sheet
        if item.effect == "identity":
            name = item.name.strip()
            slot = replacement_slot(sheet, None)
            if (
                not name
                or item.slot is not None
                or slot is None
                or any(x.name.casefold() == name.casefold() for x in sheet.identities)
            ):
                raise ValueError("Give a distinct Identity in a free ordinary slot")
            sheet.identities.append(IdentityState(id=f"{event}:{offset}", name=name, slot=slot))
            sheet.revision += 1
            return state, "New Identity " + name
        elif item.effect == "tag":
            identity = next((x for x in sheet.identities if x.slot == item.slot), None)
            if (
                item.name
                or item.slot is None
                or identity is None
                or identity.protected
                or identity.paired
                or identity.am_limiter
                or identity.obsession_sources
                or identity.id in sheet.sedation_locked
                or controls_identity(state, case.subject, identity.id)
            ):
                raise ValueError("Choose an ordinary available Identity slot")
            sheet.identities.remove(identity)
            state = give_tag(
                state,
                case.subject,
                case.harpy,
                identity.name,
                event,
                f"{event}:{offset}",
                (case.controller, int(case.subject.entity)),
            )
            return state, "Identity becomes a Tag " + identity.name
    if item.name or item.slot is not None:
        raise ValueError("Use the actual Bond with the original Harpy")
    before = depth(state, case.subject, case.harpy)
    if not before or (before == 2 and item.effect == "deepen"):
        raise ValueError("Adjust an existing Bond to a different depth")
    if item.effect == "deepen":
        state = change(state, case.subject, case.harpy, 1, event)
    else:
        state = change(state, case.subject, case.harpy, -1, event)
        if before == 2 and item.effect == "remove":
            state = change(state, case.subject, case.harpy, -1, event)
    after = depth(state, case.subject, case.harpy)
    return state, f"Bond with the Harpy changes from {before} to {after}"
