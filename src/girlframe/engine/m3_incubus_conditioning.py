"""An Incubus's original marked Tag, owned Heat roll, and durable consequences."""

from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model
from girlframe.engine.m3_hallucinations import Roll

PLAY = "incubus_conditioning"
RULE = "gorgon-type.incubus.emotional-conditioning"
KIND = "incubus_conditioning"


class Exposure(Model):
    action: str
    scene: str
    source: ActorRef
    girl: ActorRef
    tag: str
    mark_event: str
    roll: Roll | None = None
    completed: str | None = None
    tag_erased: bool = False
    void_event: str | None = None
    void_asset: str | None = None
    void_work: str | None = None
    child: str | None = None
    rebirth_event: str | None = None


def get(state: GameState, action: str) -> Exposure:
    raw = next(
        (x["body"] for x in state.facts if x.get("kind") == KIND and x.get("id") == action), None
    )
    if raw is None:
        raise ValueError("Recover the original actual Incubus exposure")
    return Exposure.model_validate_json(raw)


def put(state: GameState, exposure: Exposure) -> None:
    state.facts = [
        x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, exposure.action)
    ]
    state.facts.append(dict(kind=KIND, id=exposure.action, body=exposure.model_dump_json()))


def available(state: GameState, source: ActorView, girl: ActorView) -> tuple[TagState, ...]:
    if (
        source.ref.kind != "gorgon"
        or not source.alive
        or source.cell is None
        or source.offstage_source
        or girl.ref.kind != "pilot"
        or girl.rules != "girl_frame"
        or not girl.alive
        or girl.offstage_source
        or source.cell != girl.cell
        or state.world is None
        or not any(x.id == source.ref.entity and "incubus" in x.types for x in state.world.gorgons)
    ):
        return ()
    sheet = state.sheets[girl.ref.entity]
    return tuple(
        tag
        for tag in sheet.tags
        if not tag.marked and not tag.rejection_pending and tag.giver_actor == source.ref
    )
