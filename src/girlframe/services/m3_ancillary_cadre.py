"""An explicitly approved native Cadre for actual optional actors."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_ancillary_cadre as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, CastRole, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_ancillary import find
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_ancillary import AncillaryService
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import require_scene_clear
from girlframe.services.read_only_bot import GuildViewer


class AncillaryCadreService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        AncillaryService(MissionService(self.store))._access(c, viewer)

    def _scene(
        self,
        c: Connection,
        state: GameState,
        channel: int,
    ) -> tuple[SceneCast, int, str]:
        cast = _cast(self.game, c, state, channel)
        gm, appointment = MedicalService(self.store)._handler(c)
        if cast.facilitator != gm:
            raise WorkflowError("Use the actual original facilitator’s scene.")
        return cast, gm, appointment

    def _people(
        self,
        c: Connection,
        state: GameState,
        cast: SceneCast,
    ) -> dict[str, tuple[CastRole, str, str | None]]:
        if state.world is None:
            return {}
        bound = profiles(c, self.store.campaign_id)
        world = {x.id: x for x in state.world.pilots if x.alive}
        entries = {}
        for role in cast.roles:
            original = find(state, role.actor)
            body = world.get(role.actor.entity)
            if (
                original is None
                or body is None
                or role.controller != original.controller
                or body.controller != role.controller
                or rules.current(state, role.actor)
            ):
                continue
            try:
                actual = resolve(state, role.actor, bound)
            except ValueError:
                continue
            if (
                actual.alive
                and actual.cell is not None
                and actual.custody in (None, "free", "converted")
            ):
                entries[role.actor.token] = (role, actual.label, body.faction)
        return entries

    def _handlers(self, state: GameState) -> dict[str, tuple[ActorRef, int, str, str | None]]:
        root = active_handler(state)
        choices: dict[str, tuple[ActorRef, int, str, str | None]] = (
            {root.token: (root, int(root.entity), "Appointed Foundation Handler", None)}
            if root
            else {}
        )
        if state.world is not None:
            for person in state.world.npcs:
                if (
                    person.alive
                    and person.faction is not None
                    and person.captive_of is None
                    and "handler" in person.jobs
                    and "director" not in person.jobs
                ):
                    ref = ActorRef(kind="npc", entity=person.id)
                    choices[ref.token] = (ref, person.controller, person.name, person.faction)
        return choices

    def available(self, c: Connection, state: GameState, viewer: GuildViewer, channel: int) -> bool:
        self._gate(c, viewer)
        cast, gm, _ = self._scene(c, state, channel)
        return viewer.user_id == gm and len(self._people(c, state, cast)) >= 2

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            if not self.available(c, state, viewer, channel):
                raise WorkflowError("There are too few actual unassigned Ancillary roles.")
            cast, _, _ = self._scene(c, state, channel)
            return dict(
                revision=state.revision,
                people={k: x[1] for k, x in self._people(c, state, cast).items()},
                handlers={k: x[2] for k, x in self._handlers(state).items()},
            )

    def _save(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        key: str,
        value: rules.Cadre,
        event: str,
    ) -> dict[str, Any]:
        rules.put(state, value)
        self.game.event(
            c,
            viewer.user_id,
            key,
            "m3.ancillary_cadre_" + value.state,
            state,
            event_id=event,
            scene_id=value.scene,
        )
        return dict(id=value.id, state=value.state, event=event)

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        payload: dict[str, Any],
        callback: Callable[[Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            return self.store._write(
                viewer,
                key,
                "m3.ancillary_cadre",
                payload,
                callback,
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
        revision: int,
        handler: str,
        order: tuple[str, ...],
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            require_scene_clear(self.game, c, channel)
            state = load_state(c, self.store.campaign_id)
            cast, gm, appointment = self._scene(c, state, channel)
            people, handlers = self._people(c, state, cast), self._handlers(state)
            if (
                viewer.user_id != gm
                or state.revision != revision
                or handler not in handlers
                or not 2 <= len(order) <= 4
                or len(set(order)) != len(order)
                or not set(order) <= people.keys()
            ):
                raise WorkflowError(
                    "Choose an actual original Handler and two to four exact roles."
                )
            anchor, owner, _, faction = handlers[handler]
            if any(people[token][2] != faction for token in order):
                raise WorkflowError(
                    "The original members and Handler must share the same affiliation."
                )
            roles = tuple(people[token][0] for token in order)
            event = str(uuid4())
            refs = {member.actor for member in roles}
            for prior in rules.records(state):
                if prior.state != "pending" or refs.isdisjoint(x.actor for x in prior.order):
                    continue
                try:
                    self._valid(c, state, prior)
                except (ValueError, WorkflowError):
                    rules.put(state, prior.model_copy(update=dict(state="declined", event=event)))
                else:
                    raise WorkflowError("Resolve the original member’s existing Cadre first.")
            value = rules.Cadre(
                id=event,
                scene=cast.id,
                channel=channel,
                facilitator=gm,
                appointment=appointment,
                handler=anchor,
                handler_owner=owner,
                faction=faction,
                order=roles,
                handler_accepted=anchor.kind == "handler",
                event=event,
            )
            return self._save(c, state, viewer, key, value, event)

        return self._write(
            viewer,
            key,
            dict(
                channel=channel,
                revision=revision,
                handler=handler,
                order=order,
            ),
            operation,
        )

    def _choices(self, value: rules.Cadre, person: int) -> tuple[str, ...]:
        if value.state != "pending":
            return ()
        keys = tuple(
            role.actor.token
            for role in value.order
            if role.controller == person and role.actor.token not in value.accepted
        )
        if not value.handler_accepted and value.handler_owner == person:
            return (*keys, "handler")
        return keys

    def _valid(
        self,
        c: Connection,
        state: GameState,
        value: rules.Cadre,
    ) -> tuple[dict[str, tuple[CastRole, str, str | None]], str]:
        cast, gm, appointment = self._scene(c, state, value.channel)
        people = self._people(c, state, cast)
        handler = self._handlers(state).get(value.handler.token)
        if (
            (cast.id, gm, appointment) != (value.scene, value.facilitator, value.appointment)
            or handler is None
            or handler[0] != value.handler
            or handler[1] != value.handler_owner
            or handler[3] != value.faction
            or any(
                x.actor.token not in people
                or people[x.actor.token][0] != x
                or people[x.actor.token][2] != value.faction
                for x in value.order
            )
        ):
            raise WorkflowError("Recover the original exact Cadre roles and Handler.")
        return people, handler[2]

    def tasks(self, c: Connection, state: GameState, viewer: GuildViewer) -> tuple[str, ...]:
        values = tuple(x for x in rules.records(state) if self._choices(x, viewer.user_id))
        if not values:
            return ()
        try:
            self._gate(c, viewer)
        except (WorkflowError, ValueError):
            return ()
        ready = []
        for case in values:
            try:
                self._valid(c, state, case)
            except (WorkflowError, ValueError):
                continue
            ready.append(case.id)
        return tuple(ready)

    def _case(self, state: GameState, viewer: GuildViewer, identity: str) -> rules.Cadre:
        case = next((x for x in rules.records(state) if x.id == identity), None)
        if case is None or not self._choices(case, viewer.user_id):
            raise WorkflowError("This original Cadre invitation is unavailable.")
        return case

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            case = self._case(state, viewer, identity)
            people, handler = self._valid(c, state, case)
            visible = {x.actor.token for x in case.order if x.controller == viewer.user_id}
            visible.update(case.accepted)
            order = {
                x.actor.token: people[x.actor.token][1]
                if x.actor.token in visible
                else "Original proposed member"
                for x in case.order
            }
            handler_label = (
                handler
                if case.handler_accepted or case.handler_owner == viewer.user_id
                else "Original proposed Handler"
            )
            choices = {
                token: handler_label if token == "handler" else order[token]
                for token in self._choices(case, viewer.user_id)
            }
            return dict(
                revision=state.revision,
                order=tuple(order.values()),
                handler=handler_label,
                choices=choices,
            )

    def approve(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        role: str,
        accept: bool,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = self._case(state, viewer, identity)
            self._valid(c, state, value)
            require_scene_clear(self.game, c, value.channel)
            if (
                state.revision != revision
                or role not in self._choices(value, viewer.user_id)
                or type(accept) is not bool
            ):
                raise WorkflowError("Reopen the original invitation and choose only your role.")
            event = str(uuid4())
            if not accept:
                changed = value.model_copy(update=dict(state="declined", event=event))
            else:
                accepted = (*value.accepted, role) if role != "handler" else value.accepted
                handler_accepted = value.handler_accepted or role == "handler"
                active = handler_accepted and len(accepted) == len(value.order)
                changed = value.model_copy(
                    update=dict(
                        state="active" if active else "pending",
                        accepted=accepted,
                        handler_accepted=handler_accepted,
                        event=event,
                    )
                )
            return self._save(c, state, viewer, key, changed, event)

        return self._write(
            viewer,
            key,
            dict(
                id=identity,
                revision=revision,
                role=role,
                accept=accept,
            ),
            operation,
        )
