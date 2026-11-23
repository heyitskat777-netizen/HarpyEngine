"""A witnessed private Gorgon outcome reaches the fictional Handler through an explicit report."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_gorgon_frame_contact as rules
from girlframe.engine.m2 import GameState, Obligation
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_sentinel import require_communication
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KIND = "gorgon_frame_contact_disclosed"


class FrameContactDisclosureService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "plays")
        assert gate.registry is not None
        gate.registry.require_available(rules.RULE)

    def _case(
        self, c: Connection, state: GameState, owner: int, identity: str
    ) -> rules.Consequence:
        from girlframe.engine.m3_actor_bonds import current_ref
        from girlframe.services.m3_gorgon_play import GorgonPlayService

        source = next(
            (
                x
                for x in rules.results(state)
                if x.action == identity
                and x.girl.entity == str(owner)
                and x.girl.entity in state.sheets
                and x.girl == current_ref(state, owner)
                and x.punishment_if_discovered
            ),
            None,
        )
        if source is None:
            raise WorkflowError("This original private report is unavailable")
        action = self.game.action(c, identity)
        meta = GorgonPlayService(self.game).source(c, action)
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == source.event,
            )
        )
        if (
            action["state"] != "complete"
            or meta["kind"] != rules.PLAY
            or raw is None
            or source not in rules.results(GameState.model_validate_json(raw))
        ):
            raise WorkflowError("Recover the original committed private outcome")
        return source

    @staticmethod
    def _scenes(
        state: GameState, girl: ActorRef, handler: ActorRef | None
    ) -> tuple[SceneCast, ...]:
        if handler is None:
            return ()
        return tuple(
            cast
            for cast in state.scene_casts
            if cast.open and {girl, handler} <= {role.actor for role in cast.roles}
        )

    def available(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        if not any(x.girl.entity == str(viewer.user_id) for x in rules.results(state)):
            return []
        try:
            self._access(c, viewer)
        except (WorkflowError, ValueError):
            return []
        handler = active_handler(state)
        disclosed = {x.get("action") for x in state.facts if x.get("kind") == KIND}
        available = []
        for candidate in rules.results(state):
            if (
                candidate.girl.entity != str(viewer.user_id)
                or candidate.action in disclosed
                or not candidate.punishment_if_discovered
            ):
                continue
            try:
                source = self._case(c, state, viewer.user_id, candidate.action)
            except WorkflowError:
                continue
            scenes = self._scenes(state, source.girl, handler)
            if scenes:
                available.append(
                    dict(
                        id=source.action,
                        revision=state.revision,
                        scenes=tuple((x.id, x.channel) for x in scenes),
                    )
                )
        return available

    def menu(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            value = next((x for x in self.available(c, viewer) if x["id"] == identity), None)
            if value is None:
                raise WorkflowError("This original private report is unavailable")
            return value

    def report(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, scene: str
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self._access(c, viewer)
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_battle import _cast
            from girlframe.services.p1_facilitator import require_scene_clear

            state = load_state(c, self.store.campaign_id)
            if state.revision != revision:
                raise WorkflowError("STALE_REPORT: refresh the original private outcome")
            source = self._case(c, state, viewer.user_id, identity)
            handler = active_handler(state)
            cast = next(
                (x for x in self._scenes(state, source.girl, handler) if x.id == scene), None
            )
            if handler is None or cast is None or _cast(self.game, c, state, cast.channel) != cast:
                raise WorkflowError("Use the actual open scene with both original report roles")
            require_scene_clear(self.game, c, cast.channel)
            lock = self.game.lock(c, cast.channel)
            if lock is not None and lock["state"] != "released":
                raise WorkflowError("Recover chat in the original scene before reporting")
            require_communication(c, self.store.campaign_id, state, source.girl, (handler,))
            if any(x.get("kind") == KIND and x.get("action") == identity for x in state.facts):
                raise WorkflowError("This original contact has already been disclosed")
            event = str(uuid4())
            state.facts.append(
                dict(
                    kind=KIND,
                    id=event,
                    event=event,
                    action=identity,
                    original=source.event,
                    scene=scene,
                    speaker=source.girl.model_dump_json(),
                    recipient=handler.model_dump_json(),
                )
            )
            state.obligations.append(
                Obligation(
                    id=event,
                    kind="punishment",
                    owner=viewer.user_id,
                    target=int(handler.entity),
                    action=identity,
                    details={
                        "source_pdf": "163",
                        "cause": KIND,
                        "character_id": source.girl.incarnation or "",
                        "disclosure": event,
                    },
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3." + KIND,
                state,
                event_id=event,
                source_action=source.action,
                disclosure=event,
            )
            return dict(event=event)

        return self.store._write(
            viewer,
            key,
            "m3." + KIND,
            dict(identity=identity, revision=revision, scene=scene),
            operation,
            authorize=authorize,
            auto_audit=False,
        )
