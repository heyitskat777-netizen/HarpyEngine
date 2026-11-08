"""Casualty's original ideal parts, actual source costs and printed body consequences."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState, IdentityState, PilotSheet
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_leviathan_obsession import require_unlocked

BARELY = "girl.casualty.barely-a-girl"
BETTER = "girl.casualty.no-one-better"
GOD = "girl.casualty.wounded-god"
SEX = "girl.casualty.sex-play"
PLAY = "casualty_sex"
PARTS = ("legs", "hands", "eyes", "ears", "head", "face", "vital_organs", "link", "brain")
LABELS = dict(
    zip(
        PARTS,
        ("Legs", "Hands", "Eyes", "Ears", "Head", "Face", "Vital Organs", "Link", "Brain"),
        strict=True,
    )
)
Condition = Literal["intact", "broken", "destroyed", "removed"]


class Part(Model):
    id: Literal["legs", "hands", "eyes", "ears", "head", "face", "vital_organs", "link", "brain"]
    condition: Condition = "intact"


class Body(Model):
    actor: ActorRef
    vessel: str
    parts: tuple[Part, ...]
    setup_source: str
    initial_parts: tuple[Part, ...]
    event: str


class PartChange(Model):
    id: str
    actor: ActorRef
    vessel: str
    part: str
    before: Condition
    after: Condition
    event: str
    reason: Literal[
        "push_roll", "resist_void", "helpless", "sex", "punishment", "repair", "source_destroy"
    ]
    source_action: str | None = None
    source_work: str | None = None
    source_choice: str | None = None
    step: int = 0
    inflictor: ActorRef
    account: str


class Barely(Model):
    id: str
    actor: ActorRef
    vessel: str | None
    identity: IdentityState
    asset: str
    asset_name: str
    event: str
    account: str


class Damage(Model):
    id: str
    actor: ActorRef
    inflictor: ActorRef
    vessel: str
    part: str
    condition: Condition
    change: str
    event: str
    account: str


class Repair(Model):
    id: str
    actor: ActorRef
    vessel: str
    part: str
    change: str
    event: str
    payment: str | None = None


class RollPush(Model):
    id: str
    actor: ActorRef
    action: str
    choice: str
    receipt: str
    before: int
    total: int
    change: str
    event: str


class Resistance(Model):
    id: str
    actor: ActorRef
    vessel: str
    asset: str
    asset_name: str
    action: str | None = None
    choice: str | None = None
    work: str | None = None
    step: int
    source_kind: Literal["dive_deep", "risk_factor", "mockingbird_sex", "dormant", "budget_cleanup"]
    part: str
    account: str
    change: str
    event: str
    consumed: bool = False

    @model_validator(mode="after")
    def actual_context(self) -> "Resistance":
        if self.work is not None:
            if (
                not self.work
                or self.action is not None
                or self.choice is not None
                or self.source_kind not in ("dormant", "budget_cleanup")
            ):
                raise ValueError("Use the actual original required-work resistance context")
        elif not self.action or not self.choice:
            raise ValueError("Use the actual original Play and owned resistance choice")
        return self


class Helpless(Model):
    id: str
    actor: ActorRef
    vessel: str
    change: str
    event: str
    account: str
    recovered_event: str | None = None


class Finder(Model):
    id: str
    helpless: str
    actor: ActorRef
    finder: ActorRef
    controller: int
    cast: SceneCast
    event: str
    account: str


class SexSession(Model):
    bonded_source: str | None = Field(default=None, exclude_if=lambda value: value is None)
    changeling_source: str | None = Field(default=None, exclude_if=lambda value: value is None)
    id: str
    actor: ActorRef
    target: ActorRef
    caster: int
    counterpart: int
    cast: SceneCast
    actor_vessel: str
    target_vessel: str
    registry: str
    proposed_event: str
    proposal: str
    consent_event: str | None = None
    consent_account: str = ""
    phase: str = "invited"
    action: str | None = None
    bound_event: str | None = None
    effect_event: str | None = None
    tier: Literal["low", "mid", "high"] | None = None
    completed_event: str | None = None
    presented: tuple[str, ...] = ()


class SexSelection(Model):
    id: str
    session: str
    action: str
    actor: ActorRef
    controller: int
    kind: str
    options: tuple[str, ...]
    identities: tuple[str, ...]
    number: int | None
    text: str
    fields: dict[str, str]
    event: str
    tag: str | None = None
    change: str | None = None
    work: tuple[str, ...] = ()


KINDS = {
    Body: "casualty_body",
    PartChange: "casualty_part_change",
    Barely: "casualty_barely",
    Repair: "casualty_repair",
    Damage: "casualty_damage",
    RollPush: "casualty_roll_push",
    Resistance: "casualty_resistance",
    Helpless: "casualty_helpless",
    Finder: "casualty_finder",
    SexSession: "casualty_sex_session",
    SexSelection: "casualty_sex_selection",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def put(state: GameState, value: Model) -> None:
    kind = KINDS[type(value)]
    identity = value.actor.token if isinstance(value, Body) else value.model_dump()["id"]
    mutable = isinstance(value, (Body, Resistance, Helpless, SexSession))
    if not mutable and any(x.get("kind") == kind and x.get("id") == identity for x in state.facts):
        raise ValueError("Preserve the original immutable Casualty source occurrence")
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == identity)
    ]
    state.facts.append(dict(kind=kind, id=identity, body=value.model_dump_json()))


def body(state: GameState, actor: ActorRef) -> Body | None:
    return next((x for x in records(state, Body) if x.actor == actor), None)


def part_state(state: GameState, actor: ActorRef, part: str) -> str | None:
    value = body(state, actor)
    return next((x.condition for x in value.parts if x.id == part), None) if value else None


def can_pilot(state: GameState, actor: ActorRef) -> bool:
    return part_state(state, actor, "link") in (None, "intact") and part_state(
        state, actor, "brain"
    ) not in ("destroyed", "removed")


def change_part(
    state: GameState,
    actor: ActorRef,
    part: str,
    after: Condition,
    *,
    event: str,
    reason: str,
    inflictor: ActorRef,
    account: str,
    action: str | None = None,
    work: str | None = None,
    choice: str | None = None,
    step: int = 0,
) -> PartChange:
    value = body(state, actor)
    old = next((x for x in value.parts if x.id == part), None) if value else None
    if value is None or old is None or not event or not account.strip() or len(account) > 1200:
        raise ValueError("Use the actual original Casualty body, named part and performed source")
    if (
        after == "broken"
        and old.condition != "intact"
        or after == "intact"
        and old.condition != "broken"
        or after in ("destroyed", "removed")
        and old.condition in ("destroyed", "removed")
    ):
        raise ValueError(
            "Change a real intact/broken original part, never grant replacement hardware"
        )
    changed = PartChange.model_validate(
        dict(
            id=str(uuid5(NAMESPACE_URL, "casualty:" + actor.token + part + event)),
            actor=actor,
            vessel=value.vessel,
            part=part,
            before=old.condition,
            after=after,
            event=event,
            reason=reason,
            source_action=action,
            source_work=work,
            source_choice=choice,
            step=step,
            inflictor=inflictor,
            account=account.strip(),
        )
    )
    put(
        state,
        value.model_copy(
            update=dict(
                parts=tuple(
                    x.model_copy(update=dict(condition=after)) if x.id == part else x
                    for x in value.parts
                )
            )
        ),
    )
    put(state, changed)
    return changed


def erase_identity(sheet: PilotSheet, identity: str) -> IdentityState:
    entry = next((x for x in sheet.identities if x.id == identity), None)
    if (
        not has_rule(sheet, BARELY, "CASUALTY")
        or entry is None
        or entry.protected
        or entry.paired
        or entry.am_limiter
        or entry.id in sheet.sedation_locked
        or sheet.frame == "PROJECT ANKOU"
    ):
        raise ValueError("SOURCE_IDENTITY_REMOVAL_REQUIRED: preserve protected/lifecycle sources")
    require_unlocked(sheet.identities, (identity,))
    sheet.identities = [x for x in sheet.identities if x.id != identity]
    sheet.revision += 1
    return entry


def helpless(state: GameState, actor: ActorRef, foe: ActorRef | None = None) -> bool:
    from girlframe.engine.m3_actor_state import ProfileBinding
    from girlframe.engine.m3_actors import resolve

    bindings = tuple(
        ProfileBinding(
            owner=x.owner, character_id=x.character_id, profile_revision=x.source_profile_revision
        )
        for x in state.sheets.values()
        if x.character_id
    )
    try:
        actual = resolve(state, actor, bindings, require_current_profile=False)
    except ValueError:
        return False
    return any(
        x.actor == actor and x.vessel == actual.vessel_id and not x.recovered_event
        for x in records(state, Helpless)
    )


def consume_resistance(
    state: GameState, actor: ActorRef, asset: str, action: str, event: str, step: int
) -> bool:
    value = next(
        (
            x
            for x in records(state, Resistance)
            if x.actor == actor
            and x.asset == asset
            and (x.action if x.work is None else x.work) == action
            and x.event == event
            and x.step == step
        ),
        None,
    )
    if value is None:
        return False
    actual_body = body(state, actor)
    cost = next((x for x in records(state, PartChange) if x.id == value.change), None)
    sheet = state.sheets.get(actor.entity)
    asset_state = next((x for x in sheet.assets if x.id == asset), None) if sheet else None
    if (
        value.consumed
        or actual_body is None
        or actual_body.vessel != value.vessel
        or sheet is None
        or sheet.character_id != actor.incarnation
        or not has_rule(sheet, GOD, "CASUALTY")
        or asset_state is None
        or asset_state.family != "girl"
        or asset_state.void
        or cost is None
        or cost.actor != actor
        or cost.vessel != value.vessel
        or cost.reason != "resist_void"
        or cost.after != "broken"
        or cost.before != "intact"
        or cost.source_action != value.action
        or cost.source_work != value.work
        or cost.source_choice != value.choice
        or cost.step != step
        or cost.event != event
        or cost.part != value.part
    ):
        raise ValueError(
            "Consume only the actual source-bound original resistance and part cost once"
        )
    put(state, value.model_copy(update=dict(consumed=True)))
    return True
