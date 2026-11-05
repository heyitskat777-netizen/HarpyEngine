"""Actual reviewed Frame acquisition and owned lost-pistol return after a real final roll."""

import json
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_personal_firearm as rules
from girlframe.engine.m2 import GameState, tier
from girlframe.engine.m3_acquisition_state import PersonalFirearmGrant
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_assets import can_replace_at_limit
from girlframe.engine.m3_off_duty import Period
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.engine.rules_registry import Registry
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_frame_rewards import eligibility
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_privileges import purchase_proof
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KIND = "personal_firearm_return"


def proof(c: Connection, store: OnboardingStore, entitlement: PersonalFirearmGrant) -> None:
    history = t.m2["m2_state_history"]
    initial = c.scalar(
        sa.select(history.c.body_json).where(
            history.c.campaign_id == store.campaign_id,
            history.c.event_id == entitlement.source_event,
        )
    )
    first_state = GameState.model_validate_json(initial) if initial else None
    first = (
        next((x for x in first_state.personal_firearms if x.id == entitlement.id), None)
        if first_state
        else None
    )
    latest = entitlement.issues[-1]
    body = c.scalar(
        sa.select(history.c.body_json).where(
            history.c.campaign_id == store.campaign_id, history.c.event_id == latest.source_event
        )
    )
    issued_state = GameState.model_validate_json(body) if body else None
    issued = (
        next((x for x in issued_state.personal_firearms if x.id == entitlement.id), None)
        if issued_state
        else None
    )
    if (
        first is None
        or first.actor != entitlement.actor
        or first.source_event != entitlement.source_event
        or first.purchase != entitlement.purchase
        or first.source_work != entitlement.source_work
        or first.issues[0] != entitlement.issues[0]
        or issued is None
        or issued.actor != entitlement.actor
        or issued.issues != entitlement.issues
    ):
        raise WorkflowError(
            "SOURCE_FIREARM_MISSING: recover the actual entitlement and issued item."
        )
    if entitlement.purchase is not None:
        assert first_state is not None
        receipt = next(
            (
                x
                for x in first_state.requisitions
                if isinstance(x, FrameRuleReceipt)
                and x.id == entitlement.purchase
                and x.grant == entitlement.id
            ),
            None,
        )
        if receipt is None:
            raise WorkflowError("SOURCE_ACQUISITION_MISSING: recover the actual paid source.")
        purchase_proof(c, store, receipt)
    else:
        from girlframe.services.m3_enforcer_requisitions import prove_replacement_rule

        if entitlement.source_work is None:
            raise WorkflowError("SOURCE_PACKAGE_MISSING: recover the original free issue package.")
        prove_replacement_rule(
            c,
            store,
            entitlement.actor,
            first.frame_instance,
            rules.RULE,
            entitlement.source_work,
            entitlement.source_event,
        )
        original_sheet = first_state.sheets.get(entitlement.actor.entity) if first_state else None
        issue = first.issues[0]
        if (
            original_sheet is None
            or original_sheet.character_id != entitlement.actor.incarnation
            or not any(x.id == issue.asset and x.family == "girl" for x in original_sheet.assets)
            or issue.replaces_asset is not None
            and any(x.id == issue.replaces_asset for x in original_sheet.assets)
        ):
            raise WorkflowError(
                "Recover the actual original free pistol and owned cap replacement."
            )
    if first.frame_instance != entitlement.frame_instance:
        transfer = next(
            (
                x
                for x in reversed(load_state(c, store.campaign_id).facts)
                if x.get("kind") == "personal_firearm_retained"
                and x.get("grant") == entitlement.id
                and x.get("frame") == entitlement.frame_instance
            ),
            None,
        )
        snapshot = c.scalar(
            sa.select(history.c.body_json).where(
                history.c.campaign_id == store.campaign_id,
                history.c.event_id == transfer.get("source_event") if transfer else sa.false(),
            )
        )
        exchanged = GameState.model_validate_json(snapshot) if snapshot else None
        exchange_receipt = (
            next(
                (
                    x
                    for x in exchanged.requisitions
                    if x.kind == "frame_swap"
                    and x.actor == entitlement.actor
                    and x.new_frame == entitlement.frame_instance
                    and x.selection.retained_rule == rules.RULE
                ),
                None,
            )
            if exchanged
            else None
        )
        if exchange_receipt is None:
            raise WorkflowError(
                "SOURCE_FIREARM_RETENTION_MISSING: recover the actual paid exchange."
            )
        purchase_proof(c, store, exchange_receipt)


def work_rows(c: Connection, store: OnboardingStore) -> list[dict[str, Any]]:
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


