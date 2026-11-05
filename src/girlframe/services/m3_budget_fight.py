"""Actual original attendance and completed opposing combat, without generated Plays."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_budget_fight as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class FightService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _proof(self, c: Connection, state: GameState, identity: str) -> rules.Fight:
        value = rules.get(state, identity)
        source = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == value.source_event,
                )
            )
            .mappings()
            .first()
        )
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == value.source_event,
            )
        )
        original = rules.get(GameState.model_validate_json(raw), identity) if raw else None
        if (
            source is None
            or original is None
            or source["kind"] != "m3.strain_effect_applied"
            or source["actor_id"] != value.handler.entity
            or json.loads(source["payload_json"]).get("rule_id") != rules.RULE
            or json.loads(source["payload_json"]).get("work_id") != value.source_work
            or any(
                getattr(original, k) != getattr(value, k)
                for k in (
                    "id",
                    "source_work",
                    "source_event",
                    "period",
                    "handler",
                    "people",
                    "scene",
                    "channel",
                    "account",
                )
            )
        ):
            raise WorkflowError("Recover the original televised fight and source participants")
        return value

    def _current(self, state: GameState, value: rules.Fight) -> None:
        if not same_handler_body(state, value.handler) or any(
            x.entity not in state.sheets
            or state.sheets[x.entity].character_id != x.incarnation
            or int(x.entity) not in state.order
            for x in value.people
        ):
            raise WorkflowError(
                "SOURCE_PORT_REQUIRED: preserve the original fight after changed or ended roles"
            )

    def available(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(id=x.id, phase=x.phase)
            for x in rules.fights(state)
            if x.phase != "complete"
            and viewer.user_id in {int(x.handler.entity), *(int(y.entity) for y in x.people)}
        ]

    def _actions(self, c: Connection, state: GameState, value: rules.Fight) -> tuple[str, ...]:
        if value.started_event is None:
            return ()
        started = c.scalar(
            sa.select(t.events.c.seq).where(
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.id == value.started_event,
            )
        )
        if started is None:
            raise WorkflowError("Recover actual source attendance before the fight")
        history = t.m3["m3_off_duty_history"]
        activated = c.scalar(
            sa.select(t.events.c.seq)
            .join(
                history,
                sa.and_(
                    history.c.campaign_id == t.events.c.campaign_id,
                    history.c.event_id == t.events.c.id,
                ),
            )
            .where(
                history.c.campaign_id == self.store.campaign_id,
                history.c.id == value.period,
                t.events.c.kind == "m3.off_duty_activated",
            )
            .order_by(t.events.c.seq)
            .limit(1)
        )
        if activated is None:
            return ()
        started = max(started, activated)
        completed = {}
        for event in c.execute(
            sa.select(t.events)
            .where(
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.kind == "m3.play_confirmed",
                t.events.c.seq > started,
            )
            .order_by(t.events.c.seq)
        ).mappings():
            payload = json.loads(event["payload_json"])
            if payload.get("play") != "all_out_assault" or not payload.get("action_id"):
                continue
            action = self.game.action(c, payload["action_id"])
            meta = action["data"].get("battle", {})
            if (
                action["state"] != "complete"
                or action["scene_id"] != value.scene
                or action["channel_id"] != str(value.channel)
                or action["parent_id"] is not None
                or meta.get("actor") not in [x.model_dump(mode="json") for x in value.people]
            ):
                continue
            actor = next(x for x in value.people if x.model_dump(mode="json") == meta["actor"])
            target = next(x for x in value.people if x != actor)
            if (
                meta.get("target") != target.model_dump(mode="json")
                or event["actor_id"] != actor.entity
            ):
                continue
            receipt = c.scalar(
                sa.select(t.m2["m2_receipts"].c.body_json).where(
                    t.m2["m2_receipts"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_receipts"].c.action_id == action["id"],
                )
            )
            if receipt is None or json.loads(receipt) != action["data"].get("receipt"):
                raise WorkflowError("Recover the actual immutable combat receipt")
            completed[actor.entity] = action["id"]
        return tuple(completed[x.entity] for x in value.people if x.entity in completed)

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            Access(self.store).authorize(c, viewer, "strain")
            state = load_state(c, self.store.campaign_id)
            value = self._proof(c, state, identity)
            self._current(state, value)
            if viewer.user_id not in {
                int(value.handler.entity),
                *(int(x.entity) for x in value.people),
            }:
                raise WorkflowError("Only the original actual fight participants open this source")
            person = next((x for x in value.people if x.entity == str(viewer.user_id)), None)
            return dict(
                id=identity,
                revision=state.revision,
                phase=value.phase,
                channel=value.channel,
                handler=viewer.user_id == int(value.handler.entity),
                attended=person in value.attended,
                completed=len(self._actions(c, state, value)),
                people=[state.sheets[x.entity].callsign for x in value.people],
            )

    def act(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, action: str, account: str
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError(
                "Describe your actual participation or the actual televised fight ending"
            )

        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "strain")
            state = load_state(c, self.store.campaign_id)
            value = self._proof(c, state, identity)
            if viewer.user_id not in {
                int(value.handler.entity),
                *(int(x.entity) for x in value.people),
            }:
                raise WorkflowError("Only an original fight participant responds")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = self._proof(c, state, identity)
            self._current(state, value)
            if expected != state.revision or value.phase == "complete":
                raise WorkflowError("STALE_FIGHT: reopen the original pending fight")
            event = str(uuid4())
            if action == "attend":
                if str(viewer.user_id) not in {x.entity for x in value.people}:
                    raise WorkflowError("Only an original Girl confirms her own participation")
                person = current_ref(state, viewer.user_id)
                if person in value.attended or value.phase != "attendance":
                    raise WorkflowError("Your original participation is already recorded")
                attended = (*value.attended, person)
                value = value.model_copy(
                    update=dict(
                        attended=attended,
                        phase="fighting" if len(attended) == 2 else "attendance",
                        started_event=event if len(attended) == 2 else None,
                    )
                )
            elif action == "end":
                actual = self._actions(c, state, value)
                if (
                    viewer.user_id != int(value.handler.entity)
                    or value.phase != "fighting"
                    or not actual
                    or self.game.pending_actions(c)
                ):
                    raise WorkflowError(
                        "Finish an actual opposing combat Play before ending this televised fight"
                    )
                value = value.model_copy(
                    update=dict(phase="complete", actions=actual, ended_event=event)
                )
            else:
                raise WorkflowError("Choose actual own participation or the real fight ending")
            rules.put(state, rules.Fight.model_validate_json(value.model_dump_json()))
            state.facts.append(
                dict(
                    kind="budget_fight_action",
                    fight=identity,
                    event=event,
                    actor=str(viewer.user_id),
                    action=action,
                    account=account,
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.budget_fight_action",
                state,
                event_id=event,
                fight=identity,
                action=action,
            )
            if action == "end":
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
                    raise WorkflowError("Recover the actual pending televised fight work")
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
            return dict(id=identity, phase=value.phase)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.budget_fight_action",
                dict(id=identity, expected=expected, action=action, account=account),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
