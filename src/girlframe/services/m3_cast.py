"""Transactional actor casting with immutable legacy-scene evidence."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_actors, m3_cast
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, CastRole, SceneCast
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class CastService:
    def __init__(self, actors: ActorService):
        self.actors, self.game, self.store = actors, actors.game, actors.store

    def _safe(self, c: Connection, channel: int) -> None:
        lock = self.game.lock(c, channel)
        actions = t.m2["m2_actions"]
        if (
            self.game.pending_actions(c)
            or (lock and lock["state"] != "released")
            or c.scalar(
                sa.select(actions.c.id)
                .where(
                    actions.c.campaign_id == self.store.campaign_id,
                    actions.c.channel_id == str(channel),
                    actions.c.state.not_in(("complete", "aborted")),
                )
                .limit(1)
            )
        ):
            raise WorkflowError(
                "Restore chat and resolve the pending Play before changing its cast."
            )

    def _legacy(self, c: Connection, scene: dict[str, Any]) -> SceneCast:
        events = list(
            c.execute(
                sa.select(t.events)
                .where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.kind.in_(("m2.scene_bound", "m2.scene_joined", "m2.scene_left")),
                )
                .order_by(t.events.c.seq.desc())
            ).mappings()
        )
        events = [
            x
            for x in events
            if str(json.loads(x["payload_json"]).get("channel")) == scene["channel_id"]
        ]
        bound = next((x for x in events if x["kind"] == "m2.scene_bound"), None)
        outcome = (
            c.scalar(
                sa.select(t.commands.c.outcome_json).where(
                    t.commands.c.campaign_id == self.store.campaign_id,
                    t.commands.c.interaction_key == bound["command_key"],
                )
            )
            if bound
            else None
        )
        if bound is None or outcome is None or json.loads(outcome).get("scene") != scene["id"]:
            raise WorkflowError("SOURCE_CAST_MISSING: recover this scene's actual bind event.")
        roles: list[CastRole] = []
        facilitator, facilitator_source = None, None
        for uid in scene["participants"]:
            joined = next(
                (x for x in events if x["seq"] > bound["seq"] and x["actor_id"] == str(uid)), None
            )
            if joined is None or joined["kind"] != "m2.scene_joined":
                raise WorkflowError("SOURCE_CAST_MISSING: recover the actual explicit scene join.")
            history = t.m2["m2_state_history"]
            body = c.scalar(
                sa.select(history.c.body_json)
                .select_from(history.join(t.events, history.c.event_id == t.events.c.id))
                .where(
                    history.c.campaign_id == self.store.campaign_id, t.events.c.seq <= joined["seq"]
                )
                .order_by(t.events.c.seq.desc())
                .limit(1)
            )
            if body is None:
                raise WorkflowError("SOURCE_CAST_MISSING: recover the original joined character.")
            original = GameState.model_validate_json(body)
            if uid == original.handler:
                facilitator, facilitator_source = uid, joined["id"]
                continue
            sheet = original.sheets.get(str(uid))
            identity = (
                (
                    sheet.character_id
                    or c.scalar(
                        sa.select(t.snapshots.c.character_id).where(
                            t.snapshots.c.campaign_id == self.store.campaign_id,
                            t.snapshots.c.user_id == str(uid),
                            t.snapshots.c.revision == sheet.source_profile_revision,
                        )
                    )
                )
                if sheet
                else None
            )
            if identity is None:
                raise WorkflowError("SOURCE_CAST_MISSING: recover the original character snapshot.")
            roles.append(
                CastRole(
                    actor=ActorRef(kind="pilot", entity=str(uid), incarnation=identity),
                    controller=uid,
                    source_event=joined["id"],
                )
            )
        return SceneCast(
            id=scene["id"],
            channel=int(scene["channel_id"]),
            roles=tuple(roles),
            facilitator=facilitator,
            facilitator_source=facilitator_source,
        )

    def _current(self, c: Connection, state: GameState, channel: int) -> tuple[SceneCast, bool]:
        scene = self.game.scene(c, channel)
        cast = next((x for x in state.scene_casts if x.id == scene["id"] and x.open), None)
        return (cast, False) if cast else (self._legacy(c, scene), True)

    def view(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            cast, legacy = self._current(c, state, channel)
            bindings = profiles(c, self.store.campaign_id)
            visible = []
            offers = []
            known_refs = set()
            for role in cast.roles:
                try:
                    actor = m3_actors.resolve(state, role.actor, bindings)
                except ValueError:
                    if role.controller == viewer.user_id:
                        visible.append(
                            {
                                "ref": role.actor.model_dump(mode="json"),
                                "token": role.actor.token,
                                "label": "Your previous role — withdraw or recover",
                                "stale": True,
                                "own": True,
                            }
                        )
                    continue
                if role.controller == viewer.user_id and actor.controller != viewer.user_id:
                    visible.append(
                        {
                            "ref": role.actor.model_dump(mode="json"),
                            "token": role.actor.token,
                            "label": "Your previous role — withdraw or recover",
                            "stale": True,
                            "own": True,
                        }
                    )
                    continue
                known = actor.ref.kind in ("pilot", "handler") or actor.controller == viewer.user_id
                if state.world and actor.ref.kind in ("npc", "external_pilot", "gorgon"):
                    revealed = {
                        "npc": {x.id for x in state.world.npcs if x.revealed},
                        "external_pilot": {x.id for x in state.world.pilots if x.revealed},
                        "gorgon": {x.id for x in state.world.gorgons if x.revealed},
                    }[actor.ref.kind]
                    known = known or actor.ref.entity in revealed
                    known |= bool(
                        viewer.user_id == state.handler
                        and actor.rules == "director"
                        and any(
                            x.active and actor.ref.entity in x.directors
                            for x in state.director_contexts
                        )
                    )
                if known:
                    known_refs.add(actor.ref)
                    visible.append(
                        {
                            "ref": actor.ref.model_dump(mode="json"),
                            "token": actor.ref.token,
                            "label": actor.label,
                            "stale": role.controller != actor.controller,
                            "own": role.controller == viewer.user_id,
                        }
                    )
                if (
                    actor.controller == role.controller == viewer.user_id
                    and actor.rules == "director"
                    and viewer.user_id != state.handler
                    and cast.adjudicator != actor.ref
                ):
                    offers.append(
                        {
                            "ref": actor.ref.model_dump(mode="json"),
                            "token": actor.ref.token,
                            "label": actor.label,
                        }
                    )
            return {
                "scene": cast.id,
                "channel": channel,
                "cast_revision": cast.revision,
                "game_revision": state.revision,
                "legacy": legacy,
                "roles": visible,
                "facilitator": cast.facilitator,
                "own_facilitator": cast.facilitator == viewer.user_id,
                "may_facilitate": state.handler == viewer.user_id,
                "adjudicator": cast.adjudicator.model_dump(mode="json")
                if cast.adjudicator in known_refs
                else None,
                "adjudicator_selected": cast.adjudicator is not None,
                "adjudicator_options": offers,
            }

    def change(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        expected: int,
        cast_revision: int,
        action: str,
        ref: ActorRef | None = None,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.actors.missions.access.authorize(c, viewer, "world", director_response=True)
            # Withdrawing is OOC recovery, including during a safety pause.
            if action not in ("withdraw", "withdraw_facilitator"):
                self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            cast, legacy = self._current(c, state, channel)
            if state.revision != expected or cast.revision != cast_revision:
                raise WorkflowError("STALE_CAST: refresh the actual scene roles.")
            self._safe(c, channel)
            event_id = str(uuid4())
            try:
                if action == "join" and ref is not None:
                    actor = self.actors._actor(c, viewer, state, ref)
                    from girlframe.services.m3_scene_requisitions import guard

                    guard(c, self.store, cast.id, ref)
                    if ref.kind == "pilot":
                        scenes = t.m2["m2_scenes"]
                        others = c.execute(
                            sa.select(scenes).where(
                                scenes.c.campaign_id == self.store.campaign_id,
                                scenes.c.open.is_(True),
                                scenes.c.id != cast.id,
                            )
                        ).mappings()
                        if any(
                            actor.controller in json.loads(x["participants_json"]) for x in others
                        ):
                            raise ValueError("Withdraw this Girl from her current scene first")
                    updated = m3_cast.join(
                        [*state.scene_casts, *([cast] if legacy else [])],
                        cast.id,
                        actor,
                        viewer.user_id,
                        event_id,
                    )
                elif action == "withdraw" and ref is not None:
                    updated = m3_cast.withdraw(cast, ref, viewer.user_id)
                elif action == "adjudicate" and ref is not None:
                    updated = m3_cast.choose_adjudicator(
                        state, cast, ref, viewer.user_id, profiles(c, self.store.campaign_id)
                    )
                elif (
                    action == "withdraw_facilitator"
                    and ref is None
                    and cast.facilitator == viewer.user_id
                ):
                    updated = cast.model_copy(
                        update={
                            "facilitator": None,
                            "facilitator_source": None,
                            "revision": cast.revision + 1,
                        }
                    )
                elif action == "facilitate" and ref is None and state.handler == viewer.user_id:
                    if cast.facilitator == viewer.user_id:
                        raise ValueError("You are already facilitating this scene")
                    updated = cast.model_copy(
                        update={
                            "facilitator": viewer.user_id,
                            "facilitator_source": event_id,
                            "revision": cast.revision + 1,
                        }
                    )
                else:
                    raise ValueError("Choose your own actual role or the appointed facilitator")
            except ValueError as error:
                raise WorkflowError(str(error)) from None
            state.scene_casts = [x for x in state.scene_casts if x.id != cast.id] + [updated]
            # This legacy projection has only real Pilot humans and the facilitator.
            # NPC controllers do not silently acquire a Girl's scene participation.
            people = sorted(
                {x.controller for x in updated.roles if x.actor.kind == "pilot"}
                | ({updated.facilitator} if updated.facilitator is not None else set())
            )
            table = t.m2["m2_scenes"]
            c.execute(
                table.update()
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.channel_id == str(channel),
                )
                .values(participants_json=json.dumps(people), revision=table.c.revision + 1)
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.scene_cast_changed",
                state,
                event_id=event_id,
                scene=cast.id,
                action=action,
            )
            return {"scene": cast.id, "cast_revision": updated.revision}

        return self.store._write(
            viewer,
            key,
            "m3.scene_cast_changed",
            {
                "channel": channel,
                "expected": expected,
                "cast_revision": cast_revision,
                "action": action,
                "ref": ref.model_dump(mode="json") if ref else None,
            },
            operation,
            auto_audit=False,
            authorize=authorize,
        )