def synchronize(c: Connection, store: OnboardingStore, period: Period, event: str) -> None:
    if period.phase != "active":
        return
    state = load_state(c, store.campaign_id)
    if not state.personal_firearms:
        return
    existing = work_rows(c, store)
    for uid, progress in period.progress.items():
        if (
            uid in period.ended_characters
            or uid not in state.sheets
            or progress.roll is None
            or progress.roll.source != "status"
            or progress.roll.stage != "choices"
            or progress.action_id is None
        ):
            continue
        action = (
            c.execute(
                sa.select(t.m2["m2_actions"]).where(
                    t.m2["m2_actions"].c.campaign_id == store.campaign_id,
                    t.m2["m2_actions"].c.id == progress.action_id,
                )
            )
            .mappings()
            .one()
        )
        data = json.loads(action["body_json"])
        raw_json = c.scalar(
            sa.select(t.m2["m2_receipts"].c.body_json).where(
                t.m2["m2_receipts"].c.campaign_id == store.campaign_id,
                t.m2["m2_receipts"].c.action_id == progress.action_id,
            )
        )
        raw = json.loads(raw_json) if raw_json else None
        total = raw["pre_total"] + sum(x["amount"] for x in data["modifiers"]) if raw else None
        if (
            raw is None
            or action["state"] != "complete"
            or data.get("play") != "go_off_duty"
            or not data.get("m3_finished")
            or data.get("receipt") != raw
            or progress.roll.total != total
            or data["result"].get("total") != total
            or data["result"].get("tier") != tier(total)
        ):
            raise WorkflowError(
                "SOURCE_FIREARM_ROLL_MISSING: recover the actual final ordinary roll."
            )
        if total < 8:
            continue
        facts, source = eligibility(c, store, state, period, int(uid))
        if source is None:
            raise WorkflowError("Recover the actual pre-roll owned firearm state.")
        actor = ActorRef(kind="pilot", entity=uid, incarnation=period.character_ids[uid])
        current = resolve(
            state, actor, profiles(c, store.campaign_id), require_current_profile=False
        )
        before = resolve(
            facts, actor, profiles(c, store.campaign_id), require_current_profile=False
        )
        if (
            current.frame_instance is None
            or before.frame_instance != current.frame_instance
            or current.frame_scrapped
        ):
            continue
        for entitlement in rules.held(facts, actor, current.frame_instance):
            latest = entitlement.issues[-1].asset
            owned = next(
                (
                    x
                    for x in rules.held(state, actor, current.frame_instance)
                    if x.id == entitlement.id and x.issues[-1].asset == latest
                ),
                None,
            )
            if (
                owned is None
                or any(x.id == latest for x in facts.sheets[uid].assets)
                or any(x.id == latest for x in state.sheets[uid].assets)
            ):
                continue
            if any(
                x["state"] != "resolved"
                and json.loads(x["body_json"]).get("grant") == entitlement.id
                for x in existing
            ):
                continue
            identity = str(
                uuid5(
                    NAMESPACE_URL,
                    "girlframe:firearm-return:" + entitlement.id + ":" + progress.action_id,
                )
            )
            if any(x["id"] == identity for x in existing):
                continue
            proof(c, store, owned)
            related(
                c,
                store,
                dict(campaign_id=store.campaign_id, off_duty_id=period.id),
                identity,
                int(uid),
                int(uid),
                KIND,
                dict(
                    source_pdf=79,
                    immediate=False,
                    actor=actor.model_dump(mode="json"),
                    grant=entitlement.id,
                    lost=latest,
                    frame=current.frame_instance,
                    action=progress.action_id,
                    raw_event=source,
                    total=total,
                ),
                event,
            )


