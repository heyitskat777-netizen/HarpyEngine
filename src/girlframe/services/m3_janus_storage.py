"""Normal Dive storage and optional actual Foundation removal after Go Off-Duty."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_janus_storage as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_dive_state import Effect
from girlframe.engine.m3_janus_requisitions import STORAGE
from girlframe.engine.m3_off_duty import Period
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_janus_play import prove_link
from girlframe.services.m3_janus_requisitions import owned
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def available(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> bool:
    link = rules.live_link(state, actor)
    if link is None or owned(c, game, state, actor, STORAGE) is None:
        return False
    prove_link(game, c, state, link.id)
    return True


def gain(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    step: int,
    choice: str,
    actor: ActorRef,
    effect: Effect,
) -> None:
    if not available(game, c, state, actor) or effect.asset is None:
        raise WorkflowError("Actual Void Storage requires the owned rule and connected Harpy")
    receipt = owned(c, game, state, actor, STORAGE)
    assert receipt is not None
    rules.store(
        state,
        actor,
        asset=effect.asset,
        description=effect.description,
        purchase=receipt.id,
        action=action["id"],
        step=step,
        choice=choice,
        event=action["data"]["response_event"],
    )
    state.facts.append(
        dict(
            kind="dive_effect",
            action=action["id"],
            step=str(step),
            actor=actor.model_dump_json(),
            option="void_and_unmark_all",
            source_event=action["data"]["response_event"],
            account=effect.account,
            effect=effect.model_dump_json(),
        )
    )


def prove(game: GameService, c: Connection, state: GameState, point: rules.StoredVoid) -> None:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == point.source_event,
        )
    )
    source = GameState.model_validate_json(raw) if raw else None
    original = next((x for x in rules.points(source) if x.id == point.id), None) if source else None
    action = game.action(c, point.action)
    response = c.scalar(
        sa.select(t.m2["m2_responses"].c.choice_id).where(
            t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_responses"].c.choice_id == point.choice,
        )
    )
    meta = action["data"].get("dive") or {}
    selected = meta.get("steps", [])[point.step] if len(meta.get("steps", [])) > point.step else {}
    if (
        original is None
        or source is None
        or original.removed_event
        or original != point.model_copy(update={"removed_event": None, "removed_period": None})
        or action["data"]["play"] != "dive_deep"
        or not action["data"].get("receipt")
        or not response
        or selected.get("applied_event") != point.source_event
        or not selected.get("store_void")
        or ActorRef.model_validate(meta["actor"]) != point.actor
    ):
        raise WorkflowError("Recover this actual original Dive gain and its stored point")
    receipt = owned(c, game, source, point.actor, STORAGE)
    if receipt is None or receipt.id != point.purchase:
        raise WorkflowError("The stored point needs its actual paid original entitlement")
    link = prove_link(game, c, source, point.link)
    if link.battery != point.core or link.connection != point.connection:
        raise WorkflowError("The stored point belongs to its actual original Harpy connection")


class StorageService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def view(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            values = [x for x in rules.points(state) if x.actor == actor and not x.removed_event]
            for point in values:
                prove(self.game, c, state, point)
            active = {x.id for x in rules.active(state, actor)}
            period_rows = c.scalars(
                sa.select(t.m3["m3_off_duty"].c.body_json).where(
                    t.m3["m3_off_duty"].c.campaign_id == self.store.campaign_id,
                    t.m3["m3_off_duty"].c.phase == "active",
                )
            )
            periods = []
            for raw in period_rows:
                period = Period.model_validate_json(raw)
                progress = period.progress.get(actor.entity)
                if (
                    period.character_ids.get(actor.entity) == actor.incarnation
                    and progress
                    and progress.roll
                    and progress.roll.source == "status"
                    and progress.roll.stage == "choices"
                    and progress.action_id
                    and not any(
                        x.actor == actor and x.removed_period == period.id
                        for x in rules.points(state)
                    )
                ):
                    periods.append(period.id)
            return dict(
                revision=state.revision,
                periods=periods,
                points=[x.model_dump(mode="json") | dict(active=x.id in active) for x in values],
            )

    def request(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        point_id: str,
        period_id: str,
        account: str,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "playbooks")

        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            point = next((x for x in rules.points(state) if x.id == point_id), None)
            period = self._period(c, period_id)
            progress = period.progress.get(actor.entity)
            if (
                state.revision != revision
                or point is None
                or point.actor != actor
                or point.removed_event
                or not account.strip()
                or self.game.pending_actions(c)
                or period.phase != "active"
                or period.character_ids.get(actor.entity) != actor.incarnation
                or progress is None
                or progress.roll is None
                or progress.roll.source != "status"
                or progress.roll.stage != "choices"
                or progress.action_id is None
            ):
                raise WorkflowError(
                    "Request surgery after your own actual current Go Off-Duty roll"
                )
            source = self.game.action(c, progress.action_id)
            if source["data"]["play"] != "go_off_duty" or source["state"] != "complete":
                raise WorkflowError("Finish your actual Go Off-Duty roll before Foundation surgery")
            prove(self.game, c, state, point)
            if any(x.actor == actor and x.removed_period == period.id for x in rules.points(state)):
                raise WorkflowError("The Foundation removes at most one stored Void per period")
            if any(
                x.get("kind") == "janus_void_surgery"
                and x.get("period") == period.id
                and x.get("actor") == actor.model_dump_json()
                for x in state.facts
            ):
                raise WorkflowError("Use your existing actual surgical request")
            identity = str(uuid4())
            event = str(uuid4())
            state.facts.append(
                dict(
                    kind="janus_void_surgery",
                    id=identity,
                    point=point.id,
                    actor=actor.model_dump_json(),
                    period=period.id,
                    judge=str(period.handler_recipient or period.handler),
                    source_action=progress.action_id,
                    source_event=event,
                    account=account,
                    phase="pending",
                )
            )
            self.game.event(
                c, viewer.user_id, key, "m3.janus_storage_surgery_requested", state, event_id=event
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.janus_storage.request",
            dict(point=point_id, period=period_id, revision=revision, account=account),
            change,
            auto_audit=False,
            authorize=authorize,
        )

    def _period(self, c: Connection, identity: str) -> Period:
        raw = c.scalar(
            sa.select(t.m3["m3_off_duty"].c.body_json).where(
                t.m3["m3_off_duty"].c.campaign_id == self.store.campaign_id,
                t.m3["m3_off_duty"].c.id == identity,
            )
        )
        if not raw:
            raise WorkflowError("Use an actual existing Off-Duty period")
        return Period.model_validate_json(raw)

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(id=x["id"], revision=state.revision, actionable=str(viewer.user_id) == x["judge"])
            for x in state.facts
            if x.get("kind") == "janus_void_surgery"
            and x.get("phase") == "pending"
            and str(viewer.user_id) in (x["judge"], ActorRef.model_validate_json(x["actor"]).entity)
        ]

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            work = next(
                (
                    x
                    for x in state.facts
                    if x.get("kind") == "janus_void_surgery" and x["id"] == identity
                ),
                None,
            )
            if work is None or str(viewer.user_id) not in (
                work["judge"],
                ActorRef.model_validate_json(work["actor"]).entity,
            ):
                raise WorkflowError(
                    "This actual surgical request is private to its patient/reviewer"
                )
            return dict(
                id=identity,
                revision=state.revision,
                work=work,
                can_act=work["phase"] == "pending" and work["judge"] == str(viewer.user_id),
            )

    def confirm(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "playbooks", director_response=True)

        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            work = next(
                (
                    x
                    for x in state.facts
                    if x.get("kind") == "janus_void_surgery" and x["id"] == identity
                ),
                None,
            )
            if (
                work is None
                or work["judge"] != str(viewer.user_id)
                or work["phase"] != "pending"
                or state.revision != revision
                or not account.strip()
                or self.game.pending_actions(c)
            ):
                raise WorkflowError("Only the original Foundation reviewer records actual surgery")
            period = self._period(c, work["period"])
            if period.phase != "active":
                raise WorkflowError("Perform actual surgery during the original Off-Duty period")
            point = next(x for x in rules.points(state) if x.id == work["point"])
            patient = state.sheets.get(point.actor.entity)
            source = c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json).where(
                    t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_state_history"].c.event_id == work["source_event"],
                )
            )
            original = GameState.model_validate_json(source) if source else None
            if (
                patient is None
                or patient.character_id != point.actor.incarnation
                or (original is None or work not in original.facts)
            ):
                raise WorkflowError("Surgery needs the actual original patient and owned request")
            prove(self.game, c, state, point)
            if point.removed_event:
                raise WorkflowError("This actual stored Void was already removed")
            event = str(uuid4())
            rules.put(
                state,
                point.model_copy(update={"removed_event": event, "removed_period": period.id}),
            )
            work.update(phase="completed", completion_event=event, surgery_account=account)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.janus_storage_surgically_removed",
                state,
                event_id=event,
                point=point.id,
                period_id=period.id,
            )
            return dict(id=identity, point=point.id)

        return self.store._write(
            viewer,
            key,
            "m3.janus_storage.confirm",
            dict(id=identity, revision=revision, account=account),
            change,
            auto_audit=False,
            authorize=authorize,
        )
