"""Verified placement for approved Ancillary roles and actual cockpit operations."""

from collections.abc import Callable
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_ancillary as ancillary
from girlframe.engine import m3_chained_darling as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import is_helpless
from girlframe.engine.m3_actor_state import ActorRef, ActorView, CastRole, Model
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_cast import validate_role
from girlframe.engine.m3_leviathan_arrival import external_pose, install_external_pose
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_battle import _cast, _visible
from girlframe.services.m3_consume_support import knowledge_allowed
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.p1_source_pause import require_clear
from girlframe.services.read_only_bot import GuildViewer

KIND = "chained_pose_review"
Mode = Literal["piloting", "inside_frame", "outside_frame"]
SUPPORTED = ("CHAINED DARLING", "WARBOY")


class Placement(Model):
    id: str
    role: CastRole
    gm: int
    appointment: str
    scene: str
    channel: int
    previous: str
    mode: Mode
    account: str
    assistant: CastRole | None = None
    assisted: str | None = None
    decision: str | None = None
    accepted: bool | None = None


def records(state: GameState) -> tuple[Placement, ...]:
    return tuple(
        Placement.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


class ChainedPlacementService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer, book: ancillary.Book | None = None) -> None:
        AncillaryService(MissionService(self.store))._access(c, viewer)
        if book is not None:
            gate = Access(self.store)
            if book == "CHAINED DARLING":
                gate.require_specialist_rule(rules.RULE)
            assert gate.registry is not None
            gate.registry.require_available(ancillary.STARTERS[book].rule)

    def _book(self, state: GameState, actor: ActorRef) -> ancillary.Book:
        original = ancillary.find(state, actor)
        if original is None or original.draft.book not in SUPPORTED:
            raise WorkflowError("This Ancillary role needs its own approved physical workflow.")
        return original.draft.book

    def _scene(
        self,
        c: Connection,
        state: GameState,
        channel: int,
        actor: ActorRef,
    ) -> tuple[CastRole, ActorView, int, str, str]:
        actual = resolve(state, actor, profiles(c, self.store.campaign_id))
        self._book(state, actor)
        cast = _cast(self.game, c, state, channel)
        gm, appointment = MedicalService(self.store)._handler(c)
        role = validate_role(cast, actual)
        if (
            actual.rules != "ancillary"
            or actual.cell is None
            or actual.offstage_source
            or actual.custody not in (None, "free", "converted")
            or actual.controller == gm
            or cast.facilitator != gm
        ):
            raise WorkflowError("Use the original Ancillary role with the current facilitator.")
        return role, actual, gm, appointment, cast.id

    def _choices(self, state: GameState, actor: ActorRef) -> tuple[Mode, ...]:
        pose = external_pose(state, actor)
        if pose is None:
            return ("piloting", "inside_frame", "outside_frame")
        if pose.girl_cell != pose.frame_cell:
            return ()
        if pose.mode == "outside_frame":
            return ("inside_frame",)
        if not is_helpless(state, actor):
            options: tuple[Mode, ...] = ("outside_frame",)
            return (*options, "piloting") if pose.mode == "inside_frame" else options
        return ()

    def _assistants(
        self,
        c: Connection,
        state: GameState,
        channel: int,
        actual: ActorView,
    ) -> dict[str, tuple[CastRole, str]]:
        cast = _cast(self.game, c, state, channel)
        helpers = {}
        for role in cast.roles:
            if (
                role.controller == actual.controller
                or not _visible(state, role.actor, actual.controller)
                or not knowledge_allowed(state, role.actor)
            ):
                continue
            try:
                helper = resolve(state, role.actor, profiles(c, self.store.campaign_id))
            except ValueError:
                continue
            if (
                helper.cell == actual.cell
                and not helper.offstage_source
                and helper.alive
                and helper.controller == role.controller
                and (
                    helper.inside_frame is False
                    or helper.rules in ("npc", "handler", "director")
                    and helper.inside_frame is None
                )
                and helper.custody in (None, "free")
                and not is_helpless(state, role.actor)
            ):
                helpers[role.actor.token] = (role, helper.label)
        return helpers

    def _assisted(self, state: GameState, actor: ActorRef) -> bool:
        pose = external_pose(state, actor)
        return bool(pose and pose.mode == "outside_frame" and is_helpless(state, actor))

    def available(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        channel: int,
        actor: ActorRef,
    ) -> tuple[Mode, ...]:
        self._gate(c, viewer, self._book(state, actor))
        role, actual, gm, appointment, scene = self._scene(c, state, channel, actor)
        if role.controller != viewer.user_id:
            raise WorkflowError("Only the original owner can propose this physical action.")
        if any(
            x.role == role
            and x.decision is None
            and self._consistent(c, state, x, role, actual, gm, appointment, scene)
            for x in records(state)
        ):
            return ()
        if self._assisted(state, actor) and not self._assistants(c, state, channel, actual):
            return ()
        return self._choices(state, actor)

    def menu(self, viewer: GuildViewer, channel: int, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            modes = self.available(c, state, viewer, channel, actor)
            assistance = self._assisted(state, actor)
            people = {}
            if modes and assistance:
                _, actual, _, _, _ = self._scene(c, state, channel, actor)
                people = {
                    token: label
                    for token, (_, label) in self._assistants(c, state, channel, actual).items()
                }
            return dict(
                revision=state.revision,
                modes=modes,
                initial=external_pose(state, actor) is None,
                assistance=assistance,
                people=people,
            )

    def _save(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        key: str,
        value: Placement,
        event: str,
    ) -> dict[str, Any]:
        state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.id)]
        state.facts.append(dict(kind=KIND, id=value.id, body=value.model_dump_json()))
        kind = (
            "m3.chained_pose_assistance"
            if value.assistant
            and viewer.user_id == value.assistant.controller
            and event == value.assisted
            else "m3.chained_pose_verified"
            if value.decision
            else "m3.chained_pose_proposed"
        )
        self.game.event(
            c,
            viewer.user_id,
            key,
            kind,
            state,
            event_id=event,
            scene_id=value.scene,
        )
        return dict(id=value.id, event=event, accepted=value.accepted)

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            return self.store._write(
                viewer,
                key,
                "m3.chained_pose",
                payload,
                operation,
                authorize=lambda c: self._gate(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        actor: ActorRef,
        revision: int,
        mode: Mode,
        account: str,
        *,
        helper: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            require_clear(self.game, c, channel)
            require_scene_clear(self.game, c, channel)
            state = load_state(c, self.store.campaign_id)
            if (
                state.revision != revision
                or mode not in self.available(c, state, viewer, channel, actor)
                or not 0 < len(account.strip()) <= 1200
            ):
                raise WorkflowError("Choose the actual original position or cockpit exit.")
            role, actual, gm, appointment, scene = self._scene(c, state, channel, actor)
            pose = external_pose(state, actor)
            assistant = None
            if self._assisted(state, actor):
                available = self._assistants(c, state, channel, actual)
                if helper not in available:
                    raise WorkflowError("Choose another co-present original role for assistance.")
                assert helper is not None
                assistant, _ = available[helper]
            elif helper is not None:
                raise WorkflowError("Assistance applies only when returning to the actual Frame.")
            event = str(uuid4())
            value = Placement(
                id=event,
                role=role,
                gm=gm,
                appointment=appointment,
                scene=scene,
                channel=channel,
                previous=fingerprint(pose) if pose is not None else actual.source_sha256,
                mode=mode,
                account=account.strip(),
                assistant=assistant,
            )
            for prior in records(state):
                if prior.role == role and prior.decision is None:
                    superseded = prior.model_copy(update=dict(accepted=False, decision=event))
                    fact = next(
                        x for x in state.facts if x.get("kind") == KIND and x.get("id") == prior.id
                    )
                    fact["body"] = superseded.model_dump_json()
            return self._save(c, state, viewer, key, value, event)

        return self._write(
            viewer,
            key,
            dict(
                channel=channel,
                actor=actor.token,
                revision=revision,
                mode=mode,
                account=account,
                helper=helper,
            ),
            operation,
        )

    def _step(self, value: Placement) -> tuple[str, int]:
        if value.assistant is not None and value.assisted is None:
            return "assist", value.assistant.controller
        return "verify", value.gm

    def _read(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        identity: str,
    ) -> tuple[Placement, ActorView, str]:
        value = next(
            (
                x
                for x in records(state)
                if x.id == identity and x.decision is None and self._step(x)[1] == viewer.user_id
            ),
            None,
        )
        if value is None:
            raise WorkflowError("This original physical review is unavailable.")
        actor = value.role.actor
        self._gate(c, viewer, self._book(state, actor))
        role, actual, gm, appointment, scene = self._scene(c, state, value.channel, actor)
        if not self._consistent(c, state, value, role, actual, gm, appointment, scene):
            raise WorkflowError("STALE_CHAINED_POSE: recover the original body and scene.")
        return value, actual, self._step(value)[0]

    def _consistent(
        self,
        c: Connection,
        state: GameState,
        value: Placement,
        role: CastRole,
        actual: ActorView,
        gm: int,
        appointment: str,
        scene: str,
    ) -> bool:
        pose = external_pose(state, role.actor)
        current = fingerprint(pose) if pose is not None else actual.source_sha256
        if (
            (role, gm, appointment, scene) != (value.role, value.gm, value.appointment, value.scene)
            or current != value.previous
            or value.mode not in self._choices(state, role.actor)
        ):
            return False
        if value.assistant is None:
            return True
        assistant = self._assistants(c, state, value.channel, actual).get(
            value.assistant.actor.token
        )
        return assistant is not None and assistant[0] == value.assistant

    def tasks(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
    ) -> tuple[tuple[str, str], ...]:
        candidates = tuple(
            x for x in records(state) if x.decision is None and self._step(x)[1] == viewer.user_id
        )
        if not candidates:
            return ()
        try:
            self._gate(c, viewer)
        except (ValueError, WorkflowError):
            return ()
        ready = []
        for value in candidates:
            try:
                _, _, step = self._read(c, state, viewer, value.id)
            except (ValueError, WorkflowError):
                continue
            ready.append((value.id, step))
        return tuple(ready)

    def review(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            value, actual, step = self._read(c, state, viewer, identity)
            return dict(
                revision=state.revision,
                actor=actual.label,
                step=step,
                mode=value.mode,
                account=value.account,
            )

    def decide(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        accepted: bool,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value, actual, step = self._read(c, state, viewer, identity)
            MedicalService(self.store)._idle(c)
            require_clear(self.game, c, value.channel)
            require_scene_clear(self.game, c, value.channel)
            if state.revision != revision or type(accepted) is not bool:
                raise WorkflowError("STALE_CHAINED_POSE: reopen this original physical review.")
            event = str(uuid4())
            if step == "assist":
                update = (
                    dict(assisted=event)
                    if accepted
                    else dict(assisted=event, accepted=False, decision=event)
                )
                return self._save(c, state, viewer, key, value.model_copy(update=update), event)
            actor = value.role.actor
            pose = external_pose(state, actor)
            if accepted and pose is None:
                state = install_external_pose(
                    state,
                    actor,
                    actual.cell,
                    actual.cell,
                    value.mode,
                    event,
                    value.account,
                    owner=actual.controller,
                    judge=viewer.user_id,
                )
                if self._book(state, actor) == "CHAINED DARLING":
                    state.facts.append(dict(kind=rules.KIND, actor=actor.token, source=event))
            elif accepted and pose is not None:
                changed = pose.model_copy(
                    update=dict(mode=value.mode, position_event=event, account=value.account)
                )
                state.external_poses = [
                    changed if x.actor == actor else x for x in state.external_poses
                ]
                if self._book(state, actor) == "CHAINED DARLING" and not any(
                    x.get("kind") == rules.KIND
                    and x.get("actor") == actor.token
                    and x.get("source") == pose.source_event
                    for x in state.facts
                ):
                    state.facts.append(
                        dict(kind=rules.KIND, actor=actor.token, source=pose.source_event)
                    )
            value = value.model_copy(update=dict(accepted=accepted, decision=event))
            return self._save(c, state, viewer, key, value, event)

        return self._write(
            viewer,
            key,
            dict(
                id=identity,
                revision=revision,
                accepted=accepted,
            ),
            operation,
        )
