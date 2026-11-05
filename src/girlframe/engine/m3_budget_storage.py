"""Actual original ordinary Frame storage demands, never physical cockpit locks."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_battle import category
from girlframe.engine.m3_handler_consequences import active_handler, depart, same_handler_body
from girlframe.engine.m3_physical import occupied_frame
from girlframe.engine.m3_physical_state import Placement

RULE = "strain.budget.high.6.1"


class Entry(Model):
    action: Literal["store", "refuse", "warn", "fire", "release"]
    event: str
    actor: int
    account: str = Field(min_length=1, max_length=1200)
    proof: str | None = None


class Order(Model):
    id: str
    source_work: str
    source_event: str
    period: str
    handler: ActorRef
    appointment: str
    owner: ActorRef
    frame: str
    base: str
    cell: tuple[int, int]
    superior: ActorRef
    controller: int
    account: str = Field(min_length=1, max_length=2400)
    phase: Literal["active", "released", "fired"] = "active"
    entries: tuple[Entry, ...] = ()


def orders(state: GameState) -> tuple[Order, ...]:
    return tuple(
        Order.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "budget_storage"
    )


def get(state: GameState, identity: str) -> Order:
    value = next((x for x in orders(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Open the original higher-up Frame storage order")
    return value


def put(state: GameState, value: Order) -> None:
    state.facts = [
        x
        for x in state.facts
        if not (x.get("kind") == "budget_storage" and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind="budget_storage", id=value.id, body=value.model_dump_json()))


def pose(state: GameState, value: Order) -> Placement:
    sheet = state.sheets.get(value.owner.entity)
    actual = next((x for x in state.placements if x.actor == value.owner), None)
    frame = (
        sheet.frame_runtime.id
        if sheet and sheet.frame_runtime
        else "initial:" + str(sheet.character_id)
        if sheet
        else None
    )
    if (
        sheet is None
        or sheet.character_id != value.owner.incarnation
        or int(value.owner.entity) not in state.order
        or frame != value.frame
        or sheet.frame_scrapped
        or actual is None
        or actual.frame_instance != frame
        or actual.frame_cell is None
        or actual.girl_cell is None
        or actual.custody is not None
        or actual.subsumed
        or any(x.origin == value.owner for x in state.harpy_states)
        or any(x.actor == value.owner and x.gorgon is not None for x in state.void_thresholds)
        or any(
            x.active and value.owner in (x.traveler, x.supervisor) or value.owner in x.offstage_refs
            for x in state.escort_journeys
        )
        or any(
            x.frame_owner == value.owner and x.frame_instance == frame and (x.attached or x.linked)
            for x in state.janus_cores
        )
        or any(
            x.caster_frame_owner == value.owner
            and x.caster_frame == frame
            and x.phase not in ("unplugged", "ended")
            for x in state.battery_links
        )
        or any(
            x.frame_owner == value.owner and x.frame_instance == frame and x.phase == "connected"
            for x in state.neural_connections
        )
        or any(
            x.frame_owner == value.owner and x.frame_instance == frame and x.active
            for x in state.frame_commands
        )
    ):
        raise ValueError(
            "SOURCE_PORT_REQUIRED: recover the original known ordinary Frame pose; "
            "custody, transformation and neural control need their own source resolution"
        )
    return actual


def empty_at_base(state: GameState, value: Order) -> Placement:
    actual = pose(state, value)
    base = (
        next((x for x in state.world.locations if x.id == value.base), None)
        if state.world
        else None
    )
    if (
        base is None
        or base.kind != "base"
        or base.allegiance != "foundation"
        or base.condition == "destroyed"
        or base.cell != value.cell
        or actual.frame_cell != value.cell
        or any(occupied_frame(x) == (value.owner, value.frame) for x in state.placements)
        or any(
            x.carrier == value.owner and x.frame == value.frame and x.state == "boarded"
            for x in state.passengers
        )
        or any(
            x.owner == value.owner and x.frame_instance == value.frame and x.active
            for x in state.frame_locks
        )
    ):
        raise ValueError(
            "Storage needs this exact Frame already at its surviving Foundation base, "
            "empty and unpiloted, with every cockpit/passenger occupant resolved"
        )
    return actual


def create(
    state: GameState,
    work: str,
    period: str,
    event: str,
    owner: int,
    base: str,
    npc: str,
    appointment: str,
    account: str,
) -> GameState:
    handler = active_handler(state)
    superior = ActorRef(kind="npc", entity=npc)
    body = next((x for x in state.world.npcs if x.id == npc), None) if state.world else None
    site = next((x for x in state.world.locations if x.id == base), None) if state.world else None
    if owner not in state.order or str(owner) not in state.sheets:
        raise ValueError("Choose the original current ordinary Pilot Frame owner")
    person = current_ref(state, owner)
    sheet = state.sheets[person.entity]
    if (
        handler is None
        or not appointment
        or state.strain is None
        or state.strain.levels["budget"] != "high"
        or body is None
        or category(state, superior) != "npc"
        or not body.alive
        or body.controller is None
        or site is None
        or site.kind != "base"
        or site.allegiance != "foundation"
        or site.condition == "destroyed"
        or any(x.source_work == work for x in orders(state))
    ):
        raise ValueError(
            "Choose the actual claimed ordinary higher-up, original current Frame, "
            "surviving Foundation base and High Budget source"
        )
    value = Order(
        id=work + ":storage",
        source_work=work,
        source_event=event,
        period=period,
        handler=handler,
        appointment=appointment,
        owner=person,
        frame=sheet.frame_runtime.id
        if sheet.frame_runtime
        else "initial:" + str(sheet.character_id),
        base=base,
        cell=site.cell,
        superior=superior,
        controller=body.controller,
        account=account,
    )
    pose(state, value)
    changed = GameState.model_validate_json(state.model_dump_json())
    put(changed, value)
    return changed


def apply(
    original: GameState,
    value: Order,
    action: str,
    actor: int,
    event: str,
    account: str,
    *,
    proof: str | None = None,
    label: str = "",
) -> GameState:
    if value.phase != "active" or not same_handler_body(original, value.handler):
        raise ValueError("Recover the original active storage order and original Handler body")
    state = GameState.model_validate_json(original.model_dump_json())
    if action == "store":
        if actor != int(value.owner.entity):
            raise ValueError("Only the original Frame owner records actual storage")
        empty_at_base(state, value)
    elif action == "refuse":
        if actor != int(value.handler.entity):
            raise ValueError("Only the original Handler authors their own actual refusal")
    elif action == "warn":
        if actor != value.controller or not proof or not label.strip() or len(label) > 120:
            raise ValueError("The actual higher-up owns the warning Tag after a proved breach")
        if any(x.action == "warn" for x in value.entries):
            raise ValueError("This actual original storage warning was already given")
        state.handler_tags.append(
            TagState(
                id="storage-warning:" + value.id,
                label=label.strip(),
                giver=actor,
                giver_actor=value.superior,
                observers=(int(value.handler.entity), actor),
            )
        )
    elif action == "fire":
        if (
            actor != value.controller
            or not proof
            or not any(x.action == "warn" for x in value.entries)
        ):
            raise ValueError("Firing needs the actual higher-up, prior warning and renewed breach")
        from girlframe.engine.m3_battle import end_actor_casts

        state = depart(
            state,
            value.handler,
            reason="fired",
            source_work=value.id,
            event=event,
            appointment=value.appointment,
            account=account,
        )
        state = end_actor_casts(state, value.handler, event)
    elif action == "release":
        if (
            actor not in (value.controller, int(value.handler.entity), int(value.owner.entity))
            or not proof
        ):
            raise ValueError("Release needs an actual later canonical Budget reduction")
    else:
        raise ValueError("Choose an actual storage response")
    entry = Entry.model_validate(
        dict(action=action, event=event, actor=actor, account=account, proof=proof)
    )
    value = value.model_copy(
        update=dict(
            entries=(*value.entries, entry),
            phase="fired" if action == "fire" else "released" if action == "release" else "active",
        )
    )
    put(state, value)
    return GameState.model_validate_json(state.model_dump_json())
