"""Actual native acquisition, immutable death proof, and original-human memorial control."""

import json
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_class_grafts as grafts
from girlframe.engine import m3_martyr as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def _paid_source(
    game: "GameService", c: Connection, state: GameState, receipt: FrameRuleReceipt
) -> None:
    from girlframe.services.m3_class_retention import proof

    gate = Access(game.store)
    if gate.registry is None:
        raise WorkflowError("Recover the original Martyr source before this death")
    gate.registry.require_available(rules.RULE)
    _, chain = proof(game, c, state, receipt)
    if len(chain) > 1:
        gate.registry.require_available("core.core.frame-requisitions")


def prepare(
    game: "GameService", c: Connection, previous: GameState, state: GameState, event: str
) -> None:
    for archive in state.career_archives:
        if archive.source_event != event or archive.ending not in ("death", "execution"):
            continue
        receipt = rules.held(previous, archive.actor)
        if receipt is None:
            continue
        _paid_source(game, c, previous, receipt)
        rules.trigger(state, archive, receipt)


def synchronize(game: "GameService", c: Connection, state: GameState, event: str) -> None:
    work = t.m3["m3_required_work"]
    for value in rules.episodes(state):
        if value.source_event != event or c.scalar(
            sa.select(work.c.id)
            .where(work.c.campaign_id == game.store.campaign_id, work.c.id == value.id)
            .limit(1)
        ):
            continue
        related(
            c,
            game.store,
            dict(campaign_id=game.store.campaign_id, campaign_context=True),
            value.id,
            int(value.actor.entity),
            int(value.actor.entity),
            rules.KIND,
            dict(
                episode=value.id,
                owner=value.actor.model_dump(mode="json"),
                character=value.actor.incarnation,
                immediate=True,
            ),
            event,
        )


