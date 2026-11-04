"""Transactional canonical world setup, explicit introductions and safe projections."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_world as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_world_state import Board, Faction, Gorgon, Location, Npc, StartingNpcLink
from girlframe.engine.npc_bonds import NPC_ROLES
from girlframe.services.m2_state import load_state
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class WorldService:
    def __init__(self, missions: MissionService):
        self.missions, self.store, self.game = missions, missions.store, missions.game

    def _state(self, c: Connection, expected: int) -> GameState:
        state = load_state(c, self.store.campaign_id)
        if state.revision != expected or self.game.pending_actions(c):
            raise WorkflowError("STALE_STATE: finish pending Plays and refresh the world review.")
        return state

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        kind: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
        *,
        handler: bool = True,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.missions.access.authorize(c, viewer, "world")
            self.game.unpaused(c)
            if handler:
                self.missions._handler(c, viewer)

        try:
            return self.store._write(
                viewer, key, kind, payload, operation, auto_audit=False, authorize=authorize
            )
        except ValidationError:
            raise WorkflowError("Invalid world setup; refresh the source-backed choices.") from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def initialize(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        board: Board,
        locations: tuple[Location, ...],
        secret: Gorgon,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._state(c, expected)
            if state.world is not None:
                raise WorkflowError("The world already exists; do not replace campaign history.")
            state.world = rules.create(board, locations, secret)
            self.game.event(c, viewer.user_id, key, "m3.world_initialized", state)
            return {"game_revision": state.revision, "locations": len(locations)}

        return self._write(
            viewer,
            key,
            "m3.world_initialized",
            {
                "expected": expected,
                "board": board.model_dump(mode="json"),
                "locations": [x.model_dump(mode="json") for x in locations],
                "secret": secret.model_dump(mode="json"),
            },
            operation,
        )

    def get(self, viewer: GuildViewer, *, private: bool = False) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            if private:
                self.missions._handler(c, viewer)
            state = load_state(c, self.store.campaign_id)
            world = state.world
            if world is None:
                return {"game_revision": state.revision, "world": None}
            if private:
                return {"game_revision": state.revision, "world": world.model_dump(mode="json")}
            return {
                "game_revision": state.revision,
                "world": {
                    "board": world.board.model_dump(mode="json"),
                    "locations": [
                        x.model_dump(mode="json", exclude={"blocked_by"})
                        | {"operational": x.condition != "destroyed" and not x.blocked_by}
                        for x in world.locations
                    ],
                    "gorgons": [
                        {
                            "id": x.id,
                            "name": x.name,
                            "cell": list(x.cell),
                            "gorgon_class": x.gorgon_class,
                            "alive": x.alive,
                        }
                        for x in world.gorgons
                        if x.revealed
                    ],
                    "territory": [list(x) for x in sorted(world.territory)],
                },
            }

    def npc(self, viewer: GuildViewer, key: str, expected: int, npc: Npc) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._state(c, expected)
            if state.world is None:
                raise WorkflowError("Initialize the world before introducing NPCs.")
            if npc.controller != viewer.user_id:
                raise WorkflowError(
                    "Introduce the NPC under your control; another human claims their own role."
                )
            if "director" in npc.jobs and npc.controller == state.handler:
                raise WorkflowError(
                    "The Director must be played by a different human from the Handler."
                )
            if npc.bonds:
                raise WorkflowError(
                    "Players import their own NPC Bonds; introduction cannot choose those for them."
                )
            if npc.custody_event is not None:
                raise WorkflowError("Custody provenance comes from an actual server event.")
            event = str(uuid4())
            introduced = npc
            if (
                "prisoner" in npc.jobs
                and npc.captive_of is None
                and any(
                    x.cell == npc.cell
                    and x.kind == "base"
                    and x.allegiance == "foundation"
                    and x.condition != "destroyed"
                    for x in state.world.locations
                )
            ):
                introduced = npc.model_copy(update={"custody_event": event})
            state.world = rules.introduce_npc(state.world, introduced)
            self.game.event(
                c, viewer.user_id, key, "m3.npc_introduced", state, entity_id=npc.id, event_id=event
            )
            return {"id": npc.id, "game_revision": state.revision}

        return self._write(
            viewer,
            key,
            "m3.npc_introduced",
            {"expected": expected, "npc": npc.model_dump(mode="json")},
            operation,
        )

    def import_starting_npc(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        slot: int,
        identity: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._state(c, expected)
            sheet = state.sheets.get(str(viewer.user_id))
            world = state.world
            selected = (
                next((x for x in sheet.review.creation.npc_bonds if x.slot == slot), None)
                if sheet
                else None
            )
            npc = next((x for x in world.npcs if x.id == identity), None) if world else None
            if (
                world is None
                or selected is None
                or npc is None
                or not npc.alive
                or (
                    bool(selected.name.strip())
                    and selected.name.strip().casefold() != npc.name.strip().casefold()
                )
                or (not selected.name.strip() and not npc.revealed)
            ):
                raise WorkflowError("Choose an actual NPC matching your own saved starting Bond.")
            character = c.scalar(
                sa.select(t.characters.c.id).where(
                    t.characters.c.campaign_id == self.store.campaign_id,
                    t.characters.c.user_id == str(viewer.user_id),
                )
            )
            if character is None or any(
                x.owner == viewer.user_id and x.character_id == character and x.slot == slot
                for x in world.starting_npc_links
            ):
                raise WorkflowError("This character's starting NPC slot is already linked.")
            state.world = rules.update(
                world,
                npcs=tuple(
                    x.model_copy(
                        update={
                            "bonds": x.bonds
                            | {
                                "pilot:" + str(viewer.user_id): x.bonds.get(
                                    "pilot:" + str(viewer.user_id), 1
                                )
                            }
                        }
                    )
                    if x.id == identity
                    else x
                    for x in world.npcs
                ),
                starting_npc_links=world.starting_npc_links
                + (
                    StartingNpcLink(
                        owner=viewer.user_id, character_id=character, slot=slot, npc=identity
                    ),
                ),
            )
            self.game.event(
                c, viewer.user_id, key, "m3.starting_npc_linked", state, entity_id=identity
            )
            return {"id": identity, "game_revision": state.revision}

        return self._write(
            viewer,
            key,
            "m3.starting_npc_linked",
            {"expected": expected, "slot": slot, "id": identity},
            operation,
            handler=False,
        )

    def claim_npc(
        self, viewer: GuildViewer, key: str, expected: int, identity: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._state(c, expected)
            world = state.world
            if world is None or not any(
                x.id == identity and x.alive and (x.revealed or viewer.user_id == state.handler)
                for x in world.npcs
            ):
                raise WorkflowError("Choose a living introduced NPC.")
            state.world = rules.update(
                world,
                npcs=tuple(
                    x.model_copy(update={"controller": viewer.user_id}) if x.id == identity else x
                    for x in world.npcs
                ),
            )
            self.game.event(
                c, viewer.user_id, key, "m3.npc_control_claimed", state, entity_id=identity
            )
            return {"id": identity, "game_revision": state.revision}

        return self._write(
            viewer,
            key,
            "m3.npc_control_claimed",
            {"expected": expected, "id": identity},
            operation,
            handler=False,
        )

    def control_options(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            return {
                "game_revision": state.revision,
                "npcs": tuple(
                    (x.id, x.name)
                    for x in state.world.npcs
                    if x.alive and (x.revealed or viewer.user_id == state.handler)
                )
                if state.world
                else (),
            }

    def bond_options(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            sheet = state.sheets.get(str(viewer.user_id))
            if state.world is None or sheet is None:
                raise WorkflowError("An active own sheet and an initialized world are required.")
            character = c.scalar(
                sa.select(t.characters.c.id).where(
                    t.characters.c.campaign_id == self.store.campaign_id,
                    t.characters.c.user_id == str(viewer.user_id),
                )
            )
            linked = {
                x.slot
                for x in state.world.starting_npc_links
                if x.owner == viewer.user_id and x.character_id == character
            }
            return {
                "game_revision": state.revision,
                "options": tuple(
                    (
                        str(bond.slot) + ":" + npc.id,
                        (bond.name or NPC_ROLES[sheet.girl][bond.slot]) + " — " + npc.name,
                    )
                    for bond in sheet.review.creation.npc_bonds
                    if bond.slot not in linked
                    for npc in state.world.npcs
                    if npc.alive
                    and (
                        npc.name.strip().casefold() == bond.name.strip().casefold()
                        if bond.name.strip()
                        else npc.revealed
                    )
                ),
            }

    def faction(
        self, viewer: GuildViewer, key: str, expected: int, faction: Faction
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._state(c, expected)
            if state.world is None:
                raise WorkflowError("Initialize the world before introducing factions.")
            state.world = rules.update(state.world, factions=state.world.factions + (faction,))
            self.game.event(
                c, viewer.user_id, key, "m3.faction_introduced", state, entity_id=faction.id
            )
            return {"id": faction.id, "game_revision": state.revision}

        return self._write(
            viewer,
            key,
            "m3.faction_introduced",
            {"expected": expected, "faction": faction.model_dump(mode="json")},
            operation,
        )

    def reveal(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        identity: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._state(c, expected)
            world = state.world
            if world is None or not account.strip() or len(account) > 1200:
                raise WorkflowError("Record the actual encounter that revealed the Gorgon.")
            if not any(x.id == identity and not x.revealed for x in world.gorgons):
                raise WorkflowError("Choose an unrevealed current Gorgon.")
            state.world = rules.update(
                world,
                gorgons=tuple(
                    x.model_copy(update={"revealed": True}) if x.id == identity else x
                    for x in world.gorgons
                ),
            )
            state.facts.append(
                {"kind": "gorgon_revealed", "entity": identity, "account": account.strip()}
            )
            self.game.event(c, viewer.user_id, key, "m3.gorgon_revealed", state, entity_id=identity)
            return {"id": identity, "game_revision": state.revision}

        return self._write(
            viewer,
            key,
            "m3.gorgon_revealed",
            {"expected": expected, "id": identity, "account": account},
            operation,
        )
