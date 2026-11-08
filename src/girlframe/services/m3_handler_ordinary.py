"""Actual facilitator sessions, legal Identity provenance and one real ordinary award."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_advancements as advancement
from girlframe.engine import m3_handler_ordinary as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_handler_advancements import (
    HandlerAdvancementService,
    _appointment_at,
    _history,
)
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def evidence(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> rules.Evidence:
    if (
        actor.kind != "pilot"
        or actor.entity not in state.sheets
        or current_ref(state, int(actor.entity)) != actor
    ):
        raise WorkflowError("Use the actual original current Girl, not another generation")
    table = t.m2["m2_state_history"]
    history = list(
        c.execute(
            sa.select(t.events, table.c.body_json)
            .join(table, table.c.event_id == t.events.c.id)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                t.events.c.campaign_id == game.store.campaign_id,
                table.c.revision <= state.revision,
            )
            .order_by(t.events.c.seq)
        ).mappings()
    )
    baseline = None
    previous = None
    tracks: dict[str, str] = {}
    chains: dict[str, list[rules.Edge]] = {}
    for event in history:
        after = GameState.model_validate_json(event["body_json"])
        sheet = after.sheets.get(actor.entity)
        if baseline is None:
            if (
                event["kind"] == "m2.character_activated"
                and event["actor_id"] == actor.entity
                and sheet is not None
                and sheet.character_id == actor.incarnation
            ):
                baseline = str(event["id"])
                tracks = {x.id: x.id for x in sheet.identities}
                chains = {x.id: [] for x in sheet.identities}
            previous = after
            continue
        if (
            previous is not None
            and event["kind"] in ("m2.choice_resolved", "m3.choice_resolved")
            and sheet is not None
            and sheet.character_id == actor.incarnation
        ):
            payload = json.loads(event["payload_json"])
            choice = (
                c.execute(
                    sa.select(t.m2["m2_choices"]).where(
                        t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                        t.m2["m2_choices"].c.id == payload.get("choice_id"),
                    )
                )
                .mappings()
                .first()
            )
            response = (
                c.execute(
                    sa.select(t.m2["m2_responses"]).where(
                        t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
                        t.m2["m2_responses"].c.choice_id == payload.get("choice_id"),
                        t.m2["m2_responses"].c.event_id == event["id"],
                    )
                )
                .mappings()
                .first()
            )
            if (
                choice is not None
                and response is not None
                and choice["kind"] == "tag_resolution"
                and choice["actor_id"] == response["actor_id"] == event["actor_id"] == actor.entity
            ):
                answer = ChoiceAnswer.model_validate_json(response["answer_json"])
                old_sheet = previous.sheets.get(actor.entity)
                action = game.action(c, choice["action_id"])
                tag = (
                    next(
                        (
                            x
                            for x in old_sheet.tags
                            if x.id == json.loads(choice["body_json"])["tag"]
                        ),
                        None,
                    )
                    if old_sheet
                    else None
                )
                added = [
                    x
                    for x in sheet.identities
                    if old_sheet and x.id not in {y.id for y in old_sheet.identities}
                ]
                if (
                    answer.options == ("embrace",)
                    and len(answer.denied) == 1
                    and old_sheet is not None
                    and old_sheet.character_id == actor.incarnation
                    and tag is not None
                    and len(added) == 1
                    and added[0].name == tag.label
                    and answer.denied[0] not in {x.id for x in sheet.identities}
                    and action["actor_id"] == actor.entity
                    and action["data"].get("character_ids", {}).get(actor.entity)
                    == actor.incarnation
                    and payload.get("action_id") == choice["action_id"]
                ):
                    edge = rules.Edge(
                        old=answer.denied[0],
                        new=added[0].id,
                        name=added[0].name,
                        event=str(event["id"]),
                        choice=choice["id"],
                        action=choice["action_id"],
                    )
                    for starting, current in tracks.items():
                        if current == edge.old:
                            tracks[starting] = edge.new
                            chains[starting].append(edge)
        previous = after
    endpoints = {x.id: x for x in state.sheets[actor.entity].identities}
    if (
        baseline is None
        or not tracks
        or any(
            not chains[start]
            or target == start
            or target not in endpoints
            or endpoints[target].name != chains[start][-1].name
            for start, target in tracks.items()
        )
    ):
        raise WorkflowError(
            "Every actual starting Identity needs its legal Tag-embrace replacement chain"
        )
    return rules.Evidence(
        actor=actor,
        activation=baseline,
        chains=tuple(
            rules.Chain(
                starting=start,
                current=target,
                name=endpoints[target].name,
                edges=tuple(chains[start]),
            )
            for start, target in tracks.items()
        ),
    )


def _session(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Session:
    value = next((x for x in rules.sessions(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual campaign Session")
    born = next(
        (x for x in rules.sessions(_history(c, game, value.start_event)) if x.id == identity), None
    )
    audit = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.start_event
            )
        )
        .mappings()
        .first()
    )
    if (
        born is None
        or audit is None
        or audit["kind"] != "m3.campaign_session_started"
        or audit["actor_id"] != str(value.facilitator)
        or born != value.model_copy(update=dict(end_event=None, ended_at=None, end_account=None))
    ):
        raise WorkflowError("Recover the actual human facilitator's immutable session start")
    return value


def _review(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Review:
    value = next((x for x in rules.reviews(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual original Identity review")
    session = _session(game, c, state, value.session)
    source = next(
        (x for x in rules.reviews(_history(c, game, value.request_event)) if x.id == identity), None
    )
    if (
        source is None
        or any(
            getattr(source, k) != getattr(value, k)
            for k in (
                "id",
                "session",
                "handler",
                "appointment",
                "evidence",
                "request_event",
                "account",
            )
        )
        or session.facilitator != int(value.handler.entity)
        or session.appointment != value.appointment
    ):
        raise WorkflowError("Recover this original Handler's actual Identity review source")
    return value


def prove_award(
    game: GameService, c: Connection, state: GameState, award: advancement.Award
) -> None:
    source = award.ordinary_source
    if source is None or award.rule != rules.RULE or award.source_work is not None:
        raise WorkflowError("Recover the exact real ordinary advancement source")
    if source.trigger == "capture_convert":
        from girlframe.services.m3_handler_conversion import prove_award as prove_conversion

        prove_conversion(game, c, state, award)
        return
    if source.trigger == "public_relations":
        from girlframe.services.m3_handler_pr import prove_award as prove_pr

        prove_pr(game, c, state, award)
        return
    birth = _history(c, game, award.award_event)
    born = next((x for x in advancement.awards(birth) if x.id == award.id), None)
    review = _review(game, c, birth, source.review)
    session = _session(game, c, birth, source.session)
    audit = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == award.award_event
            )
        )
        .mappings()
        .first()
    )
    if (
        born is None
        or born.phase != "held"
        or any(
            getattr(born, k) != getattr(award, k)
            for k in (
                "id",
                "rule",
                "handler",
                "appointment",
                "source_work",
                "source_event",
                "award_event",
                "account",
                "ordinary_source",
            )
        )
        or audit is None
        or audit["kind"] != "m3.handler_ordinary_awarded"
        or audit["actor_id"] != award.handler.entity
        or review.phase != "awarded"
        or review.award != award.id
        or review.judgment_event != award.award_event
        or review.judgment_session != source.session
        or review.handler != award.handler
        or session.end_event is not None
        or _appointment_at(c, game, session.start_event, award.handler) != award.appointment
        or review.evidence != evidence(game, c, birth, review.evidence.actor)
    ):
        raise WorkflowError("Recover actual Session, legal replacements and real usefulness award")
    disclosed = next(
        (
            x
            for x in rules.reviews(_history(c, game, review.decision_event or ""))
            if x.id == review.id
        ),
        None,
    )
    if (
        disclosed is None
        or disclosed.phase != "usefulness"
        or disclosed.evidence != review.evidence
    ):
        raise WorkflowError("Recover the original Girl's actual scoped disclosure")
    expected = {x.current for x in review.evidence.chains}
    if set(review.reasons) != expected or not all(x.strip() for x in review.reasons.values()):
        raise WorkflowError("Every actual replacement needs the Handler's usefulness judgment")
    relevant = [x for x in rules.marks(birth) if x.handler == award.handler]
    if (
        len([x for x in relevant if x.session == source.session]) != 1
        or len([x for x in relevant if x.trigger == source.trigger]) != 1
        or not any(
            x.award == award.id and x.review == review.id and x.event == award.award_event
            for x in relevant
        )
    ):
        raise WorkflowError(
            "Preserve the real ordinary session cap and permanent criterion mark-off"
        )


class HandlerOrdinaryService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "playbooks", director_response=True)
        gate.authorize(c, viewer, "economy", director_response=True)
        assert gate.registry is not None
        gate.registry.require_available(rules.RULE)

    def _write(
        self, viewer: GuildViewer, key: str, kind: str, payload: dict[str, Any], operation: Any
    ) -> dict[str, Any]:
        try:
            return self.store._write(
                viewer,
                key,
                kind,
                payload,
                operation,
                auto_audit=False,
                authorize=lambda c: self._access(c, viewer),
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def record_session(
        self, viewer: GuildViewer, key: str, revision: int, name: str, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            human, appointment = MedicalService(self.store)._handler(c)
            state = load_state(c, self.store.campaign_id)
            if (
                viewer.user_id != human
                or state.revision != revision
                or any(x.end_event is None for x in rules.sessions(state))
                or not account.strip()
            ):
                raise WorkflowError(
                    "Record one actual session start as the authorized human facilitator"
                )
            event = str(uuid4())
            value = rules.Session(
                id="campaign-session:" + event,
                facilitator=human,
                appointment=appointment,
                name=name.strip(),
                start_event=event,
                started_at=datetime.now(UTC).isoformat(),
                account=account.strip(),
            )
            rules.put(state, value)
            self.game.event(
                c,
                human,
                key,
                "m3.campaign_session_started",
                state,
                event_id=event,
                session_id=value.id,
            )
            return dict(id=value.id, phase="active")

        return self._write(
            viewer,
            key,
            "m3.campaign_session_started",
            dict(revision=revision, name=name, account=account),
            operation,
        )

    def end_session(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = _session(self.game, c, state, identity)
            if (
                value.facilitator != viewer.user_id
                or value.end_event
                or state.revision != revision
                or self.game.pending_actions(c)
                or not account.strip()
            ):
                raise WorkflowError(
                    "The real facilitator records the actual session end after pending Play"
                )
            event = str(uuid4())
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        end_event=event,
                        ended_at=datetime.now(UTC).isoformat(),
                        end_account=account.strip(),
                    )
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.campaign_session_ended",
                state,
                event_id=event,
                session_id=identity,
            )
            return dict(id=identity, phase="ended")

        return self._write(
            viewer,
            key,
            "m3.campaign_session_ended",
            dict(id=identity, revision=revision, account=account),
            operation,
        )

    def request_review(
        self,
        viewer: GuildViewer,
        key: str,
        session_id: str,
        revision: int,
        girl: ActorRef,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            session = _session(self.game, c, state, session_id)
            handler = active_handler(state)
            if (
                handler is None
                or handler.entity != str(viewer.user_id)
                or session.facilitator != viewer.user_id
                or session.end_event
                or state.revision != revision
                or self.game.pending_actions(c)
                or not account.strip()
            ):
                raise WorkflowError("Use this actual active Session and original Handler")
            HandlerAdvancementService(self.store)._current(c, state, handler, session.appointment)
            if any(
                same_handler_body(state, x.handler) and x.trigger == "identities_useful"
                for x in rules.marks(state)
            ) or any(
                x.handler == handler and x.phase in ("disclosure", "usefulness")
                for x in rules.reviews(state)
            ):
                raise WorkflowError("This criterion is already marked off or has an owned review")
            actual = evidence(self.game, c, state, girl)
            event = str(uuid4())
            value = rules.Review(
                id="identity-review:" + event,
                session=session_id,
                handler=handler,
                appointment=session.appointment,
                evidence=actual,
                request_event=event,
                account=account.strip(),
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_identity_review_requested",
                state,
                event_id=event,
                review_id=value.id,
            )
            return dict(id=value.id, phase=value.phase)

        return self._write(
            viewer,
            key,
            "m3.handler_identity_review_requested",
            dict(
                session=session_id,
                revision=revision,
                girl=girl.model_dump(mode="json"),
                account=account,
            ),
            operation,
        )

    def disclose(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        accept: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            review = _review(self.game, c, state, identity)
            if (
                review.phase != "disclosure"
                or review.evidence.actor.entity != str(viewer.user_id)
                or state.revision != revision
                or review.evidence != evidence(self.game, c, state, review.evidence.actor)
                or not account.strip()
            ):
                raise WorkflowError(
                    "The original Girl controls disclosure of these actual Identities"
                )
            event = str(uuid4())
            phase = "usefulness" if accept else "declined"
            rules.put(
                state,
                review.model_copy(
                    update=dict(phase=phase, decision_event=event, decision_account=account.strip())
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_identity_disclosed"
                if accept
                else "m3.handler_identity_disclosure_declined",
                state,
                event_id=event,
                review_id=identity,
            )
            return dict(id=identity, phase=phase)

        return self._write(
            viewer,
            key,
            "m3.handler_identity_disclosed",
            dict(id=identity, revision=revision, accept=accept, account=account),
            operation,
        )

    def grant_identity_award(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        reasons: dict[str, str],
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            review = _review(self.game, c, state, identity)
            active = next(
                (
                    x
                    for x in rules.sessions(state)
                    if x.end_event is None and x.facilitator == viewer.user_id
                ),
                None,
            )
            if active is None:
                raise WorkflowError(
                    "Use the actual current campaign Session for usefulness judgment"
                )
            session = _session(self.game, c, state, active.id)
            HandlerAdvancementService(self.store)._current(
                c, state, review.handler, review.appointment
            )
            if (
                review.handler.entity != str(viewer.user_id)
                or review.phase != "usefulness"
                or session.end_event
                or state.revision != revision
                or review.evidence != evidence(self.game, c, state, review.evidence.actor)
                or set(reasons) != {x.current for x in review.evidence.chains}
                or not all(x.strip() and len(x) <= 1200 for x in reasons.values())
                or not account.strip()
                or any(
                    same_handler_body(state, x.handler)
                    and (x.session == session.id or x.trigger == "identities_useful")
                    for x in rules.marks(state)
                )
            ):
                raise WorkflowError(
                    "Judge every actual replacement useful once within the real session cap"
                )
            event = str(uuid4())
            award_id = "ordinary:" + identity
            rules.put(
                state,
                review.model_copy(
                    update=dict(
                        phase="awarded",
                        judgment_event=event,
                        judgment_session=session.id,
                        reasons=reasons,
                        award=award_id,
                    )
                ),
            )
            rules.put(
                state,
                rules.Mark(
                    id="identity-mark:" + review.handler.token,
                    handler=review.handler,
                    session=session.id,
                    review=identity,
                    award=award_id,
                    event=event,
                ),
            )
            award = advancement.Award(
                id=award_id,
                rule=rules.RULE,
                handler=review.handler,
                appointment=review.appointment,
                source_work=None,
                ordinary_source=rules.AwardSource(session=session.id, review=identity),
                source_event=event,
                award_event=event,
                account=account.strip(),
            )
            advancement.grant(state, award)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_ordinary_awarded",
                state,
                event_id=event,
                award_id=award_id,
                rule_id=rules.RULE,
                session_id=session.id,
            )
            return dict(id=award_id, phase="held")

        return self._write(
            viewer,
            key,
            "m3.handler_ordinary_awarded",
            dict(id=identity, revision=revision, reasons=reasons, account=account),
            operation,
        )

    def menu(self, viewer: GuildViewer, identity: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            human, appointment = MedicalService(self.store)._handler(c)
            if identity and identity.startswith("identity-review:"):
                review = _review(self.game, c, state, identity)
                own = review.evidence.actor.entity == str(viewer.user_id)
                if not own and review.handler.entity != str(viewer.user_id):
                    raise WorkflowError("This private review belongs to its original participants")
                return dict(
                    kind="review",
                    id=identity,
                    revision=state.revision,
                    phase=review.phase,
                    own=own,
                    identities=[dict(id=x.current, name=x.name) for x in review.evidence.chains]
                    if own or review.phase in ("usefulness", "awarded")
                    else [],
                    award=review.award,
                )
            selected = _session(self.game, c, state, identity) if identity else None
            if selected is not None and selected.facilitator != viewer.user_id:
                raise WorkflowError("This actual session history belongs to its facilitator")
            active = next(
                (
                    x
                    for x in rules.sessions(state)
                    if x.end_event is None and x.facilitator == viewer.user_id
                ),
                None,
            )
            return dict(
                selected=selected.model_dump(mode="json") if selected else None,
                active=active.model_dump(mode="json") if active else None,
                kind="session",
                revision=state.revision,
                facilitator=human == viewer.user_id,
                appointment=appointment,
                sessions=[
                    dict(id=x.id, name=x.name, phase="ended" if x.end_event else "active")
                    for x in rules.sessions(state)
                    if x.facilitator == viewer.user_id
                ],
                girls=[
                    dict(
                        actor=current_ref(state, uid).model_dump(mode="json"),
                        token=current_ref(state, uid).token,
                        label=state.sheets[str(uid)].callsign,
                    )
                    for uid in state.order
                ]
                if human == viewer.user_id
                else [],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        values = [
            dict(
                id=x.id,
                revision=state.revision,
                label="Actual campaign Session — " + x.name,
                phase="ended" if x.end_event else "active",
                pending=False,
            )
            for x in rules.sessions(state)
            if x.facilitator == viewer.user_id
        ]
        for review in rules.reviews(state):
            own = review.evidence.actor.entity == str(viewer.user_id)
            handler = review.handler.entity == str(viewer.user_id)
            if own or handler:
                values.append(
                    dict(
                        id=review.id,
                        revision=state.revision,
                        label="Starting Identity advancement — " + review.phase,
                        phase=review.phase,
                        pending=own
                        and review.phase == "disclosure"
                        or handler
                        and review.phase == "usefulness",
                    )
                )
        return values
