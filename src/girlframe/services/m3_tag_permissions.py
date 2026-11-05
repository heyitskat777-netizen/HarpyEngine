"""Original locker-owned consent for a source-locked person's retained Tag."""

import hashlib
import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_tag_permissions as rules
from girlframe.engine.m2 import GameState, Obligation
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def prove_birth(c: Connection, game: GameService, state: GameState, actor: ActorRef) -> None:
    if actor.kind != "external_pilot" or not any(x.id == actor.entity for x in state.harpy_states):
        return
    try:
        body, _ = rules.conversion(state, actor)
    except ValueError as error:
        raise WorkflowError(str(error)) from None
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == body.source_event,
        )
    )
    birth = GameState.model_validate_json(raw) if raw else None
    original = next((x for x in birth.harpy_states if x.id == body.id), None) if birth else None
    keys = ("id", "origin", "source_event", "original_archive", "old_body_vessel", "controller")
    if (
        original is None
        or birth is None
        or any(getattr(body, k) != getattr(original, k) for k in keys)
    ):
        raise WorkflowError(
            "SOURCE_CONVERSION_MISSING: recover the actual original Harpy birth history."
        )
    try:
        rules.conversion(birth, actor)
    except ValueError as error:
        raise WorkflowError(str(error)) from None
    archive = next(x for x in state.career_archives if x.id == body.original_archive)
    prior = next((x for x in birth.career_archives if x.id == body.original_archive), None)
    if prior is None or (
        archive.actor,
        archive.source_event,
        archive.links_json,
        archive.sheet_json,
    ) != (prior.actor, prior.source_event, prior.links_json, prior.sheet_json):
        raise WorkflowError(
            "SOURCE_CONVERSION_MISSING: recover the immutable original retention archive."
        )
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == body.source_event
            )
        )
        .mappings()
        .first()
    )
    metadata = json.loads(event["payload_json"]) if event else {}
    command = (
        c.execute(
            sa.select(t.commands).where(
                t.commands.c.campaign_id == game.store.campaign_id,
                t.commands.c.interaction_key == event["command_key"],
            )
        )
        .mappings()
        .first()
        if event
        else None
    )
    if (
        event is None
        or event["kind"] != "m3.void_response"
        or event["actor_id"] != body.origin.entity
        or metadata.get("operation") != "rebirth"
        or command is None
        or json.loads(command["outcome_json"]).get("id") != metadata.get("work_id")
        or json.loads(command["outcome_json"]).get("stage") != "converted"
    ):
        raise WorkflowError(
            "SOURCE_CONVERSION_MISSING: recover the actual owner's committed rebirth response."
        )
    from girlframe.services.m3_void import source

    work_row, _, original_actor = source(game, c, str(metadata.get("work_id")))
    work = json.loads(work_row["body_json"])
    if (
        original_actor != body.origin
        or work.get("resolution") != "converted"
        or work.get("actual_actor") != actor.model_dump(mode="json")
        or work.get("threshold") != metadata.get("threshold")
    ):
        raise WorkflowError(
            "SOURCE_CONVERSION_MISSING: recover the actual original conversion consequence."
        )
    marker = json.loads(archive.links_json)[rules.MARKER]
    if set(marker["retained_tag_ids"]) != {x.id for x in original.tags}:
        raise WorkflowError(
            "Only the actual selected birth Tags retain their original restrictions."
        )


