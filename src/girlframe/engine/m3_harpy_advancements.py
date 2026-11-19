"""Original Harpy advancements and their printed extra choices."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_strain_state import State as StrainState

SPARROWS = "harpy.harpy.sparrows-led-you-over-the-black-earth"
ECHOES = "harpy.harpy.echoes-of-old-command"
ONLY_SHE_MATTERS = "harpy.harpy.only-she-matters"
SONG_OF_LOVE_LOST = "harpy.harpy.a-song-of-love-lost"
EAGLE = "harpy.harpy.eagle-cracks-the-shell"
MANIC_PIXIE = "harpy.harpy.manic-pixie-dream-monster"
VISIONS = "harpy.harpy.visions-of-infinity"
NOTHING = "harpy.harpy.nothing-can-ever-be-as-important-as-us"
ADVANCEMENTS = (
    (SPARROWS, "Sparrows Led You Over the Black Earth"),
    (ECHOES, "Echoes of Old Command"),
    (ONLY_SHE_MATTERS, "Only She Matters"),
    (SONG_OF_LOVE_LOST, "A Song of Love Lost"),
    (EAGLE, "Eagle Cracks the Shell"),
    (MANIC_PIXIE, "Manic Pixie Dream Monster"),
    (VISIONS, "Visions of Infinity"),
    (NOTHING, "Nothing Can Ever Be As Important As Us"),
)
SPARROWS_CHOICES = (
    ("shadow", "I’m a shadow in the corner of their eye"),
    ("hands", "They feel my hands around their neck and my teeth on their ear"),
    ("haze", "Their mind is a haze as my voice worms its way into their brain"),
    ("eyes", "I capture their eyes in mine"),
)
KIND = "harpy_advancement"


class Advancement(Model):
    actor: ActorRef
    controller: int
    rule: str
    event: str
    capacity_source: str


def advances(state: GameState, actor: ActorRef) -> tuple[Advancement, ...]:
    return tuple(
        record
        for fact in state.facts
        if fact.get("kind") == KIND
        and (record := Advancement.model_validate_json(fact["body"])).actor == actor
    )


def strain_capacity(strain: StrainState | None) -> int:
    if strain is None:
        return 1
    if any(x.track == "void" for x in strain.endgames) or any(
        x.track == "void" and x.kind == "endgame" for x in strain.requests
    ):
        return 3
    if strain.levels["void"] == "high" or any(
        x.track == "void" and x.severity == "high" for x in strain.events
    ):
        return 2
    return 1


def add(state: GameState, record: Advancement, capacity: int) -> None:
    existing = advances(state, record.actor)
    if len(existing) >= capacity or any(x.rule == record.rule for x in existing):
        raise ValueError("Use an open advancement slot and a distinct actual Harpy advancement")
    state.facts.append(dict(kind=KIND, id=record.event, body=record.model_dump_json()))
