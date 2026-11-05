"""Paid off-duty scenes, source-bound qualification and enforced Privacy audiences."""

import json
from collections.abc import Callable
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_scene_requisitions as rules
from girlframe.engine.m2 import GameState, tier
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_career_state import CareerArchive
from girlframe.engine.m3_off_duty import Period
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import SceneReceipt
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_comforts import ComfortService
from girlframe.services.m3_frame_rewards import eligibility
from girlframe.services.m3_privileges import purchase_proof
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KIND = "scene_requisition"


def rows(c: Connection, store: OnboardingStore) -> list[dict[str, Any]]:
    work = t.m3["m3_required_work"]
    return list(
        {
            x["id"]: dict(x)
            for x in c.execute(
                sa.select(work)
                .where(
                    work.c.campaign_id == store.campaign_id,
                    work.c.kind == KIND,
                )
                .order_by(work.c.revision)
            ).mappings()
        }.values()
    )


def benefit(row: dict[str, Any]) -> rules.Benefit:
    saved = rules.Benefit.model_validate_json(json.dumps(json.loads(row["body_json"])["benefit"]))
    if (
        saved.actor.entity != row["owner_id"]
        or row["subject_id"] != row["owner_id"]
        or saved.period != row["off_duty_id"]
        or row["mission_id"] is not None
    ):
        raise WorkflowError("SOURCE_SCENE_REQUISITION: recover the original owned period benefit.")
    return saved


def privacy(
    c: Connection,
    store: OnboardingStore,
    scene_id: str,
    *,
    history: bool = False,
) -> rules.Benefit | None:
    found = [
        b
        for row in rows(c, store)
        if (b := benefit(row)).kind == "privacy"
        and (rules.active(b) or (history and b.scene is not None and b.scene.entered_event))
        and b.scene is not None
        and b.scene.id == scene_id
    ]
    if len(found) > 1:
        raise WorkflowError("Recover the conflicting original protected-room sources.")
    return found[0] if found else None


def guard(
    c: Connection,
    store: OnboardingStore,
    scene_id: str,
    actor: ActorRef,
    *,
    continuation: bool = False,
) -> None:
    room = privacy(c, store, scene_id, history=True)
    if room is not None and actor not in (room.actor, room.companion):
        raise WorkflowError(
            "PRIVACY_PROTECTED: no cameras, Handler, third actors or interruptions."
        )
    if (
        room
        and room.scene
        and (room.scene.closed_by is not None or room.scene.career_end is not None)
        and not continuation
    ):
        raise WorkflowError("PRIVACY_CLOSED: start a new actual scene for later public play.")


def audience(c: Connection, store: OnboardingStore, scene_id: str) -> tuple[int, ...] | None:
    room = privacy(c, store, scene_id, history=True)
    if room is None:
        return None
    assert room.companion is not None
    return int(room.actor.entity), int(room.companion.entity)


def end_career_rooms(c: Connection, store: OnboardingStore, archive: CareerArchive) -> None:
    """A real original participant's ending closes protection, never inventing their consent."""
    state = load_state(c, store.campaign_id)
    if archive not in state.career_archives:
        raise WorkflowError("SOURCE_CAREER_MISSING: recover the actual original ending.")
    for row in rows(c, store):
        saved = benefit(row)
        if not rules.active(saved):
            continue
        assert saved.scene is not None
        affected = (
            (saved.actor, saved.companion)
            if saved.kind == "privacy"
            else (saved.actor, saved.scene.supervisor)
        )
        if archive.actor not in affected:
            continue
        scene = saved.scene.model_copy(
            update=dict(
                career_end=archive.id,
                ended_actor=archive.actor,
                close_account="This original participant's Pilot career ended. "
                + (
                    "The visit was interrupted; no physical return is inferred."
                    if saved.kind == "visiting_home"
                    else ""
                ),
            )
        )
        ended = rules.Benefit.model_validate_json(
            saved.model_copy(update={"scene": scene}).model_dump_json()
        )
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
                state="resolved",
                event_id=archive.source_event,
                body_json=json.dumps(
                    json.loads(row["body_json"])
                    | dict(
                        benefit=ended.model_dump(mode="json"),
                        immediate=False,
                        resolution="original_scene_participant_career_ended",
                    ),
                    sort_keys=True,
                ),
            )
        )
        if saved.kind != "privacy" or archive.ending not in ("death", "execution"):
            continue
        assert saved.companion is not None
        survivor = saved.companion if archive.actor == saved.actor else saved.actor
        if state.handler is None:
            raise WorkflowError("The actual Privacy death needs its current Handler's consequence.")
        current = state.sheets.get(survivor.entity)
        surviving = current is not None and current.character_id == survivor.incarnation
        related(
            c,
            store,
            row,
            str(uuid5(NAMESPACE_URL, "girlframe:privacy-trouble:" + archive.id + ":" + row["id"])),
            state.handler,
            int(survivor.entity) if surviving else state.handler,
            "privacy_trouble",
            dict(
                source_pdf=16,
                immediate=True,
                reason="privacy_death",
                source_work=row["id"],
                source_actor=survivor.model_dump(mode="json") if surviving else None,
                ended_actor=archive.actor.model_dump(mode="json"),
                source_career=archive.id,
                handler=state.handler,
            ),
            archive.source_event,
        )


