"""Separately played NPC introductions need the invited human's actual response."""

from girlframe.engine.m3_world import introduce_npc, update
from girlframe.engine.m3_world_state import Npc, NpcRoleOffer, World


def offer(world: World, handler: int, npc: Npc, identity: str, source: str) -> World:
    if npc.controller == handler or npc.bonds or npc.custody_event or not npc.alive:
        raise ValueError(
            "Invite a different human to a living NPC; do not import Bonds/custody proofs"
        )
    # Validate all actual references before storing the invitation. The proposal is
    # not an introduced NPC and has no mechanical or public appearance yet.
    introduce_npc(world, npc)
    return update(
        world,
        npc_role_offers=world.npc_role_offers
        + (NpcRoleOffer(id=identity, proposer=handler, npc=npc, source_event=source),),
    )


def offer_transfer(
    world: World, controller: int, npc_id: str, recipient: int, identity: str, source: str
) -> World:
    npc = next((x for x in world.npcs if x.id == npc_id), None)
    if npc is None or not npc.alive or npc.controller != controller or recipient == controller:
        raise ValueError("Only the current controller offers their living NPC to another human")
    return update(
        world,
        npc_role_offers=world.npc_role_offers
        + (
            NpcRoleOffer(
                id=identity,
                proposer=controller,
                npc=npc.model_copy(update={"controller": recipient}),
                source_event=source,
                transfer=True,
            ),
        ),
    )


def respond(
    world: World, handler: int, actor: int, identity: str, decision: str, source: str
) -> World:
    proposal = next((x for x in world.npc_role_offers if x.id == identity), None)
    if (
        proposal is None
        or proposal.state != "pending"
        or decision not in ("accept", "decline", "withdraw")
    ):
        raise ValueError("Resume an actual pending NPC role invitation")
    if proposal.transfer:
        return _respond_transfer(world, handler, actor, proposal, decision, source)
    if decision == "withdraw":
        if actor != handler:
            raise ValueError("Only the current Handler withdraws this introduction")
        status = "withdrawn"
    else:
        if actor != proposal.npc.controller or proposal.proposer != handler:
            raise ValueError("Only the invited human answers under the unchanged Handler")
        if "director" in proposal.npc.jobs and actor == handler:
            raise ValueError("A Director must be played by a different human from the Handler")
        status = "accepted" if decision == "accept" else "declined"
    changed = proposal.model_copy(update={"state": status, "response_event": source})
    result = update(
        world,
        npc_role_offers=tuple(changed if x.id == identity else x for x in world.npc_role_offers),
    )
    if decision == "accept":
        npc = proposal.npc
        if (
            "prisoner" in npc.jobs
            and npc.captive_of is None
            and any(
                x.cell == npc.cell
                and x.kind == "base"
                and x.allegiance == "foundation"
                and x.condition != "destroyed"
                and x.control_loss is None
                for x in world.locations
            )
        ):
            npc = npc.model_copy(update={"custody_event": source})
        result = introduce_npc(result, npc)
    return result


def _respond_transfer(
    world: World, handler: int, actor: int, proposal: NpcRoleOffer, decision: str, source: str
) -> World:
    if decision == "withdraw":
        if actor != proposal.proposer:
            raise ValueError("Only the original controller withdraws this transfer")
        status = "withdrawn"
    else:
        if actor != proposal.npc.controller:
            raise ValueError("Only the invited human answers this transfer")
        status = "accepted" if decision == "accept" else "declined"
    npc = next((x for x in world.npcs if x.id == proposal.npc.id), None)
    if decision == "accept":
        if (
            npc is None
            or not npc.alive
            or npc != proposal.npc.model_copy(update={"controller": proposal.proposer})
        ):
            raise ValueError(
                "STALE_NPC_TRANSFER: the original controller must offer the current NPC"
            )
        if "director" in npc.jobs and actor == handler:
            raise ValueError("The Director must be played by a different human from the Handler")
    return update(
        world,
        npcs=tuple(
            x.model_copy(update={"controller": actor})
            if decision == "accept" and x.id == proposal.npc.id
            else x
            for x in world.npcs
        ),
        npc_role_offers=tuple(
            x.model_copy(update={"state": status, "response_event": source})
            if x.id == proposal.id
            else x.model_copy(update={"state": "withdrawn", "response_event": source})
            if decision == "accept"
            and x.transfer
            and x.npc.id == proposal.npc.id
            and x.state == "pending"
            else x
            for x in world.npc_role_offers
        ),
    )
