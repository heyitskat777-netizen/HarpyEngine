"""Private NPC-role invitations; no forced role assignment or public secret dump."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_npc_roles as rules
from girlframe.engine.m3_world_state import Npc
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class NpcRoleService:
    def __init__(self, world: WorldService):
        self.world, self.store, self.game = world, world.store, world.game

    def members(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            self.world.missions._handler(c, viewer)
            members = tuple(
                (uid, "Member " + uid)
                for uid in c.scalars(
                    sa.select(t.members.c.user_id).where(
                        t.members.c.campaign_id == self.store.campaign_id,
                        t.members.c.user_id != str(viewer.user_id),
                        t.members.c.active.is_(True),
                    )
                )
            )
            return {"members": members}

    def offer(self, viewer: GuildViewer, key: str, expected: int, npc: Npc) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self.world._state(c, expected)
            if (
                state.world is None
                or state.handler != viewer.user_id
                or not HandlerService(self.store)._member(c, npc.controller)
            ):
                raise WorkflowError(
                    "Invite an actual current member under the current canonical Handler."
                )
            identity, event = str(uuid4()), str(uuid4())
            state.world = rules.offer(state.world, viewer.user_id, npc, identity, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.npc_role_offered",
                state,
                event_id=event,
                invitation_id=identity,
            )
            return {"id": identity, "state": "pending"}

        return self.world._write(
            viewer,
            key,
            "m3.npc_role_offered",
            {"expected": expected, "npc": npc.model_dump(mode="json")},
            operation,
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            offer = (
                next((x for x in state.world.npc_role_offers if x.id == identity), None)
                if state.world
                else None
            )
            if offer is None or viewer.user_id not in (
                offer.proposer,
                offer.npc.controller,
                state.handler,
            ):
                raise WorkflowError("This private role invitation belongs to other participants.")
            return {
                "id": offer.id,
                "state": offer.state,
                "recipient": offer.npc.controller,
                "proposer": offer.proposer,
                "handler": state.handler,
                "game_revision": state.revision,
                "npc": offer.npc.model_dump(mode="json"),
            }

    def respond(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, decision: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self.world._state(c, expected)
            if (
                state.world is None
                or state.handler is None
                or state.handler != self.world.missions._current_handler(c)
            ):
                raise WorkflowError("Recover the changed world or Handler before this invitation.")
            offer = next((x for x in state.world.npc_role_offers if x.id == identity), None)
            if offer is None or not HandlerService(self.store)._member(c, offer.npc.controller):
                raise WorkflowError("The actual invited member must still belong to this campaign.")
            event = str(uuid4())
            state.world = rules.respond(
                state.world, int(state.handler), viewer.user_id, identity, decision, event
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.npc_role_answered",
                state,
                event_id=event,
                invitation_id=identity,
                decision=decision,
            )
            from girlframe.services.m3_battle_director import synchronize_replacement

            synchronize_replacement(self.game, c, identity, event, viewer, key)
            return {
                "id": identity,
                "state": next(x.state for x in state.world.npc_role_offers if x.id == identity),
            }

        return self.world._write(
            viewer,
            key,
            "m3.npc_role_answered",
            {"id": identity, "expected": expected, "decision": decision},
            operation,
            handler=False,
        )
