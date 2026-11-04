"""Actual Director-presence review, owned Identity setup and explicit departures."""

import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_director as rules
from girlframe.engine.m2 import GameState
from girlframe.services.m2_state import load_state
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class DirectorService:
    def __init__(self, missions: MissionService):
        self.missions, self.store, self.game = missions, missions.store, missions.game

    def _row(self, c: Connection, identity: str) -> dict[str, Any]:
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table)
                .where(table.c.campaign_id == self.store.campaign_id, table.c.id == identity)
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None or row["kind"] != "director_presence":
            raise WorkflowError("Resume an actual Director-presence review.")
        return dict(row)

    def _state(self, c: Connection, expected: int) -> GameState:
        state = load_state(c, self.store.campaign_id)
        locks = t.m2["m2_locks"]
        if (
            state.revision != expected
            or self.game.pending_actions(c)
            or state.handler != self.missions._current_handler(c)
            or c.scalar(
                sa.select(locks.c.channel_id)
                .where(locks.c.campaign_id == self.store.campaign_id, locks.c.state != "released")
                .limit(1)
            )
        ):
            raise WorkflowError(
                "STALE_DIRECTOR: finish Plays, restore chat and review the actual Handler."
            )
        return state

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        kind: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self.missions.access.authorize(c, viewer, "world", director_response=True)
            self.game.unpaused(c)

        try:
            return self.store._write(
                viewer, key, kind, payload, operation, auto_audit=False, authorize=access
            )
        except ValidationError:
            raise WorkflowError(
                "Invalid Director context; review the current owned choices."
            ) from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            row = self._row(c, identity)
            if row["owner_id"] != str(viewer.user_id):
                raise WorkflowError(
                    "The affected Handler owns its actual presence and Identity review."
                )
            state = load_state(c, self.store.campaign_id)
            body = json.loads(row["body_json"])
            result = {k: row[k] for k in ("id", "revision", "state")}
            result.update(
                game_revision=state.revision,
                overlapping=any(x.active for x in state.director_contexts),
                absence_available=False,
            )
            if row["state"] == "pending":
                try:
                    rules.absence(
                        OffDutyService(self.missions)._get(c, row["off_duty_id"]),
                        state,
                        body["npc"],
                        body["origin_outcome"],
                    )
                except ValueError:
                    pass
                else:
                    result["absence_available"] = True
            return result

    def review(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        present: bool,
        labels: tuple[str, ...],
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._state(c, game_revision)
            row = self._row(c, identity)
            body = json.loads(row["body_json"])
            if (
                row["revision"] != revision
                or row["state"] != "pending"
                or row["owner_id"] != str(viewer.user_id)
                or state.handler != viewer.user_id
                or type(present) is not bool
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "Only the actual current Handler answers this pending presence review."
                )
            npc = (
                next((x for x in state.world.npcs if x.id == body["npc"] and x.alive), None)
                if state.world
                else None
            )
            event_source = c.execute(
                sa.select(t.events.c.kind, t.events.c.actor_id).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == row["event_id"],
                )
            ).first()
            if (
                npc is None
                or npc.controller != body["controller"]
                or event_source != ("m3.observation_npc_answered", str(npc.controller))
            ):
                raise WorkflowError(
                    "Recover the changed Director or its actual appearance provenance."
                )
            event = str(uuid4())
            proof: dict[str, Any]
            if present:
                state = rules.enter(state, viewer.user_id, npc.id, identity, labels, event)
                proof = {
                    "mode": "configured",
                    "context": next(
                        x.id for x in state.director_contexts if identity in x.source_works
                    ),
                }
            else:
                if labels:
                    raise WorkflowError("An absent Handler receives no fictional Identity setup.")
                period = OffDutyService(self.missions)._get(c, row["off_duty_id"])
                proof = {
                    "mode": "absent",
                    "proof": rules.absence(period, state, npc.id, body["origin_outcome"]),
                }
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.director_presence_reviewed",
                state,
                event_id=event,
                work_id=identity,
                present=present,
            )
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("revision", "state", "body_json", "event_id")
                    },
                    revision=row["revision"] + 1,
                    state="resolved",
                    body_json=json.dumps(
                        body | proof | {"account": account.strip(), "review_event": event},
                        sort_keys=True,
                    ),
                    event_id=event,
                )
            )
            return {"id": identity, "state": "resolved", "mode": proof["mode"]}

        return self._write(
            viewer,
            key,
            "m3.director_presence_reviewed",
            {
                "work": identity,
                "revision": revision,
                "game_revision": game_revision,
                "present": present,
                "labels": labels,
                "account": account,
            },
            operation,
        )

    def context(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            context = next((x for x in state.director_contexts if x.id == identity), None)
            controlled = (
                tuple(
                    (x.id, x.name)
                    for x in state.world.npcs
                    if context and x.id in context.directors and x.controller == viewer.user_id
                )
                if state.world
                else ()
            )
            if context is None or (context.handler != viewer.user_id and not controlled):
                raise WorkflowError("This rule context belongs to other participants.")
            result = {
                "id": context.id,
                "revision": context.revision,
                "active": context.active,
                "game_revision": state.revision,
                "directors": controlled,
            }
            if context.handler == viewer.user_id:
                result.update(
                    identities=[x.model_dump(mode="json") for x in context.identities],
                    heat=state.handler_heat,
                )
            return result

    def leave(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        npc: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._state(c, game_revision)
            context = next((x for x in state.director_contexts if x.id == identity), None)
            if (
                context is None
                or context.revision != revision
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "Reopen the actual Director presence and describe your own departure."
                )
            event = str(uuid4())
            state = rules.leave(state, viewer.user_id, identity, npc, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.director_departed",
                state,
                event_id=event,
                context_id=identity,
                npc_id=npc,
            )
            return {
                "id": identity,
                "active": next(x.active for x in state.director_contexts if x.id == identity),
            }

        return self._write(
            viewer,
            key,
            "m3.director_departed",
            {
                "context": identity,
                "revision": revision,
                "game_revision": game_revision,
                "npc": npc,
                "account": account,
            },
            operation,
        )
