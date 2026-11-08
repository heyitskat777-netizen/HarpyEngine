"""Source-owned Director appearance, real Girl-rule resources and actual departure."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_budget_director as rules
from girlframe.engine import m3_director as presence
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.engine.m3_leviathan_obsession import allowed_gain, authority
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_handler_plays import _ordinary_scene_idle
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class MeetingService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _proof(self, c: Connection, state: GameState, identity: str) -> rules.Meeting:
        value = rules.get(state, identity)
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == value.source_event,
            )
        )
        original = GameState.model_validate_json(raw) if raw else None
        event = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == value.source_event,
                )
            )
            .mappings()
            .first()
        )
        source = rules.get(original, identity) if original else None
        immutable = (
            "id",
            "source_work",
            "source_event",
            "period",
            "handler",
            "director",
            "controller",
            "account",
        )
        if (
            source is None
            or event is None
            or event["kind"] != "m3.strain_effect_applied"
            or event["actor_id"] != value.handler.entity
            or json.loads(event["payload_json"]).get("work_id") != value.source_work
            or json.loads(event["payload_json"]).get("rule_id") != "strain.budget.high.1.1"
            or any(getattr(source, k) != getattr(value, k) for k in immutable)
        ):
            raise WorkflowError("Recover the original Budget meeting and separate Director")
        return value

    def available(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(id=x.id, phase=x.phase)
            for x in rules.meetings(state)
            if x.phase != "complete" and viewer.user_id in (int(x.handler.entity), x.controller)
        ]

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            Access(self.store).authorize(c, viewer, "strain")
            state = load_state(c, self.store.campaign_id)
            value = self._proof(c, state, identity)
            if viewer.user_id not in (int(value.handler.entity), value.controller):
                raise WorkflowError("This meeting belongs to its original two humans")
            body = (
                next((x for x in state.world.npcs if x.id == value.director.entity), None)
                if state.world
                else None
            )
            return dict(
                id=identity,
                revision=state.revision,
                phase=value.phase,
                handler=viewer.user_id == int(value.handler.entity),
                director=body.name if body else "Original Director",
                overlapping=any(x.active for x in state.director_contexts),
                context=value.context,
                heat=value.heat,
            )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        action: str,
        account: str,
        labels: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe the actual meeting appearance, presence or departure")

        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "strain")
            value = self._proof(c, load_state(c, self.store.campaign_id), identity)
            if viewer.user_id not in (int(value.handler.entity), value.controller):
                raise WorkflowError("Only the original meeting participants can respond")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _ordinary_scene_idle(c, self.game)
            state = load_state(c, self.store.campaign_id)
            value = self._proof(c, state, identity)
            body = (
                next(
                    (x for x in state.world.npcs if x.id == value.director.entity and x.alive), None
                )
                if state.world
                else None
            )
            if (
                state.revision != expected
                or value.phase == "complete"
                or body is None
                or body.controller != value.controller
                or not same_handler_body(state, value.handler)
            ):
                raise WorkflowError("STALE_MEETING: recover the original living participants")
            event = str(uuid4())
            if action == "appear":
                if viewer.user_id != value.controller or value.phase != "appearance" or labels:
                    raise WorkflowError(
                        "The separate Director's own human reports its real appearance"
                    )
                value = value.model_copy(update=dict(phase="setup", appearance_event=event))
            elif action == "start":
                if viewer.user_id != int(value.handler.entity) or value.phase != "setup":
                    raise WorkflowError(
                        "The original Handler confirms actual presence and its own Identities"
                    )
                active = any(x.active for x in state.director_contexts)
                if not active and authority(state, value.handler) is not None:
                    raise WorkflowError(
                        "SOURCE_PORT_REQUIRED: review the existing Identity pool "
                        "before this context"
                    )
                state = presence.enter(
                    state, viewer.user_id, value.director.entity, value.id, labels, event
                )
                context = next(x for x in state.director_contexts if value.id in x.source_works)
                actor = ActorRef(
                    kind="handler", entity=value.handler.entity, incarnation=context.id
                )
                gain = allowed_gain(state, actor, 4, "Budget performance meeting", event)
                state.handler_heat += gain
                value = value.model_copy(update=dict(phase="active", context=context.id, heat=gain))
            elif action == "end":
                if (
                    viewer.user_id != value.controller
                    or value.phase != "active"
                    or labels
                    or value.context is None
                ):
                    raise WorkflowError(
                        "The original Director's human records the real ending and departure"
                    )
                state = presence.leave(
                    state, viewer.user_id, value.context, value.director.entity, event
                )
                value = value.model_copy(update=dict(phase="complete", ended_event=event))
            else:
                raise WorkflowError("Choose the actual appearance, presence setup or departure")
            rules.put(state, value)
            state.facts.append(
                dict(
                    kind="budget_director_meeting_action",
                    meeting=identity,
                    action=action,
                    event=event,
                    account=account,
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.budget_director_meeting_changed",
                state,
                event_id=event,
                meeting=identity,
                action=action,
            )
            if action == "end":
                from girlframe.services.m3_battle import synchronize_casts

                synchronize_casts(self.game, c, event)
                work = t.m3["m3_required_work"]
                row = (
                    c.execute(
                        sa.select(work)
                        .where(work.c.campaign_id == self.store.campaign_id, work.c.id == identity)
                        .order_by(work.c.revision.desc())
                        .limit(1)
                    )
                    .mappings()
                    .one()
                )
                if row["state"] != "pending":
                    raise WorkflowError("Recover the actual pending meeting work")
                c.execute(
                    work.insert().values(
                        **{
                            k: v
                            for k, v in row.items()
                            if k not in ("revision", "state", "event_id")
                        },
                        revision=row["revision"] + 1,
                        state="resolved",
                        event_id=event,
                    )
                )
            return dict(id=identity, phase=value.phase, context=value.context, heat=value.heat)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.budget_director_meeting_changed",
                dict(id=identity, expected=expected, action=action, account=account, labels=labels),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
