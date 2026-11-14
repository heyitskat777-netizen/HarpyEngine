"""Source-owned cocktail Tags and finite real-scene lifetime (PDF38–39)."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_world_state import WorldTag

RULE = "girl.stim-blissed.dose-up"
SELF_RULE = "girl.stim-blissed.malleable-me-malleable-you"
PLAY = "dose_up"
Component = Literal["quick", "strong", "calm", "bliss", "talk", "sense"]
COMPONENTS: tuple[Component, ...] = ("quick", "strong", "calm", "bliss", "talk", "sense")
LABELS = {
    "quick": "Upper:Quick",
    "strong": "Upper:Strong",
    "calm": "Downer:Calm",
    "bliss": "Downer:Bliss",
    "talk": "Hallucinogen:Talk",
    "sense": "Hallucinogen:Sense",
}
DESCRIPTIONS = {
    "quick": "Heightened reaction time and sensitivity",
    "strong": "Fast heartbeat and abundant energy",
    "calm": "Slowed thoughts and blocked fear",
    "bliss": "Pain blocked; blissed-out",
    "talk": "Pliable and honest",
    "sense": "Changed interpretation of the senses",
}
DURATION: Literal[2] = 2
LIFETIME_VERSION = "dose-up-real-recipient-scenes-v1"


class Contact(Model):
    npc_cell: tuple[int, int] | None = Field(default=None, exclude_if=lambda x: x is None)
    npc_body_fact: str | None = Field(default=None, exclude_if=lambda x: x is None)
    id: str
    actor: ActorRef
    target: ActorRef
    caster: int
    target_controller: int
    reviewer: int
    cast: SceneCast
    actor_position: str | None
    target_position: str | None
    actor_vessel: str | None
    target_vessel: str | None
    event: str
    account: str = Field(min_length=1, max_length=1200)


class DoseOrder(Model):
    id: str
    actor: ActorRef
    issuer: ActorRef
    controller: int
    scene: str
    cast: SceneCast
    event: str


class OrderUse(Model):
    id: str
    action: str


class Selection(Model):
    role: Literal["roller", "issuer", "handler"]
    chooser: int
    components: tuple[Component, ...]
    choice: str
    event: str


class Dose(Model):
    id: str
    actor: ActorRef
    target: ActorRef
    caster: int
    target_controller: int
    handler: ActorRef
    handler_controller: int
    cast: SceneCast
    contact: str | None
    order: str | None
    heat: int = Field(ge=0)
    total: int
    roll_event: str
    selections: tuple[Selection, ...]
    event: str
    duration: Literal[1, 2] = DURATION
    lifetime_version: str = LIFETIME_VERSION
    punishment: str | None = None
    recipient_choice: str | None = None
    recipient_event: str | None = None


class DrugTag(Model):
    id: str
    dose: str
    target: ActorRef
    component: Component
    tag: TagState
    event: str


class NpcDrugTag(Model):
    id: str
    dose: str
    target: ActorRef
    component: Component
    tag: WorldTag
    event: str


class SceneEnd(Model):
    id: str
    dose: str
    scene: str
    cast: SceneCast
    event: str
    expired: bool


KINDS: dict[type[Model], str] = {
    Contact: "dose_up_contact",
    DoseOrder: "dose_up_order",
    OrderUse: "dose_up_order_use",
    Dose: "dose_up_result",
    DrugTag: "dose_up_drug_tag",
    NpcDrugTag: "dose_up_npc_drug_tag",
    SceneEnd: "dose_up_scene_end",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def put(state: GameState, value: Model) -> None:
    identity = value.model_dump()["id"]
    kind = KINDS[type(value)]
    if any(x.get("kind") == kind and x.get("id") == identity for x in state.facts):
        raise ValueError("Preserve the actual immutable Dose Up source")
    state.facts.append(dict(kind=kind, id=identity, body=value.model_dump_json()))


def expired(state: GameState, dose: str) -> bool:
    return any(x.dose == dose and x.expired for x in records(state, SceneEnd))


def drug_tags(state: GameState, actor: ActorRef) -> tuple[DrugTag, ...]:
    return tuple(
        x for x in records(state, DrugTag) if x.target == actor and not expired(state, x.dose)
    )