def _activation(
    c: Connection, store: OnboardingStore, period: Period
) -> tuple[GameState, str] | None:
    history = t.m3["m3_off_duty_history"]
    for body, source in c.execute(
        sa.select(history.c.body_json, history.c.event_id)
        .where(
            history.c.campaign_id == store.campaign_id,
            history.c.id == period.id,
        )
        .order_by(history.c.revision)
    ):
        saved = Period.model_validate_json(body)
        if saved.phase != "active":
            continue
        facts = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == store.campaign_id,
                t.m2["m2_state_history"].c.event_id == source,
            )
        )
        event = c.scalar(
            sa.select(t.events.c.kind).where(
                t.events.c.campaign_id == store.campaign_id,
                t.events.c.id == source,
            )
        )
        if facts is None or event != "m3.off_duty_activated":
            raise WorkflowError("SOURCE_OFF_DUTY_MISSING: recover the actual period activation.")
        return GameState.model_validate_json(facts), source
    return None


def synchronize(c: Connection, store: OnboardingStore, period: Period, event: str) -> None:
    if period.phase != "active":
        return
    state = load_state(c, store.campaign_id)
    purchases = [x for x in state.requisitions if isinstance(x, SceneReceipt)]
    if not purchases:
        return
    existing = {benefit(row).purchase for row in rows(c, store)}
    candidates = [
        x
        for x in purchases
        if x.id not in existing
        and x.actor.entity in state.sheets
        and x.actor.entity not in period.ended_characters
        and state.sheets[x.actor.entity].character_id in (None, x.actor.incarnation)
        and period.character_ids.get(x.actor.entity) == x.actor.incarnation
        and not suspended(state, x.id)
    ]
    if not candidates:
        return
    activation = _activation(c, store, period)
    work = t.m3["m3_required_work"]
    for purchase in candidates:
        uid = purchase.actor.entity
        sheet = state.sheets.get(uid)
        if (
            sheet is None
            or (sheet.character_id is not None and sheet.character_id != purchase.actor.incarnation)
            or uid in period.ended_characters
        ):
            continue
        if period.character_ids.get(uid) != purchase.actor.incarnation or suspended(
            state, purchase.id
        ):
            continue
        action, total = None, None
        source: str | None
        if purchase.kind == "privacy":
            if (
                activation is None
                or purchase.companion is None
                or (
                    period.character_ids.get(purchase.companion.entity)
                    != purchase.companion.incarnation
                )
            ):
                continue
            facts, source = activation
        else:
            progress = period.progress.get(uid)
            if (
                progress is None
                or progress.roll is None
                or progress.roll.stage != "choices"
                or progress.action_id is None
                or progress.roll.source != "status"
            ):
                continue
            actual = (
                c.execute(
                    sa.select(t.m2["m2_actions"]).where(
                        t.m2["m2_actions"].c.campaign_id == store.campaign_id,
                        t.m2["m2_actions"].c.id == progress.action_id,
                    )
                )
                .mappings()
                .one()
            )
            data = json.loads(actual["body_json"])
            receipt = c.scalar(
                sa.select(t.m2["m2_receipts"].c.body_json).where(
                    t.m2["m2_receipts"].c.campaign_id == store.campaign_id,
                    t.m2["m2_receipts"].c.action_id == progress.action_id,
                )
            )
            raw = json.loads(receipt) if receipt else None
            total = raw["pre_total"] + sum(x["amount"] for x in data["modifiers"]) if raw else None
            if (
                raw is None
                or actual["state"] != "complete"
                or data.get("play") != "go_off_duty"
                or data.get("receipt") != raw
                or not data.get("m3_finished")
                or progress.roll.total != total
                or data["result"].get("total") != total
                or data["result"].get("tier") != tier(total)
            ):
                raise WorkflowError(
                    "SOURCE_RECEIPT_MISSING: recover the actual final ordinary roll."
                )
            if total < 8:
                continue
            facts, source = eligibility(c, store, state, period, int(uid))
            if source is None:
                raise WorkflowError("Recover the original paid pre-roll source.")
            action = progress.action_id
        assert source is not None
        if suspended(facts, purchase.id) or not any(x == purchase for x in facts.requisitions):
            continue
        purchase_proof(c, store, purchase)
        saved = rules.Benefit(
            purchase=purchase.id,
            kind=purchase.kind,
            actor=purchase.actor,
            companion=purchase.companion,
            period=period.id,
            source_event=source,
            qualification_event=event,
            action=action,
            total=total,
        )
        identity = str(uuid5(NAMESPACE_URL, "girlframe:scene-requisition:" + purchase.id))
        if c.scalar(
            sa.select(work.c.id)
            .where(work.c.campaign_id == store.campaign_id, work.c.id == identity)
            .limit(1)
        ):
            continue
        related(
            c,
            store,
            dict(campaign_id=store.campaign_id, off_duty_id=period.id),
            identity,
            int(uid),
            int(uid),
            KIND,
            dict(source_pdf=16, immediate=False, benefit=saved.model_dump(mode="json")),
            event,
        )


