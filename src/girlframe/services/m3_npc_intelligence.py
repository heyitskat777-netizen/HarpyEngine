"""Private source-backed discovery for the original scene-cast Intelligence Agent."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.read_only_bot import GuildViewer

RULE = "npc.npc.intelligence-agent"
KIND = "npc_intelligence_inquiry"


class Inquiry(Model):
    id: str
    channel: int
    scene: str
    agent: ActorRef
    controller: int
    subject: ActorRef
    account: str
    facilitator: int
    appointment: str
    faction: str | None = None
    learned: str | None = None
    finding: str | None = None
    reviewed: str | None = None


def inquiries(state: GameState) -> tuple[Inquiry, ...]:
    return tuple(
        Inquiry.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


class IntelligenceService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "world", director_response=True)
        access.authorize(c, viewer, "plays", director_response=True)
        try:
            access.require_specialist_rule(RULE)
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _scene(
        self, c: Connection, state: GameState, channel: int, ref: ActorRef, controller: int
    ) -> tuple[SceneCast, dict[str, Npc], int, str]:
        cast = _cast(self.game, c, state, channel)
        gm, appointment = MedicalService(self.store)._handler(c)
        if state.world is None or cast.facilitator != gm:
            raise WorkflowError("Recover the proper facilitator and local cast")
        by_id = {x.id: x for x in state.world.npcs}
        agent = by_id.get(ref.entity)
        if (
            agent is None
            or ref.kind != "npc"
            or not agent.alive
            or agent.captive_of is not None
            or agent.controller != controller
            or "intelligence_agent" not in agent.jobs
            or "director" in agent.jobs
            or not any(x.actor == ref and x.controller == controller for x in cast.roles)
        ):
            raise WorkflowError("Use the actual local Intelligence Agent")
        actor = resolve(state, ref, (), require_current_profile=False)
        if actor.offstage_source or actor.cell is None or actor.custody:
            raise WorkflowError("Use the actual local Intelligence Agent")
        subjects = {}
        for role in cast.roles:
            subject = by_id.get(role.actor.entity) if role.actor.kind == "npc" else None
            if (
                subject
                and subject.alive
                and subject.id != agent.id
                and subject.controller == role.controller
                and (subject.revealed or subject.controller == controller)
            ):
                target = resolve(state, role.actor, (), require_current_profile=False)
                if target.cell == actor.cell and not target.offstage_source:
                    subjects[role.actor.token] = subject
        return cast, subjects, gm, appointment

    def menu(self, viewer: GuildViewer, channel: int, ref: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            _, subjects, _, _ = self._scene(c, state, channel, ref, viewer.user_id)
            return dict(revision=state.revision, targets={k: x.name for k, x in subjects.items()})

    def ask(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        ref: ActorRef,
        revision: int,
        target: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            require_scene_clear(self.game, c, channel)
            MedicalService(self.store)._idle(c)
            state = load_state(c, self.store.campaign_id)
            cast, subjects, gm, appointment = self._scene(c, state, channel, ref, viewer.user_id)
            subject = subjects.get(target)
            if (
                revision != state.revision
                or subject is None
                or not 0 < len(account.strip()) <= 1200
            ):
                raise WorkflowError("Choose the original local subject and describe the inquiry")
            subject_ref = next(x.actor for x in cast.roles if x.actor.token == target)
            if any(
                x.agent == ref and x.subject == subject_ref and not x.reviewed
                for x in inquiries(state)
            ):
                raise WorkflowError("Recover the original unresolved inquiry")
            event = str(uuid4())
            value = Inquiry(
                id=event,
                channel=channel,
                scene=cast.id,
                agent=ref,
                subject=subject_ref,
                controller=viewer.user_id,
                account=account.strip(),
                facilitator=gm,
                appointment=appointment,
            )
            state.facts.append(dict(kind=KIND, id=event, body=value.model_dump_json()))
            self.game.event(
                c, viewer.user_id, key, "m3.npc_intelligence_asked", state, event_id=event
            )
            return dict(id=event)

        return self.store._write(
            viewer,
            key,
            "m3.npc_intelligence_ask",
            dict(
                channel=channel, role=ref.token, revision=revision, target=target, account=account
            ),
            operation,
            authorize=lambda c: self._gate(c, viewer),
            auto_audit=False,
        )

    def tasks(
        self, c: Connection, state: GameState, viewer: GuildViewer
    ) -> tuple[tuple[Inquiry, str], ...]:
        if state.world is None:
            return ()
        agents = {x.id: x.controller for x in state.world.npcs if x.alive and x.captive_of is None}
        candidates = tuple(
            (item, step)
            for item in inquiries(state)
            if agents.get(item.agent.entity) == item.controller
            if (
                step := (
                    "report"
                    if item.reviewed and item.learned and item.controller == viewer.user_id
                    else "review"
                    if not item.reviewed and item.facilitator == viewer.user_id
                    else None
                )
            )
        )
        if candidates:
            try:
                self._gate(c, viewer)
            except WorkflowError:
                return ()
        return candidates

    def _history(self, c: Connection, event: str, kind: str, human: int) -> GameState | None:
        history = t.m2["m2_state_history"]
        body = c.scalar(
            sa.select(history.c.body_json)
            .join(t.events, t.events.c.id == history.c.event_id)
            .where(
                history.c.campaign_id == self.store.campaign_id,
                history.c.event_id == event,
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.kind == kind,
                t.events.c.actor_id == str(human),
            )
        )
        return GameState.model_validate_json(body) if body else None

    def _read(
        self, c: Connection, state: GameState, viewer: GuildViewer, identity: str
    ) -> tuple[Inquiry, str]:
        pending = next((x for x in self.tasks(c, state, viewer) if x[0].id == identity), None)
        if pending is None:
            raise WorkflowError("This original private inquiry is unavailable")
        value, step = pending
        agent = (
            next((x for x in state.world.npcs if x.id == value.agent.entity), None)
            if state.world
            else None
        )
        if agent is None or agent.controller != value.controller:
            raise WorkflowError("Recover the actual original Intelligence Agent")
        asked = self._history(c, value.id, "m3.npc_intelligence_asked", value.controller)
        root = value.model_copy(
            update=dict(faction=None, learned=None, finding=None, reviewed=None)
        )
        if asked is None or root not in inquiries(asked):
            raise WorkflowError("Recover the original authorized inquiry")
        if value.reviewed:
            saved = self._history(
                c, value.reviewed, "m3.npc_intelligence_reviewed", value.facilitator
            )
            if saved is None or value not in inquiries(saved):
                raise WorkflowError("Recover the actual original learned finding")
        elif MedicalService(self.store)._handler(c) != (viewer.user_id, value.appointment):
            raise WorkflowError("Recover the original human facilitator")
        return value, step

    def _findings(self, c: Connection, state: GameState, value: Inquiry) -> dict[str, str]:
        cast, subjects, gm, appointment = self._scene(
            c, state, value.channel, value.agent, value.controller
        )
        subject = subjects.get(value.subject.token)
        if (
            cast.id != value.scene
            or (gm, appointment) != (value.facilitator, value.appointment)
            or subject is None
            or state.world is None
        ):
            raise WorkflowError("Recover the original co-present inquiry")
        return {
            x.id: x.name
            for x in state.world.factions
            if x.id in subject.secret_factions
            and x.id != subject.faction
            and x.active
            and not any(
                previous.agent == value.agent
                and previous.subject == value.subject
                and previous.faction == x.id
                for previous in inquiries(state)
            )
        }

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            value, step = self._read(c, state, viewer, identity)
            return dict(
                step=step,
                revision=state.revision,
                inquiry=value.account,
                learned=value.learned,
                finding=value.finding,
                factions=self._findings(c, state, value) if step == "review" else {},
            )

    def review(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        faction: str | None,
        finding: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value, step = self._read(c, state, viewer, identity)
            if (
                step != "review"
                or revision != state.revision
                or not 0 < len(finding.strip()) <= 1200
            ):
                raise WorkflowError("Refresh the inquiry and record the actual review")
            learned = None
            if faction is not None:
                require_scene_clear(self.game, c, value.channel)
                MedicalService(self.store)._idle(c)
                learned = self._findings(c, state, value).get(faction)
                if learned is None:
                    raise WorkflowError("Choose an actual concealed affiliation")
            event = str(uuid4())
            value = value.model_copy(
                update=dict(
                    faction=faction, learned=learned, finding=finding.strip(), reviewed=event
                )
            )
            state.facts = [
                x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, identity)
            ]
            state.facts.append(dict(kind=KIND, id=identity, body=value.model_dump_json()))
            self.game.event(
                c, viewer.user_id, key, "m3.npc_intelligence_reviewed", state, event_id=event
            )
            return dict(id=identity, recorded=True)

        return self.store._write(
            viewer,
            key,
            "m3.npc_intelligence_review",
            dict(id=identity, faction=faction, revision=revision, finding=finding),
            operation,
            authorize=lambda c: self._gate(c, viewer),
            auto_audit=False,
        )
