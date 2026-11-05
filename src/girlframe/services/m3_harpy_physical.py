"""Actual Harpy Frame voice and independently reviewed physical help, without Pilot proxies."""

import hashlib
import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_harpy_physical as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import owned_refs, resolve
from girlframe.engine.m3_harpy_defeat import harpy
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_void import _append
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KIND = "harpy_physical_help"


def physical_fingerprint(state: GameState, actor: ActorRef) -> str:
    body = harpy(state, actor)
    return hashlib.sha256(
        json.dumps(
            dict(
                body=body.model_dump(mode="json"),
                gates=[
                    x.model_dump(mode="json")
                    for x in state.frame_locks
                    if x.owner == actor and x.frame_instance == body.frame_instance
                ],
            ),
            sort_keys=True,
        ).encode()
    ).hexdigest()


class HarpyPhysicalService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        Access(self.store).authorize(c, viewer, "world", director_response=True)

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
            raise WorkflowError("Open the actual original Harpy physical-help request.")
        return dict(row)

    def _actors(
        self, c: Connection, state: GameState, viewer: GuildViewer, actor: ActorRef
    ) -> list[dict[str, Any]]:
        body = harpy(state, actor)
        casts = [x for x in state.scene_casts if x.open and any(r.actor == actor for r in x.roles)]
        audience = (
            {body.controller}
            | {x.facilitator for x in casts if x.facilitator is not None}
            | {r.controller for x in casts for r in x.roles}
        )
        if viewer.user_id not in audience:
            raise WorkflowError(
                "Join the actual original Harpy's source scene before viewing its physical state."
            )
        available = []
        for ref in owned_refs(state, viewer.user_id, profiles(c, self.store.campaign_id)):
            if ref == actor or not any(
                any(r.actor == ref and r.controller == viewer.user_id for r in x.roles)
                for x in casts
            ):
                continue
            view = resolve(
                state, ref, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if view.alive:
                available.append(
                    dict(ref=ref.model_dump(mode="json"), token=ref.token, label=view.label)
                )
        return available

    def _proof(self, c: Connection, state: GameState, actor: ActorRef) -> None:
        body = harpy(state, actor)
        gates = [
            x
            for x in state.frame_locks
            if x.owner == actor and x.frame_instance == body.frame_instance
        ]
        if not gates:
            raise WorkflowError("This actual Harpy has no source-created cockpit subsumption.")
        gate = gates[-1]
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == gate.source_event,
            )
        )
        proof = GameState.model_validate_json(raw) if raw else None
        original = next((x for x in proof.frame_locks if x.id == gate.id), None) if proof else None
        if original is None or any(
            getattr(original, k) != getattr(gate, k)
            for k in ("owner", "subject", "frame_instance", "source_event")
        ):
            raise WorkflowError(
                "SOURCE_HARPY_LOCK_MISSING: recover the actual original subsumption event."
            )
        if not gate.active:
            raw = c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json).where(
                    t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_state_history"].c.event_id == gate.released_event,
                )
            )
            opening_audit = c.execute(
                sa.select(t.events.c.kind, t.events.c.actor_id).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == gate.released_event,
                )
            ).first()
            opened = GameState.model_validate_json(raw) if raw else None
            actual_gate = (
                next((x for x in opened.frame_locks if x.id == gate.id), None) if opened else None
            )
            if (
                actual_gate is None
                or actual_gate.active
                or actual_gate.released_event != gate.released_event
                or opening_audit is None
                or opening_audit.kind != "m3.harpy_frame_response"
                or opening_audit.actor_id != str(body.controller)
            ):
                raise WorkflowError(
                    "SOURCE_HARPY_OPENING_MISSING: recover the actual Frame's opening."
                )
        for consent in gate.consents:
            raw = c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json).where(
                    t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_state_history"].c.event_id == consent.source_event,
                )
            )
            audit = (
                c.execute(
                    sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
                        t.events.c.campaign_id == self.store.campaign_id,
                        t.events.c.id == consent.source_event,
                    )
                )
                .mappings()
                .first()
            )
            history = GameState.model_validate_json(raw) if raw else None
            original_gate = (
                next((x for x in history.frame_locks if x.id == gate.id), None) if history else None
            )
            original_consent = (
                next(
                    (x for x in original_gate.consents if x.source_event == consent.source_event),
                    None,
                )
                if original_gate
                else None
            )
            if (
                original_consent is None
                or audit is None
                or audit["kind"] != "m3.harpy_frame_response"
                or audit["actor_id"] != str(consent.controller)
                or any(
                    getattr(original_consent, field) != getattr(consent, field)
                    for field in ("actor", "controller", "allowed", "source_event", "account")
                )
            ):
                raise WorkflowError(
                    "SOURCE_HARPY_CONSENT_MISSING: recover the real Frame response."
                )

    def get(self, viewer: GuildViewer, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            self._proof(c, state, actor)
            choices = self._actors(c, state, viewer, actor)
            body, gate = harpy(state, actor), rules.locked(state, actor)
            return dict(
                actor=actor.model_dump(mode="json"),
                game_revision=state.revision,
                expected=physical_fingerprint(state, actor),
                owner=viewer.user_id == body.controller,
                locked=gate is not None,
                linked=body.linked,
                subsumed=body.subsumed,
                vitals=body.vitals_active,
                incapacitated=body.body_incapacitated,
                extractors=choices,
                consents=[x.model_dump(mode="json") for x in gate.consents] if gate else [],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        for actor in dict.fromkeys(
            x.owner for x in state.frame_locks if x.owner.kind == "external_pilot"
        ):
            try:
                body = harpy(state, actor)
                self._proof(c, state, actor)
                choices = self._actors(c, state, viewer, actor)
            except (ValueError, WorkflowError):
                continue
            if rules.locked(state, actor) is not None or body.subsumed or not body.vitals_active:
                result.append(
                    dict(
                        id=actor.entity,
                        actor=actor.model_dump(mode="json"),
                        revision=state.revision,
                        state="pending",
                        actionable=body.controller == viewer.user_id or bool(choices),
                        review=False,
                    )
                )
        work = t.m3["m3_required_work"]
        latest = {
            x["id"]: x
            for x in c.execute(
                sa.select(work)
                .where(work.c.campaign_id == self.store.campaign_id, work.c.kind == KIND)
                .order_by(work.c.revision)
            ).mappings()
        }
        for row in latest.values():
            if row["state"] != "resolved" and str(viewer.user_id) in (
                row["owner_id"],
                row["subject_id"],
            ):
                result.append(
                    dict(
                        id=row["id"],
                        revision=row["revision"],
                        state=row["state"],
                        actionable=row["owner_id"] == str(viewer.user_id),
                        review=True,
                    )
                )
        return result

    def voice(
        self,
        viewer: GuildViewer,
        key: str,
        actor: ActorRef,
        expected: str,
        operation: str,
        account: str,
    ) -> dict[str, Any]:
        def run(c: Connection) -> dict[str, Any]:
            if operation != "refuse":
                self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            self._proof(c, state, actor)
            self._actors(c, state, viewer, actor)
            body = harpy(state, actor)
            if body.controller != viewer.user_id or physical_fingerprint(state, actor) != expected:
                raise WorkflowError("STALE_HARPY: reopen the actual original Frame voice.")
            event = str(uuid4())
            if operation in ("allow", "refuse"):
                changed = rules.consent(
                    state, actor, viewer.user_id, event, account, allowed=operation == "allow"
                )
            elif operation == "open":
                changed = rules.open_frame(state, actor, viewer.user_id, event, account)
            else:
                raise WorkflowError("Choose the actual Frame's extraction response or opening.")
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_frame_response",
                changed,
                event_id=event,
                actor_ref=actor.model_dump(mode="json"),
                operation=operation,
            )
            return dict(actor=actor.model_dump(mode="json"), operation=operation)

        return self.store._write(
            viewer,
            key,
            "m3.harpy_frame_response",
            dict(
                actor=actor.model_dump(mode="json"),
                expected=expected,
                operation=operation,
                account=account,
            ),
            run,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        actor: ActorRef,
        expected: str,
        operation: str,
        account: str,
        *,
        extractor: ActorRef | None = None,
    ) -> dict[str, Any]:
        def run(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            self._proof(c, state, actor)
            choices = self._actors(c, state, viewer, actor)
            body = harpy(state, actor)
            if (
                physical_fingerprint(state, actor) != expected
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError("Reopen the current actual Harpy and describe the real help.")
            if operation == "extract":
                if extractor is None or not any(
                    x["ref"] == extractor.model_dump(mode="json") for x in choices
                ):
                    raise WorkflowError("The actual source-scene extractor owns this proposal.")
            elif (
                operation != "recover" or extractor is not None or body.controller != viewer.user_id
            ):
                raise WorkflowError(
                    "The actual affected Harpy requests medical help for this body."
                )
            handler, appointment = MedicalService(self.store)._handler(c)
            event, identity = str(uuid4()), str(uuid4())
            proposal = dict(
                actor=actor.model_dump(mode="json"),
                expected=expected,
                operation=operation,
                extractor=extractor.model_dump(mode="json") if extractor else None,
                proposer=viewer.user_id,
                handler=handler,
                appointment=appointment,
                account=account,
                source_event=event,
                immediate=False,
            )
            state.facts.append(
                dict(kind=KIND, id=identity, event=event, body=json.dumps(proposal, sort_keys=True))
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_help_proposed",
                state,
                event_id=event,
                work_id=identity,
            )
            related(
                c,
                self.store,
                dict(campaign_id=self.store.campaign_id, campaign_context=True),
                identity,
                handler,
                viewer.user_id,
                KIND,
                proposal,
                event,
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.harpy_help_proposed",
            dict(
                actor=actor.model_dump(mode="json"),
                expected=expected,
                operation=operation,
                account=account,
                extractor=extractor.model_dump(mode="json") if extractor else None,
            ),
            run,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )

    def review(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            row = self._row(c, identity)
            if str(viewer.user_id) not in (row["owner_id"], row["subject_id"]):
                raise WorkflowError(
                    "This actual help request belongs to its original participants."
                )
            return dict(
                id=identity,
                revision=row["revision"],
                state=row["state"],
                body=json.loads(row["body_json"]),
                can_review=str(viewer.user_id) == row["owner_id"],
            )

    def confirm(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        *,
        accepted: bool,
        evidence: str,
    ) -> dict[str, Any]:
        def run(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row, state = self._row(c, identity), load_state(c, self.store.campaign_id)
            body = json.loads(row["body_json"])
            handler, appointment = MedicalService(self.store)._handler(c)
            if (
                viewer.user_id != handler
                or handler != body["handler"]
                or appointment != body["appointment"]
                or row["revision"] != revision
                or row["state"] == "resolved"
                or not evidence.strip()
            ):
                raise WorkflowError(
                    "Only the original current human GM reviews this exact actual help."
                )
            raw = c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json).where(
                    t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_state_history"].c.event_id == body["source_event"],
                )
            )
            source = GameState.model_validate_json(raw) if raw else None
            fact = (
                next(
                    (x for x in source.facts if x.get("kind") == KIND and x.get("id") == identity),
                    None,
                )
                if source
                else None
            )
            if fact is None or json.loads(fact["body"]) != body:
                raise WorkflowError(
                    "SOURCE_HARPY_HELP_MISSING: recover the exact actual owned help proposal."
                )
            actor = ActorRef.model_validate(body["actor"])
            self._proof(c, state, actor)
            if physical_fingerprint(state, actor) != body["expected"]:
                raise WorkflowError("STALE_HARPY: the actual physical help must be reviewed again.")
            event = str(uuid4())
            changed = state
            if accepted:
                if body["operation"] == "extract":
                    changed = rules.extract(
                        state,
                        profiles(c, self.store.campaign_id),
                        actor,
                        ActorRef.model_validate(body["extractor"]),
                        event,
                        evidence,
                        contact_proven=True,
                    )
                else:
                    changed = rules.recover(state, actor, event, evidence)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.harpy_help_reviewed",
                changed,
                event_id=event,
                work_id=identity,
                accepted=accepted,
            )
            _append(c, row, event, body | dict(accepted=accepted, evidence=evidence), resolved=True)
            return dict(id=identity, accepted=accepted)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.harpy_help_reviewed",
                dict(work=identity, revision=revision, accepted=accepted, evidence=evidence),
                run,
                auto_audit=False,
                authorize=lambda c: self._access(c, viewer),
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
