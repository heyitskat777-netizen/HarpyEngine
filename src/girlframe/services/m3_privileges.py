"""Original-party revocation receipts and explicit temporary restoration."""

import json
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_privileges as rules
from girlframe.engine.m2 import AssetState, GameState, Obligation
from girlframe.engine.m3_actors import fingerprint
from girlframe.engine.m3_off_duty import Period
from girlframe.engine.m3_requisition_state import Requisition
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def purchase_proof(c: Connection, store: OnboardingStore, receipt: Requisition) -> None:
    history = t.m2["m2_state_history"]
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == store.campaign_id,
                t.events.c.id == receipt.source_event,
            )
        )
        .mappings()
        .first()
    )
    body = c.scalar(
        sa.select(history.c.body_json).where(
            history.c.campaign_id == store.campaign_id,
            history.c.event_id == receipt.source_event,
        )
    )
    original = GameState.model_validate_json(body) if body else None
    saved = (
        next((x for x in original.requisitions if x.id == receipt.id), None) if original else None
    )
    expected = "m3." + receipt.kind + "_purchased"
    metadata = json.loads(event["payload_json"]) if event else {}
    if (
        event is None
        or event["kind"] != expected
        or event["actor_id"] != receipt.actor.entity
        or metadata.get("requisition_id") != receipt.id
        or metadata.get("cost") != receipt.price
        or saved != receipt
    ):
        raise WorkflowError("SOURCE_REQUISITION_MISSING: recover the actual paid Requisition.")


def choices(
    c: Connection, game: GameService, state: GameState, subject: int
) -> list[dict[str, str]]:
    character = game.character_binding(c, state, subject, require_current_profile=False)
    work = t.m3["m3_required_work"]
    resolved: set[str] = set()
    seen: set[str] = set()
    for row in c.execute(
        sa.select(work)
        .where(
            work.c.campaign_id == game.store.campaign_id,
            work.c.kind.in_(("creature_comforts", "scene_requisition")),
            work.c.subject_id == str(subject),
        )
        .order_by(work.c.revision.desc())
    ).mappings():
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        benefit = json.loads(row["body_json"])["benefit"]
        if (
            benefit.get("taken") is not None
            or benefit.get("declined")
            or (benefit.get("scene") and benefit["scene"].get("entered_event"))
        ):
            resolved.add(benefit["purchase"])
    result = []
    for receipt in rules.available(state, subject, character):
        if receipt.id in resolved:
            continue
        purchase_proof(c, game.store, receipt)
        if receipt.kind == "asset_installment":
            label = next(
                x.name for x in state.sheets[str(subject)].assets if x.id == receipt.asset_id
            )
        else:
            from girlframe.engine.m3_enforcer_requisitions import TITLES

            label = {
                "creature_comforts": "Creature Comforts",
                "privacy": "Privacy",
                "visiting_home": "Visiting Home",
                "ability_unlock": "Personal Firearm",
                "frame_grafting": "Personal Firearm",
                "frame_swap": "Frame Swap retained rule",
            }[receipt.kind]
            if hasattr(receipt, "rule_id"):
                label = TITLES.get(receipt.rule_id, label)
                if receipt.rule_id.startswith("frame.class."):
                    label = receipt.rule_id.rsplit(".", 1)[1].replace("-", " ").title()
                if receipt.rule_id == "frame.class.autocrat.untouchable-frame":
                    label = "Untouchable Frame"
                elif receipt.rule_id == "frame.class.autocrat.martyr":
                    label = "Martyr"
                elif receipt.rule_id == "frame.class.legion.dampener-link":
                    label = "Dampener Link"
                elif receipt.rule_id == "frame.class.legion.kicked-puppy":
                    label = "Kicked Puppy"
            elif receipt.kind == "frame_swap":
                label = "Frame Swap: " + TITLES.get(
                    receipt.selection.retained_rule, "retained rule"
                )
        result.append(dict(id=receipt.id, name=label))
    return result


DEFERRED_KINDS = ("creature_comforts", "scene_requisition", "personal_firearm_return")