class SceneRequisitionService(ComfortService):
    """Existing purchase/idle/cast infrastructure with separate scene-specific effects."""

    def scene_purchase_view(self, viewer: GuildViewer) -> dict[str, Any]:
        result = self.view(viewer)
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            result["companions"] = [
                dict(
                    ref=ActorRef(
                        kind="pilot",
                        entity=uid,
                        incarnation=self.game.character_binding(
                            c,
                            state,
                            int(uid),
                            require_current_profile=False,
                        ),
                    ).model_dump(mode="json"),
                    label=sheet.callsign,
                )
                for uid, sheet in state.sheets.items()
                if uid != str(viewer.user_id) and HandlerService(self.store)._member(c, int(uid))
            ]
        return result

    def scene_receipts(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            result = []
            for receipt in load_state(c, self.store.campaign_id).requisitions:
                if isinstance(receipt, SceneReceipt) and receipt.actor.entity == str(
                    viewer.user_id
                ):
                    purchase_proof(c, self.store, receipt)
                    result.append(receipt.model_dump(mode="json"))
            return result

    def buy_scene(
        self,
        viewer: GuildViewer,
        key: str,
        actor: ActorRef,
        expected: str,
        kind: rules.Kind,
        account: str,
        companion: ActorRef | None = None,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "economy")
            if actor.kind != "pilot" or actor.entity != str(viewer.user_id):
                raise WorkflowError("Only the original Girl can purchase this Requisition.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            self._safe(c, state, viewer.user_id)
            identity, source = str(uuid4()), str(uuid4())
            updated = rules.purchase(
                state,
                actor,
                profiles(c, self.store.campaign_id),
                expected,
                kind,
                companion,
                account,
                identity,
                source,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3." + kind + "_purchased",
                updated,
                event_id=source,
                requisition_id=identity,
                cost=rules.PRICES[kind],
            )
            return dict(id=identity, kind=kind, cost=rules.PRICES[kind])

        try:
            return self.store._write(
                viewer,
                key,
                "m3.scene_requisition_purchase",
                dict(
                    actor=actor.model_dump(mode="json"),
                    expected=expected,
                    kind=kind,
                    account=account,
                    companion=companion.model_dump(mode="json") if companion else None,
                ),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _scene_row(self, c: Connection, identity: str) -> dict[str, Any]:
        row = next((x for x in rows(c, self.store) if x["id"] == identity), None)
        if row is None:
            raise WorkflowError("This original scene Requisition is unavailable.")
        return row

    def _party(self, viewer: GuildViewer, saved: rules.Benefit) -> None:
        humans = {int(saved.actor.entity)}
        if saved.companion is not None:
            humans.add(int(saved.companion.entity))
        if saved.scene:
            humans.update(x.controller for x in saved.scene.roles)
        if viewer.user_id not in humans:
            raise WorkflowError("This paid scene belongs to its actual participants.")

    def scene_tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            return self._scene_tasks(c, viewer)

    def _scene_tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        result = []
        for row in rows(c, self.store):
            saved = benefit(row)
            try:
                self._party(viewer, saved)
            except WorkflowError:
                continue
            result.append(
                dict(
                    id=row["id"],
                    revision=row["revision"],
                    kind=saved.kind,
                    state=row["state"],
                    active=rules.active(saved),
                    own=viewer.user_id == int(saved.actor.entity),
                    buyer=int(saved.actor.entity),
                )
            )
        return result

    def scene_get(
        self, viewer: GuildViewer, identity: str, channel: int | None = None
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            row = self._scene_row(c, identity)
            saved = benefit(row)
            self._party(viewer, saved)
            state = load_state(c, self.store.campaign_id)
            result: dict[str, Any] = dict(
                id=identity,
                revision=row["revision"],
                kind=saved.kind,
                state=row["state"],
                own=viewer.user_id == int(saved.actor.entity),
                active=rules.active(saved),
                benefit=saved.model_dump(mode="json"),
                can_attest=bool(
                    saved.scene
                    and viewer.user_id not in saved.scene.present
                    and saved.scene.closed_by is None
                    and saved.scene.career_end is None
                ),
                roles=[],
                cast_revision=None,
            )
            scheduling = json.loads(row["body_json"])
            result.update(
                resolution=scheduling.get("resolution"),
                deferred=scheduling.get("deferred", False),
                transfer_work=scheduling.get("transfer_work"),
            )
            if channel is not None and result["own"] and saved.scene is None:
                cast, _ = self.casts._current(c, state, channel)
                result["cast_revision"] = cast.revision
                result["roles"] = [
                    dict(
                        ref=x.actor.model_dump(mode="json"),
                        token=x.actor.token,
                        can_supervise=rules.supervisor_eligible(state, x.actor),
                        label=resolve(
                            state,
                            x.actor,
                            profiles(c, self.store.campaign_id),
                            require_current_profile=False,
                        ).label,
                    )
                    for x in cast.roles
                ]
            return result

    def _scene_current(
        self,
        c: Connection,
        saved: rules.Benefit,
        *,
        require_companion: bool = True,
    ) -> GameState:
        state = load_state(c, self.store.campaign_id)
        period = self.periods._get(c, saved.period)
        if (
            period.phase != "active"
            or period.character_ids.get(saved.actor.entity) != saved.actor.incarnation
        ):
            raise WorkflowError("Recover the original actual active Off-Duty period.")
        resolve(
            state, saved.actor, profiles(c, self.store.campaign_id), require_current_profile=False
        )
        if require_companion and saved.companion is not None:
            resolve(
                state,
                saved.companion,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
        receipt = next((x for x in state.requisitions if x.id == saved.purchase), None)
        if (
            receipt is None
            or not isinstance(receipt, SceneReceipt)
            or suspended(state, receipt.id)
            or receipt.actor != saved.actor
            or receipt.kind != saved.kind
            or receipt.companion != saved.companion
        ):
            raise WorkflowError("Recover the original active paid Requisition.")
        purchase_proof(c, self.store, receipt)
        return state

    def _scene_idle(self, c: Connection, channel: int | None = None) -> None:
        if self.game.pending_actions(c):
            raise WorkflowError("Finish pending Plays before changing this scene.")
        locks = t.m2["m2_locks"]
        query = sa.select(locks.c.channel_id).where(
            locks.c.campaign_id == self.store.campaign_id, locks.c.state != "released"
        )
        if channel is not None:
            query = query.where(locks.c.channel_id == str(channel))
        if c.scalar(query.limit(1)):
            raise WorkflowError("Restore actual chat permissions before changing this scene.")

    def _scene_change(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        operation: str,
        payload: dict[str, Any],
        change: Callable[
            [Connection, GameState, rules.Benefit, str], tuple[GameState | None, rules.Benefit]
        ],
        *,
        ooc: bool = False,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "economy", director_response=ooc)
            self._party(viewer, benefit(self._scene_row(c, identity)))

        def apply(c: Connection) -> dict[str, Any]:
            row = self._scene_row(c, identity)
            saved = benefit(row)
            if row["revision"] != revision or row["state"] == "resolved":
                raise WorkflowError("STALE_SCENE_REQUISITION: reopen your actual saved scene.")
            if not ooc:
                self.game.unpaused(c)
                state = self._scene_current(
                    c, saved, require_companion=operation not in ("declined", "reset")
                )
            else:
                state = load_state(c, self.store.campaign_id)
            source = str(uuid4())
            updated_state, updated = change(c, state, saved, source)
            if operation in ("entered", "declined"):
                updated_state = updated_state or state
                updated_state.facts.append(
                    dict(
                        kind="scene_requisition_consumed",
                        purchase=saved.purchase,
                        actor=saved.actor.model_dump_json(),
                        outcome=operation,
                        source_event=source,
                    )
                )
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.scene_requisition_" + operation,
                updated_state,
                event_id=source,
                benefit_id=identity,
            )
            done = updated.declined or bool(
                updated.scene
                and (updated.scene.closed_by is not None or updated.scene.career_end is not None)
            )
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("revision", "state", "body_json", "event_id")
                    },
                    revision=revision + 1,
                    state="resolved" if done else "pending",
                    event_id=event,
                    body_json=json.dumps(
                        json.loads(row["body_json"])
                        | dict(
                            benefit=updated.model_dump(mode="json"),
                            immediate=updated.scene is not None and not done,
                        ),
                        sort_keys=True,
                    ),
                )
            )
            return dict(id=identity, revision=revision + 1, active=rules.active(updated), done=done)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.scene_requisition_" + operation,
                dict(id=identity, revision=revision, **payload),
                apply,
                authorize=access,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def propose_scene(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        channel: int,
        cast_revision: int,
        account: str,
        *,
        supervisor: ActorRef | None = None,
        home: str = "",
    ) -> dict[str, Any]:
        def change(
            c: Connection, state: GameState, saved: rules.Benefit, source: str
        ) -> tuple[GameState | None, rules.Benefit]:
            self._scene_idle(c, channel)
            cast, _ = self.casts._current(c, state, channel)
            if cast.revision != cast_revision:
                raise WorkflowError("STALE_CAST: review the actual scene roles again.")
            updated = rules.propose(
                saved,
                state,
                profiles(c, self.store.campaign_id),
                cast,
                account,
                viewer.user_id,
                supervisor=supervisor,
                home=home,
            )
            return None, updated

        return self._scene_change(
            viewer,
            key,
            identity,
            revision,
            "proposed",
            dict(
                channel=channel,
                cast_revision=cast_revision,
                account=account,
                home=home,
                supervisor=supervisor.model_dump(mode="json") if supervisor else None,
            ),
            change,
        )

    def attest_scene(
        self, viewer: GuildViewer, key: str, identity: str, revision: int
    ) -> dict[str, Any]:
        def change(
            c: Connection, state: GameState, saved: rules.Benefit, source: str
        ) -> tuple[GameState | None, rules.Benefit]:
            return None, rules.attest(saved, viewer.user_id)

        return self._scene_change(viewer, key, identity, revision, "attested", {}, change, ooc=True)

    def enter_scene(
        self, viewer: GuildViewer, key: str, identity: str, revision: int
    ) -> dict[str, Any]:
        def change(
            c: Connection, state: GameState, saved: rules.Benefit, source: str
        ) -> tuple[GameState | None, rules.Benefit]:
            scene = saved.scene
            if scene is None:
                raise WorkflowError("Set the actual scene and collect owned participation first.")
            self._scene_idle(c, scene.channel)
            cast, _ = self.casts._current(c, state, scene.channel)
            if cast.revision != scene.cast_revision or cast.roles != scene.roles:
                raise WorkflowError("STALE_CAST: recover the changed actual scene before entering.")
            for role in scene.roles:
                actual = resolve(
                    state,
                    role.actor,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                if actual.controller != role.controller or not actual.alive:
                    raise WorkflowError(
                        "STALE_CAST: recover each actual role's changed controller."
                    )
            if privacy(c, self.store, scene.id) is not None:
                raise WorkflowError("This actual room already has its own Privacy source.")
            bindings = profiles(c, self.store.campaign_id)
            origin = None
            if saved.kind == "privacy":
                from girlframe.engine.m3_physical import (
                    cockpit_exit,
                    occupied_frame,
                    original_placement,
                )

                assert saved.companion is not None
                for actor in (saved.actor, saved.companion):
                    state, placed = original_placement(
                        state,
                        bindings,
                        actor,
                        source,
                        scene.account,
                        prior_event=saved.source_event,
                    )
                    if occupied_frame(placed) is not None:
                        state = cockpit_exit(state, bindings, actor, source, scene.account)
                actors = [
                    resolve(state, actor, bindings, require_current_profile=False)
                    for actor in (saved.actor, saved.companion)
                ]
                if (
                    actors[0].cell is not None
                    and actors[1].cell is not None
                    and actors[0].cell != actors[1].cell
                ):
                    raise WorkflowError(
                        "The actual Girls must reach the same place; Privacy grants no teleport."
                    )
            else:
                from girlframe.engine.m3_physical import depart_supervised, original_placement

                assert scene.supervisor is not None
                state, initial = original_placement(
                    state,
                    bindings,
                    saved.actor,
                    source,
                    scene.account,
                    prior_event=saved.source_event,
                )
                origin = initial.model_dump_json()
                state = depart_supervised(
                    state,
                    bindings,
                    saved.actor,
                    scene.supervisor,
                    source,
                    scene.account,
                    prior_event=saved.source_event,
                )
            return state, rules.enter(saved, viewer.user_id, source, origin)

        return self._scene_change(viewer, key, identity, revision, "entered", {}, change)

    def close_scene(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        account: str,
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            saved = benefit(self._scene_row(c, identity))
            ooc = saved.kind == "privacy"

        def change(
            c: Connection, state: GameState, saved: rules.Benefit, source: str
        ) -> tuple[GameState | None, rules.Benefit]:
            updated = rules.close(saved, viewer.user_id, account)
            if saved.kind == "privacy":
                return None, updated
            self._scene_idle(c)
            assert saved.scene is not None and saved.scene.supervisor is not None
            from girlframe.engine.m3_physical import return_from_visit
            from girlframe.engine.m3_physical_state import Placement

            state = return_from_visit(
                state,
                profiles(c, self.store.campaign_id),
                saved.actor,
                Placement.model_validate_json(saved.scene.physical_origin or "{}"),
                saved.scene.supervisor,
                source,
                account,
            )
            return state, updated

        return self._scene_change(
            viewer, key, identity, revision, "closed", dict(account=account), change, ooc=ooc
        )

    def reset_scene(
        self, viewer: GuildViewer, key: str, identity: str, revision: int
    ) -> dict[str, Any]:
        def change(
            c: Connection, state: GameState, saved: rules.Benefit, source: str
        ) -> tuple[GameState | None, rules.Benefit]:
            return None, rules.reset(saved, viewer.user_id)

        return self._scene_change(viewer, key, identity, revision, "reset", {}, change)

    def decline_scene(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        account: str,
    ) -> dict[str, Any]:
        def change(
            c: Connection, state: GameState, saved: rules.Benefit, source: str
        ) -> tuple[GameState | None, rules.Benefit]:
            return None, rules.decline(saved, viewer.user_id, account)

        return self._scene_change(
            viewer, key, identity, revision, "declined", dict(account=account), change
        )
