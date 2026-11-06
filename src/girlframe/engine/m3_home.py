"""Secret installed items and actual same-Frame Home, of a Sort effects."""

from pydantic import Field, model_validator

from girlframe.engine import m3_class_grafts as grafts
from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_bonds import change as change_bond
from girlframe.engine.m3_actor_state import ActorRef, Model, ProfileBinding
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_beneath import rejection_blocked
from girlframe.engine.m3_control_ritual import tags as ritual_tags
from girlframe.engine.m3_girl_runtime_state import mentor_tag
from girlframe.engine.m3_physical import occupied_frame
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.engine.m3_tag_permissions import can_reject

RULE = "frame.class.legion.home-of-a-sort"
ITEMS = (
    ("charms", "Dangly charms"),
    ("napping", "A nice corner for napping"),
    ("bottle", "A vent with hidden bottle"),
    ("book", "A good book"),
    ("movie", "A bad movie"),
    ("photograph", "A photograph"),
    ("toy", "A sex toy"),
    ("cards", "Cards and poker chips"),
    ("gun", "A gun and one bullet"),
    ("foundation", "Something you stole from a Foundation employee"),
    ("girl", "Something you stole from another Girl"),
)


class Installation(Model):
    purchase: str = Field(min_length=1)
    actor: ActorRef
    frame: str = Field(min_length=1)
    items: tuple[str, ...]
    event: str = Field(min_length=1)

    @model_validator(mode="after")
    def three_secrets(self) -> "Installation":
        if (
            len(self.items) != 3
            or len(set(self.items)) != 3
            or not set(self.items) <= dict(ITEMS).keys()
        ):
            raise ValueError("Choose exactly three distinct printed secret installed items")
        return self


class Presence(Model):
    frame: str
    purchase: str
    actor: str
    other: str
    placements: tuple[str, ...]


def held(state: GameState, actor: ActorRef) -> FrameRuleReceipt | None:
    return grafts.held(state, actor, RULE)


def installed(state: GameState, receipt: FrameRuleReceipt) -> Installation:
    values = [
        Installation.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "home_installation" and x.get("purchase") == receipt.id
    ]
    if len(values) != 1:
        raise ValueError("Recover the original private Home installation")
    value = values[0]
    if (value.actor, value.frame, value.event) != (
        receipt.actor,
        receipt.frame_instance,
        receipt.source_event,
    ):
        raise ValueError("Recover the actual original Home person, Frame and installation source")
    return value


def together(
    state: GameState, actor: ActorRef, other: ActorRef, bindings: tuple[ProfileBinding, ...]
) -> str:
    receipt = held(state, actor)
    if receipt is None or other.kind != "pilot" or actor == other:
        raise ValueError("Use your actual acquired Home with another original Pilot")
    from girlframe.engine.m3_home_objects import prepared

    home = prepared(state, receipt)
    poses = [next((x for x in state.placements if x.actor == ref), None) for ref in (actor, other)]
    if any(x is None or occupied_frame(x) != (actor, home.frame) for x in poses):
        raise ValueError("Both actual people must already occupy this exact owned Frame")
    first, second = (
        resolve(state, ref, bindings, require_current_profile=False) for ref in (actor, other)
    )
    if (
        not first.alive
        or not second.alive
        or first.cell is None
        or second.cell != first.cell
        or first.position_sha256 is None
        or second.position_sha256 is None
    ):
        raise ValueError(
            "Recover both actual living bodies at the same known occupied Frame position"
        )
    return fingerprint(
        Presence(
            frame=home.frame,
            purchase=receipt.id,
            actor=first.position_sha256,
            other=second.position_sha256,
            placements=tuple(x.model_dump_json() for x in poses if x is not None),
        )
    )


def own_tags(state: GameState, actor: ActorRef) -> list[TagState]:
    return state.sheets[actor.entity].tags + ritual_tags(state, int(actor.entity))


def rejectable(state: GameState, actor: ActorRef, tag: TagState) -> bool:
    return (
        not mentor_tag(state.sheets[actor.entity], tag, state)
        and not rejection_blocked(state, int(actor.entity), tag.id)
        and can_reject(state, actor, tag.id)
    )


def deepen(
    state: GameState,
    actor: ActorRef,
    other: ActorRef,
    item: str,
    event: str,
    bindings: tuple[ProfileBinding, ...],
) -> GameState:
    together(state, actor, other, bindings)
    receipt = held(state, actor)
    if receipt is None or item not in installed(state, receipt).items:
        raise ValueError("Use an actual original installed item to deepen this Bond")
    return change_bond(state, actor, other, 1, event)


def reject(
    state: GameState,
    actor: ActorRef,
    other: ActorRef,
    tag_id: str,
    bindings: tuple[ProfileBinding, ...],
) -> None:
    together(state, actor, other, bindings)
    tag = next((x for x in own_tags(state, actor) if x.id == tag_id), None)
    if held(state, actor) is None or tag is None or not rejectable(state, actor, tag):
        raise ValueError(
            "The actual Home cannot bypass this Tag's Mentor or original-setter permission"
        )
    sheet = state.sheets[actor.entity]
    sheet.tags = [x for x in sheet.tags if x.id != tag_id]
    sheet.revision += 1
