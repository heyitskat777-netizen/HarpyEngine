"""Human attendance, disclosed Tag rights and actual completion, without invented acts."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_political_function as rules
from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class FunctionService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _proof(self, c: Connection, state: GameState, identity: str) -> rules.Function:
        record = rules.get(state, identity)
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == record.source_event,
            )
        )
        original = GameState.model_validate_json(raw) if raw else None
        event = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == record.source_event,
                )
            )
            .mappings()
            .first()
        )
        source = rules.get(original, identity) if original else None
        immutable = (
            "id",
            "source_work",
            "source_event",
            "period",
            "patron",
            "handler",
            "kind",
            "notice",
            "people",
            "account",
        )
        if (
            source is None
            or event is None
            or event["kind"] != "m3.strain_effect_applied"
            or event["actor_id"] != record.handler.entity
            or json.loads(event["payload_json"]).get("rule_id") != "strain.budget.low.2.1"
            or json.loads(event["payload_json"]).get("work_id") != record.source_work
            or any(getattr(source, k) != getattr(record, k) for k in immutable)
        ):
            raise WorkflowError("Recover the actual original function and disclosed source")
        return record

    def _person(self, state: GameState, record: rules.Function, user: int) -> ActorRef | None:
        person = next((x for x in record.people if x.entity == str(user)), None)
        sheet = state.sheets.get(str(user))
        if not person or not sheet or sheet.character_id != person.incarnation:
            return None
        return person if user in state.order else None

    def available(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        for record in rules.functions(state):
            if record.phase == "complete":
                continue
            if (
                self._person(state, record, viewer.user_id)
                or viewer.user_id == int(record.handler.entity)
                and same_handler_body(state, record.handler)
            ):
                result.append(dict(id=record.id, kind=record.kind, phase=record.phase))
        return result

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            Access(self.store).authorize(c, viewer, "strain")
            state = load_state(c, self.store.campaign_id)
            record = self._proof(c, state, identity)
            person = self._person(state, record, viewer.user_id)
            handler = viewer.user_id == int(record.handler.entity) and same_handler_body(
                state, record.handler
            )
            if not person and not handler:
                raise WorkflowError("This actual function belongs to its original participants")
            return dict(
                id=identity,
                revision=state.revision,
                kind=record.kind,
                phase=record.phase,
                notice=record.notice,
                handler=handler,
                attended=bool(person in record.attended),
                people=[
                    dict(label=state.sheets[x.entity].callsign, attended=x in record.attended)
                    for x in record.people
                    if x.entity in state.sheets
                    and state.sheets[x.entity].character_id == x.incarnation
                ],
            )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        action: str,
        account: str,
        label: str = "",
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200 or len(label) > 120:
            raise WorkflowError("Describe your actual attendance, action or ending")

        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "strain")
            state = load_state(c, self.store.campaign_id)
            record = self._proof(c, state, identity)
            if not self._person(state, record, viewer.user_id) and viewer.user_id != int(
                record.handler.entity
            ):
                raise WorkflowError("Only an original function participant may respond")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            record = self._proof(c, state, identity)
            if (
                state.revision != expected
                or record.phase == "complete"
                or not same_handler_body(state, record.handler)
            ):
                raise WorkflowError("STALE_FUNCTION: reopen the original active function")
            person = self._person(state, record, viewer.user_id)
            event, tag_id = str(uuid4()), None
            if action == "attend":
                if person is None or person in record.attended or record.phase != "attendance":
                    raise WorkflowError(
                        "Only this original Girl confirms her actual informed attendance"
                    )
                attended = (*record.attended, person)
                record = record.model_copy(
                    update=dict(
                        attended=attended,
                        phase="active" if set(attended) == set(record.people) else "attendance",
                    )
                )
            elif action == "tag":
                if (
                    person is None
                    or person not in record.attended
                    or record.phase != "active"
                    or not label.strip()
                ):
                    raise WorkflowError(
                        "Only an informed attending Girl can report her own out-of-line action"
                    )
                tag_id = str(uuid4())
                state.handler_tags.append(
                    TagState(
                        id=tag_id,
                        label=label.strip(),
                        giver=viewer.user_id,
                        giver_actor=person,
                        observers=tuple(
                            dict.fromkeys((viewer.user_id, int(record.handler.entity)))
                        ),
                    )
                )
            elif action == "end":
                if viewer.user_id != int(record.handler.entity) or record.phase != "active":
                    raise WorkflowError("The original Handler ends the actual attended function")
                record = record.model_copy(update=dict(phase="complete", ended_event=event))
            else:
                raise WorkflowError("Choose an actual informed attendance, own action or ending")
            rules.put(state, record)
            state.facts.append(
                dict(
                    kind="political_function_action",
                    function=identity,
                    event=event,
                    action=action,
                    account=account,
                    actor=str(viewer.user_id),
                    tag=tag_id or "",
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.political_function_action",
                state,
                event_id=event,
                function=identity,
                action=action,
                tag=tag_id,
            )
            if action == "end":
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
                    raise WorkflowError("Recover this actual pending function work")
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
            return dict(id=identity, phase=record.phase, tag=tag_id)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.political_function_action",
                dict(id=identity, expected=expected, action=action, account=account, label=label),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
