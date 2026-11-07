"""Transactional mission authority with private immutable histories and mandatory work."""

import builtins
import json
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_careers as careers
from girlframe.engine import m3_missions as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_policy import RULESET as M3_RULESET
from girlframe.engine.rules_registry import Registry
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class MissionService:
    def __init__(self, store: OnboardingStore, registry: Registry | None = None):
        self.store = store
        self.access = Access(store, registry)
        self.game = GameService(store)

    def _source_characters(
        self,
        c: Connection,
        mission: rules.Mission,
        *,
        offered: bool = False,
    ) -> dict[str, str]:
        """Bind original invitations/dispatch, including old records lacking explicit CIDs."""
        history = t.m3["m3_mission_history"]
        original = c.execute(
            sa.select(history.c.body_json, t.events.c.seq)
            .join(
                t.events,
                sa.and_(
                    t.events.c.campaign_id == history.c.campaign_id,
                    t.events.c.id == history.c.event_id,
                ),
            )
            .where(
                history.c.campaign_id == self.store.campaign_id,
                history.c.id == mission.id,
                t.events.c.kind == ("m3.mission_offered" if offered else "m3.mission_started"),
            )
            .order_by(history.c.revision)
            .limit(1)
        ).first()
        if original is None:
            raise WorkflowError("SOURCE_MISSION_MISSING: recover the actual original dispatch.")
        source = rules.Mission.model_validate_json(original.body_json)
        ids = source.offered_characters if offered else source.character_ids
        people = source.offered_to if offered else source.participants
        if not ids:
            state_history = t.m2["m2_state_history"]
            body = c.scalar(
                sa.select(state_history.c.body_json)
                .join(
                    t.events,
                    sa.and_(
                        t.events.c.campaign_id == state_history.c.campaign_id,
                        t.events.c.id == state_history.c.event_id,
                    ),
                )
                .where(
                    state_history.c.campaign_id == self.store.campaign_id,
                    t.events.c.seq <= original.seq,
                )
                .order_by(t.events.c.seq.desc())
                .limit(1)
            )
            if body is None:
                raise WorkflowError(
                    "SOURCE_MISSION_MISSING: original character evidence is absent."
                )
            facts = GameState.model_validate_json(body)
            ids = {
                str(uid): self.game.character_binding(c, facts, uid, require_current_profile=False)
                for uid in people
            }
        declared = mission.offered_characters if offered else mission.character_ids
        if set(ids) != {str(uid) for uid in people} or (declared and declared != ids):
            raise WorkflowError("SOURCE_MISSION_CHANGED: original character identities changed.")
        return ids

    def _departed(
        self,
        c: Connection,
        mission: rules.Mission,
        state: GameState,
    ) -> dict[str, str]:
        expected = self._source_characters(c, mission)
        history = t.m3["m3_mission_history"]
        dispatched = c.scalar(
            sa.select(t.events.c.seq)
            .join(
                history,
                sa.and_(
                    history.c.campaign_id == t.events.c.campaign_id,
                    history.c.event_id == t.events.c.id,
                ),
            )
            .where(
                history.c.campaign_id == self.store.campaign_id,
                history.c.id == mission.id,
                t.events.c.kind == "m3.mission_started",
            )
            .order_by(t.events.c.seq)
            .limit(1)
        )
        if dispatched is None:
            raise WorkflowError("Recover the original mission dispatch provenance.")
        result = {}
        for uid, character in expected.items():
            ref = ActorRef(kind="pilot", entity=uid, incarnation=character)
            unlinked = next((x for x in state.unlinked_careers if x.actor == ref), None)
            archive = next(
                (
                    x
                    for x in reversed(state.career_archives)
                    if x.actor == ref
                    and (
                        c.scalar(
                            sa.select(t.events.c.seq).where(
                                t.events.c.campaign_id == self.store.campaign_id,
                                t.events.c.id == x.source_event,
                            )
                        )
                        or -1
                    )
                    >= dispatched
                ),
                None,
            )
            sheet = state.sheets.get(uid)
            if (
                archive is None
                and unlinked is None
                and sheet is not None
                and self.game.character_binding(c, state, int(uid), require_current_profile=False)
                == character
            ):
                continue
            archive = archive or careers.archive_for(state, ref)
            source = (
                archive.source_event if archive else unlinked.source_event if unlinked else None
            )
            body = (
                c.scalar(
                    sa.select(t.m2["m2_state_history"].c.body_json).where(
                        t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                        t.m2["m2_state_history"].c.event_id == source,
                    )
                )
                if source
                else None
            )
            proof = GameState.model_validate_json(body) if body else None
            if proof is None or not (
                (archive is not None and archive in proof.career_archives)
                or (unlinked is not None and unlinked in proof.unlinked_careers)
            ):
                raise WorkflowError(
                    "Resolve the actual original participant before mission rewards."
                )
            result[uid] = character
        return result

    def _authorize(self, c: Connection, viewer: GuildViewer, *, write: bool = True) -> None:
        if write:
            self.access.authorize(c, viewer, "missions")
            self.game.unpaused(c)
        else:
            self.game.authorize(c, viewer, game=False)

    def _handler(self, c: Connection, viewer: GuildViewer) -> int:
        HandlerService(self.store).authorize(c, viewer)
        state = load_state(c, self.store.campaign_id)
        if state.handler != viewer.user_id:
            raise WorkflowError("Canonical Handler replacement requires explicit resolution.")
        return viewer.user_id

    def _current_handler(self, c: Connection) -> int:
        value = HandlerService(self.store).current(c)[1].handler_id
        if value is None:
            raise WorkflowError("Appoint a campaign Handler first.")
        return value

    def _not_off_duty(self, c: Connection) -> None:
        table = t.m3["m3_off_duty"]
        if c.scalar(
            sa.select(table.c.id).where(
                table.c.campaign_id == self.store.campaign_id, table.c.phase != "complete"
            )
        ):
            raise WorkflowError(
                "Finish the current Off-Duty period before offering or dispatching."
            )

    def _mission(self, c: Connection, identity: str) -> rules.Mission:
        try:
            identity = str(UUID(identity))
        except ValueError:
            raise WorkflowError("Unknown mission.") from None
        table = t.m3["m3_missions"]
        body = c.scalar(
            sa.select(table.c.body_json).where(
                table.c.campaign_id == self.store.campaign_id, table.c.id == identity
            )
        )
        if body is None:
            raise WorkflowError("Unknown mission.")
        return rules.Mission.model_validate_json(body)

    def _view(self, c: Connection, viewer: GuildViewer, mission: rules.Mission) -> None:
        self._authorize(c, viewer, write=False)
        if viewer.user_id not in mission.offered_to and viewer.user_id != self._current_handler(c):
            raise WorkflowError(
                "This mission is visible only to its invited players and current Handler."
            )

    def _save(self, c: Connection, mission: rules.Mission, event: str) -> None:
        table = t.m3["m3_missions"]
        where = sa.and_(table.c.campaign_id == self.store.campaign_id, table.c.id == mission.id)
        values = {
            "handler_id": str(mission.handler),
            "revision": mission.revision,
            "phase": mission.phase,
            "body_json": mission.model_dump_json(),
        }
        if c.scalar(sa.select(table.c.revision).where(where)) is None:
            c.execute(
                table.insert().values(campaign_id=self.store.campaign_id, id=mission.id, **values)
            )
        else:
            c.execute(table.update().where(where).values(**values))
        c.execute(
            t.m3["m3_mission_history"]
            .insert()
            .values(
                campaign_id=self.store.campaign_id,
                id=mission.id,
                revision=mission.revision,
                body_json=mission.model_dump_json(),
                event_id=event,
            )
        )

    def _work(
        self,
        c: Connection,
        mission: rules.Mission,
        identity: str,
        owner: int,
        subject: int,
        kind: str,
        body: dict[str, Any],
        event: str,
    ) -> None:
        c.execute(
            t.m3["m3_required_work"]
            .insert()
            .values(
                campaign_id=self.store.campaign_id,
                id=identity,
                revision=1,
                mission_id=mission.id,
                owner_id=str(owner),
                subject_id=str(subject),
                kind=kind,
                state="pending",
                body_json=json.dumps(body, sort_keys=True),
                event_id=event,
            )
        )

    def _pending(self, c: Connection, identity: str) -> list[dict[str, Any]]:
        table = t.m3["m3_required_work"]
        rows = c.execute(
            sa.select(table)
            .where(table.c.campaign_id == self.store.campaign_id, table.c.mission_id == identity)
            .order_by(table.c.revision)
        ).mappings()
        latest = {x["id"]: dict(x) for x in rows}
        return [x for x in latest.values() if x["state"] != "resolved"]

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        kind: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
        authorize: Callable[[Connection], None] | None = None,
        *,
        director_response: bool = False,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            if director_response:
                self.access.authorize(c, viewer, "missions", director_response=True)
                self.game.unpaused(c)
            else:
                self._authorize(c, viewer)
            if authorize:
                authorize(c)
            if kind.startswith("m3.mission_"):
                from girlframe.services.m3_gorgon_dormant import (
                    require_clear as require_gorgon_costs_clear,
                )
                from girlframe.services.m3_quadrant_loss import require_aftermath_clear

                require_aftermath_clear(load_state(c, self.store.campaign_id))
                require_gorgon_costs_clear(self.game, c)

        try:
            return self.store._write(
                viewer, key, kind, payload, operation, auto_audit=False, authorize=access
            )
        except ValidationError:
            raise WorkflowError("Mission validation failed; reopen the current mission.") from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def offer(
        self,
        viewer: GuildViewer,
        key: str,
        objective: str,
        players: tuple[int, ...],
        *,
        assassination: str | None = None,
    ) -> dict[str, Any]:
        if not objective.strip() or len(objective) > 1200:
            raise WorkflowError("Describe the mission objective in 1–1200 characters.")

        def operation(c: Connection) -> dict[str, Any]:
            self._handler(c, viewer)
            self._not_off_duty(c)
            state = load_state(c, self.store.campaign_id)
            if not players or len(players) > 25 or len(set(players)) != len(players):
                raise WorkflowError("Select one to 25 distinct active Pilots.")
            setup = HandlerService(self.store)
            if any(
                str(uid) not in state.sheets
                or uid == viewer.user_id
                or not setup._member(c, uid)
                or state.sheets[str(uid)].frame_scrapped
                or self.game.immediate_work(c, uid)
                for uid in players
            ):
                raise WorkflowError(
                    "Offer missions only to active campaign Pilots with canonical sheets."
                )
            mission = rules.Mission(
                id=str(uuid4()),
                handler=viewer.user_id,
                objective=objective.strip(),
                offered_to=players,
                offered_characters={
                    str(uid): self.game.character_binding(
                        c, state, uid, require_current_profile=False
                    )
                    for uid in players
                },
            )
            if assassination is not None:
                from girlframe.services.m3_budget_assassination import bind

                self.access.authorize(c, viewer, "strain")
                bind(c, self.store, state, assassination, mission)
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.mission_offered",
                state if assassination is not None else None,
                mission_id=mission.id,
                revision=1,
            )
            self._save(c, mission, event)
            return {"id": mission.id, "revision": mission.revision, "phase": mission.phase}

        return self._write(
            viewer,
            key,
            "m3.mission_offered",
            {"objective": objective, "players": list(players)}
            | ({"assassination": assassination} if assassination is not None else {}),
            operation,
            lambda c: HandlerService(self.store).authorize(c, viewer),
        )

    def cancel(self, viewer: GuildViewer, key: str, identity: str, expected: int) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self._handler(c, viewer)
            mission = self._mission(c, identity)
            rules.handler(mission, viewer.user_id, self._current_handler(c))
            rules.revision(mission, expected)
            if mission.phase != "offered":
                raise WorkflowError("Only an undispatched mission offer can be cancelled")
            updated = rules.changed(mission, phase="cancelled")
            state = load_state(c, self.store.campaign_id)
            from girlframe.services.m3_budget_assassination import finish

            event = str(uuid4())
            changed = finish(c, self.store, state, updated, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.mission_cancelled",
                state if changed else None,
                event_id=event,
                mission_id=identity,
                revision=updated.revision,
            )
            self._save(c, updated, event)
            return dict(id=identity, revision=updated.revision, phase=updated.phase)

        return self._write(
            viewer,
            key,
            "m3.mission_cancelled",
            dict(id=identity, expected=expected),
            operation,
            lambda c: HandlerService(self.store).authorize(c, viewer),
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._authorize(c, viewer, write=False)
            mission = self._mission(c, identity)
            self._view(c, viewer, mission)
            # Work details remain private to their owner/subject; other invitees see a count only.
            pending = self._pending(c, identity)
            return {
                "mission": mission.model_dump(mode="json"),
                "pending_count": len(pending),
                "work": [
                    {
                        "id": x["id"],
                        "kind": x["kind"],
                        "subject": int(x["subject_id"]),
                        "revision": x["revision"],
                    }
                    for x in pending
                    if str(viewer.user_id) in (x["owner_id"], x["subject_id"])
                ],
            }

    def list(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self._authorize(c, viewer, write=False)
            current_handler = HandlerService(self.store).current(c)[1].handler_id
            table = t.m3["m3_missions"]
            result = []
            for body in c.scalars(
                sa.select(table.c.body_json)
                .where(table.c.campaign_id == self.store.campaign_id)
                .order_by(table.c.id)
            ):
                mission = rules.Mission.model_validate_json(body)
                if viewer.user_id in mission.offered_to or viewer.user_id == current_handler:
                    result.append(
                        {
                            "id": mission.id,
                            "revision": mission.revision,
                            "phase": mission.phase,
                            "objective": mission.objective,
                            "needs_response": mission.phase == "offered"
                            and viewer.user_id in mission.offered_to
                            and str(viewer.user_id) not in mission.responses,
                        }
                    )
            return result

    def respond(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, response: rules.Response
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self._view(c, viewer, self._mission(c, identity))

        def operation(c: Connection) -> dict[str, Any]:
            mission = self._mission(c, identity)
            state = load_state(c, self.store.campaign_id)
            if str(viewer.user_id) not in state.sheets:
                raise WorkflowError("A current canonical Pilot is required to respond.")
            if self._source_characters(c, mission, offered=True).get(
                str(viewer.user_id)
            ) != self.game.character_binding(
                c, state, viewer.user_id, require_current_profile=False
            ):
                raise WorkflowError(
                    "This invitation belongs to the original Girl, not its replacement."
                )
            if response == "accept" and (
                state.sheets[str(viewer.user_id)].frame_scrapped
                or self.game.immediate_work(c, viewer.user_id)
            ):
                raise WorkflowError(
                    "Resolve the scrapped Frame or immediate work before accepting another mission."
                )
            updated = rules.respond(mission, viewer.user_id, expected, response)
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.mission_response",
                mission_id=identity,
                revision=updated.revision,
            )
            self._save(c, updated, event)
            return {"id": identity, "revision": updated.revision, "phase": updated.phase}

        return self._write(
            viewer,
            key,
            "m3.mission_response",
            {"id": identity, "expected": expected, "response": response},
            operation,
            authorize,
        )

    def start(self, viewer: GuildViewer, key: str, identity: str, expected: int) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self._not_off_duty(c)
            if self.game.pending_actions(c):
                raise WorkflowError("Finish the pending scene Play before dispatching a mission.")
            mission = self._mission(c, identity)
            self._handler(c, viewer)
            state = load_state(c, self.store.campaign_id)
            setup = HandlerService(self.store)
            active = frozenset(
                int(uid)
                for uid in state.sheets
                if setup._member(c, int(uid))
                and not state.sheets[uid].frame_scrapped
                and not self.game.immediate_work(c, int(uid))
            )
            updated = rules.dispatch(
                mission, viewer.user_id, self._current_handler(c), expected, active
            )
            invited = self._source_characters(c, mission, offered=True)
            actual = {
                str(uid): self.game.character_binding(c, state, uid, require_current_profile=False)
                for uid in updated.participants
            }
            if any(invited[uid] != character for uid, character in actual.items()):
                raise WorkflowError(
                    "Original accepted characters changed; cancel and reoffer the mission."
                )
            updated.character_ids = actual
            from girlframe.engine.m3_repairs import dispatch as bind_shortages

            dispatch_event = str(uuid4())
            bound = bind_shortages(state, identity, dispatch_event)
            # A Pilot cannot be dispatched into two active missions at once.
            table = t.m3["m3_missions"]
            for other_body in c.scalars(
                sa.select(table.c.body_json).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.id != identity,
                    table.c.phase.in_(("active", "ending", "awaiting_consequences")),
                )
            ):
                other = rules.Mission.model_validate_json(other_body)
                if set(updated.participants) & set(other.participants):
                    raise WorkflowError("A participant already has an unfinished mission.")
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.mission_started",
                bound if bound != state else None,
                event_id=dispatch_event,
                mission_id=identity,
                revision=updated.revision,
            )
            self._save(c, updated, event)
            return {"id": identity, "revision": updated.revision, "phase": updated.phase}

        return self._write(
            viewer,
            key,
            "m3.mission_started",
            {"id": identity, "expected": expected},
            operation,
            lambda c: HandlerService(self.store).authorize(c, viewer),
        )

    def end(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, success: bool
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            mission = self._mission(c, identity)
            self._handler(c, viewer)
            rules.handler(mission, viewer.user_id, self._current_handler(c))
            if self.game.pending_actions(c):
                raise WorkflowError("Finish the pending scene Play before ending the mission.")
            rules.revision(mission, expected)
            if mission.phase != "active":
                raise WorkflowError("Only an active mission can be ended.")
            if type(success) is not bool:
                raise WorkflowError("Record an explicit mission success or failure.")
            state = load_state(c, self.store.campaign_id)
            from girlframe.services.m3_budget_assassination import before_rewards

            before_rewards(c, self.store, state, mission, success)
            from girlframe.services.m3_supply_drop import expire_mission

            expiry_work = expire_mission(self.game, c, mission, viewer, key)
            state = load_state(c, self.store.campaign_id)
            # These reactions must occur before taking the final reward/Status snapshot.
            reactions = []
            for uid, sheet in state.sheets.items():
                if has_rule(sheet, "girl.princess.to-a-higher-standard", "PRINCESS"):
                    reactions.append((int(uid), "princess_mission_end", 32))
                if (
                    sheet.frame == "DOCTORDOCTOR MK. II"
                    and not sheet.frame_scrapped
                    and not success
                ):
                    reactions.append((int(uid), "doctor_obsolescence", 71))
            if reactions or expiry_work:
                updated = rules.changed(mission, phase="ending", success=success)
                event = self.game.event(
                    c,
                    viewer.user_id,
                    key,
                    "m3.mission_end_reactions_required",
                    mission_id=identity,
                    revision=updated.revision,
                )
                self._save(c, updated, event)
                for subject_uid, kind, pdf in reactions:
                    self._work(
                        c,
                        updated,
                        identity + ":" + kind + ":" + str(subject_uid),
                        viewer.user_id,
                        subject_uid,
                        kind,
                        {"source_pdf": pdf},
                        event,
                    )
                return {
                    "id": identity,
                    "revision": updated.revision,
                    "phase": updated.phase,
                    "rewards_committed": False,
                }
            return self._finish_rewards(c, viewer, key, mission, success)

        return self._write(
            viewer,
            key,
            "m3.mission_ended",
            {"id": identity, "expected": expected, "success": success},
            operation,
            lambda c: HandlerService(self.store).authorize(c, viewer),
        )

    def _finish_rewards(
        self, c: Connection, viewer: GuildViewer, key: str, mission: rules.Mission, success: bool
    ) -> dict[str, Any]:
        state = load_state(c, self.store.campaign_id)
        from girlframe.services.m3_supply_drop import require_expired

        require_expired(state, mission.id)
        from girlframe.services.m3_budget_assassination import before_rewards

        before_rewards(c, self.store, state, mission, success)
        rulings = self.store.policy.owner_m3_rulings
        if rulings is None:
            raise WorkflowError("M3 campaign rulings are missing.")
        from girlframe.engine import m3_intracadre_marriage as marriage
        from girlframe.engine.m3_actor_bonds import current_ref
        from girlframe.services.m3_intracadre_marriage import allocate_punishment, prove_flow

        before = GameState.model_validate_json(state.model_dump_json())
        event_id = str(uuid4())
        plan = rules.end(
            mission,
            viewer.user_id,
            self._current_handler(c),
            mission.revision,
            success=success,
            status_order=state.order,
            ace_policy=rulings.ace_bonus,
            ended_participants=self._departed(c, mission, state),
            grouped_status=marriage.status_groups(state),
        )
        changed = set()
        for grant in plan.grants:
            sheet = state.sheets.get(str(grant.owner))
            if sheet is None:
                raise WorkflowError(
                    "A reward recipient has no current sheet; resolve the roster first."
                )
            if marriage.acquisitions(state):
                marriage.credit(
                    state,
                    current_ref(state, grant.owner),
                    grant.amount,
                    event=event_id,
                    source=f"mission-reward:{mission.id}:{grant.reason}:{grant.owner}",
                )
            else:
                sheet.permissions += grant.amount
            changed.add(str(grant.owner))
        for uid in changed:
            state.sheets[uid].revision += 1
        from girlframe.engine.m3_repairs import mission_ended

        staged = []
        for work in plan.consequences:
            original = current_ref(state, work.owner)
            allocation = allocate_punishment(
                self.game,
                c,
                state,
                original,
                source_event=event_id,
                source_id=work.id,
                work_id=work.id,
            )
            subject = allocation.subject if allocation else original
            body = work.model_dump(mode="json") | dict(character=subject.incarnation)
            body.update(marriage.allocation_fields(state, work.id))
            staged.append((work, int(subject.entity), body))
        state = mission_ended(state, mission.id, event_id)
        from girlframe.services.m3_a_bomb import finish_mission

        finish_mission(self.game, c, state, mission, success, event_id)
        from girlframe.services.m3_debts import bind_mission, synchronize_mission

        bind_mission(state, plan.mission)
        event = self.game.event(
            c,
            viewer.user_id,
            key,
            "m3.mission_rewards_committed",
            state,
            event_id=event_id,
            mission_id=mission.id,
            revision=plan.mission.revision,
        )
        for grant in plan.grants:
            if marriage.acquisitions(before):
                prove_flow(
                    self.game,
                    c,
                    before,
                    state,
                    current_ref(before, grant.owner),
                    event,
                    f"mission-reward:{mission.id}:{grant.reason}:{grant.owner}",
                    grant.amount,
                )
        self._save(c, plan.mission, event)
        synchronize_mission(c, self.store, state, plan.mission, event)
        for work, subject_id, body in staged:
            self._work(
                c,
                plan.mission,
                work.id,
                work.decision_owner,
                subject_id,
                "punishment",
                body,
                event,
            )
        return {
            "id": mission.id,
            "revision": plan.mission.revision,
            "phase": plan.mission.phase,
            "rewards_committed": True,
        }

    def complete(
        self, viewer: GuildViewer, key: str, identity: str, expected: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self._handler(c, viewer)
            if self.game.pending_actions(c):
                raise WorkflowError("Finish the pending scene Play before advancing the mission.")
            mission = self._mission(c, identity)
            rules.handler(mission, viewer.user_id, self._current_handler(c))
            rules.revision(mission, expected)
            if self._pending(c, identity):
                raise WorkflowError(
                    "Required mission work is still pending; it cannot be waived or expired."
                )
            if mission.phase == "ending":
                if mission.success is None:
                    raise WorkflowError("The recorded mission outcome is missing.")
                return self._finish_rewards(c, viewer, key, mission, mission.success)
            updated = rules.complete(
                mission,
                expected,
                resolved_consequences=frozenset(mission.consequence_ids),
                all_other_mandatory_work_resolved=True,
            )
            from girlframe.services.m3_budget_assassination import finish, resolve_completed

            state = load_state(c, self.store.campaign_id)
            event = str(uuid4())
            assignment_changed = finish(c, self.store, state, updated, event)
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.mission_completed",
                state if assignment_changed else None,
                event_id=event,
                mission_id=identity,
                revision=updated.revision,
            )
            if assignment_changed:
                resolve_completed(c, self.store, state, event)
            self._save(c, updated, event)
            return {"id": identity, "revision": updated.revision, "phase": updated.phase}

        return self._write(
            viewer,
            key,
            "m3.mission_completed",
            {"id": identity, "expected": expected},
            operation,
            lambda c: HandlerService(self.store).authorize(c, viewer),
        )

    def rebuild(self) -> int:
        with self.store.transaction() as c:
            history = t.m3["m3_mission_history"]
            table = t.m3["m3_missions"]
            rows = c.scalars(
                sa.select(history.c.body_json)
                .where(history.c.campaign_id == self.store.campaign_id)
                .order_by(history.c.revision)
            )
            latest = {m.id: m for m in (rules.Mission.model_validate_json(body) for body in rows)}
            for mission in latest.values():
                values = {
                    "handler_id": str(mission.handler),
                    "revision": mission.revision,
                    "phase": mission.phase,
                    "body_json": mission.model_dump_json(),
                }
                where = sa.and_(
                    table.c.campaign_id == self.store.campaign_id, table.c.id == mission.id
                )
                if c.scalar(sa.select(table.c.revision).where(where)) is None:
                    c.execute(
                        table.insert().values(
                            campaign_id=self.store.campaign_id, id=mission.id, **values
                        )
                    )
                else:
                    c.execute(table.update().where(where).values(**values))
            self.store._audit(
                c,
                "system:local_operator",
                str(uuid4()),
                "m3.mission_projections_rebuilt",
                {"missions": len(latest)},
                ruleset_version=M3_RULESET,
            )
            return len(latest)

    def roster(self, viewer: GuildViewer) -> tuple[tuple[str, str], ...]:
        with self.store.engine.connect() as c:
            self._authorize(c, viewer)
            self._handler(c, viewer)
            setup = HandlerService(self.store)
            state = load_state(c, self.store.campaign_id)
            return tuple(
                (uid, sheet.callsign)
                for uid, sheet in state.sheets.items()
                if setup._member(c, int(uid))
            )

    def owned_work(self, viewer: GuildViewer) -> builtins.list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self._authorize(c, viewer, write=False)
            table = t.m3["m3_required_work"]
            rows = c.execute(
                sa.select(table)
                .where(
                    table.c.campaign_id == self.store.campaign_id,
                    sa.or_(
                        table.c.owner_id == str(viewer.user_id),
                        table.c.subject_id == str(viewer.user_id),
                    ),
                )
                .order_by(table.c.revision)
            ).mappings()
            latest = {row["id"]: dict(row) for row in rows}
            return [
                {
                    k: v
                    for k, v in row.items()
                    if k
                    in (
                        "id",
                        "revision",
                        "mission_id",
                        "off_duty_id",
                        "owner_id",
                        "subject_id",
                        "kind",
                        "state",
                    )
                }
                for row in latest.values()
                if row["state"] != "resolved"
            ]
