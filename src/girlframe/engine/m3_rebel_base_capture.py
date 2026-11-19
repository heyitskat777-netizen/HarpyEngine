"""High Rebellion changes the original site's control, occupants and Frame custody."""

from pydantic import Field

from girlframe.engine.m2 import GameState, PilotSheet
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_physical_state import ParkedFrame
from girlframe.engine.m3_promotional_opportunity import in_responsibility
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import AdversaryPilot, Location, Model, Npc, WorldLoss

RULE = "strain.rebellion.high.2.1"
KIND = "strain_rebel_base_capture"


class Capture(Model):
    id: str
    source: str
    base: str
    faction: str
    attacker: ActorRef
    handler: ActorRef
    frame: ParkedFrame
    released: tuple[Npc, ...]
    killed: tuple[Npc, ...]
    account: str = Field(min_length=1, max_length=1200)


def captures(state: GameState) -> tuple[Capture, ...]:
    return tuple(
        Capture.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def site(state: GameState, identity: str) -> Location:
    base = (
        next((x for x in state.world.locations if x.id == identity), None) if state.world else None
    )
    handler = active_handler(state)
    if (
        base is None
        or base.kind != "base"
        or not base.foundation_operational
        or handler is None
        or not in_responsibility(state, base.cell)
    ):
        raise ValueError("Use an operational Foundation base in this Handler's actual region")
    body = resolve(state, handler, ())
    if body.cell == base.cell or (body.cell is None and body.offstage_source is None):
        raise ValueError("Prove the original Handler is actually away from this base")
    return base


def rebel(state: GameState, actor: str, base: Location) -> AdversaryPilot:
    world = state.world
    pilot = next((x for x in world.pilots if x.id == actor), None) if world else None
    if (
        world is None
        or pilot is None
        or not pilot.alive
        or pilot.kind != "rebel"
        or pilot.custody != "free"
        or resolve(state, ActorRef(kind="external_pilot", entity=actor), ()).cell != base.cell
        or not any(x.id == pilot.faction and x.active and x.kind == "rebel" for x in world.factions)
    ):
        raise ValueError("Choose the actual active Rebel officer at the overrun base")
    return pilot


def frames(state: GameState, base: Location) -> tuple[ParkedFrame, ...]:
    return tuple(
        x
        for x in state.parked_frames
        if x.cell == base.cell
        and x.core_id is None
        and not any(
            p.frame_instance == x.frame_instance or p.occupied_frame_instance == x.frame_instance
            for p in state.placements
        )
        and not any(
            lock.frame_instance == x.frame_instance and lock.active for lock in state.frame_locks
        )
        and not any(p.frame == x.frame_instance and p.state == "boarded" for p in state.passengers)
        and any(
            a.family == "frame" and not a.damaged
            for a in PilotSheet.model_validate_json(x.frame_json).assets
        )
    )


def occupants(state: GameState, base: Location) -> tuple[tuple[Npc, ...], tuple[Npc, ...]]:
    if state.world is None:
        return (), ()
    present = tuple(
        x
        for x in state.world.npcs
        if x.alive
        and x.source_kind is None
        and x.captive_of is None
        and ("prisoner" in x.jobs or x.employment == "foundation")
        and resolve(state, ActorRef(kind="npc", entity=x.id), ()).cell == base.cell
    )
    return (
        tuple(x for x in present if "prisoner" in x.jobs),
        tuple(x for x in present if "prisoner" not in x.jobs and x.employment == "foundation"),
    )


def apply(
    state: GameState,
    work: str,
    event: str,
    base_id: str,
    attacker: str,
    instance: str,
    account: str,
) -> GameState:
    from girlframe.engine.m3_battle import category, end_actor_casts
    from girlframe.engine.m3_battle_director import die as end_director
    from girlframe.engine.m3_enforcer import end_grasps
    from girlframe.engine.m3_physical import interrupt_journeys

    base = site(state, base_id)
    assailant = rebel(state, attacker, base)
    captured = next((x for x in frames(state, base) if x.frame_instance == instance), None)
    handler = active_handler(state)
    if (
        state.world is None
        or handler is None
        or captured is None
        or assailant.faction is None
        or any(x.id == work for x in captures(state))
    ):
        raise ValueError("Transfer one actual original unoccupied parked Frame already at the base")
    released, killed = occupants(state, base)
    if any(not x.custody_event for x in released) or any(
        category(state, ActorRef(kind="npc", entity=x.id)) == "harpy" for x in killed
    ):
        raise ValueError(
            "Recover actual prisoner custody and any special Core body before applying losses"
        )
    captor = ActorRef(kind="external_pilot", entity=assailant.id)
    receipt = Capture(
        id=work,
        source=event,
        base=base.id,
        faction=assailant.faction,
        attacker=captor,
        handler=handler,
        frame=captured,
        released=released,
        killed=killed,
        account=account,
    )
    for person in killed:
        ref = ActorRef(kind="npc", entity=person.id)
        if "director" in person.jobs:
            state = end_director(state, ref, event, account)
        else:
            state = end_actor_casts(
                end_grasps(interrupt_journeys(state, ref, event, account), ref, event), ref, event
            )
    assert state.world is not None
    state.world = update(
        state.world,
        locations=tuple(
            x.model_copy(
                update=dict(
                    control_loss=WorldLoss(
                        source=work, event=event, kind="captured", threat=captor, account=account
                    )
                )
            )
            if x.id == base.id
            else x
            for x in state.world.locations
        ),
        npcs=tuple(
            x.model_copy(
                update=dict(
                    jobs=tuple(j for j in x.jobs if j != "prisoner") or ("civilian",),
                    custody_event=None,
                )
            )
            if x.id in {p.id for p in released}
            else x.model_copy(update=dict(alive=False))
            if x.id in {p.id for p in killed}
            else x
            for x in state.world.npcs
        ),
    )
    state.parked_frames = [x for x in state.parked_frames if x.frame_instance != instance]
    state.facts.append(dict(kind=KIND, id=work, body=receipt.model_dump_json()))
    return state
