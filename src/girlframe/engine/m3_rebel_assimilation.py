"""An original group enters the Foundation and can grant a new work Play."""

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Faction

RULE = "strain.rebellion.endgame.4"
KIND = "rebel_group_assimilated"
USE = "foundation_employment_play_used"


class EmploymentPlay(Model):
    title: str = Field(min_length=1, max_length=100)
    trigger: str = Field(min_length=1, max_length=450)
    result: str = Field(min_length=1, max_length=450)


class Assimilation(Model):
    id: str
    original: Faction
    handler: ActorRef
    source: str
    rule: str
    event: str
    employment_play: EmploymentPlay | None = None


class WorkPlayUse(Model):
    id: str
    employment: str
    play_source: str
    handler: ActorRef
    scene: str
    account: str = Field(min_length=1, max_length=1200)


def assimilations(state: GameState) -> tuple[Assimilation, ...]:
    return tuple(
        Assimilation.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def work_plays(state: GameState, actor: ActorRef) -> tuple[Assimilation, ...]:
    if not same_handler_body(state, actor):
        return ()
    return tuple(
        x for x in assimilations(state) if x.handler == actor and x.employment_play is not None
    )


def assimilate(original: GameState, value: Assimilation) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    world = state.world
    if (
        world is None
        or value.original.kind != "rebel"
        or not value.original.active
        or value.original not in world.factions
        or not same_handler_body(state, value.handler)
        or any(x.id == value.id or x.original.id == value.original.id for x in assimilations(state))
    ):
        raise ValueError(
            "Recover the original active Rebel Group and source Handler before assimilation"
        )
    state.world = update(
        world,
        factions=tuple(
            x.model_copy(update=dict(kind="foundation")) if x.id == value.original.id else x
            for x in world.factions
        ),
    )
    state.facts.append(dict(kind=KIND, id=value.id, body=value.model_dump_json()))
    return state


def apply_play(state: GameState, value: Assimilation, use: WorkPlayUse) -> None:
    if (
        value not in work_plays(state, use.handler)
        or value.id != use.employment
        or value.event != use.play_source
        or state.world is None
        or not any(
            x.id == value.original.id and x.kind == "foundation" and x.active
            for x in state.world.factions
        )
        or any(x.get("kind") == USE and x.get("id") == use.id for x in state.facts)
    ):
        raise ValueError(
            "Use the original owned employment Play while its faction remains in the Foundation"
        )
    state.facts.append(dict(kind=USE, id=use.id, body=use.model_dump_json()))
