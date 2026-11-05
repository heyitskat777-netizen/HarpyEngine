"""Original-party revocation receipts and explicit temporary restoration."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_privileges as rules
from girlframe.engine.m2 import GameState, Obligation
from girlframe.engine.m3_actors import fingerprint
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
            work.c.kind == "creature_comforts",
            work.c.subject_id == str(subject),
        )
        .order_by(work.c.revision.desc())
    ).mappings():
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        benefit = json.loads(row["body_json"])["benefit"]
        if benefit["taken"] is not None:
            resolved.add(benefit["purchase"])
    result = []
    for receipt in rules.available(state, subject, character):
        if receipt.id in resolved:
            continue
        purchase_proof(c, game.store, receipt)
        label = (
            next(x.name for x in state.sheets[str(subject)].assets if x.id == receipt.asset_id)
            if receipt.kind == "asset_installment"
            else "Creature Comforts"
        )
        result.append(dict(id=receipt.id, name=label))
    return result


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
        if result["can_restore"] and gate.details["kind"] == "asset_installment":
            from girlframe.engine.m3_assets import can_replace_at_limit

            sheet = state.sheets[str(gate.target)]
            result["replacements"] = [
                dict(id=x.id, name=x.name)
                for x in sheet.assets
                if x.family == "frame" and can_replace_at_limit(sheet, x)
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
