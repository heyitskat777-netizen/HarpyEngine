"""Source-owned Void points; only the same genuinely connected Harpy activates them."""

from typing import TYPE_CHECKING, Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field

from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_janus_link_state import BatteryLink

if TYPE_CHECKING:
    from girlframe.engine.m2 import AssetState, GameState
    from girlframe.engine.m3_core import Followup


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
    source_kind: str = Field(default="dive_deep", exclude_if=lambda value: value == "dive_deep")
    removed_event: str | None = None
    removed_period: str | None = None


class GainSource(Model):
    purchase: str
    choice: str
    kind: Literal["dive_deep", "mockingbird_risk", "mockingbird_sex", "dormant_void", "call_guest"]
    action: str | None = None


def effective_assets(state: "GameState", actor: ActorRef) -> tuple["AssetState", ...]:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if sheet is None or sheet.character_id != actor.incarnation:
        return ()
    changes = {x.asset: x for x in active(state, actor)}
    return tuple(
        x.model_copy(update={"void": True, "description": changes[x.id].description})
        if x.id in changes
        else x
        for x in sheet.assets
    )


def effective_for_owner(state: "GameState", owner: str | int) -> tuple["AssetState", ...]:
    sheet = state.sheets.get(str(owner))
    if sheet is None:
        return ()
    if sheet.character_id is None:
        return tuple(sheet.assets)
    return effective_assets(
        state, ActorRef(kind="pilot", entity=str(owner), incarnation=sheet.character_id)
    )


def ids(state: "GameState", actor: ActorRef) -> frozenset[str]:
    return frozenset(x.asset for x in active(state, actor))


def for_family(state: "GameState", actor: ActorRef, family: str) -> tuple[StoredVoid, ...]:
    assets = {x.id for x in effective_assets(state, actor) if x.family == family}
    return tuple(x for x in active(state, actor) if x.asset in assets)


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
        and any(a.id == x.asset and not a.void for a in sheet.assets)
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
    source_kind: str = "dive_deep",
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
    identity = str(
        uuid5(
            NAMESPACE_URL,
            "girlframe:stored-void:" + action + ":" + actor.token + ":" + choice + ":" + str(step),
        )
    )
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
        source_kind=source_kind,
    )
    put(state, value)
    sheet.revision += 1
    return value


def alter(
    original: "GameState",
    actor: ActorRef,
    asset: str,
    description: str,
    action: str,
    event: str,
    *,
    piloting: bool,
    source: GainSource | None = None,
    step: int = 0,
) -> tuple["GameState", tuple["Followup", ...]]:
    from girlframe.engine.m2 import GameState
    from girlframe.engine.m3_core import corrupt, void_followups

    state = GameState.model_validate_json(original.model_dump_json())
    if source is not None:
        store(
            state,
            actor,
            asset=asset,
            description=description,
            purchase=source.purchase,
            action=source.action or action,
            step=step,
            choice=source.choice,
            event=event,
            source_kind=source.kind,
        )
        return state, void_followups(
            state.sheets[actor.entity], piloting=piloting, effective_void=ids(state, actor)
        )
    result = corrupt(
        state.sheets[actor.entity],
        asset,
        description,
        piloting=piloting,
        effective_void=ids(state, actor),
    )
    state.sheets[actor.entity] = result.sheet
    return state, result.followups


def full_family(state: "GameState", actor: ActorRef, family: str) -> bool:
    assets = [x for x in effective_assets(state, actor) if x.family == family]
    return bool(assets) and all(x.void for x in assets)


def end_inactive_causes(state: "GameState", event: str) -> tuple[str, ...]:
    from girlframe.engine.m3_girl_runtime_state import has_rule
    from girlframe.engine.m3_physical import occupied_frame
    from girlframe.engine.m3_void import FINAL

    ended = []
    for value in tuple(state.void_thresholds):
        if (
            value.storage_points
            and value.stage == "prevented"
            and value.allure_persists
            and not full_family(state, value.actor, "girl")
        ):
            state.void_thresholds = [
                x.model_copy(update={"allure_persists": False}) if x.id == value.id else x
                for x in state.void_thresholds
            ]
        if (
            not value.storage_points
            or value.stage in FINAL
            or full_family(state, value.actor, value.family)
        ):
            continue
        sheet = state.sheets.get(value.actor.entity)
        girls = bool(
            sheet
            and full_family(state, value.actor, "girl")
            and not has_rule(sheet, "girl.mockingbird.risk-factor", "MOCKINGBIRD")
        )
        frames = full_family(state, value.actor, "frame")
        if girls or frames:
            body = next((x for x in state.placements if x.actor == value.actor), None)
            own = bool(body and occupied_frame(body) == (value.actor, value.frame_instance))
            family = "frame" if frames else "girl"
            stage = (
                value.stage
                if value.stage in ("questions", "rebirth")
                else "physical_review"
                if body is None
                else "enclosed"
                if frames and own
                else "abandoned"
                if frames
                else "questions"
                if own
                else "allured"
            )
            retained = value.model_copy(
                update={
                    "family": family,
                    "stage": stage,
                    "enclosed": frames and own,
                    "allure_persists": girls,
                }
            )
            state.void_thresholds = [
                retained if x.id == value.id else x for x in state.void_thresholds
            ]
            continue
        replacement = value.model_copy(
            update={"stage": "prevented", "response_event": event, "allure_persists": False}
        )
        state.void_thresholds = [
            replacement if x.id == value.id else x for x in state.void_thresholds
        ]
        state.facts.append(dict(kind="janus_storage_cause_ended", threshold=value.id, event=event))
        ended.append(value.id)
    return tuple(ended)
