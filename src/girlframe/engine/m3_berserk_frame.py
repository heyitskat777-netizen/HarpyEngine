"""The original Frame becomes a real Aggressive Gorgon on its next activation."""

from pydantic import Field

from girlframe.engine.frame_classes import frame_class
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model, ProfileBinding
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_world_state import Gorgon

RULE = "strain.void.high.4.1"
KIND = "strain_berserk_frame"


class Threat(Model):
    id: str
    source: str
    handler: ActorRef
    owner: ActorRef
    frame: str
    design: Gorgon
    victim: str
    account: str = Field(min_length=1, max_length=1200)
    activated: str | None = None
    defeated: str | None = None


def threats(state: GameState) -> tuple[Threat, ...]:
    return tuple(
        Threat.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def save(state: GameState, threat: Threat) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, threat.id)] + [
        dict(kind=KIND, id=threat.id, body=threat.model_dump_json())
    ]


def eligible(state: GameState) -> tuple[ActorRef, ...]:
    roster = tuple(
        current_ref(state, owner)
        for owner in state.order
        if (sheet := state.sheets.get(str(owner))) is not None
        and sheet.character_id is not None
        and not sheet.frame_scrapped
    )
    priestesses = tuple(
        x for x in roster if frame_class(state.sheets[x.entity].frame) == "priestess"
    )
    return priestesses or roster


def arm(
    state: GameState,
    identity: str,
    source: str,
    owner: int,
    design: Gorgon,
    victim: str,
    account: str,
) -> None:
    from girlframe.engine.m3_actors import frame_position, resolve
    from girlframe.engine.m3_battle import category
    from girlframe.engine.m3_world import validate_initial_gorgon

    actor = current_ref(state, owner)
    if actor not in eligible(state):
        raise ValueError("Choose an original Priestess Frame when one is available")
    sheet = state.sheets[actor.entity]
    frame = sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(sheet.character_id)
    world = state.world
    handler = active_handler(state)
    cell = frame_position(state, actor, frame)
    candidate = next((x for x in world.npcs if x.id == victim and x.alive), None) if world else None
    victim_ref = ActorRef(kind="npc", entity=victim)
    if (
        world is None
        or handler is None
        or design.cell is not None
        or design.gorgon_class != "aggressive"
        or candidate is None
        or category(state, victim_ref) != "npc"
        or cell is None
        or resolve(state, victim_ref, ()).cell != cell
        or any(
            x.id == design.id
            for x in (*world.gorgons, *world.npcs, *world.pilots, *world.locations, *world.factions)
        )
        or any(
            x.id == identity
            or x.design.id == design.id
            or (x.frame == frame and x.defeated is None)
            for x in threats(state)
        )
    ):
        raise ValueError(
            "Save a new Aggressive form and an actual eligible NPC for the original Frame"
        )
    validate_initial_gorgon(design)
    save(
        state,
        Threat(
            id=identity,
            source=source,
            handler=handler,
            owner=actor,
            frame=frame,
            design=design,
            victim=victim,
            account=account,
        ),
    )


def active(state: GameState, owner: ActorRef, frame: str) -> Threat | None:
    return next(
        (
            x
            for x in threats(state)
            if x.owner == owner and x.frame == frame and x.activated and not x.defeated
        ),
        None,
    )


def activate(
    state: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    frame: str,
    event: str,
) -> GameState | None:
    threat = next(
        (
            x
            for x in threats(state)
            if x.owner == actor and x.frame == frame and x.activated is None
        ),
        None,
    )
    if threat is None:
        return None
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_battle import category
    from girlframe.engine.m3_gorgon_arrival import aggressive_casualty
    from girlframe.engine.m3_physical import lock_cockpit
    from girlframe.engine.m3_world import introduce_gorgon

    placement = next((x for x in state.placements if x.actor == actor), None)
    world = state.world
    victim = (
        next((x for x in world.npcs if x.id == threat.victim and x.alive), None) if world else None
    )
    if (
        world is None
        or placement is None
        or placement.frame_cell is None
        or victim is None
        or category(state, ActorRef(kind="npc", entity=victim.id)) != "npc"
        or resolve(state, ActorRef(kind="npc", entity=victim.id), (), require_alive=False).cell
        != placement.frame_cell
    ):
        raise ValueError(
            "UNRESOLVED_BERSERK_ARRIVAL: recover the actual NPC at the activating Frame's square"
        )
    gorgon = threat.design.model_copy(
        update=dict(cell=placement.frame_cell, position_event=event, revealed=True)
    )
    state = lock_cockpit(state, bindings, actor, event, threat.account)
    state.world = introduce_gorgon(world, gorgon, event=event).world
    state = aggressive_casualty(state, gorgon, victim, threat.id, event, threat.account)
    save(state, threat.model_copy(update=dict(activated=event)))
    return state


def record_defeat(state: GameState, target: ActorRef, event: str) -> None:
    if target.kind != "gorgon" or state.world is None:
        return
    threat = next(
        (
            x
            for x in threats(state)
            if x.design.id == target.entity and x.activated and not x.defeated
        ),
        None,
    )
    if threat is None:
        return
    slain = next((x for x in state.world.gorgons if x.id == target.entity and not x.alive), None)
    if slain is None:
        raise ValueError("Recover the actual Berserk Gorgon's defeat")
    state.placements = [
        pose.model_copy(
            update=dict(
                girl_cell=slain.cell, frame_cell=slain.cell, mode="inside_frame", source_event=event
            )
        )
        if pose.actor == threat.owner and pose.frame_instance == threat.frame and pose.subsumed
        else pose
        for pose in state.placements
    ]
    save(state, threat.model_copy(update=dict(defeated=event)))
