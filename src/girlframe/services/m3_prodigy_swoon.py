"""Spend actual Prodigy confidence on a separately owned NPC reaction."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_ancillary_cadre as rank
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, CastRole, Model
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_cast import validate_role
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_ancillary_discipline import KIND as NOTCH
from girlframe.services.m3_ancillary_discipline import (
    AncillaryDisciplineService,
    reaction_notches,
)
from girlframe.services.m3_battle import _cast, _visible
from girlframe.services.m3_consume_support import knowledge_allowed
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.p1_source_pause import require_clear
from girlframe.services.read_only_bot import GuildViewer

KIND = "prodigy_swoon"


class Swoon(Model):
    id: str
    actor: CastRole
    target: CastRole
    scene: str
    channel: int
    notch: str
    resolved: str | None = None
    accepted: bool | None = None
    reaction: str = ""


def records(state: GameState) -> tuple[Swoon, ...]:
    return tuple(Swoon.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


class SwoonService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store
        self.discipline = AncillaryDisciplineService(game)

    def _candidates(
        self, c: Connection, state: GameState, channel: int, actor: ActorRef
    ) -> tuple[str, CastRole, dict[str, tuple[CastRole, str]]]:
        cast = _cast(self.game, c, state, channel)
        registered = profiles(c, self.store.campaign_id)
        body = resolve(state, actor, registered)
        source = validate_role(cast, body)
        options: dict[str, tuple[CastRole, str]] = {}
        if (
            body.cell is None
            or body.offstage_source
            or body.custody not in (None, "free", "converted")
            or not knowledge_allowed(state, actor)
        ):
            return cast.id, source, options
        for role in cast.roles:
            if (
                role.actor.kind != "npc"
                or role.controller == source.controller
                or not _visible(state, role.actor, source.controller)
                or not knowledge_allowed(state, role.actor)
            ):
                continue
            try:
                target = resolve(state, role.actor, registered)
                validate_role(cast, target)
            except (ValueError, WorkflowError):
                continue
            if (
                target.rules == "npc"
                and target.cell == body.cell
                and not body.inside_frame
                and not target.inside_frame
                and not target.offstage_source
                and target.custody in (None, "free")
            ):
                options[role.actor.token] = (role, target.label)
        return cast.id, source, options

    def options(
        self, c: Connection, state: GameState, viewer: GuildViewer, channel: int, actor: ActorRef
    ) -> dict[str, Any]:
        self.discipline._gate(c, viewer)
        notches = reaction_notches(self.game, state, actor, viewer.user_id)
        people = {}
        if notches:
            _, _, available = self._candidates(c, state, channel, actor)
            people = {key: label for key, (_, label) in available.items()}
        return dict(notches=notches, npcs=people)

    def menu(self, viewer: GuildViewer, channel: int, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            return dict(
                revision=state.revision,
                owned=self.discipline.confidence(c, state, viewer, actor),
                **self.options(c, state, viewer, channel, actor),
            )

    def _notch(self, state: GameState, value: Swoon) -> dict[str, str]:
        row = next(
            (x for x in state.facts if x.get("kind") == NOTCH and x.get("id") == value.notch), None
        )
        if row is None or row.get("actor") != value.actor.actor.token or row.get("spent"):
            raise WorkflowError("Recover the actual original unspent confidence notch.")
        return row

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        body: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            return self.store._write(
                viewer,
                key,
                KIND,
                body,
                operation,
                authorize=lambda c: self.discipline._gate(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _save(
        self,
        c: Connection,
        viewer: GuildViewer,
        key: str,
        state: GameState,
        value: Swoon,
        event: str,
        kind: str,
    ) -> dict[str, Any]:
        state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.id)]
        state.facts.append(dict(kind=KIND, id=value.id, body=value.model_dump_json()))
        self.game.event(c, viewer.user_id, key, kind, state, event_id=event, scene_id=value.scene)
        return dict(id=value.id, event=event)

    def offer(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        actor: ActorRef,
        revision: int,
        notch: str,
        target: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            require_clear(self.game, c, channel)
            require_scene_clear(self.game, c, channel)
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision or notch not in reaction_notches(
                self.game, state, actor, viewer.user_id
            ):
                raise WorkflowError("Reopen your actual unspent confidence.")
            scene, source, people = self._candidates(c, state, channel, actor)
            if target not in people or source.controller != viewer.user_id:
                raise WorkflowError("Choose a known actual NPC present in the original scene.")
            identity = str(uuid4())
            value = Swoon(
                id=identity,
                actor=source,
                target=people[target][0],
                scene=scene,
                channel=channel,
                notch=notch,
            )
            self._notch(state, value)["reserved"] = identity
            return self._save(c, viewer, key, state, value, identity, "m3.prodigy_swoon_offered")

        return self._write(
            viewer,
            key,
            dict(
                channel=channel,
                actor=actor.token,
                revision=revision,
                notch=notch,
                target=target,
            ),
            operation,
        )

    def _role(self, c: Connection, state: GameState, viewer: GuildViewer, value: Swoon) -> str:
        if value.resolved is None and value.actor.controller == viewer.user_id:
            return "withdraw"
        if value.resolved is None and value.target.controller == viewer.user_id:
            scene, source, people = self._candidates(c, state, value.channel, value.actor.actor)
            target = people.get(value.target.actor.token)
            if (
                scene == value.scene
                and source == value.actor
                and target
                and target[0] == value.target
            ):
                return "react"
        raise WorkflowError("This original confidence reaction is unavailable.")

    def tasks(
        self, c: Connection, state: GameState, viewer: GuildViewer
    ) -> tuple[tuple[str, str], ...]:
        result = []
        for value in records(state):
            if value.resolved or viewer.user_id not in (
                value.target.controller,
                value.actor.controller,
            ):
                continue
            try:
                self.discipline._gate(c, viewer)
                result.append((value.id, self._role(c, state, viewer, value)))
            except (ValueError, WorkflowError):
                continue
        return tuple(result)

    def _owned(
        self, c: Connection, state: GameState, viewer: GuildViewer, identity: str
    ) -> tuple[Swoon, str]:
        value = next((x for x in records(state) if x.id == identity), None)
        if value is None:
            raise WorkflowError("This original confidence reaction is unavailable.")
        return value, self._role(c, state, viewer, value)

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.discipline._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            value, role = self._owned(c, state, viewer, identity)
            label = None
            if role == "react" and _visible(state, value.actor.actor, viewer.user_id):
                label = resolve(state, value.actor.actor, profiles(c, self.store.campaign_id)).label
            return dict(revision=state.revision, role=role, known=label)

    def answer(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        choice: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value, role = self._owned(c, state, viewer, identity)
            if role == "react" and choice == "confirm":
                self.game.unpaused(c)
                require_clear(self.game, c, value.channel)
                require_scene_clear(self.game, c, value.channel)
            accepted = role == "react" and choice == "confirm" and 0 < len(account.strip()) <= 1200
            if state.revision != revision or not (
                accepted
                or not account
                and choice == ("withdraw" if role == "withdraw" else "decline")
            ):
                raise WorkflowError("Reopen the original response and choose only your own action.")
            notch = self._notch(state, value)
            if notch.get("reserved") != identity:
                raise WorkflowError("Recover the exact reserved confidence notch.")
            event = str(uuid4())
            if accepted:
                cadre = rank.current(state, value.actor.actor)
                if cadre is None or cadre.id != notch.get("cadre"):
                    raise WorkflowError("Recover the original Prodigy's actual Cadre.")
                notch.update(spent=event, reaction=identity)
            del notch["reserved"]
            completed = value.model_copy(
                update=dict(
                    resolved=event,
                    accepted=accepted,
                    reaction=account.strip(),
                )
            )
            return self._save(c, viewer, key, state, completed, event, "m3.prodigy_swoon_resolved")

        return self._write(
            viewer,
            key,
            dict(
                id=identity,
                revision=revision,
                choice=choice,
                account=account,
            ),
            operation,
        )
