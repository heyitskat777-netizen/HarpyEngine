"""Source-owned Void points; only the same genuinely connected Harpy activates them."""

from typing import TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_janus_link_state import BatteryLink

if TYPE_CHECKING:
    from girlframe.engine.m2 import GameState


class StoredVoid(Model):
    id: str
    actor: ActorRef
    core: ActorRef
    frame: str
    asset: str
    family: str
    purchase: str
    connection: str
    link: str
    action: str
    step: int
    choice: str
    source_event: str
    description: str = Field(min_length=1, max_length=1200)
    removed_event: str | None = None
    removed_period: str | None = None


def points(state: "GameState") -> tuple[StoredVoid, ...]:
    return tuple(
        StoredVoid.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "janus_stored_void"
    )


def put(state: "GameState", value: StoredVoid) -> None:
    body = dict(kind="janus_stored_void", body=value.model_dump_json())
    prior = next((x for x in points(state) if x.id == value.id), None)
    if prior:
        state.facts = [
            body
            if x.get("kind") == "janus_stored_void"
            and StoredVoid.model_validate_json(x["body"]).id == value.id
            else x
            for x in state.facts
        ]
    else:
        state.facts.append(body)


def live_link(
    state: "GameState", actor: ActorRef, core: ActorRef | None = None
) -> BatteryLink | None:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if sheet is None or sheet.character_id != actor.incarnation or sheet.frame_scrapped:
        return None
    links = [
        x
        for x in state.battery_links
        if x.caster == actor
        and x.phase == "connected"
        and x.effects_event
        and x.battery.kind == "external_pilot"
        and (core is None or x.battery == core)
        and x.caster_frame
        == (sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(actor.incarnation))
        and any(
            y.id == x.connection
            and y.phase == "connected"
            and y.caster == actor
            and y.battery == x.battery
            for y in state.neural_connections
        )
    ]
    return links[-1] if links else None


def active(state: "GameState", actor: ActorRef) -> tuple[StoredVoid, ...]:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if sheet is None or sheet.character_id != actor.incarnation:
        return ()
    return tuple(
        x
        for x in points(state)
        if x.actor == actor
        and not x.removed_event
        and x.frame
        == (sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(actor.incarnation))
        and any(a.id == x.asset and a.family == x.family for a in sheet.assets)
        and live_link(state, actor, x.core) is not None
    )


def store(
    state: "GameState",
    actor: ActorRef,
    *,
    asset: str,
    description: str,
    purchase: str,
    action: str,
    step: int,
    choice: str,
    event: str,
) -> StoredVoid:
    link = live_link(state, actor)
    if not isinstance(link, BatteryLink) or link.connection is None:
        raise ValueError("Store newly gained Void only in the actual connected Harpy")
    sheet = state.sheets[actor.entity]
    actual = next((x for x in sheet.assets if x.id == asset and not x.void), None)
    if (
        actual is None
        or not description.strip()
        or any(x.asset == asset for x in active(state, actor))
    ):
        raise ValueError("Choose an actual Asset without permanent or active stored Void")
    effective = {x.asset for x in active(state, actor)} | {asset}
    family = [x for x in sheet.assets if x.family == actual.family]
    if all(x.void or x.id in effective for x in family):
        raise ValueError("Threshold-completing stored Void is not yet supported; gain it normally")
    identity = str(uuid5(NAMESPACE_URL, "girlframe:stored-void:" + action + ":" + str(step)))
    if any(x.id == identity for x in points(state)):
        raise ValueError("This actual Void gain already owns its one stored point")
    value = StoredVoid(
        id=identity,
        actor=actor,
        core=link.battery,
        frame=link.caster_frame,
        asset=asset,
        family=actual.family,
        purchase=purchase,
        connection=link.connection,
        link=link.id,
        action=action,
        step=step,
        choice=choice,
        source_event=event,
        description=description,
    )
    put(state, value)
    for entry in sheet.identities:
        if entry.id not in sheet.sedation_locked:
            entry.marked = False
    sheet.revision += 1
    return value
