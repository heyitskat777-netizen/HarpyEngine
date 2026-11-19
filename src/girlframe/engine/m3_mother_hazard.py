"""Actual contact and original-character immunity for Mother's Memetic Hazard."""

from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model
from girlframe.engine.m3_grow_unreal import original_target
from girlframe.engine.m3_hallucinations import Roll
from girlframe.engine.m3_janus_storage import effective_assets

RULE = "gorgon-type.mother.memetic-hazard"
PLAY = "mother_hazard"
KIND = "mother_memetic_hazard"


class Exposure(Model):
    action: str
    scene: str
    source: ActorRef
    girl: ActorRef
    tag: str
    mark_event: str
    roll: Roll | None = None
    frame: str | None = None
    ejected: str | None = None
    remain_event: str | None = None
    rebirth_event: str | None = None
    pursuit_event: str | None = None
    void_asset: str | None = None
    void_event: str | None = None
    void_work: str | None = None
    choice: str | None = None
    requested_play: str | None = None
    child: str | None = None
    completed: str | None = None


def get(state: GameState, action: str) -> Exposure | None:
    raw = next(
        (x["body"] for x in state.facts if (x.get("kind"), x.get("id")) == (KIND, action)), None
    )
    return Exposure.model_validate_json(raw) if raw else None


def put(state: GameState, exposure: Exposure) -> None:
    state.facts = [
        x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, exposure.action)
    ]
    state.facts.append(dict(kind=KIND, id=exposure.action, body=exposure.model_dump_json()))


def immune(state: GameState, girl: ActorRef) -> bool:
    current = {x.id for x in effective_assets(state, girl) if x.void}
    if not current:
        return False
    for fact in state.facts:
        if fact.get("kind") == KIND:
            case = Exposure.model_validate_json(fact["body"])
            if (
                case.girl == girl
                and case.void_asset in current
                and case.roll
                and case.roll.result == "high"
            ):
                return True
    return False


def available(state: GameState, source: ActorView, girl: ActorView) -> tuple[TagState, ...]:
    if (
        not original_target(source, girl)
        or source.cell != girl.cell
        or girl.inside_frame is None
        or state.world is None
        or not any(x.id == source.ref.entity and "mother" in x.types for x in state.world.gorgons)
        or immune(state, girl.ref)
    ):
        return ()
    return tuple(
        tag
        for tag in state.sheets[girl.ref.entity].tags
        if tag.giver_actor == source.ref and not tag.marked and not tag.rejection_pending
    )