class PersonalFirearmService(RequisitionService):
    def __init__(self, game: GameService, registry: Registry | None = None):
        super().__init__(game)
        self.registry = registry
        self.periods = OffDutyService(MissionService(self.store, registry))

    def acquisition_view(self, viewer: GuildViewer, kind: rules.Kind) -> dict[str, Any]:
        if kind not in ("ability_unlock", "frame_grafting"):
            raise WorkflowError("Choose actual Ability Unlock or Frame Grafting.")
        data = self.view(viewer)
        with self.store.engine.connect() as c:
            Access(self.store, self.registry).authorize(c, viewer, "economy")
            registry = self.registry or Access(self.store).registry
            assert registry is not None
            try:
                entry = registry.require_available(rules.RULE)
            except ValueError as error:
                raise WorkflowError(str(error)) from None
            state = load_state(c, self.store.campaign_id)
            frame = state.sheets[str(viewer.user_id)].frame
            same = frame == entry.frame_playbook
            if (kind == "ability_unlock") != same:
                raise WorkflowError(
                    "Use your own Enforcer Requisition for Unlock "
                    "or another donor Frame for Grafting."
                )
            data["price"] = 2 if kind == "ability_unlock" else 3
            data["rule_id"] = entry.id
            data["girl_replacements"] = [
                dict(id=x.id, name=x.name)
                for x in state.sheets[str(viewer.user_id)].assets
                if x.family == "girl" and can_replace_at_limit(state.sheets[str(viewer.user_id)], x)
            ]
        return data

    def buy_firearm(
        self,
        viewer: GuildViewer,
        key: str,
        actor: ActorRef,
        expected: str,
        kind: rules.Kind,
        account: str,
        *,
        replace: str | None = None,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store, self.registry).authorize(c, viewer, "economy")
            if actor.entity != str(viewer.user_id) or actor.kind != "pilot":
                raise WorkflowError("Acquire only your original Girl's current Frame rule.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            self._safe(c, state, viewer.user_id)
            registry = self.registry or Access(self.store).registry
            assert registry is not None
            identity, grant, source = str(uuid4()), str(uuid4()), str(uuid4())
            updated = rules.purchase(
                state,
                actor,
                profiles(c, self.store.campaign_id),
                expected,
                registry,
                kind,
                account,
                identity,
                grant,
                source,
                replace=replace,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3." + kind + "_purchased",
                updated,
                event_id=source,
                requisition_id=identity,
                rule_id=rules.RULE,
                cost=2 if kind == "ability_unlock" else 3,
            )
            return dict(id=identity, grant=grant, cost=2 if kind == "ability_unlock" else 3)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.frame_acquisition",
                dict(
                    actor=actor.model_dump(mode="json"),
                    expected=expected,
                    kind=kind,
                    account=account,
                    replace=replace,
                ),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _return_row(self, c: Connection, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        self.game.authorize(c, viewer, game=False)
        row = next(
            (
                x
                for x in work_rows(c, self.store)
                if x["id"] == identity and x["owner_id"] == str(viewer.user_id)
            ),
            None,
        )
        if row is None:
            raise WorkflowError("This actual lost-pistol return belongs to its original human.")
        return row

    def _return_tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        return [
            dict(id=x["id"], revision=x["revision"], state=x["state"])
            for x in work_rows(c, self.store)
            if x["owner_id"] == str(viewer.user_id)
        ]

    def return_tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            return self._return_tasks(c, viewer)

    def return_get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row = self._return_row(c, viewer, identity)
            body, state = json.loads(row["body_json"]), load_state(c, self.store.campaign_id)
            actor = ActorRef.model_validate_json(json.dumps(body["actor"]))
            entitlement = next(
                (x for x in state.personal_firearms if x.id == body["grant"] and x.actor == actor),
                None,
            )
            if entitlement is None:
                raise WorkflowError("SOURCE_FIREARM_MISSING: recover the original entitlement.")
            proof(c, self.store, entitlement)
            sheet = state.sheets.get(actor.entity)
            stale = sheet is None or sheet.character_id != actor.incarnation
            return dict(
                id=identity,
                revision=row["revision"],
                state=row["state"],
                stale=stale,
                expected=fingerprint(sheet) if sheet else None,
                actor=actor.model_dump(mode="json"),
                total=body["total"],
                replacement_notice=rules.REPLACEMENT_NOTICE,
                resolution=body.get("resolution"),
                deferred=body.get("deferred", False),
                transfer_work=body.get("transfer_work"),
                replacements=[
                    dict(id=x.id, name=x.name)
                    for x in sheet.assets
                    if x.family == "girl" and can_replace_at_limit(sheet, x)
                ]
                if sheet
                else [],
            )

    def claim(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        *,
        take: bool,
        account: str,
        expected: str | None,
        replace: str | None = None,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store, self.registry).authorize(c, viewer, "economy")
            self._return_row(c, viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row = self._return_row(c, viewer, identity)
            if (
                row["state"] == "resolved"
                or row["revision"] != revision
                or type(take) is not bool
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "STALE_FIREARM_RETURN: reopen and supply your own actual decision."
                )
            body, state = json.loads(row["body_json"]), load_state(c, self.store.campaign_id)
            actor = ActorRef.model_validate_json(json.dumps(body["actor"]))
            if actor.entity != str(viewer.user_id):
                raise WorkflowError("Only the actual original owner can return this pistol.")
            period = self.periods._get(c, row["off_duty_id"])
            if period.phase != "active" or actor.entity in period.ended_characters:
                raise WorkflowError("Recover the original actual active Off-Duty period.")
            source = str(uuid4())
            if take:
                self._safe(c, state, viewer.user_id)
                if (
                    actor.entity not in state.sheets
                    or fingerprint(state.sheets[actor.entity]) != expected
                ):
                    raise WorkflowError(
                        "STALE_FIREARM_RETURN: review current actual Asset choices."
                    )
                registry = self.registry or Access(self.store).registry
                assert registry is not None
                registry.require_available(rules.RULE)
                state = rules.reissue(
                    state,
                    actor,
                    profiles(c, self.store.campaign_id),
                    body["grant"],
                    body["lost"],
                    body["frame"],
                    source,
                    body["action"],
                    replace=replace,
                )
            elif replace is not None:
                raise WorkflowError("Declining does not remove an Asset.")
            state.facts.append(
                dict(
                    kind="personal_firearm_return_decision",
                    grant=body["grant"],
                    action=body["action"],
                    actor=actor.model_dump_json(),
                    taken=str(take),
                    account=account.strip(),
                )
            )
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.personal_firearm_return",
                state,
                event_id=source,
                work_id=identity,
                taken=take,
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
                    state="resolved",
                    event_id=event,
                    body_json=json.dumps(
                        body | dict(taken=take, account=account.strip()), sort_keys=True
                    ),
                )
            )
            return dict(id=identity, taken=take)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.personal_firearm_return",
                dict(
                    id=identity,
                    revision=revision,
                    take=take,
                    account=account,
                    expected=expected,
                    replace=replace,
                ),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
