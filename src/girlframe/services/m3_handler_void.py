"""Actual original Handler Void choices and source-proved medical follow-through."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_void as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import body_original, same_handler_body
from girlframe.engine.m3_handler_void_state import HandlerVoid
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


class HandlerVoidService:
    def __init__(self, store: OnboardingStore, game: "GameService | None" = None):
        from girlframe.services.m2_game import GameService

        self.store, self.game = store, game or GameService(store)

    def _row(self, c: Connection, work: str, *, first: bool = False) -> dict[str, Any]:
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table)
                .where(table.c.campaign_id == self.store.campaign_id, table.c.id == work)
                .order_by(table.c.revision.asc() if first else table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowError("Recover the actual original Handler Void source.")
        return dict(row)

    def _proof(self, c: Connection, work: str) -> tuple[GameState, dict[str, Any], HandlerVoid]:
        from girlframe.services.m3_mockingbird_void import prove_handler_void_source

        first, row = self._row(c, work, first=True), self._row(c, work)
        body = json.loads(first["body_json"])
        actor = ActorRef.model_validate(body["owner"])
        if first["kind"] == "dive_handler_void":
            from girlframe.services.m3_dive_handler_void import (
                prove_handler_void_source as prove_dive_source,
            )

            prove_dive_source(self.game, c, first, body, actor)
        else:
            prove_handler_void_source(self.game, c, first, body, actor)
        state = load_state(c, self.store.campaign_id)
        episode = next((x for x in state.handler_void if x.work == work), None)
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == first["event_id"],
            )
        )
        proof = GameState.model_validate_json(raw) if raw else None
        original = next((x for x in proof.handler_void if x.work == work), None) if proof else None
        if (
            episode is None
            or original is None
            or original.actor != actor
            or original.source_event != first["event_id"]
            or original.phase != "choice"
            or any(
                getattr(episode, k) != getattr(original, k)
                for k in (
                    "id",
                    "actor",
                    "body",
                    "controller",
                    "work",
                    "source_event",
                    "appointment",
                )
            )
            or any(json.loads(row["body_json"]).get(k) != v for k, v in body.items())
        ):
            raise WorkflowError("Recover the original actual Handler body corruption proof.")
        return state, row, episode

    def _owned(
        self, c: Connection, viewer: GuildViewer, work: str, *, write: bool = False
    ) -> tuple[GameState, dict[str, Any], HandlerVoid]:
        if write:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
        else:
            self.game.authorize(c, viewer, game=False)
        state, row, episode = self._proof(c, work)
        if viewer.user_id != episode.controller:
            raise WorkflowError(
                "Only this actual original Handler's human owns the medical choice."
            )
        if write:
            if MedicalService(self.store)._handler(c)[1] != episode.appointment:
                raise WorkflowError(
                    "Recover the original medical source appointment before acting."
                )
            if episode.phase == "ended":
                raise WorkflowError(
                    "The actual original body ended; no successor inherits this Void."
                )
            if episode.actor.kind == "npc":
                actual = (
                    next((x for x in state.world.npcs if x.id == episode.actor.entity), None)
                    if state.world
                    else None
                )
                if (
                    actual is None
                    or not actual.alive
                    or actual.controller != episode.controller
                    or "director" not in actual.jobs
                ):
                    raise WorkflowError("Recover the actual original living Director body.")
            elif not same_handler_body(state, episode.actor):
                original = body_original(state, episode.actor)
                if not any(x.body == original and x.alive for x in state.handler_archives):
                    raise WorkflowError(
                        "Recover the actual original living body, not its replacement."
                    )
        return state, row, episode

    def _authorize(self, c: Connection, viewer: GuildViewer, work: str) -> None:
        Access(self.store).authorize(c, viewer, "plays", director_response=True)
        self._owned(c, viewer, work)

    def _can_act(self, c: Connection, viewer: GuildViewer) -> bool:
        try:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
        except WorkflowError:
            return False
        return True

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        result = []
        for episode in state.handler_void:
            if episode.controller != viewer.user_id or episode.phase in ("removed", "ended"):
                continue
            self._proof(c, episode.work)
            result.append(
                dict(
                    id=episode.work,
                    kind="handler_void",
                    state=episode.phase,
                    can_act=self._can_act(c, viewer),
                    label={
                        "choice": "Choose your actual Handler Void response",
                        "stabilized": "Remove stabilized original Handler corruption",
                        "surgery": "Record actual performed source surgery",
                    }[episode.phase],
                )
            )
        return result

    def get(self, viewer: GuildViewer, work: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state, row, episode = self._owned(c, viewer, work)
            return dict(
                id=work,
                revision=state.revision,
                episode=episode.model_dump(mode="json"),
                state=row["state"],
                can_act=episode.phase not in ("removed", "ended") and self._can_act(c, viewer),
            )

    def _complete(
        self,
        c: Connection,
        row: dict[str, Any],
        episode: HandlerVoid,
        event: str,
        viewer: GuildViewer | None,
        key: str,
    ) -> None:
        if row["state"] != "resolved":
            table = t.m3["m3_required_work"]
            body = json.loads(row["body_json"]) | dict(
                handler_void=episode.id, completion_event=event
            )
            c.execute(
                table.insert().values(
                    **(
                        row
                        | dict(
                            revision=row["revision"] + 1,
                            event_id=event,
                            state="resolved",
                            body_json=json.dumps(body, sort_keys=True),
                        )
                    )
                )
            )
            if row["kind"] == "dive_handler_void":
                from girlframe.services.m3_dive_handler_void import (
                    complete_handler_void as complete_dive_handler_void,
                )

                complete_dive_handler_void(self.game, c, row["id"], event, viewer, key)
            else:
                from girlframe.services.m3_mockingbird_void import complete_handler_void

                complete_handler_void(self.game, c, row["id"], event, viewer, key)

    def choose(
        self,
        viewer: GuildViewer,
        key: str,
        work: str,
        revision: int,
        choice: str,
        account: str,
        *,
        site: str = "",
        manifestation: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, row, episode = self._owned(c, viewer, work, write=True)
            if state.revision != revision:
                raise WorkflowError("STALE_HANDLER_VOID: reopen the original owned source choice.")
            if choice in ("knife", "drugs") and not site.strip():
                raise WorkflowError("Describe the actual localized corruption/removal site.")
            source = str(uuid4())
            changed = rules.choose(
                state,
                episode.id,
                choice,
                source,
                account=account,
                site=site,
                manifestation=manifestation,
            )
            current = next(x for x in changed.handler_void if x.id == episode.id)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_void_choice",
                changed,
                event_id=source,
                work_id=work,
                episode_id=episode.id,
                choice=choice,
            )
            if current.phase in ("removed", "stabilized"):
                self._complete(c, row, current, source, viewer, key)
            return dict(id=work, phase=current.phase, void_present=current.void_present)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.handler_void_choice",
                dict(
                    work=work,
                    revision=revision,
                    choice=choice,
                    account=account,
                    site=site,
                    manifestation=manifestation,
                ),
                operation,
                authorize=lambda c: self._authorize(c, viewer, work),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def record_surgery(
        self,
        viewer: GuildViewer,
        key: str,
        work: str,
        revision: int,
        account: str,
        *,
        performed: bool,
        removed: bool,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, row, episode = self._owned(c, viewer, work, write=True)
            if state.revision != revision or performed is not True or removed is not True:
                raise WorkflowError(
                    "Record actual performed surgery and actual corruption removal."
                )
            source = str(uuid4())
            changed = rules.surgery(state, episode.id, source, account)
            current = next(x for x in changed.handler_void if x.id == episode.id)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_void_surgery",
                changed,
                event_id=source,
                work_id=work,
                episode_id=episode.id,
            )
            self._complete(c, row, current, source, viewer, key)
            return dict(id=work, phase=current.phase, void_present=False)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.handler_void_surgery",
                dict(
                    work=work,
                    revision=revision,
                    account=account,
                    performed=performed,
                    removed=removed,
                ),
                operation,
                authorize=lambda c: self._authorize(c, viewer, work),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None


def completed_effect(game: "GameService", c: Connection, work: str, event: str) -> HandlerVoid:
    service = HandlerVoidService(game.store, game)
    _, row, episode = service._proof(c, work)
    if (
        row["state"] != "resolved"
        or json.loads(row["body_json"]).get("handler_void") != episode.id
        or json.loads(row["body_json"]).get("completion_event") != event
    ):
        raise WorkflowError("An actual Handler Void effect must own this completed source work.")
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    proof = GameState.model_validate_json(raw) if raw else None
    actual = next((x for x in proof.handler_void if x.id == episode.id), None) if proof else None
    if actual is None or not (
        actual.phase == "removed"
        and actual.removal_event == event
        or actual.phase == "stabilized"
        and actual.choice_event == event
        or actual.phase == "ended"
        and actual.ended_event == event
    ):
        raise WorkflowError(
            "A label or successor cannot substitute for actual Handler Void mechanics."
        )
    audit = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    payload = json.loads(audit["payload_json"]) if audit else {}
    assert proof is not None
    if actual.phase != "ended":
        expected = "m3.handler_void_surgery" if actual.surgery_account else "m3.handler_void_choice"
        if (
            audit is None
            or audit["kind"] != expected
            or audit["actor_id"] != str(actual.controller)
            or payload.get("work_id") != work
            or payload.get("episode_id") != actual.id
            or expected == "m3.handler_void_choice"
            and payload.get("choice") != actual.choice
        ):
            raise WorkflowError(
                "Only the original patient's authenticated performed choice completes this source."
            )
    else:
        from girlframe.services.m3_harpy_defeat import ended_actor_source

        if ended_actor_source(game, c, proof, actual.actor) != event:
            raise WorkflowError(
                "Recover the actual original-body death, not a role or label change."
            )
        if actual.actor.kind == "handler":
            original_body = body_original(proof, actual.actor)
            if not any(
                x.body == original_body
                and x.ending == "death"
                and not x.alive
                and x.source_event == event
                for x in proof.handler_archives
            ):
                raise WorkflowError(
                    "Living Handler departure does not remove the body's corruption."
                )
    return actual


def synchronize_endings(
    game: "GameService",
    c: Connection,
    event: str,
    viewer: GuildViewer | None = None,
    key: str | None = None,
) -> None:
    from girlframe.services.m3_harpy_defeat import ended_actor_source

    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    proof = GameState.model_validate_json(raw) if raw else None
    if proof is None:
        raise WorkflowError(
            "Commit the actual original body ending before closing Void source work."
        )
    service = HandlerVoidService(game.store, game)
    for episode in proof.handler_void:
        if episode.phase != "ended" or episode.ended_event != event:
            continue
        if ended_actor_source(game, c, proof, episode.actor) != event:
            raise WorkflowError(
                "Only actual original-body ending proof closes its source condition."
            )
        _, row, _ = service._proof(c, episode.work)
        if row["state"] != "resolved":
            service._complete(c, row, episode, event, viewer, key or event)
