"""Sin of Temptation: one real Void onset for each actual Intense Harpy Bond change.

Book PDF180 / printed178. Restoring a relationship with set_depth is not a change.
This module records the consequence; it never substitutes a controller's character.
"""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model, ProfileBinding
from girlframe.engine.m3_bond_operations import Change

RULE = "harpy.harpy.sin-of-temptation"
NATIVE_RULE = "harpy.harpy.sin-of-temptation-native-pilot"


class Temptation(Model):
    id: str
    change: str
    source_event: str
    harpy: ActorRef
    actor: ActorRef
    controller: int
    source_action: str | None = None
    phase: Literal["rewrite", "threshold", "complete"] = "rewrite"
    asset: str | None = None
    description: str | None = None
    storage: bool = False
    gain_event: str | None = None
    thresholds: tuple[str, ...] = ()
    ended_event: str | None = None

    @model_validator(mode="after")
    def consistent(self) -> "Temptation":
        if (
            self.harpy.kind != "external_pilot"
            or self.harpy == self.actor
            or self.controller <= 0
            or (self.phase == "rewrite") != (self.gain_event is None)
            or (self.phase == "complete") != (self.ended_event is not None)
            or (self.phase == "threshold" and not self.thresholds)
            or (self.gain_event is not None and (self.asset is None or not self.description))
        ):
            raise ValueError("Preserve this actual Harpy Bond change and owned Void consequence")
        return self


def cases(state: GameState) -> tuple[Temptation, ...]:
    return tuple(
        Temptation.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "harpy_bond_void"
    )


def get(state: GameState, identity: str) -> Temptation:
    value = next((x for x in cases(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover this actual Harpy Bond's required Void onset")
    return value


def put(state: GameState, value: Temptation) -> None:
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "harpy_bond_void" and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind="harpy_bond_void", id=value.id, body=value.model_dump_json()))


def is_harpy(state: GameState, actor: ActorRef) -> bool:
    if actor.kind != "external_pilot":
        return False
    if any(x.id == actor.entity and x.alive for x in state.janus_cores):
        return True
    if any(x.id == actor.entity and x.alive for x in state.harpy_states):
        return True
    return bool(
        any(x.id == actor.entity for x in state.native_harpies)
        and state.world is not None
        and any(x.id == actor.entity and x.alive for x in state.world.pilots)
    )


def actual_girl(state: GameState, actor: ActorRef) -> ActorView:
    from girlframe.engine.m3_actors import resolve

    bindings = tuple(
        ProfileBinding(
            owner=int(uid),
            character_id=sheet.character_id,
            profile_revision=sheet.source_profile_revision,
            source_character_id=sheet.character_id,
            source_profile_revision=sheet.source_profile_revision,
        )
        for uid, sheet in state.sheets.items()
        if sheet.character_id is not None
    )
    return resolve(state, actor, bindings, require_current_profile=False)


def effect_id(change: Change, actor: ActorRef) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:harpy-bond-void:" + change.id + actor.token))


def produce(state: GameState, change: Change) -> GameState:
    """Called only after recording the genuine change, including a capped 2→2 gain."""
    if change.delta != 1 or change.before_depth < 1 or change.after_depth != 2:
        return state
    for harpy, actor in ((change.first, change.second), (change.second, change.first)):
        if not is_harpy(state, harpy):
            continue
        actual = actual_girl(state, actor)
        if actual.rules not in {"girl_frame", "handler_girl", "clone_am"}:
            continue
        identity = effect_id(change, actor)
        if any(x.id == identity for x in cases(state)):
            continue
        put(
            state,
            Temptation(
                id=identity,
                change=change.id,
                source_event=change.event,
                harpy=harpy,
                actor=actor,
                controller=actual.controller,
            ),
        )
    return state
