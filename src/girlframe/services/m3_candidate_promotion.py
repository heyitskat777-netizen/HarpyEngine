"""Keep an ordinary Pilot Candidate's identity through actual licensed activation."""

from girlframe.engine import m3_budget_candidate as budget
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import migrate_actor, rebind
from girlframe.engine.m3_actor_state import ActorRef, CastRole
from girlframe.engine.m3_actors import fingerprint
from girlframe.engine.m3_ancillary import Offer
from girlframe.engine.m3_leviathan_arrival import install_external_pose
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Location, Npc
from girlframe.services.onboarding import WorkflowError

RULE = "npc.npc.pilot-candidate"
KIND = "pilot_candidate_promoted"


def eligible(state: GameState, npc: Npc) -> bool:
    world = state.world
    if world is None or not npc.alive or npc.captive_of or npc.custody_event:
        return False
    ref = ActorRef(kind="npc", entity=npc.id)
    return bool(
        "pilot_candidate" in npc.jobs
        and set(npc.jobs) <= {"pilot_candidate", "base_personnel"}
        and not npc.tags
        and not npc.bonds
        and not npc.secret_factions
        and not any(x.manager == npc.id for x in world.field_studies)
        and not any(npc.id in r.staff_ids for r in world.regions)
        and not any(
            g.goal and g.goal.kind == "npc" and g.goal.entity_id == npc.id for g in world.gorgons
        )
        and not any(x.state == "pending" and x.npc.id == npc.id for x in world.npc_role_offers)
        and not any(r.npc == npc.id for r in world.starting_npc_links)
        and not any(r.leader == npc.id for r in world.factions)
        and not any(r.candidate == ref and r.phase != "complete" for r in budget.assessments(state))
        and not any(x.get("kind") == KIND and x.get("npc") == npc.id for x in state.facts)
        and not any(x.source_owner == ref or x.holder == ref for x in state.held_items)
        and not any(x.active and ref in (x.subject, x.foe) for x in state.helpless_conditions)
    )


def source(
    state: GameState,
    candidate: ActorRef,
    site: Location,
    faction: str | None,
    controller: int,
) -> Npc:
    npc = (
        next(
            (x for x in state.world.npcs if x.id == candidate.entity),
            None,
        )
        if state.world
        else None
    )
    if (
        candidate.kind != "npc"
        or npc is None
        or not eligible(state, npc)
        or npc.cell != site.cell
        or npc.faction != faction
        or npc.controller != controller
    ):
        raise WorkflowError("Recover the actual local Pilot Candidate and its original controller.")
    return npc


def activate(
    state: GameState,
    invitation: Offer,
    npc: Npc,
    new: ActorRef,
    event: str,
    facilitator: int,
) -> GameState:
    original = ActorRef(kind="npc", entity=npc.id)
    state = migrate_actor(state, original, event)
    state = rebind(state, original, new, event)
    assert state.world is not None
    state.world = update(state.world, npcs=tuple(x for x in state.world.npcs if x.id != npc.id))
    state.scene_casts = [
        cast.model_copy(
            update=dict(
                revision=cast.revision + 1,
                roles=tuple(
                    CastRole(actor=new, controller=role.controller, source_event=event)
                    if role.actor == original
                    else role
                    for role in cast.roles
                ),
            )
        )
        if cast.open and any(role.actor == original for role in cast.roles)
        else cast
        for cast in state.scene_casts
    ]
    state = install_external_pose(
        state,
        new,
        npc.cell,
        npc.cell,
        "piloting",
        event,
        "The original owner confirmed the Candidate and entered her approved starting Frame.",
        owner=npc.controller,
        judge=facilitator,
    )
    state.facts.append(
        dict(
            kind=KIND,
            npc=npc.id,
            actor=new.model_dump_json(),
            original=npc.model_dump_json(),
            source=invitation.source_event,
            event=event,
            original_sha256=fingerprint(npc),
        )
    )
    return state
