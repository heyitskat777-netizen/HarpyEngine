"""Scoped Gorgon commands over actual world actors and canonical immutable history."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_gorgon as rules
from girlframe.engine import m3_gorgon_combat as combat
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.m2_state import load_state
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class GorgonService:
    def __init__(self, world: WorldService):
        self.world, self.game, self.store = world, world.game, world.store

    def _authorize(self, c: Connection, viewer: GuildViewer) -> None:
        # World facilitation remains with the appointed Handler human even while
        # that human's separate fictional Handler is under a Director's rules.
        # This narrow command grants no Director NPC or Girl-sheet authority.
        for subsystem in ("world", "plays"):
            self.world.missions.access.authorize(c, viewer, subsystem, director_response=True)
        self.world.missions._handler(c, viewer)

    def _safe(self, c: Connection) -> None:
        locks = t.m2["m2_locks"]
        if self.game.pending_actions(c) or c.scalar(
            sa.select(locks.c.channel_id)
            .where(
                locks.c.campaign_id == self.store.campaign_id,
                locks.c.state != "released",
            )
            .limit(1)
        ):
            raise WorkflowError("Finish pending Plays and restore chat before a world Attack.")

    def preview(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._authorize(c, viewer)
            state = load_state(c, self.store.campaign_id)
            attackers = []
            for gorgon in state.world.gorgons if state.world else ():
                if not gorgon.alive or gorgon.gorgon_class in ("benevolent", "dormant"):
                    continue
                actor = resolve(state, ActorRef(kind="gorgon", entity=gorgon.id), ())
                targets = []
                assert state.world is not None
                for npc in state.world.npcs:
                    target = ActorRef(kind="npc", entity=npc.id)
                    try:
                        rules.eligible(state, actor.ref, target)
                    except ValueError:
                        continue
                    actual = resolve(state, target, ())
                    targets.append(
                        dict(
                            ref=target.model_dump(mode="json"),
                            token=target.token,
                            label=actual.label,
                            source_sha256=actual.source_sha256,
                        )
                    )
                if targets:
                    attackers.append(
                        dict(
                            ref=actor.ref.model_dump(mode="json"),
                            token=actor.ref.token,
                            label=actor.label,
                            source_sha256=actor.source_sha256,
                            assets=[
                                x.model_dump(mode="json") for x in actor.assets if not x.damaged
                            ],
                            targets=targets,
                        )
                    )
            return {"game_revision": state.revision, "attackers": attackers}

    def history(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            self.world.missions._handler(c, viewer)
            state = load_state(c, self.store.campaign_id)
            return [
                dict(
                    id=x["source_event"],
                    attack=rules.NpcAttack.model_validate_json(x["attack"]).model_dump(mode="json"),
                )
                for x in state.facts
                if x.get("kind") == "gorgon_attack_npc"
            ]

    def attack(
        self, viewer: GuildViewer, key: str, expected: int, attack: rules.NpcAttack
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            self._safe(c)
            state = load_state(c, self.store.campaign_id)
            if type(expected) is not int or state.revision != expected:
                raise WorkflowError("STALE_ATTACK: reopen the actual world and target review.")
            source = str(uuid4())
            state = rules.attack_npc(state, attack, source)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.gorgon_attacked_npc",
                state,
                event_id=source,
                attack_id=source,
                outcome="npc_dead",
            )
            return {"id": source, "outcome": "npc_dead", "game_revision": state.revision}

        try:
            attack = rules.NpcAttack.model_validate_json(attack.model_dump_json())
            return self.store._write(
                viewer,
                key,
                "m3.gorgon_attacked_npc",
                dict(expected=expected, attack=attack.model_dump(mode="json")),
                operation,
                auto_audit=False,
                authorize=lambda c: self._authorize(c, viewer),
            )
        except ValidationError:
            raise WorkflowError(
                "Invalid Attack; reopen the actual actor and Asset choices."
            ) from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def contests(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._authorize(c, viewer)
            state = load_state(c, self.store.campaign_id)
            actors = (
                [
                    resolve(state, ActorRef(kind="gorgon", entity=x.id), ())
                    for x in state.world.gorgons
                    if x.alive
                ]
                if state.world
                else []
            )
            entries = []
            for first in actors:
                targets = []
                for second in actors:
                    try:
                        combat.eligible(state, first.ref, second.ref)
                    except ValueError:
                        continue
                    targets.append(second.model_dump(mode="json") | {"token": second.ref.token})
                if targets:
                    entries.append(
                        first.model_dump(mode="json")
                        | {"token": first.ref.token, "targets": targets}
                    )
            return {"game_revision": state.revision, "attackers": entries}

    def cores(self, viewer: GuildViewer) -> dict[str, Any]:
        from girlframe.engine.m3_leviathan import layers_clear

        with self.store.engine.connect() as c:
            self._authorize(c, viewer)
            state = load_state(c, self.store.campaign_id)
            entries = []
            for gorgon in state.world.gorgons if state.world else ():
                dealt_with = {x.id for x in gorgon.assets if x.damaged} | {
                    x.id for x in gorgon.destroyed_assets
                }
                if (
                    not gorgon.alive
                    or gorgon.exposed
                    or not set(gorgon.core_plan.assets) <= dealt_with
                    or not layers_clear(gorgon)
                ):
                    continue
                actor = resolve(state, ActorRef(kind="gorgon", entity=gorgon.id), ())
                if actor.offstage_source is not None:
                    continue
                entries.append(
                    actor.model_dump(mode="json")
                    | {"token": actor.ref.token, "weakness": gorgon.core_plan.weakness}
                )
            return {"game_revision": state.revision, "gorgons": entries}

    def _combat_command(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        kind: str,
        body: dict[str, Any],
        operation: Callable[[GameState, str], GameState],
    ) -> dict[str, Any]:
        def apply(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            self._safe(c)
            state = load_state(c, self.store.campaign_id)
            if type(expected) is not int or expected != state.revision:
                raise WorkflowError("STALE_COMBAT: review the actual world and Assets again.")
            event = str(uuid4())
            state = operation(state, event)
            self.game.event(c, viewer.user_id, key, kind, state, event_id=event, effect_id=event)
            return {"id": event, "game_revision": state.revision}

        try:
            return self.store._write(
                viewer,
                key,
                kind,
                dict(expected=expected, choice=body),
                apply,
                auto_audit=False,
                authorize=lambda c: self._authorize(c, viewer),
            )
        except ValidationError:
            raise WorkflowError(
                "Invalid actual combat choice; reopen its current review."
            ) from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def contest(
        self, viewer: GuildViewer, key: str, expected: int, choice: combat.Contest
    ) -> dict[str, Any]:
        return self._combat_command(
            viewer,
            key,
            expected,
            "m3.gorgon_assets_contested",
            choice.model_dump(mode="json"),
            lambda state, event: combat.contest(state, choice, event),
        )

    def expose(
        self, viewer: GuildViewer, key: str, expected: int, choice: combat.Exposure
    ) -> dict[str, Any]:
        return self._combat_command(
            viewer,
            key,
            expected,
            "m3.gorgon_core_exposed",
            choice.model_dump(mode="json"),
            lambda state, event: combat.expose(state, choice, event),
        )
