"""The original bodies and receipts for Parasite infection (p. 174)."""

from typing import Literal

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model
from girlframe.engine.m3_grow_unreal import original_target
from girlframe.engine.m3_hallucinations import Roll
from girlframe.engine.m3_janus_storage import effective_assets
from girlframe.engine.m3_parasite import active as riding

RULE = "gorgon-type.parasite.infect"
PLAY = "parasite_infect"
KIND = "parasite_infection"
Loss = Literal["body", "memory", "emotion"]


class Excision(Model):
    scene: str
    doctor: ActorRef
    consent_event: str
    performed_event: str | None = None
    account: str | None = None


class Infection(Model):
    action: str
    scene: str
    source: ActorRef
    girl: ActorRef
    event: str
    damaged_asset: str | None = None
    damage_event: str | None = None
    damage_work: tuple[str, ...] = ()
    roll: Roll | None = None
    loss: Loss | None = None
    loss_account: str | None = None
    void_asset: str | None = None
    void_event: str | None = None
    void_work: str | None = None
    surgery_required: bool = False
    excision: Excision | None = None
    resolved: str | None = None
    interrupted: str | None = None


def records(state: GameState) -> tuple[Infection, ...]:
    return tuple(
        Infection.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def get(state: GameState, action: str) -> Infection | None:
    body = next(
        (x["body"] for x in state.facts if (x.get("kind"), x.get("id")) == (KIND, action)), None
    )
    return Infection.model_validate_json(body) if body else None


def put(state: GameState, value: Infection) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.action)]
    state.facts.append(dict(kind=KIND, id=value.action, body=value.model_dump_json()))


def reachable(state: GameState, source: ActorView, girl: ActorView) -> bool:
    return (
        original_target(source, girl)
        and source.cell == girl.cell
        and girl.inside_frame is not None
        and riding(state, source.ref) is None
    )


def assets(state: GameState, girl: ActorView, *, damaged_connection: bool) -> dict[str, str]:
    return {
        x.id: x.name
        for x in effective_assets(state, girl.ref)
        if x.void is damaged_connection
        and (not damaged_connection or not x.damaged)
        and (x.family == "girl" or girl.piloting is True)
    }
