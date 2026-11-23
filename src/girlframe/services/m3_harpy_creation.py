"""Invite an actual campaign member to own a new Harpy's printed creation choices."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_harpy_creation as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world_state import Cell
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class HarpyCreationService:
    def __init__(self, game: GameService):
        self.game, self.store, self.access = game, game.store, Access(game.store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        for subsystem in ("world", "plays"):
            self.access.authorize(c, viewer, subsystem, director_response=True)
        try:
            self.access.require_specialist_rule(rules.RULE)
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _issuer(self, c: Connection, viewer: GuildViewer) -> tuple[int, str]:
        HandlerService(self.store).authorize(c, viewer)
        controller, appointment = MedicalService(self.store)._handler(c)
        if controller != viewer.user_id:
            raise WorkflowError("Only the original human GM can introduce a new Harpy")
        return controller, appointment

    def _state(self, c: Connection, revision: int) -> GameState:
        state = load_state(c, self.store.campaign_id)
        if state.revision != revision:
            raise WorkflowError("STALE_HARPY_CREATION: reopen the original invitation")
        return state

    def menu(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            self._issuer(c, viewer)
            state = load_state(c, self.store.campaign_id)
            if state.world is None:
                raise WorkflowError("Establish the actual campaign map before inviting a Harpy")
            members = tuple(
                (str(row.user_id), "Campaign member " + str(row.user_id))
                for row in c.execute(
                    sa.select(t.members.c.user_id)
                    .where(
                        t.members.c.campaign_id == self.store.campaign_id,
                        t.members.c.active.is_(True),
                    )
                    .order_by(t.members.c.user_id)
                )
            )
            return dict(revision=state.revision, members=members)

    def invite(
        self, viewer: GuildViewer, key: str, revision: int, controller: int, cell: Cell
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self._access(c, viewer)
            self._issuer(c, viewer)
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            state = self._state(c, revision)
            if (
                state.world is None
                or not state.world.board.contains(cell)
                or not HandlerService(self.store)._member(c, controller)
            ):
                raise WorkflowError("Choose a current campaign member and actual map square")
            issuer, appointment = self._issuer(c, viewer)
            event = str(uuid4())
            actor = ActorRef(kind="external_pilot", entity="native-harpy:" + event)
            offer = rules.Offer(
                actor=actor,
                controller=controller,
                issuer=issuer,
                appointment=appointment,
                cell=cell,
                source=event,
            )
            rules.save(state, offer)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_creation_offered",
                state,
                event_id=event,
                actor_ref=actor.model_dump(mode="json"),
            )
            return dict(id=actor.entity, revision=state.revision)

        return self.store._write(
            viewer,
            key,
            "m3.harpy_creation_offered",
            dict(revision=revision, controller=controller, cell=cell),
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def _offer(
        self, c: Connection, state: GameState, viewer: GuildViewer, identity: str
    ) -> rules.Offer:
        offer = next((x for x in rules.offers(state) if x.actor.entity == identity), None)
        if offer is None or viewer.user_id != offer.controller:
            raise WorkflowError("The invitation belongs to the actual original invited controller")
        history = t.m2["m2_state_history"]
        raw = c.scalar(
            sa.select(history.c.body_json)
            .join(t.events, history.c.event_id == t.events.c.id)
            .where(
                history.c.campaign_id == self.store.campaign_id,
                history.c.event_id == offer.source,
                t.events.c.kind == "m3.harpy_creation_offered",
                t.events.c.actor_id == str(offer.issuer),
            )
        )
        original = offer.model_copy(update=dict(phase="offered", decision=None))
        if raw is None or original not in rules.offers(GameState.model_validate_json(raw)):
            raise WorkflowError("Recover the actual original source invitation")
        return offer

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            return dict(revision=state.revision, offer=self._offer(c, state, viewer, identity))

    def tasks(
        self, c: Connection, state: GameState, viewer: GuildViewer
    ) -> tuple[rules.Offer, ...]:
        owned = tuple(
            x
            for x in rules.offers(state)
            if x.controller == viewer.user_id and x.phase == "offered"
        )
        if not owned:
            return ()
        try:
            self._access(c, viewer)
        except WorkflowError:
            return ()
        return owned

    def respond(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, draft: rules.Draft | None
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self._access(c, viewer)
            self.game.unpaused(c)
            self._offer(c, load_state(c, self.store.campaign_id), viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            state = self._state(c, revision)
            offer = self._offer(c, state, viewer, identity)
            if offer.phase != "offered" or MedicalService(self.store)._handler(c) != (
                offer.issuer,
                offer.appointment,
            ):
                raise WorkflowError("Reopen the original pending invitation and its GM appointment")
            event = str(uuid4())
            phase = "declined" if draft is None else "accepted"
            if draft is not None:
                rules.introduce(
                    state, offer, rules.Draft.model_validate_json(draft.model_dump_json())
                )
            rules.save(state, offer.model_copy(update=dict(phase=phase, decision=event)))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_creation_answered",
                state,
                event_id=event,
                actor_ref=offer.actor.model_dump(mode="json"),
                decision=phase,
            )
            return dict(id=identity, phase=phase, event=event)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.harpy_creation_answered",
                dict(
                    id=identity,
                    revision=revision,
                    draft=draft.model_dump(mode="json") if draft else None,
                ),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
