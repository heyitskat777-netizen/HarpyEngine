"""Table-owned exact process, actual assigned assessment and durable completion."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_budget_candidate as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class CandidateService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _proof(self, c: Connection, state: GameState, identity: str) -> rules.Assessment:
        value = rules.get(state, identity)
        source = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == value.source_event,
                )
            )
            .mappings()
            .first()
        )
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == value.source_event,
            )
        )
        original = rules.get(GameState.model_validate_json(raw), identity) if raw else None
        immutable = (
            "id",
            "source_work",
            "source_event",
            "period",
            "handler",
            "candidate",
            "assessor",
            "controller",
            "humans",
            "people",
            "account",
        )
        if (
            source is None
            or source["kind"] != "m3.strain_effect_applied"
            or source["actor_id"] != value.handler.entity
            or json.loads(source["payload_json"]).get("rule_id") != "strain.budget.high.4.2"
            or json.loads(source["payload_json"]).get("work_id") != value.source_work
            or original is None
            or any(getattr(original, k) != getattr(value, k) for k in immutable)
        ):
            raise WorkflowError("Recover the original Candidate, assessor and Strain source")
        return value

    def available(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        return [
            dict(id=x.id, phase=x.phase)
            for x in rules.assessments(load_state(c, self.store.campaign_id))
            if viewer.user_id in x.humans and x.phase != "complete"
        ]

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            Access(self.store).authorize(c, viewer, "strain")
            state = load_state(c, self.store.campaign_id)
            value = self._proof(c, state, identity)
            if viewer.user_id not in value.humans:
                raise WorkflowError("This process belongs to its original table")
            return dict(
                id=identity,
                revision=state.revision,
                phase=value.phase,
                process=value.process,
                approved=viewer.user_id in value.approvals,
                assessor=viewer.user_id == int(value.assessor.entity),
                waiting=len(value.humans) - len(value.approvals),
            )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        action: str,
        account: str,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Write your own process proposal, agreement or actual assessment")

        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "strain")
            if (
                viewer.user_id
                not in self._proof(c, load_state(c, self.store.campaign_id), identity).humans
            ):
                raise WorkflowError("Only an original table member may respond")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = self._proof(c, state, identity)
            body = (
                next(
                    (x for x in state.world.npcs if x.id == value.candidate.entity and x.alive),
                    None,
                )
                if state.world
                else None
            )
            if (
                state.revision != expected
                or value.phase == "complete"
                or body is None
                or body.controller != value.controller
                or "pilot_candidate" not in body.jobs
                or not same_handler_body(state, value.handler)
                or any(current_ref(state, int(x.entity)) != x for x in value.people)
            ):
                raise WorkflowError("STALE_CANDIDATE: reopen the original living participants")
            event = str(uuid4())
            if action == "propose" and value.phase == "process":
                value = value.model_copy(
                    update=dict(process=account.strip(), approvals=(viewer.user_id,))
                )
            elif (
                action == "agree"
                and value.phase == "process"
                and value.process
                and viewer.user_id not in value.approvals
            ):
                approvals = (*value.approvals, viewer.user_id)
                value = value.model_copy(
                    update=dict(
                        approvals=approvals,
                        phase="assessing" if set(approvals) == set(value.humans) else "process",
                    )
                )
            elif (
                action == "assess"
                and value.phase == "assessing"
                and viewer.user_id == int(value.assessor.entity)
            ):
                value = value.model_copy(
                    update=dict(
                        phase="complete",
                        report=account.strip(),
                        ended_event=event,
                    )
                )
            else:
                raise WorkflowError(
                    "Choose your own proposal, exact agreement or assigned assessment"
                )
            value = rules.Assessment.model_validate_json(value.model_dump_json())
            rules.put(state, value)
            state.facts.append(
                dict(
                    kind="budget_candidate_action",
                    candidate=identity,
                    action=action,
                    actor=str(viewer.user_id),
                    event=event,
                    account=account.strip(),
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.budget_candidate_changed",
                state,
                event_id=event,
                candidate=identity,
                action=action,
            )
            if value.phase == "complete":
                work = t.m3["m3_required_work"]
                row = (
                    c.execute(
                        sa.select(work)
                        .where(
                            work.c.campaign_id == self.store.campaign_id,
                            work.c.id == identity,
                        )
                        .order_by(work.c.revision.desc())
                        .limit(1)
                    )
                    .mappings()
                    .one()
                )
                if row["state"] != "pending":
                    raise WorkflowError("Recover the pending original assessment work")
                c.execute(
                    work.insert().values(
                        **(
                            dict(row)
                            | dict(
                                revision=row["revision"] + 1,
                                state="resolved",
                                event_id=event,
                            )
                        )
                    )
                )
            return dict(id=identity, phase=value.phase)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.budget_candidate_changed",
                dict(id=identity, expected=expected, action=action, account=account),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
