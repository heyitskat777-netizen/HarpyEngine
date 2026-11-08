"""Paid delayed benefits bind actual final rolls and separately owned scene attendance."""

import json
from collections.abc import Callable, Sequence
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_cast
from girlframe.engine import m3_comforts as rules
from girlframe.engine.m2 import GameState, tier
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_off_duty import Period
from girlframe.engine.m3_requisition_state import ComfortBenefit, ComfortReceipt, GirlAsset
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import ActorService, profiles
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_frame_rewards import eligibility
from girlframe.services.m3_intracadre_marriage import prepare_payment
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KIND = "creature_comforts"


def synchronize(c: Connection, store: OnboardingStore, period: Period, event: str) -> None:
    state = load_state(c, store.campaign_id)
    if not any(x.kind == KIND for x in state.requisitions):
        return
    work = t.m3["m3_required_work"]
    for uid, progress in period.progress.items():
        if uid in period.ended_characters or uid not in state.sheets:
            continue
        if progress.roll is None or progress.roll.stage != "choices" or progress.action_id is None:
            continue
        actions = t.m2["m2_actions"]
        saved = c.execute(
            sa.select(actions.c.state, actions.c.body_json).where(
                actions.c.campaign_id == store.campaign_id,
                actions.c.id == progress.action_id,
            )
        ).one()
        data = json.loads(saved.body_json)
        if saved.state != "complete" or data.get("play") != "go_off_duty":
            continue
        receipt_body = c.scalar(
            sa.select(t.m2["m2_receipts"].c.body_json).where(
                t.m2["m2_receipts"].c.campaign_id == store.campaign_id,
                t.m2["m2_receipts"].c.action_id == progress.action_id,
            )
        )
        actual = json.loads(receipt_body) if receipt_body else None
        total = (
            actual["pre_total"] + sum(x["amount"] for x in data["modifiers"]) if actual else None
        )
        if (
            actual is None
            or data.get("receipt") != actual
            or not data.get("m3_finished")
            or progress.roll.total != total
            or data["result"].get("total") != total
            or data["result"].get("tier") != tier(total)
        ):
            raise WorkflowError("SOURCE_RECEIPT_MISSING: recover the actual final Off-Duty roll.")
        facts, raw_event = eligibility(c, store, state, period, int(uid))
        if raw_event is None:
            raise WorkflowError("Recover the original receipt source before delayed benefits.")
        actor = ActorRef(kind="pilot", entity=uid, incarnation=period.character_ids[uid])
        for purchase in facts.requisitions:
            if purchase.kind != "creature_comforts":
                continue
            from girlframe.engine.m3_privileges import suspended

            if suspended(facts, purchase.id) or suspended(state, purchase.id):
                continue
            identity = str(uuid5(NAMESPACE_URL, "girlframe:creature-comforts:" + purchase.id))
            if c.scalar(
                sa.select(work.c.id)
                .where(work.c.campaign_id == store.campaign_id, work.c.id == identity)
                .limit(1)
            ):
                continue
            benefit = rules.qualify(
                purchase,
                actor,
                period.id,
                progress.action_id,
                data["play"],
                total,
                raw_event,
                event,
            )
            if benefit is None:
                continue
            paid = (
                c.execute(
                    sa.select(t.events.c.kind, t.events.c.payload_json, t.events.c.actor_id).where(
                        t.events.c.campaign_id == store.campaign_id,
                        t.events.c.id == purchase.source_event,
                    )
                )
                .mappings()
                .first()
            )
            if (
                paid is None
                or paid["kind"] != "m3.creature_comforts_purchased"
                or paid["actor_id"] != uid
                or json.loads(paid["payload_json"]).get("cost") != purchase.price
                or json.loads(paid["payload_json"]).get("requisition_id") != purchase.id
            ):
                raise WorkflowError(
                    "SOURCE_PURCHASE_MISSING: recover this benefit's actual paid source."
                )
            related(
                c,
                store,
                dict(campaign_id=store.campaign_id, mission_id=None, off_duty_id=period.id),
                identity,
                int(uid),
                int(uid),
                KIND,
                dict(source_pdf=16, immediate=False, benefit=benefit.model_dump(mode="json")),
                event,
            )


