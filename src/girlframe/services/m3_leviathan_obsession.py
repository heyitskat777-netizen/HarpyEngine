"""Actual Leviathan gifts and source-owned compulsory rolls over the shared chat lock."""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_leviathan_obsession as influence
from girlframe.engine import m3_leviathan_tags as tags
from girlframe.engine.m2 import ChoiceAnswer, GameState, tier
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_leviathan_roll_state import Declaration, FactualIdentities
from girlframe.engine.m3_policy import RULESET
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast, _scene_judge
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

TYPE = "gorgon-type.leviathan.leviathan-type"
ROLL = "gorgon-type.leviathan.succumb-to-obsession"


def _copy(target: GameState, source: GameState) -> None:
    for field in GameState.model_fields:
        setattr(target, field, getattr(source, field))


class ObsessionService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def authorize(
        self, c: Connection, viewer: GuildViewer, action: dict[str, Any] | None = None
    ) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "world", director_response=True)
        access.authorize(c, viewer, "plays", director_response=True)
        if action is not None:
            meta = self.source(c, action)
            if (
                self.store.policy.m3_approval is None
                or self.store.policy.m3_approval.registry_sha256 != meta["registry"]
            ):
                raise WorkflowError("M3_POLICY_CHANGED: retain this original source approval")
            if viewer.user_id not in action["data"]["participants"]:
                raise WorkflowError("Only this original source table owns its responses")

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        kind: str,
        body: dict[str, Any],
        operation: Any,
        action: str | None = None,
    ) -> dict[str, Any]:
        try:
            return self.store._write(
                viewer,
                key,
                kind,
                body,
                operation,
                auto_audit=False,
                authorize=lambda c: self.authorize(
                    c, viewer, self.game.action(c, action) if action else None
                ),
            )
        except ValidationError:
            raise WorkflowError("Recover the original private Leviathan source records") from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _hash(self, c: Connection, state: GameState, actor: ActorRef) -> str:
        actual = resolve(
            state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
        )
        authority = influence.authority(state, actor)
        payload = dict(
            actor=actual.source_sha256,
            tags=[x.model_dump(mode="json") for x in tags.tags(state, actor)],
            authority=authority.model_dump(mode="json") if authority else None,
        )
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def preview(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        from girlframe.services.m3_battle import BattleService

        with self.store.engine.connect() as c:
            self.authorize(c, viewer)
        data = BattleService(self.store).preview(viewer, channel)
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            if state.revision != data["revision"] or cast.id != data["scene"]:
                raise WorkflowError("STALE_LEVIATHAN: reopen the actual original cast")
            rows = []
            for item in data["actors"]:
                ref = ActorRef.model_validate(item["ref"])
                body = (
                    next((x for x in state.world.gorgons if x.id == ref.entity and x.alive), None)
                    if state.world and ref.kind == "gorgon"
                    else None
                )
                rows.append(
                    item
                    | dict(
                        source_sha256=self._hash(c, state, ref),
                        leviathan=bool(body and "leviathan" in body.types),
                        trigger_tags=[
                            dict(id=x.id, label=x.label)
                            for x in tags.tags(state, ref)
                            if x.label.casefold() == "obsessed"
                            and not x.rejection_pending
                            and getattr(x, "scene_used", getattr(x, "trigger_scene", None))
                            != cast.id
                        ],
                    )
                )
            return dict(
                revision=state.revision, scene=cast.id, cast_revision=cast.revision, actors=rows
            )

    def begin(
        self, viewer: GuildViewer, key: str, channel: int, expected: int, declaration: Declaration
    ) -> dict[str, Any]:
        declaration = Declaration.model_validate_json(declaration.model_dump_json())

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            cast = _cast(self.game, c, state, channel)
            bound = profiles(c, self.store.campaign_id)
            source, subject = (
                resolve(state, x, bound, require_current_profile=False)
                for x in (declaration.source, declaration.subject)
            )
            if state.revision != expected or source.controller != viewer.user_id:
                raise WorkflowError("STALE_LEVIATHAN: use your actual original source body")
            from girlframe.engine.m3_janus_pandora import require_can_harm

            require_can_harm(state, declaration.source, declaration.subject)
            body = (
                next(
                    (
                        x
                        for x in state.world.gorgons
                        if x.id == declaration.source.entity and x.alive and "leviathan" in x.types
                    ),
                    None,
                )
                if state.world
                else None
            )
            if body is None or not all(
                any(x.actor == ref and x.controller == controller for x in cast.roles)
                for ref, controller in (
                    (source.ref, source.controller),
                    (subject.ref, subject.controller),
                )
            ):
                raise WorkflowError(
                    "Join the actual living Leviathan and subject to this source scene"
                )
            if (
                self._hash(c, state, source.ref) != declaration.source_sha256
                or self._hash(c, state, subject.ref) != declaration.subject_sha256
            ):
                raise WorkflowError(
                    "STALE_LEVIATHAN: actual source resources changed before declaration"
                )
            access = Access(self.store)
            assert access.registry is not None
            access.registry.require_available(TYPE if declaration.mode == "give_tag" else ROLL)
            lock = self.game.lock(c, channel)
            from girlframe.services.m3_gorgon_dormant import require_clear
            from girlframe.services.m3_recovery import pending
            from girlframe.services.m3_scene_requisitions import audience, guard

            require_clear(self.game, c)
            if lock and lock["state"] != "released" or pending(self.game, c, include_unrolled=True):
                raise WorkflowError("SCENE_BUSY: finish or recover the actual original Play first")
            guard(c, self.store, cast.id, source.ref)
            guard(c, self.store, cast.id, subject.ref)
            if declaration.mode == "succumb":
                self._trigger_available(state, declaration, cast.id)
            judge, judge_human, judge_source = _scene_judge(self.game, c, state, cast)
            gm, appointment = MedicalService(self.store)._handler(c)
            identity, event = str(uuid4()), str(uuid4())
            table = sorted(
                {x.controller for x in cast.roles}
                | ({cast.facilitator} if cast.facilitator else set())
            )
            approval = self.store.policy.m3_approval
            assert approval is not None
            meta = dict(
                declaration=declaration.model_dump(mode="json"),
                source_event=event,
                source_controller=source.controller,
                controller=subject.controller,
                cast=cast.model_dump(mode="json"),
                cast_sha256=fingerprint(cast),
                judge=judge_human,
                judge_actor=judge.model_dump(mode="json") if judge else None,
                judge_source=judge_source,
                gm=gm,
                appointment=appointment,
                registry=approval.registry_sha256,
                phase="declared",
                started=False,
                reach_approved=viewer.user_id == judge_human,
                expected_subject=declaration.subject_sha256,
            )
            actor_id = source.controller if declaration.mode == "give_tag" else subject.controller
            handler = active_handler(state)
            data = dict(
                leviathan_obsession=meta,
                play="leviathan_" + declaration.mode,
                context=declaration.account,
                participants=table,
                handler=gm,
                receipt=None,
                modifiers=[],
                result={},
                choices={},
                character_ids={
                    x.actor.entity: x.actor.incarnation
                    for x in cast.roles
                    if x.actor.kind == "pilot"
                },
                m3_shared=dict(registry=approval.registry_sha256),
                tag_context=dict(
                    actor=subject.ref.model_dump(mode="json"),
                    handler=handler.model_dump(mode="json") if handler else None,
                    gm_controller=gm,
                    table=table,
                    cast=meta["cast"],
                    cast_sha256=meta["cast_sha256"],
                ),
            )
            private = audience(c, self.store, cast.id)
            if private is not None:
                data["private_audience"] = list(private)
            state.facts.append(
                dict(
                    kind="leviathan_roll_intent",
                    action=identity,
                    event=event,
                    body=json.dumps(meta, sort_keys=True),
                )
            )
            c.execute(
                t.m2["m2_actions"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    id=identity,
                    actor_id=str(actor_id),
                    channel_id=str(channel),
                    scene_id=cast.id,
                    parent_id=None,
                    revision=1,
                    state="acquiring",
                    body_json=json.dumps(data, sort_keys=True),
                )
            )
            values = dict(
                action_id=identity,
                state="acquiring",
                body_json="{}",
                lease_until=0,
                claim_token=None,
            )
            locks = t.m2["m2_locks"]
            if lock:
                c.execute(
                    locks.update()
                    .where(
                        locks.c.campaign_id == self.store.campaign_id,
                        locks.c.channel_id == str(channel),
                    )
                    .values(**values)
                )
            else:
                c.execute(
                    locks.insert().values(
                        campaign_id=self.store.campaign_id, channel_id=str(channel), **values
                    )
                )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.leviathan_influence_declared",
                state,
                event_id=event,
                action_id=identity,
            )
            return dict(action_id=identity, state="acquiring")

        return self._write(
            viewer,
            key,
            "m3.leviathan_influence_declared",
            dict(
                channel=channel, expected=expected, declaration=declaration.model_dump(mode="json")
            ),
            operation,
        )

    def _trigger_available(
        self, state: GameState, declared: Declaration, scene: str
    ) -> dict[str, Any]:
        tag = next(
            (
                x
                for x in tags.tags(state, declared.subject)
                if x.id == declared.tag and x.label.casefold() == "obsessed"
            ),
            None,
        )
        if (
            tag is None
            or tag.rejection_pending
            or getattr(tag, "scene_used", getattr(tag, "trigger_scene", None)) == scene
        ):
            raise WorkflowError("Choose an actual available obsessed Tag for this source trigger")
        options = tags.trigger_options(state, declared.subject, str(declared.tag))
        if (
            options["requires_resolution"]
            and not options["reject"]
            and not options["embrace"]
            and not options.get("needs_factual_identities")
        ):
            raise WorkflowError(
                "This actual Tag cannot pay a cost whose required owner choice is prohibited"
            )
        return options

    def source(self, c: Connection, action: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._source(c, action)
        except (ValidationError, KeyError, TypeError):
            raise WorkflowError("Recover the original private Leviathan source records") from None

    def _source(self, c: Connection, action: dict[str, Any]) -> dict[str, Any]:
        meta = action["data"].get("leviathan_obsession")
        if not isinstance(meta, dict):
            raise WorkflowError("Use the actual saved Leviathan source action")
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == meta["source_event"],
            )
        )
        original = GameState.model_validate_json(raw) if raw else None
        marker = (
            next(
                (
                    x
                    for x in original.facts
                    if x.get("kind") == "leviathan_roll_intent"
                    and x.get("action") == action["id"]
                    and x.get("event") == meta["source_event"]
                ),
                None,
            )
            if original
            else None
        )
        saved = json.loads(marker["body"]) if marker else None
        event = (
            c.execute(
                sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == meta["source_event"],
                )
            )
            .mappings()
            .first()
        )
        immutable = (
            "declaration",
            "source_event",
            "source_controller",
            "controller",
            "cast",
            "cast_sha256",
            "judge",
            "judge_actor",
            "judge_source",
            "gm",
            "appointment",
            "registry",
        )
        if (
            event is None
            or saved is None
            or event["kind"] != "m3.leviathan_influence_declared"
            or event["actor_id"] != str(meta["source_controller"])
            or any(meta.get(x) != saved.get(x) for x in immutable)
            or json.loads(event["payload_json"]).get("action_id") != action["id"]
        ):
            raise WorkflowError("Recover the actual immutable Leviathan declaration")
        declared = Declaration.model_validate_json(json.dumps(meta["declaration"]))
        cast = SceneCast.model_validate_json(json.dumps(meta["cast"]))
        actor_id = meta["source_controller"] if declared.mode == "give_tag" else meta["controller"]
        if (
            action["actor_id"] != str(actor_id)
            or action["scene_id"] != cast.id
            or str(action["channel_id"]) != str(cast.channel)
            or set(action["data"]["participants"])
            != {x.controller for x in cast.roles}
            | ({cast.facilitator} if cast.facilitator else set())
            or fingerprint(cast) != meta["cast_sha256"]
        ):
            raise WorkflowError("Recover the actual source roles and original roll owner")
        return meta

    def current(
        self, c: Connection, action: dict[str, Any], *, unrolled: bool = False
    ) -> tuple[GameState, dict[str, Any], Declaration]:
        meta = self.source(c, action)
        declared = Declaration.model_validate_json(json.dumps(meta["declaration"]))
        state = load_state(c, self.store.campaign_id)
        cast = _cast(self.game, c, state, int(action["channel_id"]))
        if fingerprint(cast) != meta["cast_sha256"]:
            raise WorkflowError("STALE_LEVIATHAN: retain this source's actual original cast")
        judge, human, source = _scene_judge(self.game, c, state, cast)
        gm, appointment = MedicalService(self.store)._handler(c)
        if (
            human != meta["judge"]
            or (judge.model_dump(mode="json") if judge else None) != meta["judge_actor"]
            or source != meta["judge_source"]
            or gm != meta["gm"]
            or appointment != meta["appointment"]
        ):
            raise WorkflowError("Retain the actual source adjudicator and original appointment")
        for ref, controller in (
            (declared.source, meta["source_controller"]),
            (declared.subject, meta["controller"]),
        ):
            actual = resolve(
                state, ref, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if actual.controller != controller:
                raise WorkflowError("Recover the actual original body's controller")
        if unrolled and (
            self._hash(c, state, declared.subject) != meta["expected_subject"]
            or self._hash(c, state, declared.source) != declared.source_sha256
        ):
            raise WorkflowError(
                "STALE_LEVIATHAN: no cost or dice may use changed original resources"
            )
        return state, meta, declared

    def prove_type_event(
        self, c: Connection, state: GameState, event: str, source: ActorRef
    ) -> None:
        row = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == self.store.campaign_id, t.events.c.id == event
                )
            )
            .mappings()
            .first()
        )
        payload = json.loads(row["payload_json"]) if row else {}
        if row is None or row["kind"] not in (
            "m3.leviathan_obsessed_tag_given",
            "m3.leviathan_obsession_trigger_paid",
        ):
            raise WorkflowError("Recover the actual committed Leviathan Type source event")
        action = self.game.action(c, str(payload.get("action_id", "")))
        meta = self.source(c, action)
        declared = Declaration.model_validate_json(json.dumps(meta["declaration"]))
        expected = (
            "leviathan_obsessed_tag"
            if row["kind"] == "m3.leviathan_obsessed_tag_given"
            else "leviathan_obsession_cost"
        )
        marker = next(
            (
                x
                for x in state.facts
                if x.get("kind") == expected
                and x.get("event") == event
                and x.get("source") == source.model_dump_json()
                and x.get("target") == declared.subject.model_dump_json()
            ),
            None,
        )
        if (
            source != declared.source
            or marker is None
            or row["actor_id"] != str(meta["source_controller"])
            or payload.get("source") != source.model_dump(mode="json")
            or payload.get("subject") != declared.subject.model_dump(mode="json")
            or marker.get("tag") != payload.get("tag")
        ):
            raise WorkflowError("The actual Type effect must belong to this original source body")
        tag = next((x for x in tags.tags(state, declared.subject) if x.id == marker["tag"]), None)
        if tag is None or tag.label.casefold() != "obsessed":
            raise WorkflowError("Prove the actual originally given or marked obsessed Tag")
        if expected == "leviathan_obsession_cost" and (
            not tag.marked
            or getattr(tag, "scene_used", getattr(tag, "trigger_scene", None)) != action["scene_id"]
            or marker.get("modifier") != "0"
            or declared.mode != "succumb"
        ):
            raise WorkflowError("A real zero-modifier trigger mark must precede this awakening")
        if expected == "leviathan_obsessed_tag" and declared.mode != "give_tag":
            raise WorkflowError("Use the real owned Type Tag gift source")

    def _check_awake(self, c: Connection, state: GameState, source: ActorRef) -> None:
        from girlframe.services.m3_gorgon_dormant import awakened_source

        body = (
            next(x for x in state.world.gorgons if x.id == source.entity) if state.world else None
        )
        if (
            body is not None
            and body.gorgon_class == "dormant"
            and any(
                x.get("kind") == "dormant_awakening" and x.get("gorgon") == source.entity
                for x in state.facts
            )
        ):
            awakened_source(self.game, c, state, source)

    def _finish(self, c: Connection, state: GameState, action: dict[str, Any]) -> None:
        if self.game.pending(c, action["id"]):
            raise WorkflowError("Actual owned source responses remain pending")
        declared = Declaration.model_validate_json(
            json.dumps(action["data"]["leviathan_obsession"]["declaration"])
        )
        action["state"] = "complete"
        label = resolve(
            state,
            declared.subject,
            profiles(c, self.store.campaign_id),
            require_current_profile=False,
        ).label
        self.game.queue(
            c,
            action,
            "outcome",
            dict(
                play=action["data"]["play"],
                callsign=label,
                receipt=action["data"]["receipt"],
                total=action["data"]["result"].get("total"),
                tier=action["data"]["result"].get("tier"),
            ),
        )

    def roll(self, viewer: GuildViewer, key: str, identity: str) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            action = self.game.action(c, identity)
            if action["actor_id"] != str(viewer.user_id):
                raise WorkflowError("Only this exact original source action's human resumes it")
            if action["data"]["receipt"]:
                return dict(action_id=identity, receipt=action["data"]["receipt"])
            if action["state"] == "complete":
                return dict(action_id=identity, receipt=None)
            lock = self.game.lock(c, action["channel_id"])
            if (
                action["state"] not in ("acquiring", "ready_to_roll")
                or lock is None
                or lock["state"] != "held"
                or lock["action_id"] != identity
            ):
                raise WorkflowError("LOCK_NOT_ACKNOWLEDGED: no source cost or RNG was consumed")
            state, meta, declared = self.current(c, action, unrolled=True)
            if not meta["reach_approved"]:
                self.game.request(c, action, meta["judge"], "leviathan_reach")
                meta["phase"] = "reach"
                self.game.save_action(c, action, state="awaiting_choices")
                self.game.event(
                    c, viewer.user_id, key, "m3.leviathan_reach_requested", action_id=identity
                )
                return dict(action_id=identity, receipt=None)
            self._check_awake(c, state, declared.source)
            if declared.mode == "give_tag":
                event = str(uuid4())
                before = {x.id for x in tags.tags(state, declared.subject)}
                state = tags.give_obsessed(state, declared.source, declared.subject, event)
                gift = next(x.id for x in tags.tags(state, declared.subject) if x.id not in before)
                meta.update(started=True, phase="complete", effect_event=event)
                action["data"]["result"].update(tag=gift, source_effect="obsessed_tag")
                self._finish(c, state, action)
                self.game.save_action(c, action)
                self.game.event(
                    c,
                    meta["source_controller"],
                    key,
                    "m3.leviathan_obsessed_tag_given",
                    state,
                    event_id=event,
                    action_id=identity,
                    source=declared.source.model_dump(mode="json"),
                    subject=declared.subject.model_dump(mode="json"),
                    tag=gift,
                )
                return dict(action_id=identity, receipt=None)
            if not meta["started"]:
                options = self._trigger_available(state, declared, action["scene_id"])
                if options.get("needs_factual_identities") and not options["reject"]:
                    self._request_facts(c, state, action, return_phase="trigger")
                    self.game.save_action(c, action, state="awaiting_choices")
                    self.game.event(
                        c,
                        viewer.user_id,
                        key,
                        "m3.leviathan_source_facts_requested",
                        action_id=identity,
                    )
                    return dict(action_id=identity, receipt=None)
                event = str(uuid4())
                state, repeated = tags.mark_cost(
                    state,
                    declared.source,
                    declared.subject,
                    str(declared.tag),
                    action["scene_id"],
                    event,
                )
                meta.update(
                    started=True,
                    cost_event=event,
                    expected_subject=self._hash(c, state, declared.subject),
                )
                self.game.event(
                    c,
                    meta["source_controller"],
                    key + ":mark",
                    "m3.leviathan_obsession_trigger_paid",
                    state,
                    event_id=event,
                    action_id=identity,
                    source=declared.source.model_dump(mode="json"),
                    subject=declared.subject.model_dump(mode="json"),
                    tag=declared.tag,
                )
                if repeated:
                    meta.update(phase="trigger_tag", pending_tag=declared.tag)
                    self.game.request(
                        c,
                        action,
                        meta["controller"],
                        "leviathan_trigger_tag",
                        dict(tag=declared.tag),
                    )
                    self.game.save_action(c, action, state="awaiting_choices")
                    return dict(action_id=identity, receipt=None)
            count = tags.count(state, declared.subject)
            faces = self.game.dice.roll()
            if len(faces) != 2 or any(type(x) is not int or not 1 <= x <= 6 for x in faces):
                raise WorkflowError("The actual dice source returned invalid faces")
            event = str(uuid4())
            receipt = dict(
                id=str(uuid4()),
                action_id=identity,
                faces=list(faces),
                heat=0,
                pre_total=sum(faces) + count,
                base_modifier=count,
                modifier_source="Actual subject Tags",
                pre_modifiers=[],
                rng_source=self.game.rng_source,
                rolled_utc=datetime.now(UTC).isoformat(),
                ruleset=RULESET,
            )
            c.execute(
                t.m2["m2_receipts"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    action_id=identity,
                    id=receipt["id"],
                    body_json=json.dumps(receipt, sort_keys=True),
                )
            )
            action["data"]["receipt"] = receipt
            meta.update(phase="tags", roll_event=event, tag_count=count)
            self.game.save_action(c, action, state="tag_window")
            for human in action["data"]["participants"]:
                self.game.request(c, action, human, "tag_window")
            label = resolve(
                state,
                declared.subject,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            ).label
            self.game.queue(
                c,
                action,
                "receipt",
                dict(receipt=receipt, callsign=label, play=action["data"]["play"]),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.leviathan_obsession_rolled",
                state,
                event_id=event,
                action_id=identity,
                receipt_id=receipt["id"],
                tag_count=count,
            )
            return dict(action_id=identity, receipt=receipt)

        return self._write(
            viewer,
            key,
            "m3.leviathan_obsession_rolled",
            dict(action_id=identity),
            operation,
            action=identity,
        )

    def _request_facts(
        self, c: Connection, state: GameState, action: dict[str, Any], *, return_phase: str
    ) -> None:
        meta = action["data"]["leviathan_obsession"]
        meta.update(phase="facts", facts_return=return_phase)
        self.game.request(c, action, meta["controller"], "leviathan_facts")
        action["state"] = "awaiting_choices"

    def _result_options(
        self, state: GameState, declared: Declaration, action: dict[str, Any]
    ) -> list[dict[str, str]]:
        values = influence.pool(state, declared.subject)
        eligible = influence.ordinary(state, declared.subject)
        result = []
        candidates: list[tuple[str, str, dict[str, str]]] = [
            ("gain", "Gain the actual obsessed Identity", {})
        ]
        candidates += [
            ("replace:" + x.id, "Replace " + x.name, dict(replace=x.id))
            for x in values
            if x.id in eligible and not x.obsession_sources
        ]
        candidates += [
            ("reuse:" + x.id, "Bind existing " + x.name, dict(reuse=x.id))
            for x in values
            if x.id in eligible and (x.obsession_sources or x.name.casefold() == "obsessed")
        ]
        for token, label, kwargs in candidates:
            try:
                influence.influence(
                    state,
                    declared.source,
                    declared.subject,
                    "mid",
                    "preview:" + action["id"],
                    judge=action["data"]["leviathan_obsession"]["judge"],
                    replace=kwargs.get("replace"),
                    reuse=kwargs.get("reuse"),
                )
            except ValueError:
                continue
            result.append(dict(id=token, label=label))
        return result

    def _results(self, c: Connection, state: GameState, action: dict[str, Any]) -> None:
        meta = action["data"]["leviathan_obsession"]
        declared = Declaration.model_validate_json(json.dumps(meta["declaration"]))
        total = action["data"]["receipt"]["pre_total"] + sum(
            x["amount"] for x in action["data"]["modifiers"]
        )
        action["data"]["result"].update(total=total, tier=tier(total))
        action["state"] = "awaiting_choices"
        if tier(total) == "low":
            meta["phase"] = "arrival"
            self.game.request(c, action, meta["controller"], "leviathan_arrival_owner")
            return
        try:
            values = influence.pool(state, declared.subject)
            influence.ordinary(state, declared.subject)
        except ValueError as error:
            if "FACTUAL_IDENTITIES_REQUIRED" not in str(
                error
            ) and "STALE_ORDINARY_IDENTITIES" not in str(error):
                raise
            self._request_facts(c, state, action, return_phase="result")
            return
        if tier(total) == "mid":
            options = self._result_options(state, declared, action)
            if not options:
                raise WorkflowError(
                    "The actual required Identity gain has no legal source replacement"
                )
            meta.update(
                phase="identity", identity_subject_sha=self._hash(c, state, declared.subject)
            )
            self.game.request(c, action, meta["controller"], "leviathan_identity_result")
            return
        eligible = influence.ordinary(state, declared.subject)
        reused = tuple(x.id for x in values if x.id in eligible and x.obsession_sources)
        changed = influence.influence(
            state,
            declared.source,
            declared.subject,
            "high",
            action["data"]["response_event"],
            reuse_many=reused,
            judge=meta["judge"],
        )
        _copy(state, changed)
        action["data"]["result"]["source_effect"] = "high_obsession"
        meta["phase"] = "complete"
        self._finish(c, state, action)

    def _arrival_response(
        self,
        c: Connection,
        state: GameState,
        action: dict[str, Any],
        row: dict[str, Any],
        answer: ChoiceAnswer,
        viewer: GuildViewer,
    ) -> None:
        from girlframe.engine.m3_leviathan_arrival import arrive, requirements
        from girlframe.engine.m3_leviathan_arrival_state import ArrivalRequirement

        if (
            answer.flag is not True
            or not answer.text.strip()
            or answer.options
            or answer.denied
            or answer.fields
            or answer.number is not None
            or answer.member is not None
        ):
            raise WorkflowError("Confirm the actual completed arrival and describe what happened")
        meta = action["data"]["leviathan_obsession"]
        declared = Declaration.model_validate(meta["declaration"])
        bindings = profiles(c, self.store.campaign_id)
        if row["kind"] == "leviathan_arrival_owner":
            required = requirements(state, declared.subject, declared.source, bindings)
            if required.blocker:
                raise WorkflowError(
                    "Complete the actual physical prerequisite before arrival: " + required.blocker
                )
            humans = list(
                dict.fromkeys(
                    resolve(state, ref, bindings, require_current_profile=False).controller
                    for ref in required.attestors
                )
            )
            humans = [x for x in humans if x != viewer.user_id]
            meta["arrival"] = dict(
                requirement=required.model_dump(mode="json"),
                account=answer.text,
                pending=humans,
            )
        arrival = meta["arrival"]
        if row["kind"] == "leviathan_arrival_mover":
            if not arrival["pending"] or arrival["pending"][0] != viewer.user_id:
                raise WorkflowError("Only the actual source mover confirms this arrival")
            arrival["pending"].pop(0)
        if row["kind"] != "leviathan_arrival_judge":
            if arrival["pending"]:
                self.game.request(c, action, arrival["pending"][0], "leviathan_arrival_mover")
            else:
                self.game.request(c, action, meta["judge"], "leviathan_arrival_judge")
            return
        required = ArrivalRequirement.model_validate_json(json.dumps(arrival["requirement"]))
        changed = arrive(
            state,
            required,
            action["data"]["response_event"],
            arrival["account"],
            source_action=action["id"],
            bindings=bindings,
        )
        _copy(state, changed)
        action["data"]["result"]["source_effect"] = "actual_arrival"
        self.game.request(c, action, meta["controller"], "leviathan_low_play")

    def _repeated(
        self,
        c: Connection,
        state: GameState,
        action: dict[str, Any],
        row: dict[str, Any],
        answer: ChoiceAnswer,
        viewer: GuildViewer,
    ) -> None:
        meta = action["data"]["leviathan_obsession"]
        declared = Declaration.model_validate_json(json.dumps(meta["declaration"]))
        tag = json.loads(row["body_json"])["tag"]
        if answer.options == ("review_facts",) and not answer.denied and not answer.fields:
            meta["pending_tag"] = tag
            self._request_facts(c, state, action, return_phase="tag")
            return
        if (
            answer.fields
            or answer.number is not None
            or answer.flag is not None
            or answer.member is not None
        ):
            raise WorkflowError("Choose only the actual owned repeated-Tag response")
        if answer.options == ("reject",) and not answer.denied:
            if declared.subject.kind == "external_pilot":
                from girlframe.services.m3_tag_permissions import PermissionService

                PermissionService(self.store).authorize_rejection(
                    c, viewer, state, declared.subject, tag
                )
            changed = tags.defer_rejection(
                state, declared.subject, tag, action["data"]["response_event"]
            )
            _copy(state, changed)
            kind = "reject_tag" if declared.subject.kind == "pilot" else "actor_reject_tag"
            self.game.obligation(
                state,
                action,
                kind,
                meta["controller"],
                actor=declared.subject.model_dump_json(),
                tag=tag,
            )
        elif answer.options == ("embrace",) and len(answer.denied) <= 1:
            changed = tags.embrace_trigger(
                state,
                declared.subject,
                tag,
                action["data"]["response_event"],
                replace=answer.denied[0] if answer.denied else None,
                judge=meta["judge"],
            )
            _copy(state, changed)
            for obligation in state.obligations:
                if (
                    obligation.details.get("tag") == tag
                    and obligation.state == "pending"
                    and (
                        obligation.details.get("actor") == declared.subject.model_dump_json()
                        or obligation.owner == meta["controller"]
                        and obligation.details.get("owner_character")
                        == declared.subject.incarnation
                    )
                    and obligation.kind
                    in ("reject_tag", "actor_reject_tag", "cannot_refuse_until_tag_resolved")
                ):
                    obligation.state = "fulfilled"
        else:
            raise WorkflowError(
                "Choose to embrace or owe an actual action rejecting this repeated Tag"
            )
        meta.pop("pending_tag", None)
        if row["kind"] == "leviathan_trigger_tag":
            meta.update(phase="declared", expected_subject=self._hash(c, state, declared.subject))
            action["state"] = "ready_to_roll"
        else:
            self._results(c, state, action)

    def _facts(
        self,
        c: Connection,
        state: GameState,
        action: dict[str, Any],
        row: dict[str, Any],
        answer: ChoiceAnswer,
    ) -> None:
        meta = action["data"]["leviathan_obsession"]
        declared = Declaration.model_validate_json(json.dumps(meta["declaration"]))
        if row["kind"] == "leviathan_facts":
            if (
                set(answer.fields) != {"facts"}
                or answer.options
                or answer.denied
                or answer.flag is not None
                or answer.number is not None
                or answer.member is not None
            ):
                raise WorkflowError("Supply only your actual existing Identity facts")
            facts = FactualIdentities.model_validate_json(answer.fields["facts"])
            if not facts.account.strip():
                raise WorkflowError("Describe the actual existing Identity source facts")
            meta.update(
                facts_pending=facts.model_dump(mode="json"),
                facts_subject_sha=self._hash(c, state, declared.subject),
            )
            self.game.request(c, action, meta["judge"], "leviathan_facts_review")
            return
        if (
            answer.flag is None
            or not answer.text.strip()
            or answer.options
            or answer.denied
            or answer.fields
            or answer.number is not None
            or answer.member is not None
        ):
            raise WorkflowError("The frozen actual judge reviews these factual resources")
        if not answer.flag:
            self.game.request(c, action, meta["controller"], "leviathan_facts")
            return
        if self._hash(c, state, declared.subject) != meta["facts_subject_sha"]:
            raise WorkflowError(
                "STALE_FACTS: reject this review and request current actual resources"
            )
        facts = FactualIdentities.model_validate_json(json.dumps(meta["facts_pending"]))
        changed = influence.install_authority(
            state,
            declared.subject,
            facts.ordinary,
            action["data"]["response_event"],
            owner=meta["controller"],
            judge=meta["judge"],
            identities=facts.identities,
            mentor=facts.mentor,
        )
        _copy(state, changed)
        meta["expected_subject"] = self._hash(c, state, declared.subject)
        follow = meta["facts_return"]
        if follow == "trigger":
            meta["phase"] = "declared"
            action["state"] = "ready_to_roll"
        elif follow == "tag":
            self.game.request(
                c,
                action,
                meta["controller"],
                "leviathan_trigger_tag"
                if not action["data"]["receipt"]
                else "leviathan_tag_resolution",
                dict(tag=meta["pending_tag"]),
            )
        else:
            self._results(c, state, action)

    def respond(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, answer: ChoiceAnswer
    ) -> dict[str, Any]:
        answer = ChoiceAnswer.model_validate_json(answer.model_dump_json())

        def owned(c: Connection) -> tuple[dict[str, Any], dict[str, Any]]:
            row = (
                c.execute(
                    sa.select(t.m2["m2_choices"]).where(
                        t.m2["m2_choices"].c.campaign_id == self.store.campaign_id,
                        t.m2["m2_choices"].c.id == identity,
                        t.m2["m2_choices"].c.actor_id == str(viewer.user_id),
                    )
                )
                .mappings()
                .first()
            )
            if row is None:
                raise WorkflowError("Only the actual original owner may answer this source choice")
            action = self.game.action(c, row["action_id"])
            self.authorize(c, viewer, action)
            return dict(row), action

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row, action = owned(c)
            if (
                row["state"] != "pending"
                or row["revision"] != revision
                or action["state"] in ("complete", "aborted")
            ):
                raise WorkflowError("STALE_LEVIATHAN_CHOICE: reopen the original saved response")
            state, meta, declared = self.current(c, action)
            lock = self.game.lock(c, action["channel_id"])
            if lock is None or lock["state"] != "held" or lock["action_id"] != action["id"]:
                raise WorkflowError(
                    "Restore the actual original chat lock before the source response"
                )
            c.execute(
                t.m2["m2_choices"]
                .update()
                .where(
                    t.m2["m2_choices"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_choices"].c.id == identity,
                )
                .values(state="answered", revision=revision + 1)
            )
            event = str(uuid4())
            action["data"]["response_event"] = event
            action["data"]["choices"][row["kind"] + ":" + row["actor_id"]] = answer.model_dump(
                mode="json"
            )
            kind = row["kind"]
            if kind == "leviathan_reach":
                if (
                    answer.flag is None
                    or not answer.text.strip()
                    or answer.options
                    or answer.denied
                    or answer.fields
                    or answer.number is not None
                    or answer.member is not None
                ):
                    raise WorkflowError(
                        "Confirm or reject this actual source's declared influence reach"
                    )
                if answer.flag:
                    meta.update(reach_approved=True, phase="declared")
                    action["state"] = "ready_to_roll"
                else:
                    action["data"]["result"]["reach_rejected"] = True
                    self._finish(c, state, action)
            elif kind in ("leviathan_facts", "leviathan_facts_review"):
                self._facts(c, state, action, row, answer)
            elif kind in ("leviathan_trigger_tag", "leviathan_tag_resolution"):
                self._repeated(c, state, action, row, answer, viewer)
            elif kind == "leviathan_identity_result":
                if (
                    answer.denied
                    or answer.fields
                    or answer.flag is not None
                    or answer.number is not None
                    or answer.member is not None
                    or len(answer.options) != 1
                ):
                    raise WorkflowError("Choose one actual owned Identity result")
                if meta["identity_subject_sha"] != self._hash(c, state, declared.subject):
                    raise WorkflowError("STALE_IDENTITIES: reopen current actual source resources")
                selected = next(
                    (
                        x
                        for x in self._result_options(state, declared, action)
                        if x["id"] == answer.options[0]
                    ),
                    None,
                )
                if selected is None:
                    raise WorkflowError("Choose a legal actual gain, replacement or source binding")
                mode, _, resource = selected["id"].partition(":")
                kwargs = {mode: resource} if mode in ("replace", "reuse") else {}
                changed = influence.influence(
                    state,
                    declared.source,
                    declared.subject,
                    "mid",
                    event,
                    judge=meta["judge"],
                    replace=kwargs.get("replace"),
                    reuse=kwargs.get("reuse"),
                )
                _copy(state, changed)
                action["data"]["result"]["source_effect"] = "mid_obsession"
                meta["phase"] = "complete"
                self._finish(c, state, action)
            elif (
                kind == "tag_window"
                or kind.startswith("leviathan_tag_")
                or kind == "leviathan_pair_tag"
            ):
                self._tag_response(c, state, action, row, answer, viewer)
            elif kind.startswith("leviathan_arrival_"):
                self._arrival_response(c, state, action, row, answer, viewer)
            elif kind == "leviathan_low_play":
                if (
                    not answer.text.strip()
                    or answer.options
                    or answer.denied
                    or answer.fields
                    or answer.flag is not None
                    or answer.number is not None
                    or answer.member is not None
                ):
                    raise WorkflowError(
                        "The actual original subject's human describes how she plays it now"
                    )
                action["data"]["result"]["reaction"] = answer.text
                self._finish(c, state, action)
            else:
                raise WorkflowError("This actual source choice is unavailable")
            self.game.save_action(c, action)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.leviathan_choice_resolved",
                state,
                event_id=event,
                action_id=action["id"],
                choice_id=identity,
            )
            c.execute(
                t.m2["m2_responses"]
                .insert()
                .values(
                    campaign_id=self.store.campaign_id,
                    choice_id=identity,
                    actor_id=str(viewer.user_id),
                    event_id=event,
                    answer_json=answer.model_dump_json(),
                )
            )
            return dict(action_id=action["id"], state=action["state"], choice_id=identity)

        def access(c: Connection) -> None:
            owned(c)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.leviathan_choice_resolved",
                dict(id=identity, revision=revision, answer=answer.model_dump(mode="json")),
                operation,
                auto_audit=False,
                authorize=access,
            )
        except ValidationError:
            raise WorkflowError("Recover the original private Leviathan source records") from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _tag_eligible(
        self, state: GameState, actor: ActorRef, tag: Any, controller: int, scene: str
    ) -> bool:
        return (
            hasattr(tag, "observers")
            and controller in tag.observers
            and tag.scene_used != scene
            and not tag.rejection_pending
        )

    def _tag_response(
        self,
        c: Connection,
        state: GameState,
        action: dict[str, Any],
        row: dict[str, Any],
        answer: ChoiceAnswer,
        viewer: GuildViewer,
    ) -> None:
        from girlframe.engine.m3_tag_markers import modifier
        from girlframe.services import m3_tag_markers as markers

        meta = action["data"]["leviathan_obsession"]
        declared = Declaration.model_validate_json(json.dumps(meta["declaration"]))
        owner = int(row["actor_id"])
        if row["kind"] == "tag_window":
            if (
                set(answer.fields) - {"marker", "status"}
                or answer.flag is not None
                or answer.member is not None
            ):
                raise WorkflowError("Choose only your actual role's printed Tag modifier")
            if "status" in answer.fields and answer.fields["status"] != "0":
                from girlframe.engine.m3_girl_runtime_state import has_rule

                sheet = (
                    state.sheets.get(declared.subject.entity)
                    if declared.subject.kind == "pilot"
                    else None
                )
                if (
                    owner != meta["controller"]
                    or sheet is None
                    or state.order[-1] != owner
                    or sheet.status_marked
                    or not has_rule(sheet, "girl.alpha.nothing-more-than-a-hound", "ALPHA")
                    or answer.fields["status"] not in ("-1", "1")
                ):
                    raise WorkflowError(
                        "Only this actual current Dog's owned rule marks its Status"
                    )
                sheet.status_marked = True
                sheet.revision += 1
                action["data"]["modifiers"].append(
                    dict(source="alpha_status", amount=int(answer.fields["status"]))
                )
            if answer.options == ("pass",):
                if answer.denied or answer.number is not None or answer.text:
                    raise WorkflowError("A pass does not commit another Tag or narrative effect")
            elif (
                answer.options == ("tag",)
                and len(answer.denied) == 1
                and answer.number in (-1, 1)
                and answer.text.strip()
            ):
                marker = markers.select(
                    self.game, c, state, action, owner, answer.fields.get("marker")
                )
                chosen = next(
                    (x for x in tags.tags(state, declared.subject) if x.id == answer.denied[0]),
                    None,
                )
                self_mark = False
                if declared.subject.kind == "pilot":
                    from girlframe.engine.m3_girl_runtime_state import mentor_tag

                    self_mark = bool(
                        chosen and mentor_tag(state.sheets[declared.subject.entity], chosen, state)
                    )
                if (
                    chosen is None
                    or not self._tag_eligible(
                        state, declared.subject, chosen, owner, action["scene_id"]
                    )
                    or owner == meta["controller"]
                    and not self_mark
                ):
                    raise WorkflowError(
                        "Choose an observed unused Girl Tag through another human "
                        "or its printed Mentor exception"
                    )
                options = tags.trigger_options(state, declared.subject, chosen.id)
                if (
                    options["requires_resolution"]
                    and not options["reject"]
                    and not options["embrace"]
                    and not options.get("needs_factual_identities")
                ):
                    raise WorkflowError(
                        "This repeated Tag's required owner response is presently prohibited"
                    )
                amount = modifier(state, declared.subject, marker, 1 if answer.number == 1 else -1)
                action["data"].setdefault("leviathan_tag_proposals", []).append(
                    dict(
                        id=str(uuid4()),
                        controller=owner,
                        marker=marker.model_dump(mode="json"),
                        tag=chosen.id,
                        direction=answer.number,
                        account=answer.text,
                        amount=amount,
                    )
                )
            else:
                raise WorkflowError(
                    "Pass or propose one actual observed Tag with its direction and relevance"
                )
            if not any(x["kind"] == "tag_window" for x in self.game.pending(c, action["id"])):
                self._close_tags(c, state, action)
            return
        proposals = action["data"].get("leviathan_tag_proposals", [])
        if row["kind"] == "leviathan_tag_selection":
            if (
                answer.fields
                or answer.denied
                or answer.flag is not None
                or answer.number is not None
                or answer.member is not None
                or len(answer.options) != 1
            ):
                raise WorkflowError("Select one actual saved proposal for table discussion")
            selected = next((x for x in proposals if x["id"] == answer.options[0]), None)
            if selected is None:
                raise WorkflowError("Select one of the actual original Tag proposals")
            meta.update(tag_candidate=selected["id"], tag_consensus={str(owner): True})
            for person in action["data"]["participants"]:
                if person != owner:
                    self.game.request(c, action, person, "leviathan_tag_agreement")
            return
        if row["kind"] == "leviathan_tag_agreement":
            if (
                answer.flag is None
                or answer.options
                or answer.denied
                or answer.fields
                or answer.number is not None
                or answer.member is not None
            ):
                raise WorkflowError("Record only your own agreement or disagreement")
            meta["tag_consensus"][str(owner)] = answer.flag
            if not any(
                x["kind"] == "leviathan_tag_agreement" for x in self.game.pending(c, action["id"])
            ):
                if all(meta["tag_consensus"].values()):
                    self._select_tag(
                        c,
                        state,
                        action,
                        next(x for x in proposals if x["id"] == meta["tag_candidate"]),
                    )
                else:
                    self.game.request(c, action, meta["judge"], "leviathan_tag_selection")
            return
        if row["kind"] == "leviathan_pair_tag":
            if (
                answer.options not in (("yes",), ("no",))
                or answer.denied
                or answer.fields
                or answer.flag is not None
                or answer.number is not None
                or answer.member is not None
            ):
                raise WorkflowError(
                    "The actual Pair chooses whether to change its protected Paired Identity"
                )
            body = json.loads(row["body_json"])
            tag = next(x for x in tags.tags(state, declared.subject) if x.id == body["tag"])
            if answer.options == ("yes",):
                sheet = state.sheets[declared.subject.entity]
                paired = next(x for x in sheet.identities if x.paired)
                influence.require_unlocked(sheet.identities, (paired.id,))
                paired.name = tag.label
                paired.marked = paired.id in sheet.sedation_locked
                sheet.tags = [x for x in sheet.tags if x.id != tag.id]
                sheet.revision += 1
                self._results(c, state, action)
            elif body["repeated"]:
                self.game.request(
                    c, action, meta["controller"], "leviathan_tag_resolution", dict(tag=tag.id)
                )
            else:
                self._results(c, state, action)
            return
        raise WorkflowError("This actual source Tag response is unavailable")

    def _close_tags(self, c: Connection, state: GameState, action: dict[str, Any]) -> None:
        proposals = action["data"].get("leviathan_tag_proposals", [])
        if not proposals:
            self._results(c, state, action)
            return
        if len(proposals) == 1:
            self._select_tag(c, state, action, proposals[0])
            return
        from girlframe.engine.m2 import higher

        ranked = all(
            x["marker"]["actor"] and x["marker"]["actor"]["kind"] in ("pilot", "handler")
            for x in proposals
        )
        if ranked:
            selected = proposals[0]
            for option in proposals[1:]:
                if higher(
                    state,
                    int(option["marker"]["actor"]["entity"]),
                    int(selected["marker"]["actor"]["entity"]),
                ):
                    selected = option
            self._select_tag(c, state, action, selected)
        else:
            self.game.request(
                c, action, action["data"]["leviathan_obsession"]["judge"], "leviathan_tag_selection"
            )

    def _select_tag(
        self, c: Connection, state: GameState, action: dict[str, Any], proposal: dict[str, Any]
    ) -> None:
        from girlframe.engine.m3_tag_markers import Marker, modifier
        from girlframe.services import m3_tag_markers as markers

        meta = action["data"]["leviathan_obsession"]
        declared = Declaration.model_validate_json(json.dumps(meta["declaration"]))
        marker = Marker.model_validate_json(json.dumps(proposal["marker"]))
        if not any(
            x.model_dump(mode="json") == proposal["marker"]
            for x in markers.current(self.game, c, state, action, proposal["controller"])
        ):
            action["data"]["leviathan_tag_proposals"] = [
                x for x in action["data"]["leviathan_tag_proposals"] if x["id"] != proposal["id"]
            ]
            meta.pop("tag_candidate", None)
            action["state"] = "tag_window"
            self.game.request(c, action, proposal["controller"], "tag_window")
            return
        tag = next((x for x in tags.tags(state, declared.subject) if x.id == proposal["tag"]), None)
        if tag is None or not self._tag_eligible(
            state, declared.subject, tag, proposal["controller"], action["scene_id"]
        ):
            raise WorkflowError("The proposed actual Tag changed before its one source application")
        amount = modifier(state, declared.subject, marker, proposal["direction"])
        repeated = tag.marked
        tags._put(
            state,
            declared.subject,
            tuple(
                x.model_copy(update={"marked": True, "scene_used": action["scene_id"]})
                if x.id == tag.id
                else x
                for x in tags.tags(state, declared.subject)
            ),
        )
        action["data"]["modifiers"].append(
            dict(source="girl_tag", amount=amount, tag=tag.id, marker=proposal["marker"])
        )
        if declared.subject.kind == "pilot":
            from girlframe.engine.m3_girl_runtime_state import has_rule, relation_current

            sheet = state.sheets[declared.subject.entity]
            if (
                has_rule(sheet, "girl.bonded.bonded-pair", "BONDED")
                and relation_current(sheet, "pair", state)
                and marker.actor is not None
                and marker.actor.kind == "pilot"
                and sheet.pair == int(marker.actor.entity)
            ):
                self.game.request(
                    c,
                    action,
                    marker.controller,
                    "leviathan_pair_tag",
                    dict(tag=tag.id, repeated=repeated),
                )
                return
        if repeated:
            meta["pending_tag"] = tag.id
            self.game.request(
                c, action, meta["controller"], "leviathan_tag_resolution", dict(tag=tag.id)
            )
        else:
            self._results(c, state, action)

    def inspect(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            action = self.game.action(c, identity)
            meta = self.source(c, action)
            if viewer.user_id not in action["data"]["participants"]:
                raise WorkflowError("This saved source action belongs to its original table")
            result = (
                dict(action["data"]["result"])
                if viewer.user_id == meta["controller"]
                else {
                    k: v
                    for k, v in action["data"]["result"].items()
                    if k in ("total", "tier", "source_effect")
                }
            )
            return dict(
                id=identity,
                state=action["state"],
                revision=action["revision"],
                play=action["data"]["play"],
                receipt=action["data"]["receipt"],
                result=result,
                modifiers=[
                    {k: v for k, v in x.items() if k in ("source", "amount")}
                    for x in action["data"]["modifiers"]
                ],
            )

    def decision(
        self, c: Connection, viewer: GuildViewer, action: dict[str, Any], row: dict[str, Any]
    ) -> dict[str, Any]:
        from girlframe.services import m3_tag_markers as markers

        self.authorize(c, viewer, action)
        state, meta, declared = self.current(c, action)
        body = json.loads(row["body_json"])
        actual = resolve(
            state,
            declared.subject,
            profiles(c, self.store.campaign_id),
            require_current_profile=False,
        )
        detail: dict[str, Any] = {}
        if row["kind"] == "tag_window":
            available = []
            for tag in tags.tags(state, declared.subject):
                if not self._tag_eligible(
                    state, declared.subject, tag, viewer.user_id, action["scene_id"]
                ):
                    continue
                if viewer.user_id == meta["controller"]:
                    from girlframe.engine.m3_girl_runtime_state import mentor_tag

                    if declared.subject.kind != "pilot" or not mentor_tag(
                        state.sheets[declared.subject.entity], tag, state
                    ):
                        continue
                available.append(dict(id=tag.id, label=tag.label))
            detail.update(
                tags=available,
                markers=[
                    dict(id=x.token, label=x.label)
                    for x in markers.current(self.game, c, state, action, viewer.user_id)
                ],
            )
            from girlframe.engine.m3_girl_runtime_state import has_rule

            sheet = (
                state.sheets.get(declared.subject.entity)
                if declared.subject.kind == "pilot"
                else None
            )
            detail["can_status"] = bool(
                sheet
                and viewer.user_id == meta["controller"]
                and state.order[-1] == viewer.user_id
                and not sheet.status_marked
                and has_rule(sheet, "girl.alpha.nothing-more-than-a-hound", "ALPHA")
            )
        elif row["kind"] in ("leviathan_trigger_tag", "leviathan_tag_resolution"):
            options = tags.trigger_options(state, declared.subject, body["tag"])
            try:
                pool = influence.pool(state, declared.subject)
            except ValueError:
                pool = ()
            detail.update(
                options=options,
                replacements=[
                    dict(id=x.id, label=x.name) for x in pool if x.id in options["replacements"]
                ],
            )
        elif row["kind"] == "leviathan_identity_result":
            detail["options"] = self._result_options(state, declared, action)
        elif row["kind"] == "leviathan_facts":
            from girlframe.services.m3_battle import _visible

            try:
                pool = influence.pool(state, declared.subject)
                needs_import = False
            except ValueError:
                pool = ()
                needs_import = True
            cast = SceneCast.model_validate_json(json.dumps(meta["cast"]))
            mentors = []
            for role in cast.roles:
                if role.actor == declared.subject or not _visible(
                    state, role.actor, viewer.user_id
                ):
                    continue
                candidate = resolve(
                    state,
                    role.actor,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                if candidate.girl:
                    mentors.append(
                        dict(ref=role.actor.model_dump(mode="json"), label=candidate.label)
                    )
            detail["facts"] = dict(
                actor=declared.subject.model_dump(mode="json"),
                girl=actual.girl,
                existing=[x.model_dump(mode="json") for x in pool],
                needs_import=needs_import,
                mentor_options=mentors,
            )
        elif row["kind"] == "leviathan_facts_review":
            detail["facts"] = meta["facts_pending"]
        elif row["kind"] in ("leviathan_tag_selection", "leviathan_tag_agreement"):
            proposals = action["data"].get("leviathan_tag_proposals", [])
            detail["proposals"] = [
                dict(id=x["id"], label=x["account"], tag=x["tag"], direction=x["direction"])
                for x in proposals
            ]
            detail["candidate"] = meta.get("tag_candidate")
        elif row["kind"].startswith("leviathan_arrival_"):
            from girlframe.engine.m3_leviathan_arrival import requirements

            detail["arrival"] = requirements(
                state, declared.subject, declared.source, profiles(c, self.store.campaign_id)
            ).model_dump(mode="json")
        return dict(row) | dict(
            body=body,
            play=action["data"]["play"],
            actor=meta["controller"],
            parent=action["id"],
            channel=int(action["channel_id"]),
            leviathan=True,
            result={k: v for k, v in action["data"]["result"].items() if k in ("tier", "total")},
            detail=detail,
        )
