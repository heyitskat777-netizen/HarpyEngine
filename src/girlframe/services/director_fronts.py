"""Native-authorized, append-only Front attention; no scheduler or consequence consumer."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.ai.director_fronts import (
    FictionalTime,
    Front,
    FrontAdvance,
    FrontDraft,
    FrontEvidence,
    FrontMove,
    MissionAccess,
    MissionMoveTrigger,
    PortrayalMove,
    PreparationTrigger,
)
from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_world_development import current as current_developments
from girlframe.services import campaign_time_history as calendar
from girlframe.services.director_context import DirectorContextService
from girlframe.services.director_knowledge import DirectorKnowledgeService
from girlframe.services.director_observation import _digest
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_world import WorldService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def records(state: GameState, *, current: bool = True) -> tuple[Front, ...]:
    values = tuple(
        Front.model_validate_json(fact["body"])
        for fact in state.facts
        if fact.get("kind") == "director_front"
    )
    heads: dict[str, Front] = {}
    identities: set[str] = set()
    for value in values:
        prior = heads.get(value.key)
        if (
            value.id in identities
            or (prior is None and (value.version != 1 or value.supersedes is not None))
            or (
                prior is not None
                and (value.supersedes != prior.id or value.version != prior.version + 1)
            )
        ):
            raise WorkflowError("FRONT_HISTORY_INVALID: preserve exact versioned history.")
        heads[value.key] = value
        identities.add(value.id)
    return tuple(heads.values()) if current else values


def times(state: GameState) -> tuple[FictionalTime, ...]:
    values = tuple(
        FictionalTime.model_validate_json(fact["body"])
        for fact in state.facts
        if fact.get("kind") == "director_fictional_time"
    )
    tick = 0
    identities: set[str] = set()
    for value in values:
        if value.id in identities or value.tick != tick + value.steps:
            raise WorkflowError("FICTIONAL_TIME_INVALID: preserve explicit time-event history.")
        identities.add(value.id)
        tick = value.tick
    return values


def evidence_refs(draft: FrontDraft) -> tuple[FrontEvidence, ...]:
    values = list(draft.fact_refs)
    for participant in draft.participants:
        values.extend((*participant.objective_refs, *participant.resource_refs))
    for hypothesis in draft.hypotheses:
        values.extend(hypothesis.support_refs)
    for move in draft.possible_moves:
        values.extend(move.evidence_refs)
    return tuple({(value.kind, value.id): value for value in values}.values())


class DirectorFrontService:
    def __init__(self, context: DirectorContextService):
        self.context, self.observer, self.store = context, context.observations, context.store
        self.knowledge = DirectorKnowledgeService(context)
        self.world = WorldService(MissionService(self.store))
        self.world.game = self.observer.game

    def _scope(
        self, c: Connection, viewer: GuildViewer | None, scene: str, *, owner: bool = False
    ) -> None:
        if viewer is not None:
            self.store.guild_member(viewer)
        self.observer._scope()
        row = self.observer._scene(c, scene, viewer)
        policy = self.observer._state(c, scene)
        self.observer.game.unpaused(c)
        if policy.policy.mode != "shadow" or not self.observer._consented(c, row, policy):
            raise WorkflowError("OBSERVATION_DISABLED: retain current scene consent.")
        if owner:
            assert viewer is not None
            self.world.missions.access.authorize(c, viewer, "world")
            self.world.missions._handler(c, viewer)

    def _subject_controllers(self, state: GameState, draft: FrontDraft) -> dict[str, int]:
        if state.world is None:
            raise WorkflowError("WORLD_REQUIRED: initialize actual Front subjects first.")
        subjects = {value.subject for value in draft.participants} | {
            value.subject for value in draft.possible_moves
        }
        controllers = {}
        for subject in subjects:
            actual = next(
                (
                    value
                    for value in getattr(
                        state.world,
                        {"location": "locations", "npc": "npcs", "faction": "factions"}[
                            subject.kind
                        ],
                    )
                    if value.id == subject.id
                ),
                None,
            )
            if actual is None or (
                draft.status != "resolved"
                and (
                    subject.kind == "npc"
                    and not actual.alive
                    or subject.kind == "faction"
                    and not actual.active
                )
            ):
                raise WorkflowError("FRONT_SUBJECT_UNAVAILABLE: use current actual world subjects.")
            if subject.kind == "npc":
                controllers[subject.kind + ":" + subject.id] = actual.controller
        return controllers

    def _evidence(self, c: Connection, scene: str, state: GameState, draft: FrontDraft) -> None:
        references = {value.id: value for value in self.context._current(c, scene)}
        developments = {value.id: value for value in current_developments(state)}
        for evidence in evidence_refs(draft):
            if evidence.kind == "reference":
                if evidence.id not in references:
                    raise WorkflowError("STALE_FRONT_EVIDENCE: retain actual current references.")
            elif evidence.id not in developments:
                raise WorkflowError("STALE_FRONT_EVIDENCE: retain current native developments.")
            else:
                development = developments[evidence.id]
                event = c.execute(
                    sa.select(t.events.c.id).where(
                        t.events.c.campaign_id == self.store.campaign_id,
                        t.events.c.id == development.source_event,
                        t.events.c.kind == "m3.world_development_recorded",
                        t.events.c.actor_id == str(development.confirmed_by),
                    )
                ).first()
                if event is None:
                    raise WorkflowError("UNPROVEN_FRONT_EVIDENCE: retain native world provenance.")
        for move in draft.possible_moves:
            actor = move.portrayed_by
            if actor and (
                actor not in self.knowledge._actors(c, self.observer._scene(c, scene))
                or any(actor.token not in references[ref.id].known_by for ref in move.evidence_refs)
            ):
                raise WorkflowError("FRONT_MOVE_SCOPE: use an actual actor and sources they heard.")
            if isinstance(move.trigger, MissionMoveTrigger):
                self._mission_access(c, move.trigger)

    def _mission_access(self, c: Connection, trigger: MissionMoveTrigger) -> MissionAccess:
        mission = self.world.missions._mission(c, trigger.offer)
        pilot = trigger.participant
        if mission.offered_characters.get(pilot.entity) != pilot.incarnation:
            raise WorkflowError("FRONT_MISSION_SCOPE: use an original invited Pilot.")
        if mission.phase == "cancelled":
            return "withdrawn"
        if (
            mission.phase == "active"
            and mission.character_ids.get(pilot.entity) == pilot.incarnation
        ):
            return "allocated"
        if mission.phase != "offered":
            return "closed"
        answer = mission.responses.get(pilot.entity)
        return (
            "accepted" if answer == "accept" else "declined" if answer == "decline" else "offered"
        )

    def _advance(self, c: Connection, scene: str, state: GameState, advance: FrontAdvance) -> str:
        if advance.kind == "outcome":
            outcome = self.context._approved_outcome(c, scene, advance.id)
            return "outcome:" + str(outcome["action_id"])
        value = next((value for value in times(state) if value.id == advance.id), None)
        policy = self.observer._state(c, scene)
        if (
            value is None
            or value.scene_id != scene
            or value.consent_generation != policy.consent_generation
        ):
            raise WorkflowError("STALE_FRONT_ADVANCE: use current consent-bound fictional time.")
        event = c.execute(
            sa.select(t.events.c.id).where(
                t.events.c.campaign_id == self.store.campaign_id,
                t.events.c.id == value.source_event,
                t.events.c.kind == "m3.director_fictional_time_recorded",
                t.events.c.actor_id == str(value.confirmed_by),
            )
        ).first()
        if event is None or value.confirmed_by != state.handler:
            raise WorkflowError("UNPROVEN_FRONT_ADVANCE: retain the actual fictional-time source.")
        return "fictional_time:" + value.source_event

    def _status(self, draft: FrontDraft, tick: int) -> str:
        if draft.status != "resolved" and (
            draft.clock is not None
            and draft.clock.mark == draft.clock.limit
            or draft.deadline_tick is not None
            and tick >= draft.deadline_tick
        ):
            return "ready"
        return draft.status

    def _append(
        self,
        state: GameState,
        scene: str,
        viewer: GuildViewer,
        draft: FrontDraft,
        prior: Front | None,
        event: str,
        tick: int,
        consent_generation: int,
        advance: FrontAdvance | None,
        advance_source: str | None = None,
    ) -> Front:
        data = draft.model_dump(mode="json")
        data["status"] = self._status(draft, tick)
        value = Front.model_validate_json(
            json.dumps(
                {
                    **data,
                    "id": "director-front:" + str(uuid4()),
                    "scene_id": scene,
                    "version": prior.version + 1 if prior else 1,
                    "source_event": event,
                    "confirmed_by": viewer.user_id,
                    "consent_generation": consent_generation,
                    "subject_controllers": self._subject_controllers(state, draft),
                    "advance": advance.model_dump(mode="json") if advance else None,
                    "advance_source": advance_source,
                    "fictional_tick": tick,
                }
            )
        )
        state.facts.append(dict(kind="director_front", body=value.model_dump_json()))
        return value

    def save(
        self,
        viewer: GuildViewer,
        key: str,
        scene: str,
        expected: int,
        draft: FrontDraft,
        *,
        advance: FrontAdvance | None = None,
    ) -> dict[str, Any]:
        draft = FrontDraft.model_validate_json(draft.model_dump_json())
        advance = FrontAdvance.model_validate_json(advance.model_dump_json()) if advance else None

        def operation(c: Connection) -> dict[str, Any]:
            state = self.world._state(c, expected)
            prior = next((value for value in records(state) if value.key == draft.key), None)
            if (prior is None and draft.supersedes is not None) or (
                prior is not None and draft.supersedes != prior.id
            ):
                raise WorkflowError("STALE_FRONT: retain the exact active Front predecessor.")
            if prior is not None and prior.status == "resolved":
                raise WorkflowError(
                    "FRONT_FINAL: preserve resolved history; use a new situation key."
                )
            self._evidence(c, scene, state, draft)
            bindings = self._subject_controllers(state, draft)
            if prior is not None and any(
                bindings.get(subject) != controller
                for subject, controller in prior.subject_controllers.items()
            ):
                raise WorkflowError("STALE_FRONT_CONTROLLER: reconcile actual participant control.")
            if prior is not None:
                if advance is None:
                    raise WorkflowError(
                        "FRONT_ADVANCE_REQUIRED: use an accepted outcome or explicit time event."
                    )
                if prior.clock is not None and (
                    draft.clock is None
                    or draft.clock.limit != prior.clock.limit
                    or draft.clock.mark < prior.clock.mark
                ):
                    raise WorkflowError(
                        "FRONT_CLOCK_INVALID: preserve the clock and prior attention marks."
                    )
            elif draft.clock is not None and draft.clock.mark:
                raise WorkflowError(
                    "FRONT_CLOCK_INVALID: a new Front starts without advanced marks."
                )
            advance_source = None
            if advance is not None:
                advance_source = self._advance(c, scene, state, advance)
                if any(
                    value.key == draft.key
                    and (value.advance == advance or value.advance_source == advance_source)
                    for value in records(state, current=False)
                ):
                    raise WorkflowError(
                        "FRONT_ADVANCE_USED: this source already advanced this Front."
                    )
            if draft.status == "resolved" and (advance is None or advance.kind != "outcome"):
                raise WorkflowError(
                    "FRONT_RESOLUTION_REQUIRED: retain an actual accepted native outcome."
                )
            values = times(state)
            tick = values[-1].tick if values else 0
            event = str(uuid4())
            value = self._append(
                state,
                scene,
                viewer,
                draft,
                prior,
                event,
                tick,
                self.observer._state(c, scene).consent_generation,
                advance,
                advance_source,
            )
            self.observer.game.event(
                c,
                viewer.user_id,
                key,
                "m3.director_front_saved",
                state,
                event_id=event,
                front_id=value.id,
            )
            return {
                "id": value.id,
                "version": value.version,
                "status": value.status,
                "game_revision": state.revision,
                "effects_applied": False,
            }

        return self.store._write(
            viewer,
            key,
            "director.front_save",
            {
                "scene": scene,
                "expected": expected,
                "draft": draft.model_dump(mode="json"),
                "advance": advance.model_dump(mode="json") if advance else None,
            },
            operation,
            authorize=lambda c: self._scope(c, viewer, scene, owner=True),
            auto_audit=False,
        )

    def fictional_time(
        self, viewer: GuildViewer, key: str, scene: str, expected: int, steps: int, account: str
    ) -> dict[str, Any]:
        """Manual fictional time only. No default worker, real-time timer or mechanical effect."""
        if (
            type(steps) is not int
            or not 1 <= steps <= 1_000_000
            or not account.strip()
            or len(account) > 1200
        ):
            raise WorkflowError(
                "FICTIONAL_TIME_INVALID: give explicit bounded fictional time and account."
            )

        def operation(c: Connection) -> dict[str, Any]:
            state = self.world._state(c, expected)
            values = times(state)
            tick = (values[-1].tick if values else 0) + steps
            event, identity = str(uuid4()), "director-fictional-time:" + str(uuid4())
            consent = self.observer._state(c, scene).consent_generation
            time = FictionalTime(
                id=identity,
                scene_id=scene,
                source_event=event,
                confirmed_by=viewer.user_id,
                consent_generation=consent,
                steps=steps,
                tick=tick,
                account=account,
            )
            prior = records(state)
            state.facts.append(dict(kind="director_fictional_time", body=time.model_dump_json()))
            ready = []
            for front in prior:
                if (
                    front.status in ("ready", "resolved")
                    or front.deadline_tick is None
                    or tick < front.deadline_tick
                ):
                    continue
                draft = FrontDraft.model_validate_json(
                    front.model_dump_json(include=set(FrontDraft.model_fields))
                )
                draft = draft.model_copy(update={"supersedes": front.id, "status": "ready"})
                if self._subject_controllers(state, draft) != front.subject_controllers:
                    raise WorkflowError(
                        "STALE_FRONT_CONTROLLER: reconcile control before its deadline review."
                    )
                ready.append(
                    self._append(
                        state,
                        scene,
                        viewer,
                        draft,
                        front,
                        event,
                        tick,
                        consent,
                        FrontAdvance(kind="fictional_time", id=identity),
                        "fictional_time:" + event,
                    ).id
                )
            self.observer.game.event(
                c,
                viewer.user_id,
                key,
                "m3.director_fictional_time_recorded",
                state,
                event_id=event,
            )
            return {
                "id": identity,
                "tick": tick,
                "ready": ready,
                "game_revision": state.revision,
                "effects_applied": False,
            }

        return self.store._write(
            viewer,
            key,
            "director.fictional_time",
            {"scene": scene, "expected": expected, "steps": steps, "account": account},
            operation,
            authorize=lambda c: self._scope(c, viewer, scene, owner=True),
            auto_audit=False,
        )

    def _tracked(
        self, c: Connection, scene: str
    ) -> list[tuple[Front, FrontMove, PortrayalMove, int, str]]:
        campaign = self.store.campaign_id
        location = calendar.booking(c, campaign, scene)
        if location is None or location.location is None:
            return []
        canon = load_state(c, campaign)
        result = []
        for front in records(canon):
            moves = [
                move
                for move in front.possible_moves
                if move.trigger and move.location == location.location and move.portrayed_by
            ]
            if not moves or front.status not in ("active", "ready"):
                continue
            try:
                origin = self.observer._scene(c, front.scene_id, allow_closed=True)
                original = self.observer._state(c, front.scene_id)
                if (
                    original.policy.mode != "shadow"
                    or original.consent_generation != front.consent_generation
                    or not self.observer._consented(c, origin, original)
                ):
                    continue
                refs = {
                    ref.id: ref
                    for ref in self.context._current(c, front.scene_id, allow_closed=True)
                }
            except WorkflowError:
                continue
            for move in moves:
                actor = move.portrayed_by
                assert actor is not None
                try:
                    role = resolve(
                        canon, actor, profiles(c, campaign), require_current_profile=False
                    )
                except ValueError:
                    continue
                if not role.alive or role.controller != front.subject_controllers.get(
                    "npc:" + actor.entity
                ):
                    continue
                if not all(
                    ref.id in refs and actor.token in refs[ref.id].known_by
                    for ref in move.evidence_refs
                ):
                    continue
                origin_refs = tuple(refs[ref.id] for ref in move.evidence_refs)
                status: MissionAccess | None = None
                reply = None
                answer = None
                triggered = "ready"
                if isinstance(move.trigger, MissionMoveTrigger):
                    try:
                        status = self._mission_access(c, move.trigger)
                        answer = self.world.missions._mission(c, move.trigger.offer).responses.get(
                            move.trigger.participant.entity
                        )
                    except WorkflowError:
                        continue
                    reply = move.trigger.participant
                    if status != move.trigger.when or (
                        move.trigger.answer and answer != move.trigger.answer
                    ):
                        if status != "offered":
                            continue
                        triggered = "waiting"
                else:
                    assert isinstance(move.trigger, PreparationTrigger)
                    now = calendar.anchor(c, campaign)
                    earliest = move.trigger.earliest
                    if (
                        now is None
                        or now[1].chapter != earliest.chapter
                        or now[1].position.order < earliest.position.order
                    ):
                        continue
                key = _digest(
                    (
                        front.key,
                        move.model_dump(mode="json"),
                        role.controller,
                        status,
                        answer,
                        [ref.model_dump(mode="json") for ref in origin_refs],
                    )
                )
                result.append(
                    (
                        front,
                        move,
                        PortrayalMove(
                            id=key,
                            text=move.text,
                            source_refs=tuple(
                                ref.origin_reference or ref.id for ref in origin_refs
                            ),
                            mission_access=status,
                            reply_from=reply,
                            reply_answer=answer,
                            tracked=True,
                        ),
                        role.controller,
                        triggered,
                    )
                )
        return result

    def _move_reviewed(self, c: Connection, identity: str) -> str | None:
        events = t.events
        return c.scalar(
            sa.select(sa.func.json_extract(events.c.payload_json, "$.decision"))
            .where(
                events.c.campaign_id == self.store.campaign_id,
                events.c.kind == "director.front_move_reviewed",
                sa.func.json_extract(events.c.payload_json, "$.move") == identity,
            )
            .order_by(events.c.seq.desc())
            .limit(1)
        )

    def _move_raised(self, c: Connection, identity: str) -> bool:
        rows = t.director_context["shadow"]
        return bool(
            c.scalar(
                sa.select(rows.c.id)
                .where(
                    rows.c.campaign_id == self.store.campaign_id,
                    sa.func.json_extract(rows.c.body_json, "$.front_move") == identity,
                    sa.func.json_extract(rows.c.body_json, "$.record_type").in_(
                        ("reaction_proposal", "handler_delivery")
                    ),
                )
                .limit(1)
            )
        )

    def plan_review(self, c: Connection, scene: str, *, owner: int | None = None) -> dict[str, Any]:
        candidates = self._tracked(c, scene)
        waiting = None
        available = None
        for _, move, plan, controller, status in candidates:
            if owner is not None and owner != controller:
                continue
            reviewed = self._move_reviewed(c, plan.id)
            if reviewed or self._move_raised(c, plan.id):
                continue
            if status == "waiting":
                waiting = {
                    "status": "waiting",
                    "reply_from": plan.reply_from.model_dump(mode="json")
                    if plan.reply_from
                    else None,
                }
                continue
            if not isinstance(move.trigger, PreparationTrigger):
                if (
                    available is None
                    and move.portrayed_by is not None
                    and self.tracked_portrayal(
                        c,
                        scene,
                        move.portrayed_by,
                        claimed=plan.id,
                    )
                ):
                    available = {
                        "status": "available",
                        "text": plan.text,
                        "why": "The native mission record matches this move.",
                        "reply_from": plan.reply_from.model_dump(mode="json")
                        if plan.reply_from
                        else None,
                    }
                continue
            return {
                "status": "ready",
                "id": plan.id,
                "text": plan.text,
                "why": "Authorized fictional time reached the preparation slot.",
                "controller": controller,
            }
        return available or waiting or {"status": "no_reply_needed"}

    def review_preparation(
        self, viewer: GuildViewer, key: str, scene: str, move: str, decision: str
    ) -> dict[str, Any]:
        if decision not in ("prepare", "decline"):
            raise WorkflowError("Use prepare or decline for an available plan.")

        def authorize(c: Connection) -> None:
            self._scope(c, viewer, scene)
            self.observer.game.scene_unpaused(c, scene)

        def operation(c: Connection) -> dict[str, Any]:
            item = self.plan_review(c, scene, owner=viewer.user_id)
            if item["status"] != "ready" or item.get("id") != move:
                raise WorkflowError("STALE_FRONT_MOVE: refresh this controller's next move.")
            receipt = self.store._audit(
                c,
                viewer.user_id,
                key,
                "director.front_move_reviewed",
                {"scene": scene, "move": move, "decision": decision},
            )
            return {"receipt": receipt, "status": decision, "effects_applied": False}

        return self.store._write(
            viewer,
            key,
            "director.front_move_reviewed",
            {"scene": scene, "move": move, "decision": decision},
            operation,
            authorize=authorize,
            auto_audit=False,
        )

    def tracked_portrayal(
        self, c: Connection, scene: str, actor: ActorRef, *, claimed: str | None = None
    ) -> PortrayalMove | None:
        from girlframe.services.director_planning import DirectorPlanningService

        planned = DirectorPlanningService(self.context).portrayal(c, scene, actor, claimed=claimed)
        if planned is not None:
            return planned
        candidates = self._tracked(c, scene)
        if not candidates:
            return None
        visible = {
            ref.origin_reference or ref.id: ref
            for ref in self.context._current(c, scene)
            if actor.token in ref.known_by
        }
        for _, move, plan, _, status in candidates:
            if move.portrayed_by != actor or status != "ready" or (claimed and claimed != plan.id):
                continue
            reviewed = self._move_reviewed(c, plan.id)
            if isinstance(move.trigger, PreparationTrigger) and reviewed != "prepare":
                continue
            if not claimed and self._move_raised(c, plan.id):
                continue
            if set(plan.source_refs) <= visible.keys():
                return plan.model_copy(
                    update={"source_refs": tuple(visible[ref].id for ref in plan.source_refs)}
                )
        return None

    def portrayal_move(self, c: Connection, scene: str, actor: ActorRef) -> PortrayalMove | None:
        """Offer one explicitly shared, still-relevant possibility for the actual actor."""
        row = self.observer._scene(c, scene)
        role = next(
            (item for item in self.knowledge._actor_views(c, row) if item.ref == actor), None
        )
        if role is None:
            return None
        tracked = self.tracked_portrayal(c, scene, actor) if actor.kind == "npc" else None
        if tracked:
            return tracked
        fronts = records(load_state(c, self.store.campaign_id))
        candidates = [
            (front, move)
            for front in fronts
            if front.status in ("active", "ready")
            for move in front.possible_moves
            if move.portrayed_by == actor and move.trigger is None
        ]
        if not candidates:
            return None
        visible = {
            identity: ref.id
            for ref in self.context._current(c, scene)
            if actor.token in ref.known_by
            for identity in (ref.id, ref.origin_reference)
            if identity is not None
        }
        for front, move in sorted(candidates, key=lambda entry: entry[0].status != "ready"):
            if (
                actor.kind == "npc"
                and front.subject_controllers.get("npc:" + actor.entity) != role.controller
            ):
                continue
            if actor.kind == "handler" and front.confirmed_by != role.controller:
                continue
            try:
                origin = self.observer._scene(c, front.scene_id, allow_closed=True)
            except WorkflowError:
                continue
            original = self.observer._state(c, front.scene_id)
            if (
                original.consent_generation != front.consent_generation
                or not self.observer._consented(c, origin, original)
            ):
                continue
            aliases = {
                ref.id: ref.origin_reference or ref.id
                for ref in self.context._references(c, front.scene_id)
            }
            keys = [aliases.get(ref.id, ref.id) for ref in move.evidence_refs]
            if all(key in visible for key in keys):
                return PortrayalMove(
                    id=_digest((front.id, move.id)),
                    text=move.text,
                    source_refs=tuple(visible[key] for key in keys),
                )
        return None

    def _actor_view(self, c: Connection, scene: str, actor: ActorRef) -> dict[str, Any]:
        """Internal role packet after GM authorization; never expose private Front grouping."""
        self._scope(c, None, scene)
        row = self.observer._scene(c, scene)
        if actor not in self.knowledge._actors(c, row):
            raise WorkflowError("ACTOR_UNAVAILABLE: select a current actual scene actor.")
        state = load_state(c, self.store.campaign_id)
        selected = [evidence for value in records(state) for evidence in evidence_refs(value)]
        reference_ids = {value.id for value in selected if value.kind == "reference"}
        development_ids = {value.id for value in selected if value.kind == "world_development"}
        visible = self.context._actor_references(self.context._current(c, scene), actor)
        fragments = []
        table = t.director_context["shadow"]
        for reference in visible:
            linked = reference.id in reference_ids or reference.origin_reference in reference_ids
            if (
                not linked
                and development_ids
                and reference.source_id.startswith("world-disclosure:")
            ):
                raw = c.scalar(
                    sa.select(table.c.body_json).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.id == reference.source_id,
                    )
                )
                disclosure = json.loads(raw) if raw else {}
                raw = c.scalar(
                    sa.select(table.c.body_json).where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.id == disclosure.get("commit_id"),
                    )
                )
                commit = json.loads(raw) if raw else {}
                linked = commit.get("native_result", {}).get("id") in development_ids
            if linked:
                fragments.append(reference.model_dump(mode="json"))
        return {"scope": "actor", "actor": actor.model_dump(mode="json"), "fragments": fragments}

    def view(
        self, viewer: GuildViewer, scene: str, *, actor: ActorRef | None = None
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._scope(c, viewer, scene)
            if actor is not None:
                self.context._build(c, viewer, scene, actor=actor)
                return self._actor_view(c, scene, actor)
            self.store.administrator(viewer)
            state = load_state(c, self.store.campaign_id)
            values = times(state)
            return {
                "scope": "gm",
                "fronts": [value.model_dump(mode="json") for value in records(state)],
                "fictional_tick": values[-1].tick if values else 0,
            }