def _benefit_rows(c: Connection, store: OnboardingStore) -> list[dict[str, Any]]:
    work = t.m3["m3_required_work"]
    return list(
        {
            row["id"]: dict(row)
            for row in c.execute(
                sa.select(work)
                .where(
                    work.c.campaign_id == store.campaign_id,
                    work.c.kind.in_(DEFERRED_KINDS),
                )
                .order_by(work.c.revision)
            ).mappings()
        }.values()
    )


def _save_benefit(
    c: Connection,
    row: dict[str, Any],
    event: str,
    body: dict[str, Any],
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
            state="resolved",
            event_id=event,
            body_json=json.dumps(body, sort_keys=True),
        )
    )


def suspend_benefits(c: Connection, store: OnboardingStore, state: GameState, event: str) -> None:
    """Resolve only old work scheduling, preserving its unconsumed original entitlement."""
    for gate in state.obligations:
        if (
            gate.kind != rules.KIND
            or gate.state != "pending"
            or gate.details.get("source_event") != event
        ):
            continue
        for row in _benefit_rows(c, store):
            if row["state"] == "resolved" or row["subject_id"] != str(gate.target):
                continue
            body = json.loads(row["body_json"])
            saved = body.get("benefit", {})
            matches = saved.get("purchase") == gate.details["purchase"]
            if row["kind"] == "personal_firearm_return":
                matches = gate.details.get("grant") is not None and body.get(
                    "grant"
                ) == gate.details.get("grant")
            if not matches or saved.get("taken") is not None or saved.get("declined"):
                continue
            if row["kind"] == "scene_requisition" and (saved.get("scene") or {}).get(
                "entered_event"
            ):
                continue
            _save_benefit(
                c,
                row,
                event,
                body
                | dict(
                    immediate=False,
                    deferred=True,
                    deferred_by=gate.id,
                    resolution="requisition_temporarily_suspended",
                    qualification_period=body.get("qualification_period", row["off_duty_id"]),
                ),
            )


def resume_restored_benefits(
    c: Connection,
    store: OnboardingStore,
    period: Period,
    event: str,
) -> None:
    """Append a new actual period scope; never rewrite the original source context or dice."""
    if period.phase != "active":
        return
    from girlframe.services.m3_work import related

    state = load_state(c, store.campaign_id)
    gates = {x.id: x for x in state.obligations if x.kind == rules.KIND and x.state == "fulfilled"}
    for row in _benefit_rows(c, store):
        body = json.loads(row["body_json"])
        gate = gates.get(body.get("deferred_by"))
        if (
            gate is None
            or not body.get("deferred")
            or body.get("resolution") != "requisition_temporarily_suspended"
        ):
            continue
        owner = str(gate.target)
        if (
            period.character_ids.get(owner) != gate.details["character"]
            or owner in period.ended_characters
            or owner not in state.sheets
        ):
            continue
        restored = c.scalar(
            sa.select(t.events.c.id)
            .where(
                t.events.c.campaign_id == store.campaign_id,
                t.events.c.kind == "m3.requisition_restored",
                t.events.c.actor_id == owner,
                sa.func.json_extract(t.events.c.payload_json, "$.revocation_id") == gate.id,
            )
            .order_by(t.events.c.seq.desc())
            .limit(1)
        )
        if restored is None:
            raise WorkflowError(
                "SOURCE_RESTORATION_MISSING: recover the original owner's restoration."
            )
        proof = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == store.campaign_id,
                t.m2["m2_state_history"].c.event_id == restored,
            )
        )
        restored_state = GameState.model_validate_json(proof) if proof else None
        restored_gate = (
            next((x for x in restored_state.obligations if x.id == gate.id), None)
            if restored_state
            else None
        )
        if restored_gate != gate:
            raise WorkflowError("SOURCE_RESTORATION_MISSING: recover the exact restored resource.")
        paid = next((x for x in state.requisitions if x.id == gate.details["purchase"]), None)
        if paid is None:
            raise WorkflowError("SOURCE_REQUISITION_MISSING: recover the actual paid resource.")
        purchase_proof(c, store, paid)
        fresh = json.loads(row["body_json"])
        saved = fresh.get("benefit")
        if saved is not None:
            saved["period"] = period.id
            scene = saved.get("scene")
            if row["kind"] == "scene_requisition":
                saved["scene"] = None
            elif scene is not None and set(scene.get("acknowledgements", [])) != {
                role["controller"] for role in scene["roles"]
            }:
                saved["scene"] = None
        fresh.update(
            deferred=False,
            deferred_from=row["id"],
            restoration_event=restored,
            resolution="restored_original_entitlement",
            qualification_period=body.get("qualification_period", row["off_duty_id"]),
        )
        fresh["immediate"] = bool(
            row["kind"] == "creature_comforts" and saved and saved.get("scene")
        )
        identity = str(
            uuid5(NAMESPACE_URL, "girlframe:restored-benefit:" + row["id"] + ":" + period.id)
        )
        related(
            c,
            store,
            dict(campaign_id=store.campaign_id, off_duty_id=period.id),
            identity,
            int(row["owner_id"]),
            int(row["subject_id"]),
            row["kind"],
            fresh,
            event,
        )
        _save_benefit(
            c,
            row,
            event,
            body
            | dict(
                resolution="requisition_benefit_transferred",
                transfer_work=identity,
                transfer_period=period.id,
                restoration_event=restored,
            ),
        )


