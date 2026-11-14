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
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_harpy_defeat import offstage_travel
from girlframe.engine.m3_world_state import (
    AdversaryPilot,
    Board,
    Cell,
    Faction,
    Gorgon,
    Location,
    Npc,
    StartingNpcLink,
)
from girlframe.engine.npc_bonds import NPC_ROLES
from girlframe.services.m2_state import load_state
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def require_onstage(state: GameState, actor: ActorRef) -> None:
    """A cached map square cannot establish a body that actually crossed a Rift."""
    if offstage_travel(state, actor) is not None:
        raise WorkflowError(
            "OFFSTAGE_RIFT: record this actual body's return through its Rift travel review first."
        )


def _escaped_native_harpy(state: GameState, actor: ActorRef) -> bool:
    return (
        actor.kind == "external_pilot"
        and any(x.id == actor.entity and x.cell is None for x in state.native_harpies)
        and any(x.escaped and actor in x.departed for x in state.harpy_defeats)
    )


def offstage_world_actors(state: GameState) -> tuple[ActorRef, ...]:
    if state.world is None:
        return ()
    actors: list[ActorRef] = []
    for rows, kind in (
        (state.world.npcs, "npc"),
        (state.world.gorgons, "gorgon"),
        (state.world.pilots, "external_pilot"),
    ):
        for row in rows:
            actor = ActorRef.model_validate(dict(kind=kind, entity=row.id))
            if row.alive and (
                offstage_travel(state, actor) is not None or _escaped_native_harpy(state, actor)
            ):
                actors.append(actor)
    return tuple(actors)


def require_world_advancement(state: GameState) -> None:
    if offstage_world_actors(state):
        raise WorkflowError(
            "OFFSTAGE_RIFT: map advancement needs source-aware offstage support. "
            "Cached map positions cannot move these bodies or cause destruction. "
            "An actual reviewed return may restore their map presence."
        )


