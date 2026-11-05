"""Source-owned Leviathan flesh-layer Play using the original World resources."""

from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_leviathan as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

RULE = "gorgon-type.leviathan.leviathan-type"


class LeviathanService:
    def __init__(self, store: OnboardingStore, game: GameService | None = None):
        self.store, self.game = store, game or GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        access = Access(self.store)
        for scope in ("world", "plays"):
            access.authorize(c, viewer, scope, director_response=True)
        assert access.registry is not None
        try:
            access.registry.require_available(RULE)
        except ValueError:
            raise WorkflowError("RULE_REVIEW_PENDING: this Type Play is not released") from None

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        if state.world is None or not any(
            "leviathan" in x.types
            and x.flesh_layers is None
            and x.alive
            and state.handler == viewer.user_id
            for x in state.world.gorgons
        ):
            return []
        try:
            self._access(c, viewer)
        except (ValueError, WorkflowError):
            return []
        scenes = t.m2["m2_scenes"]
        actual = {
            x.id: x
            for x in state.world.gorgons
            if x.alive
            and "leviathan" in x.types
            and x.flesh_layers is None
            and state.handler == viewer.user_id
        }
        open_scenes: dict[str, str] = {
            str(row[0]): str(row[1])
            for row in c.execute(
                sa.select(scenes.c.id, scenes.c.channel_id).where(
                    scenes.c.campaign_id == self.store.campaign_id, scenes.c.open.is_(True)
                )
            ).all()
        }
        results = []
        for cast in state.scene_casts:
            if cast.id not in open_scenes:
                continue
            for role in cast.roles:
                if role.actor.kind != "gorgon" or role.actor.entity not in actual:
                    continue
                body = resolve(state, role.actor, ())
                if body.offstage_source is not None:
                    continue
                results.append(
                    dict(
                        id=str(
                            uuid5(
                                NAMESPACE_URL, "leviathan-layer-play:" + cast.id + role.actor.token
                            )
                        ),
                        actor=role.actor.model_dump(mode="json"),
                        label=body.label,
                        source_sha256=body.source_sha256,
                        channel=int(open_scenes[cast.id]),
                        scene=cast.id,
                        cast_revision=cast.revision,
                        revision=state.revision,
                    )
                )
        return results

    def _get(self, c: Connection, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        self._access(c, viewer)
        task = next((x for x in self._tasks(c, viewer) if x["id"] == identity), None)
        if task is None:
            raise WorkflowError(
                "Reopen your actual original Leviathan's available flesh-layer Play"
            )
        return task

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            return self._get(c, viewer, identity)

    def protect(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        source_sha256: str,
        descriptions: tuple[str, str],
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            task = self._get(c, viewer, identity)
            state: GameState = load_state(c, self.store.campaign_id)
            if task["revision"] != revision or task["source_sha256"] != source_sha256:
                raise WorkflowError("STALE_LEVIATHAN: review the actual original body and scene")
            held = c.scalar(
                sa.select(t.m2["m2_locks"].c.channel_id)
                .where(
                    t.m2["m2_locks"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_locks"].c.state != "released",
                )
                .limit(1)
            )
            if self.game.pending_actions(c) or held:
                raise WorkflowError("Finish pending Plays and restore chat before this Type Play")
            from girlframe.services.m3_battle import _cast
            from girlframe.services.m3_gorgon_dormant import awakened_source, require_clear
            from girlframe.services.m3_scene_requisitions import guard

            actor = ActorRef.model_validate(task["actor"])
            cast = _cast(self.game, c, state, task["channel"])
            if cast.id != task["scene"] or cast.revision != task["cast_revision"]:
                raise WorkflowError("Restore the actual original Leviathan source scene first")
            require_clear(self.game, c, actor)
            guard(c, self.store, cast.id, actor)
            assert state.world is not None
            body = next(x for x in state.world.gorgons if x.id == actor.entity)
            wake = (
                body.gorgon_class == "dormant"
                and awakened_source(self.game, c, state, actor) is None
            )
            event = str(uuid4())
            state = rules.protect(state, actor, descriptions, account, event)
            if wake:
                state.facts.append(
                    dict(
                        kind="dormant_awakening",
                        cause="own_type_play",
                        gorgon=actor.entity,
                        actor=actor.model_dump_json(),
                        event=event,
                        source_type=RULE,
                        source_action="",
                        source_choice="",
                    )
                )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.leviathan_layers_raised",
                state,
                event_id=event,
                actor_ref=actor.model_dump(mode="json"),
                scene=cast.id,
            )
            assert state.world is not None
            layers = next(x.flesh_layers for x in state.world.gorgons if x.id == actor.entity)
            return dict(
                actor=actor.model_dump(mode="json"),
                layers=list(layers) if layers else [],
                event=event,
                game_revision=state.revision,
            )

        try:
            return self.store._write(
                viewer,
                key,
                "m3.leviathan_layers_raised",
                dict(
                    id=identity,
                    revision=revision,
                    source_sha256=source_sha256,
                    descriptions=descriptions,
                    account=account,
                ),
                operation,
                authorize=lambda c: self._access(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
