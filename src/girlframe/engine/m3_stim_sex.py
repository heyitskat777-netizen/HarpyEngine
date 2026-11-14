"""Genuine Stim Sex sources, drugs and source-specific temporary physiology."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef, Model, ProfileBinding, SceneCast
from girlframe.engine.m3_dose_up import DURATION, Component
from girlframe.engine.m3_world_state import WorldTag

RULE = "girl.stim-blissed.sex-play"
PLAY = "stim_sex"
EFFECTS = ("helpless", "orders", "bond", "tag")


class NpcContact(Model):
    session: str
    target: ActorRef
    actor: ActorRef
    controller: int
    vessel: str
    actor_vessel: str
    cell: tuple[int, int]
    cast: SceneCast
    revision: int
    event: str
    account: str = Field(min_length=1, max_length=1200)


class Session(Model):
    npc_contact: NpcContact | None = Field(default=None, exclude_if=lambda value: value is None)
    id: str
    actor: ActorRef
    target: ActorRef
    caster: int
    counterpart: int
    cast: SceneCast
    registry: str
    bonded_source: str | None = Field(default=None, exclude_if=lambda value: value is None)
    changeling_source: str | None = Field(default=None, exclude_if=lambda value: value is None)
    learned_source: str | None = Field(default=None, exclude_if=lambda value: value is None)
    actor_vessel: str
    target_vessel: str
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


class Selection(Model):
    id: str
    action: str
    owner: ActorRef
    target: ActorRef
    phase: str
    controller: int
    kind: str
    options: tuple[str, ...]
    text: str
    event: str


class Drug(Model):
    id: str
    session: str
    action: str
    target: ActorRef
    vessel: str
    giver: ActorRef
    component: Component
    tag: TagState | WorldTag
    choice: str
    event: str
    duration: Literal[1, 2] = DURATION
    lifetime_version: str = "stim-sex-real-recipient-scenes-v1"


class Effect(Model):
    id: str
    action: str
    kind: Literal["helpless", "orders", "bond", "tag"]
    target: ActorRef
    giver: ActorRef
    drug: str
    choice: str
    event: str
    tag: TagState | WorldTag | None = None
    bond_before: int | None = None
    bond_after: int | None = None


class HelplessRecovery(Model):
    """One genuine Nanobot treatment ends only its selected physiological effect."""

    id: str
    effect: str
    effect_event: str
    target: ActorRef
    drug: str
    doctor_action: str
    event: str


class SceneEnd(Model):
    id: str
    drug: str
    scene: str
    cast: SceneCast
    event: str
    expired: bool


KINDS: dict[type[Model], str] = {
    Session: "stim_sex_session",
    Selection: "stim_sex_selection",
    Drug: "stim_sex_drug",
    Effect: "stim_sex_effect",
    SceneEnd: "stim_sex_scene_end",
    HelplessRecovery: "stim_sex_helpless_recovery",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def get(state: GameState, identity: str) -> Session:
    value = next((x for x in records(state, Session) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the original actual Stim intimacy source")
    return value


def put(state: GameState, value: Model) -> None:
    kind, identity = KINDS[type(value)], value.model_dump()["id"]
    if not isinstance(value, Session) and any(
        x.get("kind") == kind and x.get("id") == identity for x in state.facts
    ):
        raise ValueError("Keep the immutable original Stim Sex consequence")
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == identity)
    ]
    state.facts.append(dict(kind=kind, id=identity, body=value.model_dump_json()))


def expired(state: GameState, drug: str) -> bool:
    return any(x.drug == drug and x.expired for x in records(state, SceneEnd))


def active(state: GameState, drug: Drug) -> bool:
    if expired(state, drug.id):
        return False
    from girlframe.engine.m3_actors import resolve

    try:
        bound = tuple(
            ProfileBinding(
                owner=sheet.owner,
                character_id=sheet.character_id,
                profile_revision=sheet.source_profile_revision,
            )
            for sheet in state.sheets.values()
            if sheet.character_id is not None
        )
        actual = resolve(state, drug.target, bound, require_current_profile=False)
    except ValueError:
        return False
    return actual.vessel_id == drug.vessel


def helpless_effects(state: GameState, subject: ActorRef) -> tuple[Effect, ...]:
    """Current source effects, minus individually treated ones; drugs retain their clock."""
    drugs = {x.id: x for x in records(state, Drug)}
    recoveries = records(state, HelplessRecovery)
    return tuple(
        effect
        for effect in records(state, Effect)
        if effect.kind == "helpless"
        and effect.target == subject
        and effect.drug in drugs
        and active(state, drugs[effect.drug])
        and not any(
            recovery.effect == effect.id
            and recovery.effect_event == effect.event
            and recovery.target == effect.target
            and recovery.drug == effect.drug
            for recovery in recoveries
        )
    )


def helpless(state: GameState, subject: ActorRef, foe: ActorRef | None = None) -> bool:
    # Printed unqualified physiology remains independent of unrelated Helpless sources.
    return bool(helpless_effects(state, subject))