def _world_projection(state: GameState) -> dict[str, Any]:
    from girlframe.services.m3_red_queen_accusation import official_allegations

    assert state.world is not None
    projected = state.world.model_dump(mode="json")
    for row in projected["locations"]:
        row["official_allegations"] = official_allegations(state, row["kind"], row["id"])
    for row in projected["npcs"]:
        row["official_allegations"] = official_allegations(
            state, "npc", ActorRef(kind="npc", entity=row["id"])
        )
    for key, kind in (("npcs", "npc"), ("gorgons", "gorgon"), ("pilots", "external_pilot")):
        for row in projected[key]:
            actor = ActorRef.model_validate(dict(kind=kind, entity=row["id"]))
            if offstage_travel(state, actor) is not None or _escaped_native_harpy(state, actor):
                row["cell"] = None
            elif any(x.actor == actor for x in state.external_poses) or any(
                x.actor == actor for x in state.leviathan_arrivals
            ):
                from girlframe.engine.m3_actors import resolve

                actual_cell = resolve(state, actor, (), require_alive=False).cell
                row["cell"] = list(actual_cell) if actual_cell is not None else None
    return projected


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
                return {
                    "game_revision": state.revision,
                    "world": _world_projection(state),
                    "offstage_world": [
                        x.model_dump(mode="json") for x in offstage_world_actors(state)
                    ],
                }
            return {
                "game_revision": state.revision,
                "world": {
                    "board": world.board.model_dump(mode="json"),
                    **(
                        {
                            "regions": [
                                {
                                    "id": region.id,
                                    "name": region.name,
                                    "bounds": region.bounds.model_dump(mode="json"),
                                    "responsible": "Handler"
                                    if region.responsible is not None
                                    else None,
                                    **(
                                        {
                                            "rival": {
                                                "name": npc.name,
                                                "job": "handler",
                                                "alive": npc.alive,
                                            }
                                        }
                                        if (
                                            npc := next(
                                                (
                                                    x
                                                    for x in world.npcs
                                                    if x.id == region.rival.entity and x.revealed
                                                ),
                                                None,
                                            )
                                        )
                                        is not None
                                        else {}
                                    ),
                                }
                                for region in world.regions
                            ]
                        }
                        if world.regions
                        else {}
                    ),
                    "locations": [
                        x.model_dump(
                            mode="json",
                            exclude={"blocked_by", "ship", "fallout_sources", "control_loss"},
                        )
                        | {
                            "operational": x.operational,
                            "official_allegations": _official_location_claims(state, x.kind, x.id),
                        }
                        | (
                            {
                                "ship": {
                                    "armoured": x.ship.armoured,
                                    "airborne": x.ship.airborne,
                                }
                            }
                            if x.ship is not None
                            else {}
                        )
                        for x in world.locations
                    ],
                    "gorgons": [
                        {
                            "id": x.id,
                            "name": x.name,
                            "cell": list(x.cell)
                            if x.cell is not None
                            and offstage_travel(state, ActorRef(kind="gorgon", entity=x.id)) is None
                            else None,
                            "gorgon_class": x.gorgon_class,
                            "alive": x.alive,
                        }
                        for x in world.gorgons
                        if x.revealed
                    ],
                    "territory": [list(x) for x in sorted(world.territory)],
                    **(
                        {
                            "fallout": [
                                {
                                    "cells": [list(cell) for cell in zone.cells],
                                    "active": zone.expired_event is None,
                                }
                                for zone in world.fallout
                            ]
                        }
                        if world.fallout
                        else {}
                    ),
                    **(
                        {
                            "features": [
                                {
                                    "id": feature.id,
                                    "cell": list(feature.cell),
                                    "label": feature.label,
                                    "description": feature.description,
                                }
                                for feature in world.features
                            ]
                        }
                        if world.features
                        else {}
                    ),
                    **(
                        {
                            "field_studies": [
                                {
                                    "id": study.id,
                                    "location": study.location,
                                    "protected": study.protected,
                                }
                                for study in world.field_studies
                            ]
                        }
                        if world.field_studies
                        else {}
                    ),
                },
            }

    def advancement(self, viewer: GuildViewer) -> dict[str, Any]:
        from girlframe.engine.m3_world_advance import plan, steps

        data = self.get(viewer, private=True)
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            if state.revision != data["game_revision"]:
                raise WorkflowError("STALE_STATE: refresh the actual map advancement source.")
            present, deferred = plan(state)
            data.update(
                advancing_gorgons=sorted(present),
                directed_steps=steps(state),
                deferred=list(deferred),
            )
            return data

    def introduce_patrol_harpy(
        self,
        viewer: GuildViewer,
        key: str,
        work: str,
        work_revision: int,
        game_revision: int,
        pilot: AdversaryPilot,
        account: str,
    ) -> dict[str, Any]:
        value = AdversaryPilot.model_validate_json(pilot.model_dump_json())

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_patrol_harpy import validate_introduction

            state = self._state(c, game_revision)
            validate_introduction(self.game, c, state, viewer, work, work_revision, value)
            world = state.world
            if (
                world is None
                or not account.strip()
                or len(account) > 1200
                or value.kind != "harpy"
                or value.controller != viewer.user_id
                or not value.alive
                or value.custody != "free"
                or value.custodian is not None
                or value.custody_event is not None
                or value.revealed
                or value.exposed
                or value.tags
                or value.rebel_resources_json is not None
                or not world.board.contains(value.cell)
                or any(
                    item.id == value.id
                    for group in (world.pilots, world.npcs, world.gorgons, world.locations)
                    for item in group
                )
            ):
                raise WorkflowError(
                    "Introduce the actual source Handler's living, free, unrevealed Harpy "
                    "with its real placed facts."
                )
            if any(
                row.get("kind") == "patrol_harpy_introduction" and row.get("work") == work
                for row in state.facts
            ):
                raise WorkflowError("Resume this patrol source's already introduced actual Harpy.")
            event = str(uuid4())
            actor = ActorRef(kind="external_pilot", entity=value.id)
            state.world = rules.update(world, pilots=world.pilots + (value,))
            state.facts.append(
                dict(
                    kind="patrol_harpy_introduction",
                    work=work,
                    actor=actor.model_dump_json(),
                    pilot=value.model_dump_json(),
                    handler=str(viewer.user_id),
                    event=event,
                    account=account.strip(),
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.patrol_harpy_introduced",
                state,
                event_id=event,
                source_work=work,
                entity_id=value.id,
            )
            return dict(id=value.id, actor=actor.model_dump(mode="json"))

        return self._write(
            viewer,
            key,
            "m3.patrol_harpy_introduced",
            dict(
                work=work,
                work_revision=work_revision,
                game_revision=game_revision,
                pilot=value.model_dump(mode="json"),
                account=account,
            ),
            operation,
        )

    def npc(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        npc: Npc,
        *,
        show_dog: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._state(c, expected)
            if npc.source_kind is not None:
                raise WorkflowError("This NPC kind requires its actual source producer")
            if show_dog is not None:
                from girlframe.services.m3_show_dog import validate_npc_introduction

                validate_npc_introduction(self.game, c, state, viewer, show_dog, npc)
            if state.world is None:
                raise WorkflowError("Initialize the world before introducing NPCs.")
            if npc.controller != viewer.user_id:
                raise WorkflowError(
                    "Introduce the NPC under your control; invite another human to accept a role."
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
                    and x.control_loss is None
                    for x in state.world.locations
                )
            ):
                introduced = npc.model_copy(update={"custody_event": event})
            state.world = rules.introduce_npc(state.world, introduced)
            npc_source: dict[str, Any] = {"source_work": show_dog} if show_dog is not None else {}
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.npc_introduced",
                state,
                entity_id=npc.id,
                event_id=event,
                **npc_source,
            )
            return {"id": npc.id, "game_revision": state.revision}

        return self._write(
            viewer,
            key,
            "m3.npc_introduced",
            {"expected": expected, "npc": npc.model_dump(mode="json")}
            | ({"show_dog": show_dog} if show_dog is not None else {}),
            operation,
            handler=show_dog is None,
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
            if (
                any(x.id == identity and "director" in x.jobs for x in world.npcs)
                and viewer.user_id == state.handler
            ):
                raise WorkflowError(
                    "The Director must be played by a different human from the Handler."
                )
            if any(x.id == identity and x.controller != viewer.user_id for x in world.npcs):
                raise WorkflowError(
                    "The current controller must offer this NPC role, then you explicitly accept."
                )
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
                    if x.alive and x.controller == viewer.user_id
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

    def locate_gorgon(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        identity: str,
        cell: Cell,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._state(c, expected)
            if state.world is None or not account.strip() or len(account) > 1200:
                raise WorkflowError("Record the actual missing position and factual source.")
            if self.game.pending_actions(c):
                raise WorkflowError("Finish pending Plays before recording world positions.")
            require_onstage(state, ActorRef(kind="gorgon", entity=identity))
            source = str(uuid4())
            state.world = rules.locate_gorgon(state.world, identity, cell, source)
            state.facts.append(
                dict(
                    kind="gorgon_initial_position",
                    entity=identity,
                    account=account,
                    source_event=source,
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.gorgon_position_recorded",
                state,
                event_id=source,
                entity_id=identity,
                cell=list(cell),
            )
            return dict(id=identity, game_revision=state.revision, cell=list(cell))

        return self._write(
            viewer,
            key,
            "m3.gorgon_position_recorded",
            dict(expected=expected, identity=identity, cell=list(cell), account=account),
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


def _official_location_claims(state: GameState, kind: str, identity: str) -> list[dict[str, Any]]:
    from girlframe.services.m3_red_queen_accusation import official_allegations

    return official_allegations(state, kind, identity)
