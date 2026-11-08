"""Exact Handler-priced extra repairs after actual shortage recovery; no automatic spending."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_economy import RepairQuote, quoted_repair_in_state
from girlframe.engine.m3_modular import Replacement, replace_repaired
from girlframe.engine.m3_repair_state import Quote
from girlframe.engine.m3_repairs import active
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_intracadre_marriage import prepare_payment
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def frame_instance(state: GameState, owner: int, character: str) -> str:
    sheet = state.sheets[str(owner)]
    return sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + character


class RepairService:
    def __init__(self, periods: OffDutyService):
        self.periods, self.missions = periods, periods.missions
        self.store, self.game = periods.store, periods.game

    def _owner(
        self, c: Connection, state: GameState, owner: int, *, fresh: bool = True
    ) -> ActorRef:
        return ActorRef(
            kind="pilot",
            entity=str(owner),
            incarnation=self.game.character_binding(
                c,
                state,
                owner,
                require_current_profile=fresh,
            ),
        )

    def _scope(
        self, c: Connection, state: GameState, period_id: str, owner: int
    ) -> tuple[str, ...]:
        period = self.periods._get(c, period_id)
        progress = period.progress.get(str(owner))
        shortage = active(state, period_id)
        if (
            period.phase != "active"
            or not shortage
            or owner not in period.pilots
            or progress is None
            or not progress.recovered
            or period.handler != state.handler
            or period.character_ids.get(str(owner)) != self._owner(c, state, owner).incarnation
            or state.sheets[str(owner)].frame_scrapped
        ):
            raise WorkflowError("Finish your actual shortage recovery before extra Asset repairs.")
        return shortage

    def _safe(self, c: Connection) -> None:
        locks = t.m2["m2_locks"]
        if self.game.pending_actions(c) or c.scalar(
            sa.select(locks.c.channel_id)
            .where(
                locks.c.campaign_id == self.store.campaign_id,
                locks.c.state != "released",
            )
            .limit(1)
        ):
            raise WorkflowError("Resolve pending Plays and restore chat before repairing Assets.")

    def _quote(self, state: GameState, identity: str) -> Quote:
        quote = next((x for x in state.repair_quotes if x.id == identity), None)
        if quote is None:
            raise WorkflowError("This private repair quote is unavailable.")
        return quote

    def _visible(self, c: Connection, state: GameState, viewer: GuildViewer, quote: Quote) -> bool:
        if viewer.user_id == state.handler == quote.handler:
            return True
        if str(viewer.user_id) != quote.owner.entity:
            return False
        try:
            return self._owner(c, state, viewer.user_id, fresh=False) == quote.owner
        except WorkflowError:
            return False

    def _current(self, c: Connection, state: GameState, quote: Quote) -> None:
        owner = int(quote.owner.entity)
        sheet = state.sheets.get(quote.owner.entity)
        if (
            quote.state != "pending"
            or quote.handler != state.handler
            or sheet is None
            or self._owner(c, state, owner) != quote.owner
            or sheet.revision != quote.sheet_revision
            or frame_instance(state, owner, quote.owner.incarnation or "") != quote.frame_instance
            or self._scope(c, state, quote.period, owner) != quote.shortages
            or not any(x.id == quote.asset and x.damaged for x in sheet.assets)
        ):
            raise WorkflowError(
                "STALE_QUOTE: ask the current Handler for a fresh exact repair quote."
            )

    def list(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            return [
                {"id": x.id, "label": x.asset_name, "state": x.state}
                for x in state.repair_quotes
                if self._visible(c, state, viewer, x)
            ]

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            quote = self._quote(state, identity)
            if not self._visible(c, state, viewer, quote):
                raise WorkflowError("This private repair quote belongs to another character.")
            available = True
            try:
                self._current(c, state, quote)
            except WorkflowError:
                available = False
            from girlframe.services.m3_modular import repair_options

            return {
                "id": quote.id,
                "revision": quote.revision,
                "game_revision": state.revision,
                "state": quote.state,
                "cost": quote.cost,
                "asset": quote.asset_name,
                "asset_id": quote.asset,
                "period": quote.period,
                "owner": int(quote.owner.entity),
                "available": available,
                "may_answer": str(viewer.user_id) == quote.owner.entity
                and quote.state == "pending",
                "modular": [
                    x
                    for x in repair_options(self.game, c, state, quote.owner)
                    if x["id"] == quote.asset
                ]
                if available
                else [],
                "may_reprice": viewer.user_id == state.handler == quote.handler
                and quote.state != "accepted",
            }

    def eligible(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            HandlerService(self.store).authorize(c, viewer)
            state = load_state(c, self.store.campaign_id)
            rows = t.m3["m3_off_duty"]
            period_id = c.scalar(
                sa.select(rows.c.id).where(
                    rows.c.campaign_id == self.store.campaign_id, rows.c.phase == "active"
                )
            )
            choices: list[dict[str, Any]] = []
            if period_id is not None:
                for owner in state.order:
                    try:
                        self._scope(c, state, period_id, owner)
                    except WorkflowError:
                        continue
                    choices.extend(
                        {
                            "owner": owner,
                            "callsign": state.sheets[str(owner)].callsign,
                            "asset": x.id,
                            "name": x.name,
                        }
                        for x in state.sheets[str(owner)].assets
                        if x.damaged
                    )
            return {"game_revision": state.revision, "period": period_id, "assets": choices}

    def offer(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        period_id: str,
        owner: int,
        asset_id: str,
        cost: int,
        quote_id: str | None = None,
        quote_revision: int = 0,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.missions.access.authorize(c, viewer, "economy")
            HandlerService(self.store).authorize(c, viewer)
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            if state.revision != expected:
                raise WorkflowError("STALE_STATE: refresh the actual damaged Assets.")
            self._safe(c)
            shortage = self._scope(c, state, period_id, owner)
            sheet = state.sheets[str(owner)]
            asset = next((x for x in sheet.assets if x.id == asset_id and x.damaged), None)
            if asset is None:
                raise WorkflowError("Quote one actual damaged Girl or Frame Asset.")
            ref = self._owner(c, state, owner)
            previous = self._quote(state, quote_id) if quote_id else None
            if (
                previous is not None
                and (
                    previous.revision != quote_revision
                    or previous.state == "accepted"
                    or previous.owner != ref
                    or previous.asset != asset_id
                    or previous.period != period_id
                )
            ) or (previous is None and quote_revision != 0):
                raise WorkflowError("STALE_QUOTE: refresh before revising this actual offer.")
            event = str(uuid4())
            quote = Quote(
                id=quote_id or str(uuid4()),
                revision=previous.revision + 1 if previous else 1,
                period=period_id,
                shortages=shortage,
                owner=ref,
                handler=viewer.user_id,
                asset=asset_id,
                asset_name=asset.name,
                frame_instance=frame_instance(state, owner, ref.incarnation or ""),
                sheet_revision=sheet.revision,
                cost=cost,
                source_event=event,
            )
            state.repair_quotes = [x for x in state.repair_quotes if x.id != quote.id] + [quote]
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.repair_quote_offered",
                state,
                event_id=event,
                quote_id=quote.id,
                quote_revision=quote.revision,
            )
            return {"id": quote.id, "revision": quote.revision, "state": quote.state}

        try:
            return self.store._write(
                viewer,
                key,
                "m3.repair_quote_offered",
                {
                    "expected": expected,
                    "period": period_id,
                    "owner": owner,
                    "asset": asset_id,
                    "cost": cost,
                    "quote": quote_id,
                    "quote_revision": quote_revision,
                },
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        quote_revision: int,
        accept: bool,
        replacement: Replacement | None = None,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.missions.access.authorize(c, viewer, "economy")
            if accept:
                self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            quote = self._quote(state, identity)
            if (
                type(accept) is not bool
                or state.revision != expected
                or quote.revision != quote_revision
                or quote.state != "pending"
                or str(viewer.user_id) != quote.owner.entity
                or self._owner(c, state, viewer.user_id, fresh=False) != quote.owner
            ):
                raise WorkflowError("STALE_QUOTE: reopen your actual pending repair offer.")
            event = str(uuid4())
            if replacement is not None and (not accept or replacement.asset != quote.asset):
                raise WorkflowError("Choose replacement only for this exact accepted quoted repair")
            if accept:
                self._safe(c)
                self._current(c, state, quote)
                if replacement is not None:
                    from girlframe.services.m3_modular import entitlement

                    if entitlement(self.game, c, state, quote.owner) is None:
                        raise WorkflowError("Restore your actual Modular repair entitlement")
                before = state.sheets[quote.owner.entity].model_copy(deep=True)
                prepare_payment(
                    self.game,
                    c,
                    state,
                    viewer,
                    quote.owner,
                    "extra_asset_repair",
                    quote.cost,
                    quote.id,
                )
                result = quoted_repair_in_state(
                    state,
                    quote.owner,
                    RepairQuote(
                        id=quote.id,
                        handler_id=quote.handler,
                        owner_id=viewer.user_id,
                        asset_id=quote.asset,
                        sheet_revision=quote.sheet_revision,
                        quote_revision=quote.revision,
                        cost=quote.cost,
                    ),
                    current_handler=int(state.handler) if state.handler else 0,
                    expected_quote_revision=quote_revision,
                    event=event,
                    source=quote.id,
                )
                state.sheets[quote.owner.entity] = result.sheet
                if replacement is not None:
                    replace_repaired(
                        state,
                        quote.owner,
                        before,
                        (replacement,),
                        None,
                        source="repair_quote:" + quote.id,
                    )
            updated = quote.model_copy(
                update={
                    "revision": quote.revision + 1,
                    "state": "accepted" if accept else "declined",
                    "response_event": event,
                }
            )
            state.repair_quotes = [updated if x.id == identity else x for x in state.repair_quotes]
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.repair_quote_answered",
                state,
                event_id=event,
                quote_id=identity,
                accepted=accept,
            )
            return {"id": identity, "revision": updated.revision, "state": updated.state}

        try:
            return self.store._write(
                viewer,
                key,
                "m3.repair_quote_answered",
                {
                    "id": identity,
                    "expected": expected,
                    "quote_revision": quote_revision,
                    "accept": accept,
                    **(
                        {"modular_replacement": replacement.model_dump(mode="json")}
                        if replacement is not None
                        else {}
                    ),
                },
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except (ValueError, ValidationError) as error:
            raise WorkflowError(str(error)) from None
