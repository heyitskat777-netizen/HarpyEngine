"""Owned resumable optional exchanges: actual baseline, four Permissions, one transaction."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_frame_swap as rules
from girlframe.engine.creation import official_frame
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.m2 import GameState, PilotSheet
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_frame_swap_state import Selection, SwapReceipt
from girlframe.engine.playbooks import FRAME_TYPES
from girlframe.engine.rules_registry import Registry
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_personal_firearm import PersonalFirearmService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KIND = "frame_swap"


class FrameSwapService(PersonalFirearmService):
    def _class_sources(
        self, c: Connection, state: GameState, actor: ActorRef
    ) -> list[dict[str, str]]:
        from girlframe.engine.m3_class_grafts import held
        from girlframe.engine.m3_class_retention import RULES
        from girlframe.services.m3_class_retention import proof

        result = []
        for rule in RULES:
            paid = held(state, actor, rule)
            if paid is not None:
                proof(self.game, c, state, paid)
                result.append(
                    dict(
                        rule=rule,
                        receipt=paid.id,
                        label=rule.rsplit(".", 1)[-1].replace("-", " ").title()
                        + " — original "
                        + paid.kind.replace("_", " ")
                        + " "
                        + str(paid.price)
                        + "P",
                        origin_frame=paid.frame_instance,
                    )
                )
        return result

    def _registry(self) -> Registry:
        registry = self.registry or Access(self.store).registry
        assert registry is not None
        return registry

    def _rows(self, c: Connection) -> list[dict[str, Any]]:
        work = t.m3["m3_required_work"]
        return list(
            {
                x["id"]: dict(x)
                for x in c.execute(
                    sa.select(work)
                    .where(
                        work.c.campaign_id == self.store.campaign_id,
                        work.c.kind == KIND,
                    )
                    .order_by(work.c.revision)
                ).mappings()
            }.values()
        )

    def _row(self, c: Connection, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        self.game.authorize(c, viewer, game=False)
        row = next((x for x in self._rows(c) if x["id"] == identity), None)
        if row is None:
            raise WorkflowError("This original paid-exchange plan is unavailable.")
        body = json.loads(row["body_json"])
        work = t.m3["m3_required_work"]
        first = (
            c.execute(
                sa.select(work).where(
                    work.c.campaign_id == self.store.campaign_id,
                    work.c.id == identity,
                    work.c.revision == 1,
                )
            )
            .mappings()
            .first()
        )
        source = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == first["event_id"] if first else sa.false(),
                )
            )
            .mappings()
            .first()
        )
        original = json.loads(first["body_json"]) if first else {}
        if (
            source is None
            or source["kind"] != "m3.frame_swap_planned"
            or source["actor_id"] != row["owner_id"]
            or json.loads(source["payload_json"]).get("plan_id") != identity
            or any(body.get(k) != original.get(k) for k in ("actor", "frame", "old_frame"))
        ):
            raise WorkflowError("SOURCE_FRAME_SWAP_MISSING: recover the original owned plan.")
        target = body.get("selection", {}).get("court_target") if body.get("selection") else None
        if str(viewer.user_id) != row["owner_id"] and (
            target is None or target["entity"] != str(viewer.user_id)
        ):
            raise WorkflowError("This plan belongs to its actual original participants.")
        return row

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        result = []
        for row in self._rows(c):
            try:
                self._row(c, viewer, row["id"])
            except WorkflowError:
                continue
            result.append(
                dict(
                    id=row["id"],
                    revision=row["revision"],
                    state=row["state"],
                    own=row["owner_id"] == str(viewer.user_id),
                )
            )
        return result

    def tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            return self._tasks(c, viewer)

    def choices(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            Access(self.store, self._registry()).authorize(c, viewer, "economy")
            state = load_state(c, self.store.campaign_id)
            actor = self._actor(c, state, viewer)
            self._class_sources(c, state, actor.ref)
            available, blocked = [], []
            for frame in FRAME_TYPES:
                if official_frame(frame) == official_frame(actor.frame or ""):
                    continue
                try:
                    rules.destination(self._registry(), frame)
                    available.append(frame)
                except ValueError as error:
                    blocked.append(dict(frame=frame, reason=str(error)))
            return dict(
                frames=available,
                blocked=blocked,
                retained_rules=rules.retained_rules(
                    state, actor.ref, profiles(c, self.store.campaign_id), self._registry()
                ),
            )

    def _save(
        self,
        c: Connection,
        row: dict[str, Any],
        body: dict[str, Any],
        event: str,
        *,
        done: bool = False,
    ) -> None:
        c.execute(
            t.m3["m3_required_work"]
            .insert()
            .values(
                **{
                    k: v
                    for k, v in row.items()
                    if k not in ("revision", "state", "body_json", "event_id")
                },
                revision=row["revision"] + 1,
                state="resolved" if done else "pending",
                body_json=json.dumps(body, sort_keys=True),
                event_id=event,
            )
        )

    def create(self, viewer: GuildViewer, key: str, frame: str) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            actor = self._actor(c, state, viewer)
            self._class_sources(c, state, actor.ref)
            selected, _ = rules.destination(self._registry(), frame)
            if official_frame(actor.frame or "") == official_frame(selected):
                raise WorkflowError("Choose a different destination Frame.")
            if not rules.retained_rules(
                state, actor.ref, profiles(c, self.store.campaign_id), self._registry()
            ):
                raise WorkflowError(
                    "No current Frame rule has a complete supported retention runtime."
                )
            if any(
                x["owner_id"] == str(viewer.user_id) and x["state"] != "resolved"
                for x in self._rows(c)
            ):
                raise WorkflowError("Resume or cancel your original optional exchange plan first.")
            identity = str(uuid4())
            event = self.game.event(
                c, viewer.user_id, key, "m3.frame_swap_planned", plan_id=identity
            )
            related(
                c,
                self.store,
                dict(campaign_id=self.store.campaign_id, campaign_context=True),
                identity,
                viewer.user_id,
                viewer.user_id,
                KIND,
                dict(
                    actor=actor.ref.model_dump(mode="json"),
                    frame=selected,
                    old_frame=actor.frame_instance,
                    selection=None,
                    accepted=None,
                    immediate=False,
                    optional=True,
                ),
                event,
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.frame_swap_plan",
            dict(frame=frame),
            operation,
            authorize=lambda c: Access(self.store, self._registry()).authorize(
                c, viewer, "economy"
            ),
            auto_audit=False,
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row = self._row(c, viewer, identity)
            body = json.loads(row["body_json"])
            own = row["owner_id"] == str(viewer.user_id)
            if not own:
                selection = body["selection"]
                return dict(
                    id=identity,
                    revision=row["revision"],
                    state=row["state"],
                    own=False,
                    assignment=dict(
                        role=selection["court_role"],
                        buyer=body["actor"],
                        target=selection["court_target"],
                    ),
                    accepted=body.get("accepted") is not None,
                )
            state = load_state(c, self.store.campaign_id)
            actor = ActorRef.model_validate(body["actor"])
            current = resolve(
                state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            sheet = state.sheets[actor.entity]
            class_sources = self._class_sources(c, state, actor)
            catalog_available = True
            try:
                held_rules = rules.retained_rules(
                    state, actor, profiles(c, self.store.campaign_id), self._registry()
                )
            except (ValueError, WorkflowError):
                catalog_available, held_rules = False, ()
            return dict(
                id=identity,
                revision=row["revision"],
                state=row["state"],
                own=True,
                actor=body["actor"],
                frame=body["frame"],
                selection=body["selection"],
                accepted=body.get("accepted") is not None,
                expected=current.source_sha256,
                old_frame=body["old_frame"],
                current_frame=current.frame_instance,
                girl_cell=current.cell,
                strings=[x.model_dump(mode="json") for x in rules.bonded_refs(state, actor)],
                assets=[dict(id=x.id, name=x.name) for x in sheet.assets if x.family == "frame"],
                starting=list(CATALOG[official_frame(body["frame"])]["assets"]),
                rules=held_rules,
                class_sources=class_sources,
                rule_catalog_available=catalog_available,
                people=[
                    dict(
                        ref=ActorRef(
                            kind="pilot",
                            entity=str(uid),
                            incarnation=state.sheets[str(uid)].character_id,
                        ).model_dump(mode="json"),
                        label=state.sheets[str(uid)].callsign,
                    )
                    for uid in state.order
                    if uid != viewer.user_id and str(uid) in state.sheets
                ],
            )

    def change(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        *,
        selection: Selection | None = None,
        accept: bool = False,
        cancel: bool = False,
        purchase: bool = False,
        expected: str | None = None,
        delivered: bool = False,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store, self._registry()).authorize(
                c, viewer, "economy", director_response=accept
            )
            self._row(c, viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, viewer, identity)
            body = json.loads(row["body_json"])
            if row["state"] == "resolved" or row["revision"] != revision:
                raise WorkflowError("STALE_FRAME_SWAP: reopen your actual saved exchange.")
            if sum((selection is not None, accept, cancel, purchase)) != 1:
                raise WorkflowError("Choose one explicit owned exchange operation.")
            state = load_state(c, self.store.campaign_id)
            actor = ActorRef.model_validate(body["actor"])
            bindings = profiles(c, self.store.campaign_id)
            current = resolve(state, actor, bindings, require_current_profile=False)
            self._class_sources(c, state, actor)
            if current.frame_instance != body["old_frame"]:
                raise WorkflowError("This plan belongs to its exact original current Frame.")
            if not accept and str(viewer.user_id) != actor.entity:
                raise WorkflowError("Only the original buyer controls payment and choices.")
            event = str(uuid4())
            if selection is not None:
                if (
                    rules.validate(state, actor, bindings, self._registry(), selection)
                    != body["frame"]
                ):
                    raise WorkflowError("Keep the saved destination or start a new owned plan.")
                body.update(selection=selection.model_dump(mode="json"), accepted=None)
                kind = "configured"
            elif accept:
                chosen = Selection.model_validate_json(json.dumps(body["selection"]))
                if (
                    chosen.court_target is None
                    or chosen.court_target.entity != str(viewer.user_id)
                    or chosen.court_target == actor
                ):
                    raise WorkflowError(
                        "Only this exact original external Girl accepts her assignment."
                    )
                resolve(state, chosen.court_target, bindings, require_current_profile=False)
                body["accepted"] = dict(
                    actor=chosen.court_target.model_dump(mode="json"),
                    role=chosen.court_role,
                    source_event=event,
                )
                kind = "court_accepted"
            elif cancel:
                body["resolution"], kind = "owner_cancelled_unpaid_plan", "cancelled"
            else:
                from girlframe.engine.m3_physical import exchange_assigned_frame
                from girlframe.engine.m3_scene_requisitions import active
                from girlframe.services.m3_scene_requisitions import benefit, rows

                self.game.unpaused(c)
                self._safe(c, state, viewer.user_id)
                from girlframe.engine.m3_supply_drop import require_temporary_clear

                require_temporary_clear(state, actor)
                if not delivered or current.cell is None:
                    raise WorkflowError(
                        "Confirm actual delivery at your known unchanged body location."
                    )
                if any(
                    active(b) and actor in {x.actor for x in b.scene.roles}
                    for r in rows(c, self.store)
                    if (b := benefit(r)).scene
                ):
                    raise WorkflowError("End your actual protected scene before exchanging Frames.")
                chosen = Selection.model_validate_json(json.dumps(body["selection"]))
                accepted = body.get("accepted")
                if chosen.court_target is not None:
                    source = (
                        c.execute(
                            sa.select(t.events).where(
                                t.events.c.campaign_id == self.store.campaign_id,
                                t.events.c.id == accepted["source_event"]
                                if accepted
                                else sa.false(),
                            )
                        )
                        .mappings()
                        .first()
                    )
                    if (
                        source is None
                        or source["kind"] != "m3.frame_swap_court_accepted"
                        or source["actor_id"] != chosen.court_target.entity
                        or accepted["actor"] != chosen.court_target.model_dump(mode="json")
                        or accepted["role"] != chosen.court_role
                    ):
                        raise WorkflowError("Recover the exact original external Court acceptance.")
                from girlframe.engine.m3_clone_am import RULE as CLONE_RULE

                clone_before: GameState | None = None
                clone_paid = None
                if chosen.retained_rule == CLONE_RULE:
                    from girlframe.engine.m3_class_grafts import held as class_held
                    from girlframe.services.m3_clone_am import prepare_transfer

                    clone_paid = class_held(state, actor, CLONE_RULE)
                    if clone_paid is None:
                        raise WorkflowError("Recover the exact original retained Clone source.")
                    clone_before = prepare_transfer(self.game, c, state, clone_paid)
                original = PilotSheet.model_validate_json(
                    state.sheets[actor.entity].model_dump_json()
                )
                purchase_id = str(uuid4())
                state = rules.purchase(
                    state,
                    actor,
                    bindings,
                    expected or "",
                    self._registry(),
                    chosen,
                    purchase_id,
                    event,
                    row["id"],
                    court_accepted=body.get("accepted") is not None,
                )
                state = exchange_assigned_frame(
                    state, bindings, actor, original, current.cell, event, chosen.account
                )
                if clone_before is not None:
                    from girlframe.engine.m3_clone_residency import transfer

                    assert clone_paid is not None
                    swap = next(
                        item
                        for item in state.requisitions
                        if isinstance(item, SwapReceipt) and item.id == purchase_id
                    )
                    transfer(clone_before, state, clone_paid, swap)
                body.update(requisition=purchase_id, resolution="actual_paid_exchange_completed")
                kind = "purchased"
            metadata: dict[str, Any] = dict(plan_id=row["id"])
            if purchase:
                metadata.update(requisition_id=purchase_id, cost=4)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.frame_swap_" + kind,
                state if purchase else None,
                event_id=event,
                **metadata,
            )
            self._save(c, row, body, event, done=purchase or cancel)
            return dict(id=row["id"], paid=purchase, cost=4 if purchase else 0)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.frame_swap_change",
                dict(
                    id=identity,
                    revision=revision,
                    selection=selection.model_dump(mode="json") if selection else None,
                    accept=accept,
                    cancel=cancel,
                    purchase=purchase,
                    expected=expected,
                    delivered=delivered,
                ),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
