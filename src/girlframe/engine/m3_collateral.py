"""Actual collateral destroys concrete things and preserves source-bound job-loss facts."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_strain_state import Trigger
from girlframe.engine.m3_world import destroy
from girlframe.engine.m3_world_state import Cell


class Target(Model):
    actor: ActorRef
    asset: str | None = None


class Selection(Model):
    structures: tuple[str, ...] = Field(default=(), max_length=25)
    objects: tuple[str, ...] = Field(default=(), max_length=25)
    assets: tuple[Target, ...] = Field(default=(), max_length=25)
    ordinary: tuple[str, ...] = Field(default=(), max_length=25)
    account: str = Field(min_length=1, max_length=2000)
    reach: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def real_targets(self) -> "Selection":
        if (
            not (self.structures or self.objects or self.assets or self.ordinary)
            or len(set(self.structures)) != len(self.structures)
            or len(set(self.objects)) != len(self.objects)
            or len({(x.actor.token, x.asset) for x in self.assets}) != len(self.assets)
            or any(not x.strip() for x in self.ordinary)
            or not self.account.strip()
            or not self.reach.strip()
        ):
            raise ValueError("Choose distinct concrete collateral and record actual causal reach")
        return self


class Source(Model):
    id: str
    action: str
    choice: str
    event: str
    actor: ActorRef
    actor_controller: int
    judge: int
    appointment: str
    handler: ActorRef | None = None
    gorgon_cause: bool = False


class Arrival(Model):
    actor: ActorRef
    cell: Cell
    frame_arrived: bool = False
    frame_cell: Cell | None = None
    event: str
    account: str = Field(min_length=1, max_length=1200)


class Loss(Model):
    id: str
    source: str
    source_event: str
    handler: ActorRef | None
    judge: int
    appointment: str
    phase: Literal["employment", "outcome", "handler", "transport", "execution", "complete"] = (
        "employment"
    )
    employment: Literal["retained", "fired", "imprisoned", "retired"] | None = None
    outcome: Literal["new_handler", "reassigned", "execution"] | None = None
    response_event: str | None = None
    account: str = ""
    replacement: ActorRef | None = None
    cadre: tuple[ActorRef, ...] = ()
    creation: str | None = None
    executor: ActorRef | None = None
    new_world_json: str | None = None
    quadrant: str | None = None
    arrivals: tuple[Arrival, ...] = ()


def loss(state: GameState, identity: str) -> Loss:
    raw = next(
        (
            x
            for x in reversed(state.facts)
            if x.get("kind") == "quadrant_loss" and x.get("id") == identity
        ),
        None,
    )
    if raw is None:
        raise ValueError("Recover the actual original first Base-loss episode")
    return Loss.model_validate_json(raw["body"])


def save_loss(state: GameState, value: Loss) -> None:
    state.facts.append(dict(kind="quadrant_loss", id=value.id, body=value.model_dump_json()))


def install_budget(state: GameState) -> None:
    if state.strain is None:
        return
    ids = {x.id for x in state.strain.triggers}
    additions = []
    for row in state.facts:
        if row.get("kind") != "structure_destroyed_source" or row["id"] in ids:
            continue
        additions.append(
            Trigger(
                id=row["id"],
                kind="structure_destroyed",
                entity=row["entity"],
                source_event=row["event"],
            )
        )
        ids.add(row["id"])
    if additions:
        state.strain = state.strain.model_copy(
            update={"triggers": state.strain.triggers + tuple(additions)}
        )


def stage_loss(
    original: GameState,
    state: GameState,
    *,
    source: str,
    event: str,
    judge: int,
    appointment: str,
    handler: ActorRef | None,
) -> Loss | None:
    if original.world is None or state.world is None:
        return None
    before = any(
        x.kind == "base" and x.allegiance == "foundation" and x.condition != "destroyed"
        for x in original.world.locations
    )
    after = any(
        x.kind == "base" and x.allegiance == "foundation" and x.condition != "destroyed"
        for x in state.world.locations
    )
    if not before or after:
        return None
    identity = str(uuid5(NAMESPACE_URL, "actual-quadrant-loss:" + event))
    value = Loss(
        id=identity,
        source=source,
        source_event=event,
        handler=handler,
        judge=judge,
        appointment=appointment,
        phase="employment" if handler else "outcome",
        cadre=tuple(
            ActorRef(
                kind="pilot", entity=str(uid), incarnation=original.sheets[str(uid)].character_id
            )
            for uid in original.order
        ),
    )
    save_loss(state, value)
    return value


def perform(
    original: GameState, source: Source, choice: Selection, event: str
) -> tuple[GameState, Loss | None]:
    state = GameState.model_validate_json(original.model_dump_json())
    choice = Selection.model_validate_json(choice.model_dump_json())
    if not event or any(
        x.get("kind") == "collateral_performed" and x.get("id") == source.id for x in state.facts
    ):
        raise ValueError("Apply this actual source collateral once")
    if choice.structures and state.world is None:
        raise ValueError("Choose actual canonical structures")
    bases = (
        tuple(
            x.id
            for x in state.world.locations
            if x.kind == "base" and x.allegiance == "foundation" and x.condition != "destroyed"
        )
        if state.world
        else ()
    )
    for identity in choice.structures:
        assert state.world is not None
        state.world = destroy(state.world, identity, gorgon_cause=source.gorgon_cause).world
        if not any(x.id == identity and x.condition == "destroyed" for x in state.world.locations):
            continue  # Real Armoured interception is not destruction or a Budget trigger.
        stamp = str(uuid5(NAMESPACE_URL, "actual-structure:" + identity + ":" + event))
        state.facts.append(
            dict(
                kind="structure_destroyed_source",
                id=stamp,
                entity=identity,
                event=event,
                source=source.id,
            )
        )
    for identity in choice.objects:
        item = next((x for x in state.held_items if x.id == identity), None)
        if item is None or item.asset_json is not None or item.condition != "intact":
            raise ValueError(
                "Destroy an actual nonmechanical held object; "
                "mechanical Assets use their real damage port"
            )
        state.facts.append(
            dict(
                kind="held_object_destroyed",
                id=item.id,
                body=item.model_dump_json(),
                event=event,
                source=source.id,
            )
        )
        state.held_items = [
            x.model_copy(update=dict(condition="ruined", state_event=event))
            if x.id == item.id
            else x
            for x in state.held_items
        ]
    install_budget(state)
    value = None
    if (
        bases
        and state.world
        and not any(
            x.kind == "base" and x.allegiance == "foundation" and x.condition != "destroyed"
            for x in state.world.locations
        )
    ):
        # A later City loss cannot create a second episode from an already-lost quadrant.
        identity = str(uuid5(NAMESPACE_URL, "actual-quadrant-loss:" + event))
        value = Loss(
            id=identity,
            source=source.id,
            source_event=event,
            handler=source.handler,
            judge=source.judge,
            appointment=source.appointment,
            cadre=tuple(
                ActorRef(
                    kind="pilot", entity=str(uid), incarnation=state.sheets[str(uid)].character_id
                )
                for uid in state.order
            ),
        )
        save_loss(state, value)
    state.facts.append(
        dict(
            kind="collateral_performed",
            id=source.id,
            event=event,
            source=source.model_dump_json(),
            selection=choice.model_dump_json(),
        )
    )
    return state, value