class MartyrService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def menu(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            try:
                sheet, frame, kind, price, _ = grafts.offer(state, actor, rules.RULE)
                gate = Access(self.store)
                if (
                    gate.registry is None
                    or state.strain is None
                    or self.store.policy.m3_approval is None
                    or "strain" not in self.store.policy.m3_approval.subsystems
                ):
                    return dict(available=False)
                gate.registry.require_available(rules.RULE)
            except (ValueError, KeyError, WorkflowError):
                return dict(available=False)
            self.game.character_binding(c, state, viewer.user_id)
            receipt = rules.held(state, actor)
            if receipt:
                _paid_source(self.game, c, state, receipt)
            return dict(
                available=True,
                revision=state.revision,
                actor=actor.model_dump(mode="json"),
                frame=frame,
                owned=receipt is not None,
                permissions=sheet.permissions,
                kind=kind,
                price=price,
                donors=list(grafts.donors(rules.RULE)) if kind == "frame_grafting" else [],
                suspended=any(
                    isinstance(x, FrameRuleReceipt)
                    and x.actor == actor
                    and x.rule_id == rules.RULE
                    and grafts.eligible(state, x)
                    and suspended(state, x.id)
                    for x in state.requisitions
                ),
            )

    def buy(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        actor: ActorRef,
        frame: str,
        account: str,
        donor_frame: str | None = None,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            gate = Access(self.store)
            gate.authorize(c, viewer, "economy")
            gate.authorize(c, viewer, "strain")
            assert gate.registry is not None
            entry = gate.registry.require_available(rules.RULE)
            if (entry.frame_class, entry.frame_rule) != ("autocrat", "class_requisition"):
                raise WorkflowError("Recover the actual Autocrat Martyr source")

        def change(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_requisitions import RequisitionService

            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            RequisitionService(self.game)._safe(c, state, viewer.user_id)
            if (
                state.revision != revision
                or actor != current_ref(state, viewer.user_id)
                or state.strain is None
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError("Reopen the actual Martyr acquisition and existing Strain")
            self.game.character_binding(c, state, viewer.user_id)
            sheet, current, kind, price, donor = grafts.acquisition(
                state, actor, rules.RULE, donor_frame
            )
            if current != frame or sheet.permissions < price:
                raise WorkflowError("Use the actual original Frame and available Permissions")
            if any(
                isinstance(x, FrameRuleReceipt)
                and x.actor == actor
                and x.rule_id == rules.RULE
                and grafts.eligible(state, x)
                for x in state.requisitions
            ):
                raise WorkflowError(
                    "Restore the original paid Martyr entitlement instead of buying twice"
                )
            identity, event = str(uuid4()), str(uuid4())
            sheet.permissions -= price
            sheet.revision += 1
            state.requisitions.append(
                FrameRuleReceipt(
                    id=identity,
                    kind=kind,
                    actor=actor,
                    frame_instance=frame,
                    frame=sheet.frame,
                    donor_frame=donor,
                    rule_id=rules.RULE,
                    grant="martyr:" + identity,
                    price=price,
                    account=account,
                    source_event=event,
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3." + kind + "_purchased",
                state,
                event_id=event,
                requisition_id=identity,
                rule_id=rules.RULE,
                cost=price,
            )
            return dict(id=identity, cost=price)

        return self.store._write(
            viewer,
            key,
            "m3.martyr_purchased",
            dict(
                revision=revision, actor=actor.model_dump(mode="json"), frame=frame, account=account
            )
            | (dict(donor_frame=donor_frame) if donor_frame is not None else {}),
            change,
            auto_audit=False,
            authorize=access,
        )

    def _source(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[GameState, rules.Martyr, dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        value = next((x for x in rules.episodes(state) if x.id == identity), None)
        if (
            value is None
            or value.actor.kind != "pilot"
            or value.actor.entity != str(viewer.user_id)
        ):
            raise WorkflowError("Only the original dead character's human owns this memorial")
        body = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == value.source_event,
            )
        )
        original = GameState.model_validate_json(body) if body else None
        first = (
            next((x for x in rules.episodes(original) if x.id == identity), None)
            if original
            else None
        )
        fields = ("id", "actor", "frame", "purchase", "archive", "source_event")
        if (
            first is None
            or any(getattr(first, k) != getattr(value, k) for k in fields)
            or original is None
            or not rules.budget_death_excluded(original, value.source_event)
        ):
            raise WorkflowError("Recover the actual immutable paid Martyr death and archive")
        receipt = next(x for x in original.requisitions if x.id == value.purchase)
        from girlframe.services.m3_class_retention import proof

        if not isinstance(receipt, FrameRuleReceipt):
            raise WorkflowError("Recover the original paid Martyr acquisition")
        proof(self.game, c, original, receipt)
        work = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(work)
                .where(
                    work.c.campaign_id == self.store.campaign_id,
                    work.c.id == identity,
                    work.c.kind == rules.KIND,
                )
                .order_by(work.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None or json.loads(row["body_json"]).get("owner") != value.actor.model_dump(
            mode="json"
        ):
            raise WorkflowError("Recover the original human-owned memorial work")
        return state, value, dict(row)

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state, value, row = self._source(c, viewer, identity)
            return dict(
                id=identity,
                revision=state.revision,
                callsign=json.loads(
                    next(x.sheet_json for x in state.career_archives if x.id == value.archive)
                )["callsign"],
                episode=value.model_dump(mode="json"),
                can_act=value.phase == "pending" and row["state"] == "pending",
            )

    def choose(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        memorial: Literal["hero", "obscurity"],
        account: str,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "playbooks", director_response=True)
            self._source(c, viewer, identity)

        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, value, row = self._source(c, viewer, identity)
            if (
                state.revision != revision
                or value.phase != "pending"
                or row["state"] != "pending"
                or memorial not in dict(rules.MEMORIALS)
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError("Reopen your own actual pending memorial choice")
            event = str(uuid4())
            rules.save(
                state,
                value.model_copy(
                    update=dict(
                        phase="complete",
                        memorial=memorial,
                        response_event=event,
                        response_account=account,
                    )
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.martyr_memorial_chosen",
                state,
                event_id=event,
                episode=identity,
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
                    revision=row["revision"] + 1,
                    body_json=row["body_json"],
                    event_id=event,
                    state="resolved",
                )
            )
            return dict(id=identity, memorial=memorial)

        return self.store._write(
            viewer,
            key,
            "m3.martyr_memorial_chosen",
            dict(id=identity, revision=revision, memorial=memorial, account=account),
            change,
            auto_audit=False,
            authorize=access,
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        return [
            dict(id=x.id, revision=state.revision, actionable=True)
            for x in rules.episodes(state)
            if x.actor.entity == str(viewer.user_id) and x.phase == "pending"
        ]
