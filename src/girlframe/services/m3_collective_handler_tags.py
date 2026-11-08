"""Actual Endgame6 and finite, human-owned per-period collective Tag opportunities."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_collective_handler_tags as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_budget_tags import original_girl_alive
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_off_duty import Period
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_budget_tags import _selection
from girlframe.services.m3_frame_rewards import eligibility
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

RULE = "strain.budget.endgame.6"


class NotQualified(WorkflowError):
    """An actual optional opportunity has not arisen or has ended."""


class CollectiveTagService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer, *, write: bool) -> None:
        Access(self.store).authorize(c, viewer, "strain")
        if write:
            self.game.unpaused(c)

    def _write(
        self, viewer: GuildViewer, key: str, kind: str, body: dict[str, Any], operation: Any
    ) -> dict[str, Any]:
        try:
            return self.store._write(
                viewer,
                key,
                kind,
                body,
                operation,
                auto_audit=False,
                authorize=lambda c: self._access(c, viewer, write=True),
            )
        except ValidationError:
            raise WorkflowError(
                "Recover the original private collective Tag source records"
            ) from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def install(
        self, viewer: GuildViewer, key: str, identity: str, expected: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            row, original = _selection(c, self.game, identity, rule=RULE)
            state = load_state(c, self.store.campaign_id)
            handler = active_handler(original)
            if state.revision != expected or row["state"] != "pending":
                raise WorkflowError("STALE_COLLECTIVE_TAG: reopen the original Endgame")
            if (
                handler is None
                or viewer.user_id != int(handler.entity)
                or not same_handler_body(state, handler)
            ):
                raise WorkflowError("Only the actual original Handler records this Endgame")
            if any(x.id == identity for x in rules.entitlements(state)):
                raise WorkflowError("The actual original Endgame entitlement already exists")
            event = str(uuid4())
            value = rules.Entitlement(
                id=identity, handler=handler, selection_event=row["event_id"], source_event=event
            )
            state.facts.append(
                dict(kind="budget_collective_tag_entitlement", body=value.model_dump_json())
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.collective_tag_endgame_recorded",
                state,
                event_id=event,
                source_work=identity,
            )
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **(row | dict(revision=row["revision"] + 1, state="resolved", event_id=event))
                )
            )
            return dict(id=identity, state="recorded")

        return self._write(
            viewer,
            key,
            "m3.collective_tag_endgame_recorded",
            dict(id=identity, expected=expected),
            operation,
        )

    def _entitlement(self, c: Connection, state: GameState, identity: str) -> rules.Entitlement:
        value = next((x for x in rules.entitlements(state) if x.id == identity), None)
        if value is None:
            raise WorkflowError("Recover the actual original collective Tag entitlement")
        _, original = _selection(c, self.game, identity, rule=RULE)
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == value.source_event,
            )
        )
        event = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == value.source_event,
                )
            )
            .mappings()
            .first()
        )
        source = GameState.model_validate_json(raw) if raw else None
        if (
            event is None
            or event["kind"] != "m3.collective_tag_endgame_recorded"
            or event["actor_id"] != value.handler.entity
            or active_handler(original) != value.handler
            or source is None
            or value not in rules.entitlements(source)
            or json.loads(event["payload_json"]).get("source_work") != identity
        ):
            raise WorkflowError("Recover the immutable original Endgame entitlement")
        return value

    def _period(self, c: Connection, identity: str) -> Period:
        work = t.m3["m3_off_duty"]
        raw = c.scalar(
            sa.select(work.c.body_json).where(
                work.c.campaign_id == self.store.campaign_id, work.c.id == identity
            )
        )
        if raw is None:
            raise WorkflowError("Use the actual original Off-Duty period")
        return Period.model_validate_json(raw)

    def _qualification(
        self, c: Connection, state: GameState, value: rules.Entitlement, period: Period
    ) -> tuple[tuple[ActorRef, ...], str]:
        if period.phase != "active" or not same_handler_body(state, value.handler):
            raise NotQualified("This original Handler's actual Off-Duty opportunity is unavailable")
        if set(period.character_ids) != {str(x) for x in period.pilots}:
            raise WorkflowError("Recover the actual original period character bindings")
        installed = c.scalar(
            sa.select(t.events.c.seq).where(
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.id == value.source_event,
            )
        )
        qualifying = None
        for uid, progress in period.progress.items():
            if progress.roll is None or progress.roll.source != "status":
                continue
            _, source = eligibility(c, self.store, state, period, int(uid))
            sequence = c.scalar(
                sa.select(t.events.c.seq).where(
                    t.events.c.campaign_id == self.store.campaign_id, t.events.c.id == source
                )
            )
            action = c.scalar(
                sa.select(t.m2["m2_actions"].c.body_json).where(
                    t.m2["m2_actions"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_actions"].c.id == progress.action_id,
                )
            )
            if (
                source is not None
                and action
                and json.loads(action).get("play") == "go_off_duty"
                and installed is not None
                and sequence is not None
                and sequence > installed
            ):
                qualifying = source
                break
        girls = tuple(
            ActorRef(kind="pilot", entity=str(uid), incarnation=period.character_ids[str(uid)])
            for uid in period.pilots
            if str(uid) not in period.ended_characters
            and original_girl_alive(
                state,
                ActorRef(kind="pilot", entity=str(uid), incarnation=period.character_ids[str(uid)]),
            )
        )
        if qualifying is None or not girls:
            raise NotQualified(
                "A real subsequent Go Off-Duty roll and its original Girls are required"
            )
        return girls, qualifying

    def _proposal(self, c: Connection, state: GameState, identity: str) -> rules.Proposal:
        value = next((x for x in rules.proposals(state) if x.id == identity), None)
        if value is None:
            raise WorkflowError("Reopen the actual collective Tag proposal")
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == value.event,
            )
        )
        source = GameState.model_validate_json(raw) if raw else None
        if source is None or value not in rules.proposals(source):
            raise WorkflowError("Recover the original immutable collective proposal")
        self._entitlement(c, state, value.entitlement)
        return value

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        try:
            with self.store.engine.connect() as c:
                self._access(c, viewer, write=False)
                state = load_state(c, self.store.campaign_id)
                if ":period:" not in identity:
                    row, selected = _selection(c, self.game, identity, rule=RULE)
                    handler = active_handler(selected)
                    ended = handler is not None and not same_handler_body(state, handler)
                    if handler is None or (
                        viewer.user_id != int(handler.entity)
                        and not (ended and viewer.user_id == state.handler)
                    ):
                        raise WorkflowError("Only the actual original Handler reviews this Endgame")
                    return dict(
                        id=identity,
                        state=("ending_install" if ended else "install")
                        if row["state"] == "pending"
                        else "recorded",
                        expected=state.revision,
                        proposal=None,
                    )
                entitlement, period_id = identity.rsplit(":period:", 1)
                source = self._entitlement(c, state, entitlement)
                period = self._period(c, period_id)
                value = next((x for x in rules.proposals(state) if x.id == identity), None)
                if value:
                    value = self._proposal(c, state, identity)
                    girls = value.girls
                else:
                    girls, _ = self._qualification(c, state, source, period)
                girl = next((x for x in girls if int(x.entity) == viewer.user_id), None)
                if girl is None:
                    if (
                        value
                        and viewer.user_id == state.handler
                        and value.stage == "proposed"
                        and (
                            not same_handler_body(state, value.handler)
                            or any(
                                not original_girl_alive(state, x)
                                for x in value.girls
                                if x not in value.ended
                            )
                        )
                    ):
                        return dict(
                            id=identity,
                            state="ending_review",
                            expected=state.revision,
                            proposal=None,
                            original_ended=True,
                            active=period.phase == "active",
                        )
                    raise WorkflowError(
                        "This private collective proposal belongs to its actual original Girls"
                    )
                return dict(
                    id=identity,
                    entitlement=entitlement,
                    period=period_id,
                    expected=state.revision,
                    state=(
                        "available"
                        if value is None or value.stage == "withdrawn" and period.phase == "active"
                        else value.stage
                    ),
                    proposal=value.model_dump(mode="json") if value else None,
                    can_agree=bool(
                        value and girl not in value.votes and original_girl_alive(state, girl)
                    ),
                    can_withdraw=bool(value and girl == value.proposer),
                    original_ended=bool(
                        value
                        and (
                            not same_handler_body(state, value.handler)
                            or any(
                                not original_girl_alive(state, x)
                                for x in value.girls
                                if x not in value.ended
                            )
                        )
                    ),
                    active=period.phase == "active",
                )
        except ValidationError:
            raise WorkflowError(
                "Recover the original private collective Tag source records"
            ) from None

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        if viewer.user_id == state.handler:
            work = t.m3["m3_required_work"]
            latest = {
                row["id"]: dict(row)
                for row in c.execute(
                    sa.select(work)
                    .where(
                        work.c.campaign_id == self.store.campaign_id,
                        work.c.kind == "strain_endgame_effect",
                        sa.func.json_extract(work.c.body_json, "$.rule_id") == RULE,
                    )
                    .order_by(work.c.revision)
                ).mappings()
            }
            for row in latest.values():
                if row["state"] != "pending":
                    continue
                _, original = _selection(c, self.game, row["id"], rule=RULE)
                handler = active_handler(original)
                if (
                    handler is not None
                    and int(handler.entity) != viewer.user_id
                    and not same_handler_body(state, handler)
                ):
                    result.append(
                        dict(
                            id=row["id"],
                            revision=row["revision"],
                            state="ending_install",
                            actionable=True,
                            title="Original Endgame Handler ended",
                        )
                    )
        known = rules.proposals(state)
        for value in known:
            member = any(int(x.entity) == viewer.user_id for x in value.girls)
            ending_review = (
                viewer.user_id == state.handler
                and value.stage == "proposed"
                and (
                    not same_handler_body(state, value.handler)
                    or any(
                        not original_girl_alive(state, x)
                        for x in value.girls
                        if x not in value.ended
                    )
                )
            )
            if not member and not ending_review:
                continue
            self._proposal(c, state, value.id)
            result.append(
                dict(
                    id=value.id,
                    revision=value.revision,
                    state=value.stage,
                    actionable=value.stage == "proposed",
                    title="Collective Handler Tag agreement",
                )
            )
        periods = t.m3["m3_off_duty"]
        for source in rules.entitlements(state):
            self._entitlement(c, state, source.id)
            if not same_handler_body(state, source.handler):
                continue
            for raw in c.scalars(
                sa.select(periods.c.body_json).where(
                    periods.c.campaign_id == self.store.campaign_id, periods.c.phase == "active"
                )
            ):
                period = Period.model_validate_json(raw)
                identity = source.id + ":period:" + period.id
                prior = next((x for x in known if x.id == identity), None)
                if prior and prior.stage != "withdrawn":
                    continue
                try:
                    girls, _ = self._qualification(c, state, source, period)
                except NotQualified:
                    continue
                if any(int(x.entity) == viewer.user_id for x in girls):
                    # Withdrawn proposals remain history; this is the same optional slot.
                    result = [x for x in result if x["id"] != identity]
                    result.append(
                        dict(
                            id=identity,
                            revision=state.revision,
                            state="available",
                            actionable=True,
                            title="Optional collective Handler Tag",
                        )
                    )
        return result

    def _close_work(self, c: Connection, identity: str, event: str) -> None:
        work = t.m3["m3_required_work"]
        latest = {
            row["id"]: dict(row)
            for row in c.execute(
                sa.select(work)
                .where(
                    work.c.campaign_id == self.store.campaign_id,
                    work.c.kind == "collective_handler_tag_vote",
                    sa.func.json_extract(work.c.body_json, "$.proposal") == identity,
                )
                .order_by(work.c.revision)
            ).mappings()
        }
        for row in latest.values():
            if row["state"] != "resolved":
                c.execute(
                    work.insert().values(
                        **(
                            row
                            | dict(revision=row["revision"] + 1, state="resolved", event_id=event)
                        )
                    )
                )

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        entitlement: str,
        period: str,
        expected: int,
        label: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            source = self._entitlement(c, state, entitlement)
            actual_period = self._period(c, period)
            girls, roll_event = self._qualification(c, state, source, actual_period)
            girl = next((x for x in girls if int(x.entity) == viewer.user_id), None)
            identity = entitlement + ":period:" + period
            old = next((x for x in rules.proposals(state) if x.id == identity), None)
            if state.revision != expected or old and old.stage != "withdrawn":
                raise WorkflowError("STALE_COLLECTIVE_TAG: reopen the actual period opportunity")
            if girl is None:
                raise WorkflowError("Only an actual original Girl proposes her collective Tag")
            if old:
                self._proposal(c, state, identity)
            event = str(uuid4())
            value = rules.Proposal(
                id=identity,
                revision=old.revision + 1 if old else 1,
                entitlement=entitlement,
                period=period,
                handler=source.handler,
                girls=girls,
                roll_event=roll_event,
                proposer=girl,
                label=label,
                account=account,
                votes=(girl,),
                stage="proposed",
                event=event,
            )
            value = rules.apply(state, value, event)
            rules.save(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.collective_tag_proposed",
                state,
                event_id=event,
                proposal=identity,
                period_id=period,
            )
            if value.stage == "proposed":
                for member in girls:
                    if member == girl:
                        continue
                    related(
                        c,
                        self.store,
                        dict(campaign_id=self.store.campaign_id, off_duty_id=period),
                        identity + ":proposal:" + str(value.revision) + ":vote:" + member.entity,
                        int(member.entity),
                        int(source.handler.entity),
                        "collective_handler_tag_vote",
                        dict(
                            proposal=identity, member=member.model_dump(mode="json"), immediate=True
                        ),
                        event,
                    )
            return dict(id=identity, state=value.stage)

        return self._write(
            viewer,
            key,
            "m3.collective_tag_proposed",
            dict(
                entitlement=entitlement,
                period=period,
                expected=expected,
                label=label,
                account=account,
            ),
            operation,
        )

    def respond(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, decision: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = self._proposal(c, state, identity)
            girl = next((x for x in value.girls if int(x.entity) == viewer.user_id), None)
            if (
                state.revision != expected
                or value.stage != "proposed"
                or self._period(c, value.period).phase != "active"
            ):
                raise WorkflowError("STALE_COLLECTIVE_TAG: reopen the actual original proposal")
            if girl is None or not original_girl_alive(state, girl):
                raise WorkflowError("Only this actual living original Girl supplies her agreement")
            if not same_handler_body(state, value.handler):
                raise WorkflowError("Review the actual original Handler's ending first")
            event = str(uuid4())
            if decision == "withdraw" and girl == value.proposer:
                updated = value.model_copy(update=dict(stage="withdrawn"))
            elif decision == "decline":
                updated = value.model_copy(update=dict(stage="declined"))
            elif decision == "agree" and girl not in value.votes:
                updated = value.model_copy(update=dict(votes=value.votes + (girl,)))
                updated = rules.apply(state, updated, event)
            else:
                raise WorkflowError(
                    "Choose your own outstanding agreement, decline or proposal withdrawal"
                )
            updated = updated.model_copy(update=dict(revision=value.revision + 1, event=event))
            rules.save(state, updated)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.collective_tag_answered",
                state,
                event_id=event,
                proposal=identity,
                decision=decision,
                original=girl.model_dump(mode="json"),
            )
            if updated.stage != "proposed":
                self._close_work(c, identity, event)
            else:
                work = t.m3["m3_required_work"]
                latest = {
                    row["id"]: dict(row)
                    for row in c.execute(
                        sa.select(work)
                        .where(
                            work.c.campaign_id == self.store.campaign_id,
                            work.c.kind == "collective_handler_tag_vote",
                            work.c.owner_id == str(viewer.user_id),
                            sa.func.json_extract(work.c.body_json, "$.proposal") == identity,
                        )
                        .order_by(work.c.revision)
                    ).mappings()
                }
                for row in latest.values():
                    if row["state"] != "resolved":
                        c.execute(
                            work.insert().values(
                                **(
                                    row
                                    | dict(
                                        revision=row["revision"] + 1,
                                        state="resolved",
                                        event_id=event,
                                    )
                                )
                            )
                        )
            return dict(id=identity, state=updated.stage, tag=updated.tag)

        return self._write(
            viewer,
            key,
            "m3.collective_tag_answered",
            dict(id=identity, expected=expected, decision=decision),
            operation,
        )

    def review_endings(
        self, viewer: GuildViewer, key: str, identity: str, expected: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_harpy_defeat import ended_actor_source

            state = load_state(c, self.store.campaign_id)
            value = self._proposal(c, state, identity)
            if viewer.user_id != state.handler and not any(
                int(x.entity) == viewer.user_id for x in value.girls
            ):
                raise WorkflowError(
                    "Only actual source participants or the facilitator review this ending"
                )
            if state.revision != expected or value.stage != "proposed":
                raise WorkflowError("STALE_COLLECTIVE_TAG: reopen the actual original proposal")
            ended = tuple(
                x for x in value.girls if not original_girl_alive(state, x) and x not in value.ended
            )
            handler_ended = not same_handler_body(state, value.handler)
            bodies = ended + ((value.handler,) if handler_ended else ())
            proofs = {x.token: ended_actor_source(self.game, c, state, x) for x in bodies}
            if not bodies or any(x is None for x in proofs.values()):
                raise WorkflowError(
                    "Prove the actual original endings; no replacement or timeout supplies consent"
                )
            event = str(uuid4())
            updated = value.model_copy(
                update=dict(ended=value.ended + ended, revision=value.revision + 1, event=event)
            )
            if handler_ended or not (set(updated.girls) - set(updated.ended)):
                updated = updated.model_copy(update=dict(stage="original_ended"))
            else:
                updated = rules.apply(state, updated, event)
            rules.save(state, updated)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.collective_tag_original_endings_reviewed",
                state,
                event_id=event,
                proposal=identity,
                ending_sources=proofs,
            )
            if updated.stage != "proposed":
                self._close_work(c, identity, event)
            return dict(id=identity, state=updated.stage)

        return self._write(
            viewer,
            key,
            "m3.collective_tag_original_endings_reviewed",
            dict(id=identity, expected=expected),
            operation,
        )

    def close_uninstalled(
        self, viewer: GuildViewer, key: str, identity: str, expected: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_harpy_defeat import ended_actor_source

            row, original = _selection(c, self.game, identity, rule=RULE)
            state = load_state(c, self.store.campaign_id)
            handler = active_handler(original)
            if handler is None or viewer.user_id not in (original.handler, state.handler):
                raise WorkflowError(
                    "Only the original human or actual facilitator reviews this ending"
                )
            if (
                row["state"] != "pending"
                or state.revision != expected
                or any(x.id == identity for x in rules.entitlements(state))
            ):
                raise WorkflowError("STALE_COLLECTIVE_TAG: reopen the actual selected Endgame")
            ending = ended_actor_source(self.game, c, state, handler)
            if same_handler_body(state, handler) or ending is None:
                raise WorkflowError("Prove this actual original Handler's ending first")
            event = str(uuid4())
            state.facts.append(
                dict(
                    kind="collective_tag_uninstalled_original_ended",
                    source_work=identity,
                    handler=handler.model_dump_json(),
                    ending_event=ending,
                    event=event,
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.collective_tag_uninstalled_original_ended",
                state,
                event_id=event,
                source_work=identity,
                ending_event=ending,
            )
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **(row | dict(revision=row["revision"] + 1, state="resolved", event_id=event))
                )
            )
            return dict(id=identity, state="original_ended")

        return self._write(
            viewer,
            key,
            "m3.collective_tag_uninstalled_original_ended",
            dict(id=identity, expected=expected),
            operation,
        )
