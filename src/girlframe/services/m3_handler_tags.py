"""Actual Tag consumption and original Handler replies, including during another held Play."""

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_tags as rules
from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_world_state import WorldTag
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class HandlerTagService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        Access(self.store).authorize(c, viewer, "plays", director_response=True)

    @contextmanager
    def _read(self, viewer: GuildViewer, *, enabled: bool = True) -> Iterator[Connection]:
        try:
            with self.store.engine.connect() as c:
                if enabled:
                    self._access(c, viewer)
                else:
                    self.game.authorize(c, viewer, game=False)
                yield c
        except ValidationError:
            raise WorkflowError(
                "Invalid source state; ask staff to recover the original records"
            ) from None
        except ValueError:
            raise WorkflowError(
                "The actual roles changed; reopen the original Handler Tag request"
            ) from None

    def _view(
        self,
        c: Connection,
        viewer: GuildViewer,
        channel: int,
        girl: ActorRef,
        handler_ref: ActorRef | None = None,
    ) -> dict[str, Any]:
        from girlframe.services.m3_battle import _cast

        state = load_state(c, self.store.campaign_id)
        actual = resolve(
            state, girl, profiles(c, self.store.campaign_id), require_current_profile=False
        )
        cast = _cast(self.game, c, state, channel)
        if (
            actual.controller != viewer.user_id
            or not rules.girl_rules(actual)
            or not any(
                role.actor == girl and role.controller == viewer.user_id for role in cast.roles
            )
        ):
            raise WorkflowError("Join and select your actual living Girl role in this scene")
        main = active_handler(state)
        if main is not None and girl.kind == "handler":
            from girlframe.engine.m3_handler_consequences import same_handler_body

            if same_handler_body(state, girl):
                main = None
        targets = (
            [dict(ref=main.model_dump(mode="json"), token=main.token, label="Cadre Handler")]
            if main
            else []
        )
        for role in cast.roles:
            npc = rules.director(state, role.actor)
            if npc is not None and (npc.revealed or npc.controller == viewer.user_id):
                targets.append(
                    dict(
                        ref=role.actor.model_dump(mode="json"),
                        token=role.actor.token,
                        label=npc.name,
                    )
                )
        handler = (
            handler_ref or main or (ActorRef.model_validate(targets[0]["ref"]) if targets else None)
        )
        if handler is None:
            raise WorkflowError(
                "The original Handler role ended; create the actual replacement first"
            )
        if not any(item["ref"] == handler.model_dump(mode="json") for item in targets):
            raise WorkflowError("Choose the actual current Handler or a known present Director")
        npc = rules.director(state, handler)
        tags: list[TagState | WorldTag] = (
            list(npc.tags)
            if npc
            else [tag for tag in state.handler_tags if viewer.user_id in tag.observers]
        )
        return dict(
            actor=girl.model_dump(mode="json"),
            handler=handler.model_dump(mode="json"),
            targets=targets,
            scene=cast.id,
            tags=[dict(id=tag.id, label=tag.label) for tag in tags],
            source_sha256=hashlib.sha256(
                json.dumps(
                    dict(
                        actor=actual.source_sha256,
                        handler=handler.model_dump(mode="json"),
                        tags=[tag.model_dump(mode="json") for tag in tags],
                        cast=cast.model_dump(mode="json"),
                    ),
                    sort_keys=True,
                ).encode()
            ).hexdigest(),
        )

    def view(
        self, viewer: GuildViewer, channel: int, girl: ActorRef, handler_ref: ActorRef | None = None
    ) -> dict[str, Any]:
        with self._read(viewer) as c:
            return self._view(c, viewer, channel, girl, handler_ref)

    def actors(self, viewer: GuildViewer, channel: int) -> list[dict[str, Any]]:
        from girlframe.services.m3_battle import _cast

        with self._read(viewer) as c:
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            result = []
            for role in cast.roles:
                if role.controller != viewer.user_id:
                    continue
                actual = resolve(
                    state,
                    role.actor,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                if rules.girl_rules(actual):
                    result.append(
                        dict(
                            ref=role.actor.model_dump(mode="json"),
                            token=role.actor.token,
                            label=actual.label,
                        )
                    )
            return result

    def use(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        girl: ActorRef,
        expected: str,
        tag: str,
        kind: rules.Kind,
        account: str,
        *,
        handler_ref: ActorRef | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            view = self._view(c, viewer, channel, girl, handler_ref)
            if view["source_sha256"] != expected:
                raise WorkflowError("STALE_HANDLER_TAG: refresh the actual Tag and original roles")
            state = load_state(c, self.store.campaign_id)
            identity, event = str(uuid4()), str(uuid4())
            changed, value = rules.consume(
                state,
                profiles(c, self.store.campaign_id),
                girl,
                tag,
                kind,
                account,
                identity,
                event,
                view["scene"],
                handler_ref=ActorRef.model_validate(view["handler"]),
            )
            changed_actions = self._invalidate_uncommitted(c, changed, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_tag_used",
                changed,
                event_id=event,
                case_id=identity,
                tag_id=tag,
                use_kind=kind,
                refreshed_actions=changed_actions,
            )
            if value.state == "pending":
                related(
                    c,
                    self.store,
                    dict(campaign_id=self.store.campaign_id, scene_id=view["scene"]),
                    identity,
                    value.handler_controller,
                    value.girl_controller,
                    "handler_tag_response",
                    dict(
                        case=identity,
                        handler=value.handler.model_dump(mode="json"),
                        girl=girl.model_dump(mode="json"),
                        immediate=False,
                    ),
                    event,
                )
            return dict(id=identity, state=value.state, revision=value.revision)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.handler_tag_used",
                dict(
                    channel=channel,
                    girl=girl.model_dump(mode="json"),
                    expected=expected,
                    tag=tag,
                    kind=kind,
                    account=account,
                    handler=handler_ref.model_dump(mode="json") if handler_ref else None,
                ),
                operation,
                auto_audit=False,
                authorize=lambda c: self._access(c, viewer),
            )
        except ValidationError:
            raise WorkflowError(
                "Invalid source state; ask staff to recover the original records"
            ) from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _invalidate_uncommitted(
        self, c: Connection, state: GameState, value: rules.Use
    ) -> list[str]:
        """A spent Tag cannot strand an uncommitted proposal; known dice/modifiers survive."""
        from girlframe.engine.m3_handler_consequences import same_handler_body
        from girlframe.services.m3_actor_plays import ActorPlayService

        changed: list[str] = []
        if value.handler.kind != "handler":
            return changed
        actions, choices = t.m2["m2_actions"], t.m2["m2_choices"]
        for identity in c.scalars(
            sa.select(actions.c.id).where(
                actions.c.campaign_id == self.store.campaign_id,
                actions.c.state.not_in(("complete", "aborted")),
            )
        ):
            action = self.game.action(c, identity)
            meta = action["data"].get("actor_basic")
            if meta is None:
                continue
            ref = ActorRef.model_validate(meta["ref"])
            if ref.kind != "handler" or not same_handler_body(state, ref):
                continue
            proposals = action["data"].get("tag_proposals", [])
            committed = any(
                item.get("source") == "girl_tag" and item.get("tag") == value.tag
                for item in action["data"].get("modifiers", [])
            )
            removed = (
                [item for item in proposals if item["tag"] == value.tag] if not committed else []
            )
            pending = self.game.pending(c, identity)
            resolutions = [
                item
                for item in pending
                if item["kind"] == "tag_resolution"
                and json.loads(item["body_json"]).get("tag") == value.tag
            ]
            if not removed and not resolutions:
                continue
            affected = {item["controller"] for item in removed}
            stale = [
                item["id"]
                for item in pending
                if item["kind"] in ("actor_tag_selection", "actor_tag_agreement")
            ] + [item["id"] for item in resolutions]
            if stale:
                c.execute(
                    choices.update()
                    .where(
                        choices.c.campaign_id == self.store.campaign_id,
                        choices.c.id.in_(stale),
                        choices.c.state == "pending",
                    )
                    .values(state="superseded_by_tag_removal", revision=choices.c.revision + 1)
                )
            if removed:
                action["data"]["tag_proposals"] = [
                    item for item in proposals if item not in removed
                ]
                action["data"].pop("tag_candidate", None)
                action["data"].pop("tag_consensus", None)
                action["state"] = "tag_window"
                for human in affected:
                    self.game.request(c, action, human, "tag_window")
            elif resolutions and not self.game.pending(c, identity):
                ActorPlayService(self.game).results(c, action, state=state)
            self.game.save_action(c, action)
            changed.append(identity)
        return changed

    def _case(self, c: Connection, state: GameState, identity: str) -> rules.Use:
        value = next((x for x in rules.uses(state) if x.id == identity), None)
        if value is None:
            raise WorkflowError("This original Handler Tag use is unavailable")
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == value.source_event,
            )
        )
        original = GameState.model_validate_json(raw) if raw else None
        first = (
            next((x for x in rules.uses(original) if x.id == identity), None) if original else None
        )
        source = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.id == value.source_event,
            )
        ).first()
        stable = (
            "girl",
            "girl_controller",
            "handler",
            "handler_controller",
            "tag",
            "tag_label",
            "kind",
            "account",
            "source_event",
            "scene",
        )
        if (
            first is None
            or source is None
            or source.kind != "m3.handler_tag_used"
            or source.actor_id != str(value.girl_controller)
            or json.loads(source.payload_json).get("case_id") != identity
            or any(getattr(first, name) != getattr(value, name) for name in stable)
        ):
            raise WorkflowError(
                "SOURCE_HANDLER_TAG_MISSING: recover the original actual Tag consumption"
            )
        return value

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self._read(viewer, enabled=False) as c:
            state = load_state(c, self.store.campaign_id)
            value = self._case(c, state, identity)
            if viewer.user_id not in (value.girl_controller, value.handler_controller):
                raise WorkflowError("Only the original two humans can read this request")
            return value.model_dump(mode="json") | dict(
                original_current=rules.current(state, value.handler)
            )

    def notices(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        """Reading a request is an OOC notice, never a fictional answer or required effect."""
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        read = {
            json.loads(payload).get("case_id")
            for payload in c.scalars(
                sa.select(t.events.c.payload_json).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.actor_id == str(viewer.user_id),
                    t.events.c.kind == "m3.handler_tag_attention_read",
                )
            )
        }
        return [
            dict(id=value.id, revision=value.revision, read=value.id in read)
            for value in reversed(rules.uses(state))
            if value.kind == "attention" and value.handler_controller == viewer.user_id
        ]

    def read_attention(self, viewer: GuildViewer, key: str, identity: str) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            value = self._case(c, load_state(c, self.store.campaign_id), identity)
            if value.kind != "attention" or value.handler_controller != viewer.user_id:
                raise WorkflowError("Only the original Handler's human owns this attention notice")
            if not next(item["read"] for item in self.notices(c, viewer) if item["id"] == identity):
                self.game.event(
                    c, viewer.user_id, key, "m3.handler_tag_attention_read", case_id=identity
                )
            return dict(id=identity, read=True)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.handler_tag_attention_read",
                dict(case_id=identity),
                operation,
                auto_audit=False,
                authorize=lambda c: self.game.authorize(c, viewer, game=False),
            )
        except (ValidationError, ValueError):
            raise WorkflowError("Invalid source notice; recover the original records") from None

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        response: rules.Response,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = self._case(c, state, identity)
            if viewer.user_id != value.handler_controller:
                raise WorkflowError("Only the original Handler's human owns this response")
            from girlframe.services.m3_harpy_defeat import ended_actor_source

            ended = (
                ended_actor_source(self.game, c, state, value.handler)
                if response == "original_handler_ended"
                else None
            )
            event = str(uuid4())
            changed, result = rules.respond(
                state, identity, expected, response, account, event, ended_source=ended is not None
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_tag_answered",
                changed,
                event_id=event,
                case_id=identity,
                response=response,
                ended_source=ended,
            )
            work = t.m3["m3_required_work"]
            row = (
                c.execute(
                    sa.select(work)
                    .where(work.c.campaign_id == self.store.campaign_id, work.c.id == identity)
                    .order_by(work.c.revision.desc())
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if (
                row is None
                or row["state"] == "resolved"
                or row["owner_id"] != str(viewer.user_id)
                or row["kind"] != "handler_tag_response"
            ):
                raise WorkflowError("Recover the actual original Handler reply work")
            c.execute(
                work.insert().values(
                    **{k: v for k, v in row.items() if k not in ("revision", "state", "event_id")},
                    revision=row["revision"] + 1,
                    state="resolved",
                    event_id=event,
                )
            )
            return dict(id=identity, revision=result.revision, state=result.state)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.handler_tag_answered",
                dict(id=identity, expected=expected, response=response, account=account),
                operation,
                auto_audit=False,
                authorize=lambda c: self._access(c, viewer),
            )
        except ValidationError:
            raise WorkflowError(
                "Invalid source state; ask staff to recover the original records"
            ) from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None