class PrivilegeService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _get(
        self,
        c: Connection,
        viewer: GuildViewer,
        identity: str,
    ) -> tuple[GameState, Obligation]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        gate = next(
            (
                x
                for x in state.obligations
                if x.kind == rules.KIND
                and x.id == identity
                and viewer.user_id in (x.owner, x.target)
            ),
            None,
        )
        if gate is None:
            raise WorkflowError("This Requisition belongs to its original participants.")
        history = t.m2["m2_state_history"]
        body = c.scalar(
            sa.select(history.c.body_json).where(
                history.c.campaign_id == self.store.campaign_id,
                history.c.event_id == gate.details.get("source_event"),
            )
        )
        event = c.scalar(
            sa.select(t.events.c.kind).where(
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.id == gate.details.get("source_event"),
            )
        )
        original = GameState.model_validate_json(body) if body else None
        first = (
            next((x for x in original.obligations if x.id == gate.id), None) if original else None
        )

        def stable(item: Obligation) -> dict[str, str]:
            return {
                k: v
                for k, v in item.details.items()
                if k not in ("restoration_allowed", "restoration_event")
            }

        if (
            first is None
            or event != "m3.punishment_applied"
            or first.state != "pending"
            or (first.owner, first.target, first.action) != (gate.owner, gate.target, gate.action)
            or stable(first) != stable(gate)
        ):
            raise WorkflowError("SOURCE_REVOCATION_MISSING: recover the original Punishment.")
        if gate.details["restoration_allowed"] == "true":
            allowed_source = gate.details.get("restoration_event")
            allowed_body = c.scalar(
                sa.select(history.c.body_json).where(
                    history.c.campaign_id == self.store.campaign_id,
                    history.c.event_id == allowed_source,
                )
            )
            allowed_event = c.execute(
                sa.select(t.events.c.kind, t.events.c.actor_id).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == allowed_source,
                )
            ).first()
            allowed_state = GameState.model_validate_json(allowed_body) if allowed_body else None
            allowed_gate = (
                next((x for x in allowed_state.obligations if x.id == identity), None)
                if allowed_state
                else None
            )
            if (
                allowed_event is None
                or allowed_event.kind != "m3.requisition_restoration_allowed"
                or allowed_event.actor_id != str(gate.owner)
                or allowed_gate is None
                or allowed_gate.details != gate.details
                or allowed_gate.state != "pending"
            ):
                raise WorkflowError("SOURCE_RESTORATION_MISSING: recover the inflictor's decision.")
        return state, gate

    def _current(self, c: Connection, state: GameState, gate: Obligation) -> None:
        if (
            gate.target is None
            or self.game.character_binding(c, state, gate.target, require_current_profile=False)
            != gate.details["character"]
        ):
            raise WorkflowError(
                "STALE_CHARACTER: restore only the original character's Requisition."
            )
        expected = gate.details["inflictor_character"]
        if expected == "handler":
            if (
                state.handler != gate.owner
                or HandlerService(self.store).current(c)[1].handler_id != gate.owner
            ):
                raise WorkflowError("Recover the original inflictor's Handler appointment.")
        elif (
            self.game.character_binding(c, state, gate.owner, require_current_profile=False)
            != expected
        ):
            raise WorkflowError("STALE_INFLICTOR: recover the original inflictor character.")
        if not all(HandlerService(self.store)._member(c, uid) for uid in (gate.owner, gate.target)):
            raise WorkflowError("Recover the original participants' campaign membership.")

    def view(self, c: Connection, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        state, gate = self._get(c, viewer, identity)
        stale = False
        try:
            self._current(c, state, gate)
        except WorkflowError:
            stale = True
        pending = gate.state == "pending"
        allowed = gate.details["restoration_allowed"] == "true"
        result: dict[str, Any] = dict(
            id=gate.id,
            label=gate.details["label"],
            condition=gate.details["condition"],
            pending=pending,
            allowed=allowed,
            stale=stale,
            expected=fingerprint(gate),
            game_revision=state.revision,
            can_allow=pending and not allowed and not stale and viewer.user_id == gate.owner,
            can_restore=pending and allowed and not stale and viewer.user_id == gate.target,
            replacements=[],
        )
        if result["can_restore"] and "asset" in gate.details:
            from girlframe.engine.m3_assets import can_replace_at_limit

            sheet = state.sheets[str(gate.target)]
            family = AssetState.model_validate_json(gate.details["asset"]).family
            result["replacements"] = [
                dict(id=x.id, name=x.name)
                for x in sheet.assets
                if x.family == family and can_replace_at_limit(sheet, x)
            ]
        return result

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            return self.view(c, viewer, identity)

    def change(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: str,
        revision: int,
        *,
        allow: bool,
        evidence: str,
        replace: str | None = None,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "discipline")
            self._get(c, viewer, identity)
            policy = self.store.policy.owner_m3_rulings
            if (
                policy is None
                or policy.privilege_restoration != "inflictor_condition_owner_restores"
            ):
                raise WorkflowError("UNRESOLVED_RULING: record temporary restoration ownership.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, gate = self._get(c, viewer, identity)
            self._current(c, state, gate)
            data = self.view(c, viewer, identity)
            source_event = str(uuid4())
            if (
                data["expected"] != expected
                or state.revision != revision
                or not evidence.strip()
                or len(evidence) > 1200
                or not data["can_allow" if allow else "can_restore"]
            ):
                raise WorkflowError("STALE_REVOCATION: reopen the original owned restoration.")
            if allow:
                if replace is not None:
                    raise WorkflowError(
                        "The affected owner chooses any required Asset replacement."
                    )
                gate.details["restoration_allowed"] = "true"
                gate.details["restoration_event"] = source_event
            else:
                if self.game.pending_actions(c):
                    raise WorkflowError(
                        "Finish pending Plays before restoring mechanical resources."
                    )
                locks = t.m2["m2_locks"]
                if c.scalar(
                    sa.select(locks.c.channel_id)
                    .where(
                        locks.c.campaign_id == self.store.campaign_id,
                        locks.c.state != "released",
                    )
                    .limit(1)
                ):
                    raise WorkflowError(
                        "Restore scene chat permissions before restoring resources."
                    )
                state = rules.restore(state, identity, gate.details["character"], replace)
            state.facts.append(
                dict(
                    kind="requisition_restoration",
                    revocation=identity,
                    owner=str(viewer.user_id),
                    evidence=evidence,
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.requisition_restoration_allowed" if allow else "m3.requisition_restored",
                state,
                event_id=source_event,
                revocation_id=identity,
            )
            if not allow:
                periods = t.m3["m3_off_duty"]
                for body in c.scalars(
                    sa.select(periods.c.body_json).where(
                        periods.c.campaign_id == self.store.campaign_id,
                        periods.c.phase == "active",
                    )
                ):
                    resume_restored_benefits(
                        c, self.store, Period.model_validate_json(body), source_event
                    )
            return dict(id=identity, allowed=True, restored=not allow)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.requisition_restore",
                dict(
                    id=identity,
                    expected=expected,
                    revision=revision,
                    allow=allow,
                    evidence=evidence,
                    replace=replace,
                ),
                operation,
                authorize=authorize,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
