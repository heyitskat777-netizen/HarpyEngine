"""Actual NPC rank declarations, Foundation arrest and evidence-bound innocence review."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_enforcer as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

RANK = "enforcer_rank"


class EnforcerService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "playbooks")
        assert access.registry is not None
        try:
            access.registry.require_available(rules.OBEDIENCE)
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _actor(self, c: Connection, viewer: GuildViewer) -> ActorRef:
        state = load_state(c, self.store.campaign_id)
        actor = ActorRef(
            kind="pilot",
            entity=str(viewer.user_id),
            incarnation=self.game.character_binding(
                c, state, viewer.user_id, require_current_profile=False
            ),
        )
        if not rules.conditioning(state, actor):
            raise WorkflowError("Obedience Conditioning requires your actual non-Dog Enforcer.")
        return actor

    def _known(self, state: GameState, actor: ActorRef) -> set[str]:
        if state.world is None:
            return set()
        linked = {
            x.npc
            for x in state.world.starting_npc_links
            if x.owner == int(actor.entity) and x.character_id == actor.incarnation
        }
        return {x.id for x in state.world.npcs if x.alive and (x.revealed or x.id in linked)}

    def preview(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            actor = self._actor(c, viewer)
            state = load_state(c, self.store.campaign_id)
            actual = resolve(
                state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            ranks = {x.subject.entity: x for x in state.enforcer_ranks if x.relative_to == actor}
            return dict(
                actor=actor.model_dump(mode="json"),
                expected=actual.source_sha256,
                trusted_by_foundation=True,
                handler_judgment_independent=True,
                targets=[
                    dict(
                        id=x.id,
                        name=x.name,
                        rank=ranks[x.id].id if x.id in ranks else None,
                        superior=ranks[x.id].superior_officer if x.id in ranks else None,
                    )
                    for x in state.world.npcs
                    if x.id in self._known(state, actor)
                    and rules.detention(state, ActorRef(kind="npc", entity=x.id)) is None
                ]
                if state.world
                else [],
            )

    def _rank_rows(self, c: Connection) -> list[dict[str, Any]]:
        work = t.m3["m3_required_work"]
        return list(
            {
                x["id"]: dict(x)
                for x in c.execute(
                    sa.select(work)
                    .where(
                        work.c.campaign_id == self.store.campaign_id,
                        work.c.kind == RANK,
                    )
                    .order_by(work.c.revision)
                ).mappings()
            }.values()
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        handler = HandlerService(self.store).current(c)[1].handler_id == viewer.user_id
        result = [
            dict(id=x["id"], kind=RANK, revision=x["revision"], state=x["state"])
            for x in self._rank_rows(c)
            if handler or x["subject_id"] == str(viewer.user_id)
        ]
        result += [
            dict(
                id=x.id,
                kind="enforcer_innocence" if x.detained else "enforcer_release_position",
                revision=state.revision,
                state="pending" if x.detained or x.position_event is None else "resolved",
            )
            for x in state.enforcer_accusations
            if handler or x.actor.entity == str(viewer.user_id)
        ]
        return result

    def tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            return self._tasks(c, viewer)

    def request_rank(self, viewer: GuildViewer, key: str, target: str) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            actor = self._actor(c, viewer)
            state = load_state(c, self.store.campaign_id)
            if target not in self._known(state, actor):
                raise WorkflowError("Choose an actually known living NPC.")
            handler = HandlerService(self.store).current(c)[1].handler_id
            if handler is None:
                raise WorkflowError("Recover the actual Handler appointment.")
            if any(
                x["state"] != "resolved"
                and json.loads(x["body_json"])["target"] == target
                and json.loads(x["body_json"])["actor"] == actor.model_dump(mode="json")
                for x in self._rank_rows(c)
            ):
                raise WorkflowError("The actual factual rank request is already pending.")
            identity = str(uuid4())
            event = self.game.event(
                c, viewer.user_id, key, "m3.enforcer_rank_requested", work_id=identity
            )
            related(
                c,
                self.store,
                dict(campaign_id=self.store.campaign_id, campaign_context=True),
                identity,
                handler,
                viewer.user_id,
                RANK,
                dict(actor=actor.model_dump(mode="json"), target=target, immediate=False),
                event,
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.enforcer_rank_request",
            dict(target=target),
            operation,
            authorize=lambda c: self._access(c, viewer),
            auto_audit=False,
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            handler = HandlerService(self.store).current(c)[1].handler_id == viewer.user_id
            state = load_state(c, self.store.campaign_id)
            row = next((x for x in self._rank_rows(c) if x["id"] == identity), None)
            if row:
                if not handler and row["subject_id"] != str(viewer.user_id):
                    raise WorkflowError(
                        "This factual request belongs to its original participants."
                    )
                body = json.loads(row["body_json"])
                return dict(
                    id=identity,
                    revision=row["revision"],
                    state=row["state"],
                    kind=RANK,
                    can_decide=handler,
                    actor=body["actor"],
                    target=body["target"],
                )
            case = next((x for x in state.enforcer_accusations if x.id == identity), None)
            if case is None or not handler and case.actor.entity != str(viewer.user_id):
                raise WorkflowError("This actual accusation belongs to other participants.")
            self._proof(c, case.id)
            return dict(
                id=identity,
                revision=state.revision,
                state="pending" if case.detained or case.position_event is None else "resolved",
                kind="enforcer_innocence" if case.detained else "enforcer_release_position",
                can_decide=handler,
                case=case.model_dump(mode="json"),
            )

    def _proof(self, c: Connection, identity: str) -> None:
        state = load_state(c, self.store.campaign_id)
        case = next((x for x in state.enforcer_accusations if x.id == identity), None)
        if case is None:
            raise WorkflowError("This actual original accusation is unavailable.")
        history = t.m2["m2_state_history"]
        snapshot = c.scalar(
            sa.select(history.c.body_json).where(
                history.c.campaign_id == self.store.campaign_id,
                history.c.event_id == case.source_event,
            )
        )
        source = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == case.source_event,
                )
            )
            .mappings()
            .first()
        )
        original = GameState.model_validate_json(snapshot) if snapshot else None
        saved = (
            next((x for x in original.enforcer_accusations if x.id == identity), None)
            if original
            else None
        )
        stable = {
            k: v
            for k, v in case.model_dump().items()
            if k
            not in (
                "detained",
                "release_event",
                "released_by",
                "innocence_evidence",
                "release_cell",
                "position_event",
                "position_account",
            )
        }
        if (
            source is None
            or source["kind"] != "m3.enforcer_accusation"
            or source["actor_id"] != case.actor.entity
            or saved is None
            or any(saved.model_dump().get(k) != v for k, v in stable.items())
        ):
            raise WorkflowError("SOURCE_ACCUSATION_MISSING: recover the actual Foundation arrest.")

    def _rank_proof(self, c: Connection, identity: str) -> None:
        state = load_state(c, self.store.campaign_id)
        rank = next((x for x in state.enforcer_ranks if x.id == identity), None)
        if rank is None:
            raise WorkflowError("Recover the actual factual rank declaration.")
        history = t.m2["m2_state_history"]
        body = c.scalar(
            sa.select(history.c.body_json).where(
                history.c.campaign_id == self.store.campaign_id,
                history.c.event_id == rank.source_event,
            )
        )
        source = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == rank.source_event,
                )
            )
            .mappings()
            .first()
        )
        original = GameState.model_validate_json(body) if body else None
        if (
            source is None
            or source["kind"] != "m3.enforcer_rank_recorded"
            or source["actor_id"] != rank.handler.entity
            or original is None
            or str(original.handler) != rank.handler.entity
            or rank not in original.enforcer_ranks
        ):
            raise WorkflowError(
                "SOURCE_RANK_MISSING: recover the actual Handler's factual declaration."
            )

    def rank(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        superior: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            HandlerService(self.store).authorize(c, viewer)
            row = next((x for x in self._rank_rows(c) if x["id"] == identity), None)
            if row is None or row["state"] == "resolved" or row["revision"] != revision:
                raise WorkflowError("STALE_ENFORCER_RANK: reopen the actual factual request.")
            body, event = json.loads(row["body_json"]), str(uuid4())
            updated = rules.record_rank(
                load_state(c, self.store.campaign_id),
                ActorRef(kind="npc", entity=body["target"]),
                ActorRef.model_validate(body["actor"]),
                superior,
                ActorRef(kind="handler", entity=str(viewer.user_id)),
                str(uuid4()),
                event,
                account,
                profiles(c, self.store.campaign_id),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.enforcer_rank_recorded",
                updated,
                event_id=event,
                work_id=identity,
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
                    event_id=event,
                    body_json=json.dumps(body | dict(rank=updated.enforcer_ranks[-1].id)),
                )
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.enforcer_rank",
            dict(id=identity, revision=revision, superior=superior, account=account),
            operation,
            authorize=lambda c: self._access(c, viewer),
            auto_audit=False,
        )

    def accuse(
        self, viewer: GuildViewer, key: str, target: str, rank: str, expected: str, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            actor = self._actor(c, viewer)
            state = load_state(c, self.store.campaign_id)
            if target not in self._known(state, actor):
                raise WorkflowError("Choose an actually known NPC.")
            self._rank_proof(c, rank)
            identity, event = str(uuid4()), str(uuid4())
            updated = rules.accuse(
                state,
                actor,
                ActorRef(kind="npc", entity=target),
                expected,
                profiles(c, self.store.campaign_id),
                rank,
                identity,
                event,
                account,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.enforcer_accusation",
                updated,
                event_id=event,
                accusation_id=identity,
            )
            return dict(id=identity, detained=True)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.enforcer_accuse",
                dict(target=target, rank=rank, expected=expected, account=account),
                operation,
                authorize=lambda c: self._access(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def release(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, evidence: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            HandlerService(self.store).authorize(c, viewer)
            self._proof(c, identity)
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision:
                raise WorkflowError("STALE_ENFORCER_CASE: review the actual current custody.")
            event = str(uuid4())
            updated = rules.release(
                state,
                identity,
                ActorRef(kind="handler", entity=str(viewer.user_id)),
                event,
                evidence,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.enforcer_innocence_proved",
                updated,
                event_id=event,
                accusation_id=identity,
            )
            return dict(id=identity, detained=False)

        return self.store._write(
            viewer,
            key,
            "m3.enforcer_release",
            dict(id=identity, revision=revision, evidence=evidence),
            operation,
            authorize=lambda c: self._access(c, viewer),
            auto_audit=False,
        )

    def record_released_position(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        cell: tuple[int, int],
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            HandlerService(self.store).authorize(c, viewer)
            self._proof(c, identity)
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision:
                raise WorkflowError("STALE_ENFORCER_CASE: reopen the actual released body source.")
            event = str(uuid4())
            updated = rules.record_released_position(
                state,
                identity,
                cell,
                ActorRef(kind="handler", entity=str(viewer.user_id)),
                event,
                account,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.enforcer_release_position_recorded",
                updated,
                event_id=event,
                accusation_id=identity,
            )
            return dict(id=identity, cell=list(cell))

        try:
            return self.store._write(
                viewer,
                key,
                "m3.enforcer_release_position",
                dict(id=identity, revision=revision, cell=list(cell), account=account),
                operation,
                authorize=lambda c: self._access(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
