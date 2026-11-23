"""An actual Gorgon addresses one original Girl in their source scene."""

from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_benevolent_contact as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class ContactService:
    def __init__(self, strain: StrainService):
        self.strain, self.game, self.store = strain, strain.game, strain.store
        self.casts = CastService(ActorService(strain.missions))

    def _owned(self, state: GameState, viewer: GuildViewer, identity: str) -> rules.Contact:
        contact = next((x for x in rules.contacts(state) if x.id == identity), None)
        if contact is None or viewer.user_id not in (
            contact.speaker.controller,
            contact.recipient.controller,
        ):
            raise WorkflowError("Only the original speaker and addressee can review this contact")
        return contact

    def _cast(
        self, c: Connection, state: GameState, viewer: GuildViewer, channel: int, gorgon: ActorRef
    ) -> SceneCast:
        cast, _ = self.casts._current(c, state, channel)
        if (
            state.world is None
            or not any(
                x.id == gorgon.entity and x.alive and x.gorgon_class == "benevolent"
                for x in state.world.gorgons
            )
            or not any(x.actor == gorgon and x.controller == viewer.user_id for x in cast.roles)
        ):
            raise WorkflowError("Join the actual living Benevolent Gorgon in this scene")
        actual = resolve(
            state, gorgon, profiles(c, self.store.campaign_id), require_current_profile=False
        )
        if actual.controller != viewer.user_id or actual.cell is None:
            raise WorkflowError("Use your original Gorgon with its actual current position")
        return cast

    def _girls(
        self, c: Connection, state: GameState, cast: SceneCast
    ) -> dict[str, tuple[str, str]]:
        result = {}
        bindings = profiles(c, self.store.campaign_id)
        for role in cast.roles:
            if role.actor.kind != "pilot" or not HandlerService(self.store)._member(
                c, role.controller
            ):
                continue
            girl = resolve(state, role.actor, bindings, require_current_profile=False)
            if girl.controller == role.controller and girl.rules == "girl_frame":
                result[role.actor.entity] = (role.actor.entity, girl.label)
        return result

    def performed(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
        *,
        identity: str,
        event: str,
        grant: str,
        play: rules.Play,
        gorgon: ActorRef,
        girl: str,
        channel: int,
        account: str,
    ) -> rules.Contact:
        self.strain.missions.access.authorize(c, viewer, "plays")
        cast = self._cast(c, state, viewer, channel, gorgon)
        if girl not in self._girls(c, state, cast) or not 0 < len(account.strip()) <= 1200:
            raise WorkflowError(
                "Record the actual Play addressed to an original Girl in this scene"
            )
        return rules.Contact(
            id=identity,
            event=event,
            grant=grant,
            play=play,
            speaker=next(x for x in cast.roles if x.actor == gorgon),
            recipient=next(
                x for x in cast.roles if x.actor.kind == "pilot" and x.actor.entity == girl
            ),
            scene=cast.id,
            cast_revision=cast.revision,
            account=account.strip(),
        )

    def get(self, viewer: GuildViewer, identity: str, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            contact = self._owned(state, viewer, identity)
            targets: tuple[tuple[str, str], ...] = ()
            if contact.speaker.controller == viewer.user_id:
                try:
                    cast = self._cast(c, state, viewer, channel, contact.speaker.actor)
                    targets = tuple(self._girls(c, state, cast).values())
                except (ValueError, WorkflowError):
                    pass  # The original account remains readable after a scene ends.
            return dict(
                revision=state.revision,
                play=contact.play,
                account=contact.account,
                targets=targets,
            )

    def repeat(
        self,
        viewer: GuildViewer,
        key: str,
        source: str,
        expected: int,
        girl: str,
        channel: int,
        account: str,
    ) -> dict[str, str]:
        def authorize(c: Connection) -> None:
            self.strain.missions.access.authorize(c, viewer, "plays")
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            prior = self._owned(state, viewer, source)
            if prior.speaker.controller != viewer.user_id:
                raise WorkflowError("Only the original Gorgon controller makes its granted Play")
            self._cast(c, state, viewer, channel, prior.speaker.actor)

        def operation(c: Connection) -> dict[str, str]:
            state = self.strain._state(c, expected)
            prior = self._owned(state, viewer, source)
            event = str(uuid4())
            entry = self.performed(
                c,
                state,
                viewer,
                identity=event,
                event=event,
                grant=prior.grant,
                play=prior.play,
                gorgon=prior.speaker.actor,
                girl=girl,
                channel=channel,
                account=account,
            )
            rules.commit(state, entry)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.benevolent_contact",
                state,
                event_id=event,
                source=source,
            )
            return dict(id=entry.id, grant=entry.grant)

        return self.strain.missions._write(
            viewer,
            key,
            "m3.benevolent_contact",
            dict(source=source, expected=expected, girl=girl, channel=channel, account=account),
            operation,
            authorize,
        )
