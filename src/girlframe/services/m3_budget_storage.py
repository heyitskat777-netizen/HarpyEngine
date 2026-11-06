"""Owned storage responses and immutable post-order breach/reduction proof."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_budget_storage as rules
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class StorageService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _history(self, c: Connection) -> list[dict[str, Any]]:
        history = t.m2["m2_state_history"]
        return [
            dict(x)
            for x in c.execute(
                sa.select(t.events, history.c.body_json)
                .join(
                    history,
                    sa.and_(
                        history.c.event_id == t.events.c.id,
                        history.c.campaign_id == t.events.c.campaign_id,
                    ),
                )
                .where(t.events.c.campaign_id == self.store.campaign_id)
                .order_by(t.events.c.seq)
            ).mappings()
        ]

    def _proof(self, c: Connection, state: GameState, identity: str) -> rules.Order:
        value = rules.get(state, identity)
        source = next((x for x in self._history(c) if x["id"] == value.source_event), None)
        if source is None:
            raise WorkflowError("Recover the original immutable storage source")
        original = rules.get(GameState.model_validate_json(source["body_json"]), identity)
        if (
            source["kind"] != "m3.strain_effect_applied"
            or source["actor_id"] != value.handler.entity
            or json.loads(source["payload_json"]).get("rule_id") != rules.RULE
            or json.loads(source["payload_json"]).get("work_id") != value.source_work
            or original != value.model_copy(update=dict(phase="active", entries=()))
        ):
            raise WorkflowError(
                "Recover the original Frame, base, higher-up and Handler appointment"
            )
        return value

    def _controller(self, state: GameState, value: rules.Order, user: int) -> bool:
        npc = (
            next((x for x in state.world.npcs if x.id == value.superior.entity), None)
            if state.world
            else None
        )
        return bool(npc and npc.alive and npc.controller == value.controller == user)

    def _participant(self, state: GameState, value: rules.Order, user: int) -> bool:
        sheet = state.sheets.get(value.owner.entity)
        return (
            self._controller(state, value, user)
            or user == int(value.handler.entity)
            and same_handler_body(state, value.handler)
            or user == int(value.owner.entity)
            and sheet is not None
            and sheet.character_id == value.owner.incarnation
        )

    def _reduction(self, c: Connection, source_event: str) -> str | None:
        from girlframe.engine import m3_martyr
        from girlframe.services.m3_class_retention import proof
        from girlframe.services.m3_girl_insurance import prove_reduction

        previous = None
        after_source = False
        for row in self._history(c):
            actual = GameState.model_validate_json(row["body_json"])
            if row["id"] == source_event:
                after_source = True
            elif (
                after_source
                and previous
                and previous.strain
                and actual.strain
                and previous.strain.levels["budget"] == "high"
                and actual.strain.levels["budget"] == "low"
            ):
                if prove_reduction(self.game, c, previous, actual, str(row["id"])):
                    return str(row["id"])
                if row["kind"] == "m3.strain_start_prepared":
                    payload = json.loads(row["payload_json"])
                    if (
                        payload.get("levels", {}).get("budget") == "low"
                        and payload.get("period_id") in actual.strain.periods
                    ):
                        return str(row["id"])
                for episode in m3_martyr.episodes(actual):
                    if (
                        episode.source_event == row["id"]
                        and m3_martyr.budget_death_excluded(actual, str(row["id"]))
                        and any(
                            x.id == episode.archive and x not in previous.career_archives
                            for x in actual.career_archives
                        )
                    ):
                        held = m3_martyr.held(previous, episode.actor)
                        if held is None or held.id != episode.purchase:
                            continue
                        proof(self.game, c, previous, held)
                        return str(row["id"])
            previous = actual
        return None

    def _frame_play(
        self, c: Connection, row: dict[str, Any], actual: GameState, value: rules.Order
    ) -> bool:
        if row["kind"] not in ("m2.rolled", "m3.rolled") or row["actor_id"] != value.owner.entity:
            return False
        payload = json.loads(row["payload_json"])
        actions, receipts = t.m2["m2_actions"], t.m2["m2_receipts"]
        source = (
            c.execute(
                sa.select(actions.c.body_json, receipts.c.body_json.label("receipt"))
                .join(
                    receipts,
                    sa.and_(
                        receipts.c.campaign_id == actions.c.campaign_id,
                        receipts.c.action_id == actions.c.id,
                    ),
                )
                .where(
                    actions.c.campaign_id == self.store.campaign_id,
                    actions.c.id == payload.get("action_id"),
                    actions.c.actor_id == value.owner.entity,
                    actions.c.state == "complete",
                    receipts.c.id == payload.get("receipt_id"),
                )
            )
            .mappings()
            .first()
        )
        if source is None:
            return False
        data, receipt = json.loads(source["body_json"]), json.loads(source["receipt"])
        prepared = PlayInput.model_validate(data["prepared"])
        return bool(
            prepared.piloting
            and prepared.play
            in (
                "check_sensors",
                "engage",
                "dive_deep",
                "all_out_assault",
                "go_for_the_core",
                "enforcement_initiative",
            )
            and data.get("character_ids", {}).get(value.owner.entity) == value.owner.incarnation
            and receipt.get("action_id") == payload.get("action_id")
            and receipt.get("id") == data.get("receipt", {}).get("id")
            and rules.pose(actual, value).mode == "piloting"
        )

    def _breach(self, c: Connection, value: rules.Order, after: str) -> str | None:
        later = False
        previous = None
        for row in self._history(c):
            actual = GameState.model_validate_json(row["body_json"])
            if row["id"] == after:
                later = True
            elif later:
                if (
                    row["kind"] == "m3.budget_storage_action"
                    and row["actor_id"] == value.handler.entity
                    and json.loads(row["payload_json"]).get("storage") == value.id
                    and json.loads(row["payload_json"]).get("action") == "refuse"
                ):
                    return str(row["id"])
                try:
                    placed = rules.pose(actual, value)
                    prior = rules.pose(previous, value) if previous else None
                except ValueError:
                    previous = actual
                    continue
                if self._frame_play(c, row, actual, value):
                    return str(row["id"])
                if (
                    placed.source_event == row["id"]
                    and row["actor_id"] == value.owner.entity
                    and any(
                        x.get("kind") == "physical_operation"
                        and x.get("source_event") == row["id"]
                        and x.get("actor") == value.owner.model_dump_json()
                        for x in actual.facts
                    )
                    and (
                        placed.mode == "piloting"
                        or prior is not None
                        and placed.frame_cell != prior.frame_cell
                    )
                ):
                    return str(row["id"])
            previous = actual
        return None

    def available(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(id=x.id, phase=x.phase)
            for x in rules.orders(state)
            if x.phase == "active" and self._participant(state, x, viewer.user_id)
        ]

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            Access(self.store).authorize(c, viewer, "strain")
            state = load_state(c, self.store.campaign_id)
            value = self._proof(c, state, identity)
            if not self._participant(state, value, viewer.user_id):
                raise WorkflowError("Only this original order's participants may open it")
            actions: list[tuple[str, str]] = []
            blocked = ""
            reduction = self._reduction(c, value.source_event)
            if value.phase == "active" and same_handler_body(state, value.handler):
                if reduction:
                    actions.append(
                        ("release", "Record the actual Budget reduction and order release")
                    )
                else:
                    if viewer.user_id == int(value.owner.entity):
                        try:
                            rules.empty_at_base(state, value)
                            actions.append(
                                ("store", "Confirm my exact empty Frame is stored at this base")
                            )
                        except ValueError as error:
                            blocked = str(error)
                    if viewer.user_id == int(value.handler.entity):
                        actions.append(
                            ("refuse", "Record my actual Handler refusal of this storage order")
                        )
                    if self._controller(state, value, viewer.user_id):
                        warning = next((x for x in value.entries if x.action == "warn"), None)
                        if self._breach(c, value, warning.event if warning else value.source_event):
                            actions.append(
                                (
                                    "fire" if warning else "warn",
                                    "Fire original Handler after renewed breach"
                                    if warning
                                    else "Give the original Handler a warning Tag",
                                )
                            )
            return dict(
                id=identity,
                revision=state.revision,
                phase=value.phase,
                owner=state.sheets[value.owner.entity].callsign
                if value.owner.entity in state.sheets
                else "Original Frame owner",
                base=next(
                    (x.name for x in state.world.locations if x.id == value.base),
                    "Original storage base",
                )
                if state.world
                else "Original storage base",
                frame=value.frame,
                actions=actions,
                blocked=blocked,
                entries=[x.model_dump(mode="json") for x in value.entries],
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
        label: str = "",
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe your actual storage response in 1–1200 characters")

        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "strain")
            state = load_state(c, self.store.campaign_id)
            value = self._proof(c, state, identity)
            if not self._participant(state, value, viewer.user_id):
                raise WorkflowError("Only the actual original participants own this order")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = self._proof(c, state, identity)
            if (
                state.revision != expected
                or MedicalService(self.store)._handler(c)[1] != value.appointment
            ):
                raise WorkflowError(
                    "STALE_STORAGE: reopen the original current order and appointment"
                )
            reduction = self._reduction(c, value.source_event)
            proof = None
            if action == "release":
                if not reduction:
                    raise WorkflowError(
                        "No actual later canonical High to Low Budget source exists"
                    )
                proof = reduction
            elif reduction:
                raise WorkflowError(
                    "This order ended with actual Budget reduction; record its release"
                )
            if action in ("warn", "fire"):
                if not self._controller(state, value, viewer.user_id):
                    raise WorkflowError(
                        "Only the actual higher-up's original controller owns this response"
                    )
                warning = next((x for x in value.entries if x.action == "warn"), None)
                if action == "fire" and warning is None:
                    raise WorkflowError("The original Handler must receive a warning before firing")
                proof = self._breach(c, value, warning.event if warning else value.source_event)
                if proof is None:
                    raise WorkflowError(
                        "Record an actual distinct post-order or post-warning breach first"
                    )
            if action == "fire" and self.game.pending_actions(c):
                raise WorkflowError("Finish pending Plays before firing the original Handler")
            event = str(uuid4())
            updated = rules.apply(
                state,
                value,
                action,
                viewer.user_id,
                event,
                account.strip(),
                proof=proof,
                label=label,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.budget_storage_action",
                updated,
                event_id=event,
                storage=identity,
                action=action,
                proof=proof,
            )
            if action == "fire":
                from girlframe.services.m3_battle import synchronize_casts
                from girlframe.services.m3_handler_consequences import end_body_reviews
                from girlframe.services.m3_handler_girl_void import synchronize_endings as sync_girl
                from girlframe.services.m3_handler_void import synchronize_endings

                for archive in updated.handler_archives:
                    if archive.source_event == event:
                        end_body_reviews(self.game, c, archive)
                synchronize_casts(self.game, c, event)
                synchronize_endings(self.game, c, event, viewer, key)
                sync_girl(self.game, c, event, viewer, key)
            if action in ("release", "fire"):
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
                    raise WorkflowError("Recover the original pending storage order")
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
            return dict(id=identity, phase=rules.get(updated, identity).phase, event=event)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.budget_storage_action",
                dict(id=identity, expected=expected, action=action, account=account, label=label),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
