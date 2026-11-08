"""An actual leader opportunity, no invented mission success or personal kill credit."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_rebel_leader as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_budget_tags import _selection
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class LeaderService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _source(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[dict[str, Any], GameState, str, ActorRef]:
        Access(self.store).authorize(c, viewer, "strain")
        Access(self.store).authorize(c, viewer, "world")
        row, original = _selection(c, self.game, identity, rule=rules.RULE)
        current = load_state(c, self.store.campaign_id)
        handler = active_handler(original)
        selected = (
            next((x for x in original.strain.endgames if x.rule_id == rules.RULE), None)
            if original.strain
            else None
        )
        if (
            handler is None
            or handler.entity != str(viewer.user_id)
            or row["owner_id"] != str(viewer.user_id)
            or not same_handler_body(current, handler)
            or not selected
            or not selected.faction
            or not original.world
            or not any(
                x.id == selected.faction and x.active and x.kind == "rebel"
                for x in original.world.factions
            )
        ):
            raise WorkflowError(
                "Recover the actual original Handler and selected active Rebel Group"
            )
        return row, current, selected.faction, handler

    def _proof(self, c: Connection, state: GameState, identity: str) -> rules.Opportunity | None:
        value = next((x for x in rules.opportunities(state) if x.id == identity), None)
        if value is None:
            return None
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == value.named_event,
            )
        )
        source = GameState.model_validate_json(raw) if raw else None
        first = (
            next((x for x in rules.opportunities(source) if x.id == identity), None)
            if source
            else None
        )
        event = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == value.named_event,
                )
            )
            .mappings()
            .first()
        )
        if (
            event is None
            or event["kind"] != "m3.rebel_leader_identified"
            or first is None
            or event["actor_id"] != value.handler.entity
            or json.loads(event["payload_json"]).get("work_id") != identity
            or any(
                getattr(first, k) != getattr(value, k)
                for k in ("source_event", "named_event", "group", "handler", "leader", "account")
            )
        ):
            raise WorkflowError("Recover the original living leader and genuine opportunity source")
        return value

    def available(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(id=x.id, phase=x.phase)
            for x in rules.opportunities(state)
            if x.handler.entity == str(viewer.user_id) and same_handler_body(state, x.handler)
        ]

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row, state, groupid, _ = self._source(c, viewer, identity)
            value = self._proof(c, state, identity)
            group = (
                next((x for x in state.world.factions if x.id == groupid), None)
                if state.world
                else None
            )
            return dict(
                id=identity,
                revision=state.revision,
                work_revision=row["revision"],
                phase=value.phase if value else "identify",
                group=group.name if group else groupid,
                leader=value.leader.entity if value else None,
                account=value.account if value else None,
                response=value.response if value else None,
                candidates=[
                    dict(id=x.id, label=x.name)
                    for x in state.world.npcs
                    if x.alive
                    and group
                    and (
                        x.id == group.leader
                        if group.leader
                        else x.faction == groupid or groupid in x.secret_factions
                    )
                ]
                if state.world
                else [],
            )

    def _death(self, c: Connection, value: rules.Opportunity, state: GameState) -> str:
        npc = (
            next((x for x in state.world.npcs if x.id == value.leader.entity), None)
            if state.world
            else None
        )
        if npc is None or npc.alive:
            raise WorkflowError("The actual leader is still alive")
        start = c.scalar(
            sa.select(t.events.c.seq).where(
                t.events.c.campaign_id == self.store.campaign_id, t.events.c.id == value.named_event
            )
        )
        if start is None:
            raise WorkflowError("Recover the real leader opportunity event")
        history = t.m2["m2_state_history"]
        rows = c.execute(
            sa.select(t.events.c.id, t.events.c.kind, history.c.body_json)
            .join(
                history,
                sa.and_(
                    history.c.campaign_id == t.events.c.campaign_id,
                    history.c.event_id == t.events.c.id,
                ),
            )
            .where(t.events.c.campaign_id == self.store.campaign_id, t.events.c.seq > start)
            .order_by(t.events.c.seq)
        ).mappings()
        before: bool | None = True
        for row in rows:
            world = json.loads(row["body_json"]).get("world")
            body = (
                next((x for x in world["npcs"] if x["id"] == value.leader.entity), None)
                if world
                else None
            )
            alive = body.get("alive") if body else None
            if before is True and alive is False:
                if row["kind"] in (
                    "m3.npc_damage_applied",
                    "m3.choice_resolved",
                    "m3.budget_bonds_departed",
                ):
                    return str(row["id"])
                raise WorkflowError(
                    "SOURCE_PORT_REQUIRED: actual leader death needs its supported runtime source"
                )
            before = alive
        raise WorkflowError(
            "Prove the actual post-opportunity leader death; no caller assertion substitutes"
        )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        action: str,
        account: str,
        *,
        leader: str = "",
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe the actual opportunity or group outcome")

        def authorize(c: Connection) -> None:
            self._source(c, viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row, state, group, handler = self._source(c, viewer, identity)
            value = self._proof(c, state, identity)
            if state.revision != expected or self.game.pending_actions(c):
                raise WorkflowError("STALE_OPPORTUNITY: finish pending Plays and reopen")
            event = str(uuid4())
            if action == "identify":
                if value is not None or row["state"] != "pending":
                    raise WorkflowError("Leader already identified")
                value = rules.Opportunity(
                    id=identity,
                    source_event=row["event_id"],
                    named_event=event,
                    group=group,
                    handler=handler,
                    leader=ActorRef(kind="npc", entity=leader),
                    account=account,
                )
                state = rules.identify(state, value)
                kind = "m3.rebel_leader_identified"
            elif action in ("destroy", "forgo") and value is not None:
                death = self._death(c, value, state) if action == "destroy" else None
                state = rules.finish(state, value, event, death, account)
                kind = "m3.rebel_leader_settled"
            else:
                raise WorkflowError("Choose actual identification, proven destruction or forgoing")
            self.game.event(c, viewer.user_id, key, kind, state, event_id=event, work_id=identity)
            if action == "identify":
                c.execute(
                    t.m3["m3_required_work"]
                    .insert()
                    .values(
                        **(
                            row
                            | dict(revision=row["revision"] + 1, state="resolved", event_id=event)
                        )
                    )
                )
            return dict(
                id=identity,
                phase=next(x.phase for x in rules.opportunities(state) if x.id == identity),
            )

        try:
            return self.store._write(
                viewer,
                key,
                "m3.rebel_leader_response",
                dict(id=identity, expected=expected, action=action, account=account, leader=leader),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
