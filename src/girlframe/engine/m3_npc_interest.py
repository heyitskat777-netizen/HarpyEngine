"""Keep the original NPC's Void gain and the Girl's discovery in printed order."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.engine.m3_npc_void import npc_void_tag
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Npc

RULE = "strain.void.low.5.2"
KIND = "strain_npc_void_interest"
Timing = Literal["before", "after"]


class Interest(Model):
    id: str
    event: str
    period: str
    npc: ActorRef
    girl: ActorRef
    handler: ActorRef
    timing: Timing
    account: str = Field(min_length=1, max_length=1200)
    gain_event: str | None = None
    tag: str | None = None
    seen_event: str | None = None
    seen_scene: str | None = None
    seen_account: str | None = None
    seen_tag: str | None = None

    @property
    def complete(self) -> bool:
        return bool(self.gain_event and self.seen_event)


def interests(state: GameState) -> tuple[Interest, ...]:
    return tuple(
        Interest.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def save(state: GameState, value: Interest) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.id)] + [
        dict(kind=KIND, id=value.id, body=value.model_dump_json()),
    ]


def ordinary_npc(state: GameState, case: Interest) -> Npc:
    npc = (
        next((x for x in state.world.npcs if x.id == case.npc.entity), None)
        if state.world
        else None
    )
    if (
        npc is None
        or not npc.alive
        or npc.captive_of is not None
        or npc.source_kind is not None
        or "director" in npc.jobs
        or npc.controller != int(case.handler.entity)
        or not same_handler_body(state, case.handler)
    ):
        raise ValueError("Use the original living ordinary NPC under the source Handler's control")
    return npc


def gain(state: GameState, case: Interest, manifestation: str, event: str) -> Interest:
    if case.gain_event is not None or (case.timing == "before" and not case.seen_event):
        raise ValueError("Apply only the pending gain after its original discovery")
    npc = ordinary_npc(state, case)
    tag = npc_void_tag(
        str(uuid5(NAMESPACE_URL, "girlframe:npc-void-interest:" + case.id)),
        manifestation,
        case.handler.model_dump_json(),
    )
    assert state.world is not None
    state.world = update(
        state.world,
        npcs=tuple(
            x.model_copy(update={"tags": (*x.tags, tag)}) if x.id == npc.id else x
            for x in state.world.npcs
        ),
    )
    return case.model_copy(update={"tag": tag.id, "gain_event": event})


def known_void_tags(state: GameState, ref: ActorRef) -> tuple[str, ...]:
    return tuple(x.tag for x in interests(state) if x.npc == ref and x.tag is not None)