class ComfortService(RequisitionService):
    def __init__(self, game: GameService):
        super().__init__(game)
        self.periods = OffDutyService(MissionService(self.store))
        self.actors = ActorService(self.periods.missions)
        self.casts = CastService(self.actors)

    def _row(self, c: Connection, identity: str) -> dict[str, Any]:
        work = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(work)
                .where(
                    work.c.campaign_id == self.store.campaign_id,
                    work.c.id == identity,
                    work.c.kind == KIND,
                )
                .order_by(work.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowError("This saved Creature Comforts opportunity is unavailable.")
        return dict(row)

    def _benefit(self, row: dict[str, Any]) -> ComfortBenefit:
        try:
            benefit = ComfortBenefit.model_validate_json(
                json.dumps(json.loads(row["body_json"])["benefit"])
            )
            if (
                benefit.actor.entity != row["owner_id"]
                or row["subject_id"] != row["owner_id"]
                or benefit.period != row["off_duty_id"]
                or row["mission_id"] is not None
            ):
                raise ValueError("Recover the actual original benefit ownership")
            return benefit
        except (ValueError, KeyError):
            raise WorkflowError("This saved benefit needs source recovery.") from None

    def _visible(
        self, c: Connection, viewer: GuildViewer, row: dict[str, Any], benefit: ComfortBenefit
    ) -> None:
        self.game.authorize(c, viewer, game=False)
        humans = {x.controller for x in benefit.scene.roles} if benefit.scene else set()
        if viewer.user_id != int(row["owner_id"]) and viewer.user_id not in humans:
            raise WorkflowError("This benefit and scene belong to other participants.")

    def _current(self, c: Connection, benefit: ComfortBenefit) -> GameState:
        period = self.periods._get(c, benefit.period)
        state = load_state(c, self.store.campaign_id)
        if (
            period.phase != "active"
            or period.character_ids.get(benefit.actor.entity) != benefit.actor.incarnation
        ):
            raise WorkflowError("Recover the actual original active period and character first.")
        resolve(
            state, benefit.actor, profiles(c, self.store.campaign_id), require_current_profile=False
        )
        from girlframe.engine.m3_privileges import suspended

        if suspended(state, benefit.purchase):
            raise WorkflowError("REVOKED_PRIVILEGE: restore the original Requisition first.")
        return state

    def _idle(self, c: Connection, state: GameState, owner: int) -> None:
        locks = t.m2["m2_locks"]
        if self.game.pending_actions(c) or c.scalar(
            sa.select(locks.c.channel_id)
            .where(
                locks.c.campaign_id == self.store.campaign_id,
                locks.c.state != "released",
            )
            .limit(1)
        ):
            raise WorkflowError("Finish pending Plays and restore chat before this benefit.")
        work = t.m3["m3_required_work"]
        latest = {
            x["id"]: x
            for x in c.execute(
                sa.select(work)
                .where(
                    work.c.campaign_id == self.store.campaign_id,
                    work.c.subject_id == str(owner),
                )
                .order_by(work.c.revision)
            ).mappings()
        }
        if any(
            x["state"] != "resolved"
            and x["kind"] != KIND
            and json.loads(x["body_json"]).get("immediate")
            for x in latest.values()
        ):
            raise WorkflowError("Resolve the other actual immediate sheet consequence first.")
        if any(
            x.owner == owner
            and x.state == "pending"
            and x.kind
            in (
                "defeat",
                "helpless",
                "girl_void_threshold",
                "frame_void_threshold",
                "mockingbird_resist",
            )
            for x in state.obligations
        ):
            raise WorkflowError(
                "Resolve the actual compulsory sheet consequence before this benefit."
            )

    def buy_comforts(
        self, viewer: GuildViewer, key: str, actor: ActorRef, expected: str, account: str
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "economy")
            if actor.kind != "pilot" or actor.entity != str(viewer.user_id):
                raise WorkflowError("Purchase only for your own actual Girl.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            self._safe(c, state, viewer.user_id)
            identity, source = str(uuid4()), str(uuid4())
            prepare_payment(self.game, c, state, viewer, actor, "creature_comforts", 1)
            state = rules.purchase(
                state,
                actor,
                profiles(c, self.store.campaign_id),
                expected,
                identity,
                source,
                account,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.creature_comforts_purchased",
                state,
                event_id=source,
                requisition_id=identity,
                cost=1,
            )
            return {"id": identity, "permissions": state.sheets[actor.entity].permissions}

        try:
            return self.store._write(
                viewer,
                key,
                "m3.creature_comforts_purchased",
                dict(actor=actor.model_dump(mode="json"), expected=expected, account=account),
                operation,
                auto_audit=False,
                authorize=access,
            )
        except ValidationError:
            raise WorkflowError("Review the actual owned Creature Comforts request.") from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def list(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            work = t.m3["m3_required_work"]
            latest = {
                x["id"]: dict(x)
                for x in c.execute(
                    sa.select(work)
                    .where(
                        work.c.campaign_id == self.store.campaign_id,
                        work.c.kind == KIND,
                    )
                    .order_by(work.c.revision)
                ).mappings()
            }
            result = []
            for row in latest.values():
                benefit = self._benefit(row)
                humans = {x.controller for x in benefit.scene.roles} if benefit.scene else set()
                if viewer.user_id == int(row["owner_id"]) or viewer.user_id in humans:
                    result.append(
                        dict(
                            id=row["id"],
                            revision=row["revision"],
                            state=row["state"],
                            own=viewer.user_id == int(row["owner_id"]),
                        )
                    )
            return result

    def _paid_source(self, c: Connection, viewer: GuildViewer, purchase: ComfortReceipt) -> None:
        from girlframe.services.m3_privileges import purchase_proof

        purchase_proof(c, self.store, purchase)
        source = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == purchase.source_event,
                )
            )
            .mappings()
            .first()
        )
        history = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == purchase.source_event,
            )
        )
        try:
            original = GameState.model_validate_json(history) if history else None
            metadata = json.loads(source["payload_json"]) if source else {}
        except ValueError:
            raise WorkflowError(
                "SOURCE_PURCHASE_MISSING: recover the actual paid request."
            ) from None
        saved = (
            next((x for x in original.requisitions if x.id == purchase.id), None)
            if original
            else None
        )
        if (
            purchase.actor.entity != str(viewer.user_id)
            or source is None
            or source["actor_id"] != str(viewer.user_id)
            or source["kind"] != "m3.creature_comforts_purchased"
            or metadata.get("cost") != purchase.price
            or metadata.get("requisition_id") != purchase.id
            or saved != purchase
        ):
            raise WorkflowError("SOURCE_PURCHASE_MISSING: recover the actual paid request.")

    def paid_receipt(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        receipt = next((x for x in self.receipts(viewer) if x["id"] == identity), None)
        if receipt is None:
            raise WorkflowError(
                "This paid request belongs to its original owner or is unavailable."
            )
        return receipt

    def receipts(self, viewer: GuildViewer) -> Sequence[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            result = []
            for purchase in state.requisitions:
                if purchase.kind != "creature_comforts" or purchase.actor.entity != str(
                    viewer.user_id
                ):
                    continue
                self._paid_source(c, viewer, purchase)
                identity = str(uuid5(NAMESPACE_URL, "girlframe:creature-comforts:" + purchase.id))
                work = t.m3["m3_required_work"]
                status = c.scalar(
                    sa.select(work.c.state)
                    .where(
                        work.c.campaign_id == self.store.campaign_id,
                        work.c.id == identity,
                    )
                    .order_by(work.c.revision.desc())
                    .limit(1)
                )
                result.append(
                    dict(
                        id=purchase.id,
                        account=purchase.account,
                        price=purchase.price,
                        state=status or "waiting_for_roll",
                        benefit_id=identity if status else None,
                    )
                )
            return result

    def get(self, viewer: GuildViewer, identity: str, channel: int | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row = self._row(c, identity)
            benefit = self._benefit(row)
            self._visible(c, viewer, row, benefit)
            owner = viewer.user_id == int(row["owner_id"])
            scene = benefit.scene
            result = dict(
                id=identity,
                revision=row["revision"],
                state=row["state"],
                own=owner,
                scene=dict(
                    summary=scene.summary,
                    location=scene.location,
                    own_roles=[
                        x.actor.model_dump(mode="json")
                        for x in scene.roles
                        if x.controller == viewer.user_id
                    ],
                    own_attested=viewer.user_id in scene.acknowledgements,
                    human_count=len({x.controller for x in scene.roles}),
                    awaiting=len({x.controller for x in scene.roles} - set(scene.acknowledgements)),
                )
                if scene
                else None,
                ready=rules.ready(benefit),
                taken=benefit.taken,
                resolution=json.loads(row["body_json"]).get("resolution"),
                deferred=json.loads(row["body_json"]).get("deferred", False),
                transfer_work=json.loads(row["body_json"]).get("transfer_work"),
            )
            if owner:
                result.update(
                    total=benefit.total,
                    asset_id=benefit.asset_id,
                    asset_name=benefit.asset_name,
                    asset_description=benefit.asset_description,
                    account=benefit.account,
                )
            if owner and row["state"] == "resolved":
                return result
            if owner:
                state = self._current(c, benefit)
                actor = resolve(
                    state,
                    benefit.actor,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                result.update(
                    source_sha256=actor.source_sha256,
                    girl_assets=[
                        x.model_dump(mode="json") for x in actor.assets if x.family == "girl"
                    ],
                )
                if channel is not None and benefit.scene is None and row["state"] != "resolved":
                    cast, legacy = self.casts._current(c, state, channel)
                    known = self.actors.known(viewer, benefit.actor, require_current_profile=False)
                    refs = {ActorRef.model_validate(x["ref"]) for x in known["actors"]}
                    available = []
                    for role in cast.roles:
                        if role.actor not in refs and role.actor.kind != "handler":
                            continue
                        actual = resolve(
                            state,
                            role.actor,
                            profiles(c, self.store.campaign_id),
                            require_current_profile=False,
                        )
                        m3_cast.validate_role(cast, actual)
                        available.append(
                            dict(
                                ref=role.actor.model_dump(mode="json"),
                                token=role.actor.token,
                                label=actual.label,
                            )
                        )
                    result.update(
                        cast_revision=cast.revision,
                        roles=available,
                        locations=[
                            dict(id=x.id, name=x.name)
                            for x in state.world.locations
                            if x.operational
                        ]
                        if state.world
                        else [],
                    )
            return result

    def _change(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        kind: str,
        payload: dict[str, Any],
        change: Callable[
            [Connection, GameState, ComfortBenefit], tuple[GameState | None, ComfortBenefit]
        ],
        *,
        attendance: bool = False,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "economy", director_response=attendance)
            row = self._row(c, identity)
            benefit = self._benefit(row)
            self._visible(c, viewer, row, benefit)
            if not attendance and viewer.user_id != int(row["owner_id"]):
                raise WorkflowError("Only the purchasing Girl may choose this benefit.")

        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            benefit = self._benefit(row)
            if row["revision"] != revision or row["state"] == "resolved":
                raise WorkflowError("STALE_COMFORTS: refresh your actual saved benefit.")
            if attendance:
                state = load_state(c, self.store.campaign_id)
            else:
                self.game.unpaused(c)
                state = self._current(c, benefit)
                self._idle(c, state, viewer.user_id)
            updated_state, updated = change(c, state, benefit)
            source = self.game.event(
                c, viewer.user_id, key, kind, updated_state, benefit_id=identity
            )
            body = json.loads(row["body_json"]) | dict(
                benefit=updated.model_dump(mode="json"),
                immediate=updated.scene is not None and updated.taken is None,
            )
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("revision", "body_json", "event_id", "state")
                    },
                    revision=revision + 1,
                    body_json=json.dumps(body, sort_keys=True),
                    event_id=source,
                    state="resolved" if updated.taken is not None else "pending",
                )
            )
            return {
                "id": identity,
                "revision": revision + 1,
                "ready": rules.ready(updated),
                "taken": updated.taken,
            }

        try:
            return self.store._write(
                viewer,
                key,
                kind,
                dict(id=identity, revision=revision, **payload),
                operation,
                auto_audit=False,
                authorize=access,
            )
        except ValidationError:
            raise WorkflowError(
                "Review the current saved benefit and owned scene choices."
            ) from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def decline(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        return self._change(
            viewer,
            key,
            identity,
            revision,
            "m3.creature_comforts_declined",
            dict(account=account),
            lambda c, state, benefit: (None, rules.decline(benefit, viewer.user_id, account)),
        )

    def record_scene(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        channel: int,
        cast_revision: int,
        participants: tuple[ActorRef, ...],
        location: str,
        summary: str,
    ) -> dict[str, Any]:
        def change(
            c: Connection, state: GameState, benefit: ComfortBenefit
        ) -> tuple[None, ComfortBenefit]:
            data = self.get(viewer, identity, channel)
            if cast_revision != data["cast_revision"] or not set(participants) <= {
                ActorRef.model_validate(x["ref"]) for x in data["roles"]
            }:
                raise WorkflowError("Choose only known actual roles from the current cast.")
            cast, legacy = self.casts._current(c, state, channel)
            girls = [x for x in state.sheets[benefit.actor.entity].assets if x.family == "girl"]
            if len(girls) >= 4 and not any(not x.void for x in girls):
                raise WorkflowError("A new Girl Asset needs legal space or a non-Void replacement.")
            return None, rules.record_scene(
                state,
                profiles(c, self.store.campaign_id),
                benefit,
                cast,
                participants,
                viewer.user_id,
                summary,
                str(uuid4()),
                location,
            )

        return self._change(
            viewer,
            key,
            identity,
            revision,
            "m3.creature_comforts_scene_recorded",
            dict(
                channel=channel,
                cast_revision=cast_revision,
                participants=[x.model_dump(mode="json") for x in participants],
                location=location,
                summary=summary,
            ),
            change,
        )

    def attest(self, viewer: GuildViewer, key: str, identity: str, revision: int) -> dict[str, Any]:
        return self._change(
            viewer,
            key,
            identity,
            revision,
            "m3.creature_comforts_scene_attested",
            {},
            lambda c, state, benefit: (None, rules.attest(benefit, viewer.user_id)),
            attendance=True,
        )

    def grant(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        expected: str,
        chosen: GirlAsset,
    ) -> dict[str, Any]:
        chosen = GirlAsset.model_validate_json(chosen.model_dump_json())
        return self._change(
            viewer,
            key,
            identity,
            revision,
            "m3.creature_comforts_asset_granted",
            dict(expected=expected, chosen=chosen.model_dump(mode="json")),
            lambda c, state, benefit: rules.grant(
                state,
                profiles(c, self.store.campaign_id),
                expected,
                benefit,
                chosen,
                "comforts:" + identity,
            ),
        )