class PermissionService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _gate(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[GameState, Obligation]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        gate = next(
            (
                x
                for x in state.obligations
                if x.id == identity
                and x.kind == "tag_rejection_permission"
                and viewer.user_id in (x.owner, x.target)
            ),
            None,
        )
        if gate is None:
            raise WorkflowError(
                "This Tag permission belongs to its original participants or is unavailable."
            )
        responses, history = t.m2["m2_responses"], t.m2["m2_state_history"]
        body = c.scalar(
            sa.select(history.c.body_json)
            .join(
                responses,
                sa.and_(
                    responses.c.event_id == history.c.event_id,
                    responses.c.campaign_id == history.c.campaign_id,
                ),
            )
            .where(
                history.c.campaign_id == self.store.campaign_id,
                responses.c.choice_id == gate.details.get("effect_choice"),
            )
        )
        original = GameState.model_validate_json(body) if body else None
        first = (
            next((x for x in original.obligations if x.id == gate.id), None) if original else None
        )
        if (
            first is None
            or first.state != "pending"
            or any(
                getattr(first, key) != getattr(gate, key)
                for key in ("id", "kind", "owner", "target", "action", "details")
            )
        ):
            raise WorkflowError(
                "SOURCE_TAG_PERMISSION_MISSING: recover the original effect and decision."
            )
        if gate.state == "fulfilled":
            events = c.execute(
                sa.select(t.events)
                .where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.kind == "m3.tag_rejection_permission_granted",
                    sa.func.json_extract(t.events.c.payload_json, "$.permission_id") == identity,
                )
                .order_by(t.events.c.seq.desc())
            ).mappings()
            verified = False
            for event in events:
                saved = c.scalar(
                    sa.select(history.c.body_json).where(
                        history.c.campaign_id == self.store.campaign_id,
                        history.c.event_id == event["id"],
                    )
                )
                consent = GameState.model_validate_json(saved) if saved else None
                permission = (
                    next((x for x in consent.obligations if x.id == identity), None)
                    if consent
                    else None
                )
                if (
                    consent is None
                    or permission is None
                    or permission.state != "fulfilled"
                    or rules.signature(permission) != rules.signature(gate)
                    or event["actor_id"] != str(gate.owner)
                ):
                    continue
                locker, _ = rules.participants(consent, permission)
                if locker is None:
                    continue
                prove_birth(c, self.game, consent, locker)
                recorded = json.loads(event["payload_json"]).get("consenting_actor")
                if recorded is not None and recorded != locker.model_dump(mode="json"):
                    continue
                if recorded is None and locker != rules.original_role(gate, locker=True):
                    continue
                pending = permission.model_copy(deep=True)
                pending.state = "pending"
                _, bearer = rules.participants(consent, permission)
                context = dict(
                    gate=pending.model_dump(mode="json"),
                    locker=locker.model_dump(mode="json"),
                    bearer=bearer.model_dump(mode="json") if bearer else None,
                )
                expected = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
                choices = [expected]
                if recorded is None:
                    choices.append(hashlib.sha256(pending.model_dump_json().encode()).hexdigest())
                hashes = {
                    hashlib.sha256(
                        json.dumps(
                            dict(
                                actor=gate.owner,
                                kind="m3.tag_rejection_permission_granted",
                                payload=dict(id=identity, expected=sha, confirmed=True),
                            ),
                            sort_keys=True,
                        ).encode()
                    ).hexdigest()
                    for sha in choices
                }
                command = (
                    c.execute(
                        sa.select(t.commands).where(
                            t.commands.c.campaign_id == self.store.campaign_id,
                            t.commands.c.interaction_key == event["command_key"],
                        )
                    )
                    .mappings()
                    .first()
                )
                if (
                    command is None
                    or command["request_hash"] not in hashes
                    or json.loads(command["outcome_json"]).get("id") != identity
                    or json.loads(command["outcome_json"]).get("allowed") is not True
                ):
                    continue
                verified = True
                break
            if not verified:
                raise WorkflowError(
                    "SOURCE_CONSENT_MISSING: recover the original locker's real response."
                )
        return state, gate

    def _get(self, c: Connection, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        state, gate = self._gate(c, viewer, identity)
        try:
            locker, bearer = rules.participants(state, gate)
            for actor in (locker, bearer):
                if actor is not None:
                    prove_birth(c, self.game, state, actor)
            present = bearer is not None
            current = locker is not None and bearer is not None
        except ValueError as error:
            raise WorkflowError(str(error)) from None
        locker_label = "Original locker"
        if locker is not None:
            try:
                locker_label = resolve(
                    state,
                    locker,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                ).label
            except ValueError:
                pass
        context = dict(
            gate=gate.model_dump(mode="json"),
            locker=locker.model_dump(mode="json") if locker else None,
            bearer=bearer.model_dump(mode="json") if bearer else None,
        )
        return dict(
            id=identity,
            label=gate.details["label"],
            owner=viewer.user_id == gate.owner,
            active=gate.state == "pending" and present,
            allowed=gate.state == "fulfilled",
            can_consent=current
            and present
            and gate.state == "pending"
            and viewer.user_id == gate.owner,
            stale=not current,
            source_sha256=hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest(),
            locker_actor=context["locker"],
            bearer_actor=context["bearer"],
            locker_label=locker_label,
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            return self._get(c, viewer, identity)

    def authorize_rejection(
        self, c: Connection, viewer: GuildViewer, state: GameState, actor: ActorRef, tag_id: str
    ) -> None:
        self.game.authorize(c, viewer, game=False)
        actual = resolve(
            state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
        )
        if actual.controller != viewer.user_id:
            raise WorkflowError("The actual original Tag bearer owns this rejection.")
        try:
            gates = rules.locks(state, actor, tag_id)
        except ValueError as error:
            raise WorkflowError(str(error)) from None
        if gates:
            prove_birth(c, self.game, state, actor)
        for gate in gates:
            _, verified = self._gate(c, viewer, gate.id)
            if verified.state != "fulfilled":
                raise WorkflowError(
                    "ORIGINAL_LOCKER_CONSENT_REQUIRED: open this Tag's actual permission request."
                )

    def for_tag(self, viewer: GuildViewer, actor: ActorRef, tag_id: str) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            actual = resolve(
                state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if actual.controller != viewer.user_id:
                raise WorkflowError(
                    "Only this actual Tag bearer's human opens their consent requests."
                )
            try:
                gates = rules.locks(state, actor, tag_id)
            except ValueError as error:
                raise WorkflowError(str(error)) from None
            if gates:
                prove_birth(c, self.game, state, actor)
            return [self._get(c, viewer, x.id) for x in gates]

    def grant(
        self, viewer: GuildViewer, key: str, identity: str, expected: str, confirmed: bool
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays")
            _, gate = self._gate(c, viewer, identity)
            if gate.owner != viewer.user_id:
                raise WorkflowError("Only the original locker may consent to rejecting this Tag.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            data = self._get(c, viewer, identity)
            if (
                confirmed is not True
                or data["source_sha256"] != expected
                or not data["can_consent"]
            ):
                raise WorkflowError(
                    "STALE_TAG_PERMISSION: reopen the original active characters and confirm."
                )
            state, gate = self._gate(c, viewer, identity)
            gate.state = "fulfilled"
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.tag_rejection_permission_granted",
                state,
                permission_id=identity,
                consenting_actor=data["locker_actor"],
                affected_actor=data["bearer_actor"],
            )
            return dict(id=identity, allowed=True)

        return self.store._write(
            viewer,
            key,
            "m3.tag_rejection_permission_granted",
            dict(id=identity, expected=expected, confirmed=confirmed),
            operation,
            auto_audit=False,
            authorize=access,
        )
