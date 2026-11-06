"""Printed stipend offer uses existing actual career ending; no paid proxy receipt."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_void_retirement as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_budget_tags import _selection
from girlframe.services.m3_careers import end_in_transaction, synchronize_end
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class StipendService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _source(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[dict[str, Any], GameState, ActorRef, rules.Offer | None]:
        Access(self.store).authorize(c, viewer, "strain")
        Access(self.store).authorize(c, viewer, "economy")
        row, original = _selection(c, self.game, identity, rule=rules.RULE)
        handler = active_handler(original)
        state = load_state(c, self.store.campaign_id)
        value = next((x for x in rules.offers(state) if x.id == identity), None)
        if handler is None or row["owner_id"] != handler.entity:
            raise WorkflowError("Recover the original actual retirement Endgame Handler")
        if viewer.user_id != int(handler.entity) and (
            value is None or viewer.user_id != int(value.girl.entity)
        ):
            raise WorkflowError("This private offer belongs to its original Handler and Girl")
        if value:
            raw = c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json).where(
                    t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_state_history"].c.event_id == value.offered_event,
                )
            )
            saved_state = GameState.model_validate_json(raw) if raw else None
            first = (
                next((x for x in rules.offers(saved_state) if x.id == identity), None)
                if saved_state
                else None
            )
            event = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == self.store.campaign_id,
                        t.events.c.id == value.offered_event,
                    )
                )
                .mappings()
                .first()
            )
            if (
                first is None
                or event is None
                or first.phase != "offered"
                or event["kind"] != "m3.void_retirement_offered"
                or event["actor_id"] != handler.entity
                or first.handler != handler
                or first.source_event
                != c.scalar(
                    sa.select(t.m3["m3_required_work"].c.event_id)
                    .where(
                        t.m3["m3_required_work"].c.campaign_id == self.store.campaign_id,
                        t.m3["m3_required_work"].c.id == identity,
                    )
                    .order_by(t.m3["m3_required_work"].c.revision)
                    .limit(1)
                )
                or any(
                    getattr(first, k) != getattr(value, k)
                    for k in ("id", "source_event", "offered_event", "handler", "girl", "account")
                )
            ):
                raise WorkflowError("Recover the real immutable stipend offer source")
        return row, state, handler, value

    def available(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        return [
            dict(id=x.id, phase=x.phase)
            for x in rules.offers(load_state(c, self.store.campaign_id))
            if str(viewer.user_id) == x.girl.entity
        ]

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row, state, handler, value = self._source(c, viewer, identity)
            return dict(
                id=identity,
                revision=state.revision,
                work_revision=row["revision"],
                phase=value.phase if value else "nominate",
                handler=int(handler.entity),
                girl=int(value.girl.entity) if value else None,
                account=value.account if value else None,
                response=value.response if value else None,
                candidates=[
                    dict(id=uid, label=state.sheets[str(uid)].callsign) for uid in state.order
                ],
            )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        mode: str,
        account: str,
        *,
        girl: int | None = None,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError(
                "Describe the actual offer or your own response in 1–1200 characters"
            )

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row, state, handler, value = self._source(c, viewer, identity)
            if (
                state.revision != expected
                or row["state"] != "pending"
                or not same_handler_body(state, handler)
            ):
                raise WorkflowError("Reopen the current original stipend offer")
            changed = GameState.model_validate_json(state.model_dump_json())
            event = str(uuid4())
            if mode == "nominate":
                if (
                    value is not None
                    or viewer.user_id != int(handler.entity)
                    or girl not in state.order
                ):
                    raise WorkflowError(
                        "Only the original Handler offers one current Girl retirement"
                    )
                assert girl is not None
                actor = current_ref(state, girl)
                # Existing real person/physical/resource validation; no surrogate sheet.
                RequisitionService(self.game)._safe(c, state, girl)
                value = rules.Offer(
                    id=identity,
                    source_event=row["event_id"],
                    offered_event=event,
                    handler=handler,
                    girl=actor,
                    account=account.strip(),
                )
                rules.put(changed, value)
                self.game.event(
                    c,
                    viewer.user_id,
                    key,
                    "m3.void_retirement_offered",
                    changed,
                    event_id=event,
                    work_id=identity,
                    recipient=actor.model_dump(mode="json"),
                )
            else:
                if (
                    value is None
                    or value.phase != "offered"
                    or viewer.user_id != int(value.girl.entity)
                    or mode not in ("accept", "decline")
                ):
                    raise WorkflowError(
                        "Only the original recipient can accept or decline this offer"
                    )
                if current_ref(state, viewer.user_id) != value.girl:
                    raise WorkflowError(
                        "This offer belongs to its original Girl, not a replacement"
                    )
                archive = None
                if mode == "accept":
                    RequisitionService(self.game)._safe(c, state, viewer.user_id)
                    if RequisitionService(self.game)._actor(c, state, viewer).ref != value.girl:
                        raise WorkflowError("Recover the original living retirement recipient")
                    # Reuse voluntary discharge safeguards, without the paid Requisition.
                    if any(
                        x.active and value.girl in (x.traveler, x.supervisor)
                        for x in state.escort_journeys
                    ) or any(
                        x.held and value.girl in (x.actor, x.target) for x in state.enforcer_grasps
                    ):
                        raise WorkflowError(
                            "Finish the actual supervised journey or held grasp first"
                        )
                    archive = str(uuid4())
                    changed = end_in_transaction(
                        c,
                        self.game,
                        changed,
                        value.girl,
                        reason="retirement",
                        source_event=event,
                        account=account.strip(),
                        archive_id=archive,
                    )
                    changed.facts.append(
                        dict(
                            kind="void_retirement_stipend",
                            work=identity,
                            actor=value.girl.model_dump_json(),
                            archive=archive,
                            source_event=event,
                            destination="retired_offstage",
                            stipend="granted",
                            account=account.strip(),
                        )
                    )
                value = value.model_copy(
                    update=dict(
                        phase="accepted" if mode == "accept" else "declined",
                        response=account.strip(),
                        response_event=event,
                        archive=archive,
                    )
                )
                rules.put(changed, value)
                self.game.event(
                    c,
                    viewer.user_id,
                    key,
                    "m3.void_retirement_responded",
                    changed,
                    event_id=event,
                    work_id=identity,
                    outcome=value.phase,
                )
                if archive:
                    synchronize_end(
                        c, self.game, changed.career_archives[-1], exclude_work=(identity,)
                    )
                c.execute(
                    t.m3["m3_required_work"]
                    .insert()
                    .values(
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

        def authorize(c: Connection) -> None:
            self._source(c, viewer, identity)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.void_retirement_response",
                dict(id=identity, expected=expected, mode=mode, account=account, girl=girl),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
