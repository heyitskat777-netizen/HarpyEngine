"""Owned Off-Duty phase transitions, scene attestations and canonical recovery.

Start consequences require actual typed effect records. A narrative account cannot
waive unsupported work, impersonate another participant or fabricate a receipt.
"""

import json
from collections.abc import Callable
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_off_duty as rules
from girlframe.engine import m3_world as world_rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_careers import can_pilot, original_sheet
from girlframe.engine.m3_core import Recovery
from girlframe.engine.m3_strain_state import TRACKS, Trigger
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_choices import ChoiceEngine
from girlframe.services.m2_state import load_state
from girlframe.services.m3_off_duty import OffDutyService, current_original_characters
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

Outcome = tuple[rules.Period, GameState, list[dict[str, Any]], dict[str, Any]]


class CycleService:
    def __init__(self, periods: OffDutyService):
        self.periods, self.missions = periods, periods.missions
        self.store, self.game = periods.store, periods.game

    def _current(
        self,
        c: Connection,
        viewer: GuildViewer,
        identity: str,
        game_revision: int,
        *,
        invited_observation: str | None = None,
    ) -> tuple[rules.Period, GameState]:
        period = self.periods._get(c, identity)
        if invited_observation is None:
            self.periods._view(c, viewer, period)
        else:
            self.game.authorize(c, viewer, game=False)
            table = t.m3["m3_required_work"]
            row = (
                c.execute(
                    sa.select(table)
                    .where(
                        table.c.campaign_id == self.store.campaign_id,
                        table.c.id == invited_observation,
                    )
                    .order_by(table.c.revision.desc())
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if (
                row is None
                or row["off_duty_id"] != identity
                or row["owner_id"] != str(viewer.user_id)
                or row["kind"] != "observation_effect"
                or row["state"] != "pending"
                or json.loads(row["body_json"]).get("mode") != "npc_response"
            ):
                raise WorkflowError("Only the actual invited NPC controller answers this request.")
        state = load_state(c, self.store.campaign_id)
        characters = current_original_characters(c, self.game, state, period)
        locks = t.m2["m2_locks"]
        unrestored_chat = (
            c.scalar(
                sa.select(locks.c.channel_id)
                .where(locks.c.campaign_id == self.store.campaign_id, locks.c.state != "released")
                .limit(1)
            )
            is not None
        )
        if (
            state.revision != game_revision
            or self.game.pending_actions(c)
            or unrestored_chat
            or state.handler != period.handler
            or self.missions._current_handler(c) != period.handler
            or not {int(uid) for uid in characters} <= set(state.order)
            or any(not HandlerService(self.store)._member(c, uid) for uid in state.order)
        ):
            raise WorkflowError(
                "STALE_OFF_DUTY: finish pending Plays and review the current roster and state."
            )
        from girlframe.services.m3_frame_rewards import needs_refresh

        if needs_refresh(c, self.store, state, period):
            raise WorkflowError(
                "Refresh the actual Frame reward tasks before advancing this period."
            )
        return period, state

    def _original(self, c: Connection, period: rules.Period, state: GameState, owner: int) -> None:
        if (
            str(owner) in period.ended_characters
            or owner not in period.pilots
            or self.game.character_binding(c, state, owner, require_current_profile=False)
            != period.character_ids.get(str(owner))
        ):
            raise WorkflowError("This action belongs to the original living Girl's period.")

    def _bind_scene(
        self,
        c: Connection,
        state: GameState,
        scene: rules.Scene,
        *,
        independent_controllers: frozenset[int] = frozenset(),
    ) -> None:
        scene.character_ids = {
            str(uid): self.game.character_binding(c, state, uid, require_current_profile=False)
            for uid in scene.participants
            if str(uid) in state.sheets and uid not in independent_controllers
        }

    def _resolve(
        self, c: Connection, rows: list[dict[str, Any]], event: str, body: dict[str, Any]
    ) -> None:
        for row in rows:
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("revision", "state", "body_json", "event_id")
                    },
                    revision=row["revision"] + 1,
                    state="resolved",
                    body_json=json.dumps(body, sort_keys=True),
                    event_id=event,
                )
            )

    def _change(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        game_revision: int,
        kind: str,
        payload: dict[str, Any],
        change: Callable[
            [Connection, rules.Period, GameState],
            tuple[rules.Period, GameState, list[dict[str, Any]], dict[str, Any]],
        ],
        *,
        director_response: bool = False,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            period, state = self._current(c, viewer, identity, game_revision)
            if period.revision != expected:
                raise WorkflowError("STALE_OFF_DUTY: reopen the period.")
            updated, state, resolved, proof = change(c, period, state)
            from girlframe.services.m3_observation import settle, synchronize

            settle(updated, state)
            event = self.game.event(c, viewer.user_id, key, kind, state, period_id=identity)
            self.periods._save(c, updated, event)
            synchronize(c, self.store, updated, event)
            self._resolve(c, resolved, event, proof)
            if updated.handler_work is not None and period.handler_work is None:
                from girlframe.services.m3_work import related

                assert updated.handler_recipient is not None
                anchor = next(
                    x
                    for x in self.periods._pending(c, identity)
                    if x["kind"] == "off_duty_handler_scene"
                )
                related(
                    c,
                    self.store,
                    anchor,
                    updated.handler_work,
                    period.handler,
                    updated.handler_recipient,
                    "punishment",
                    {"reason": "off_duty_handler", "source_pdf": 118, "due_stage": "active"},
                    event,
                )
            return {"id": identity, "revision": updated.revision, "phase": updated.phase}

        return self.missions._write(
            viewer,
            key,
            kind,
            {"id": identity, "expected": expected, "game_revision": game_revision, **payload},
            operation,
            lambda c: self.missions.access.authorize(
                c, viewer, "plays", director_response=director_response
            ),
            director_response=director_response,
        )

    def activate(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, game_revision: int
    ) -> dict[str, Any]:
        def change(c: Connection, period: rules.Period, state: GameState) -> Outcome:
            self.missions._handler(c, viewer)
            self.missions.access.authorize(c, viewer, "strain")
            self.missions.access.authorize(c, viewer, "world")
            strain = state.strain
            if (
                state.world is None
                or strain is None
                or identity not in strain.periods
                or any(x.period_id == identity for x in strain.requests)
            ):
                raise WorkflowError("Finish the real world setup and Strain cycle first.")
            base = [x for x in strain.events if x.period_id == identity and x.parent is None]
            if (
                len(base) != 3
                or {x.track for x in base} != set(TRACKS)
                or any(x.column is None for x in base)
            ):
                raise WorkflowError("All three real Strain rolls need saved column choices.")
            work = self.periods._pending(c, identity)
            start = [x for x in work if x["kind"] == "off_duty_strain_start"]
            blockers = frozenset(
                x["id"]
                for x in work
                if x["kind"]
                not in ("off_duty_strain_start", "off_duty_handler_scene", "off_duty_status_review")
                and not (
                    x["kind"] == "punishment"
                    and json.loads(x["body_json"]).get("due_stage") == "active"
                )
                and not (
                    x["kind"] == "frame_off_duty_reward"
                    and json.loads(x["body_json"]).get("due_stage") == "active"
                )
            )
            if len(start) != 1 or any(
                (
                    sheet.frame_scrapped
                    and can_pilot(
                        state,
                        ActorRef(
                            kind="pilot",
                            entity=str(uid),
                            incarnation=period.character_ids[str(uid)],
                        ),
                    )
                )
                or self.game.immediate_work(c, uid)
                for uid in period.pilots
                if str(uid) not in period.ended_characters
                for sheet in (state.sheets[str(uid)],)
            ):
                raise WorkflowError("Resolve actual start triggers and immediate sheet work first.")
            updated = rules.activate(period, period.revision, pending_preparation=blockers)
            return updated, state, start, {"source_pdf": 142, "strain_events": [x.id for x in base]}

        return self._change(
            viewer, key, identity, expected, game_revision, "m3.off_duty_activated", {}, change
        )

    def scene(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        game_revision: int,
        kind: str | None,
        participants: tuple[int, ...],
        summary: str,
    ) -> dict[str, Any]:
        def change(c: Connection, period: rules.Period, state: GameState) -> Outcome:
            self._original(c, period, state, viewer.user_id)
            progress = period.progress.get(str(viewer.user_id))
            if progress is not None and progress.observation is not None:
                from girlframe.engine.m3_observation import scene, scene_roles

                if kind is None:
                    raise WorkflowError("Void Observation always requires an actual scene.")
                selected = scene(
                    period,
                    expected,
                    viewer.user_id,
                    kind,
                    participants,
                    summary,
                    extra_participants=scene_roles(period, state, viewer.user_id),
                    required_participants=scene_roles(period, state, viewer.user_id, kind),
                )
                selected_scene = selected.progress[str(viewer.user_id)].scene
                assert selected_scene is not None
                self._bind_scene(
                    c,
                    state,
                    selected_scene,
                    independent_controllers=scene_roles(period, state, viewer.user_id)
                    - {viewer.user_id, period.handler},
                )
                return selected, state, [], {}
            updated = rules.choose_scene(
                period,
                expected,
                viewer.user_id,
                kind=kind,
                participants=participants,
                summary=summary,
                available_pilots=frozenset(state.order),
            )
            saved = updated.progress[str(viewer.user_id)].scene
            if saved is not None:
                self._bind_scene(c, state, saved)
            return updated, state, [], {}

        return self._change(
            viewer,
            key,
            identity,
            expected,
            game_revision,
            "m3.off_duty_scene_chosen",
            {"kind": kind, "participants": participants, "summary": summary},
            change,
        )

    def acknowledge(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        game_revision: int,
        scene_owner: int | None,
    ) -> dict[str, Any]:
        def change(c: Connection, period: rules.Period, state: GameState) -> Outcome:
            actual_scene = (
                period.handler_scene
                if scene_owner is None
                else (period.progress.get(str(scene_owner), rules.Progress()).scene)
            )
            if actual_scene is not None and str(viewer.user_id) in (
                actual_scene.character_ids or period.character_ids
            ):
                expected_character = (actual_scene.character_ids or period.character_ids)[
                    str(viewer.user_id)
                ]
                if (
                    self.game.character_binding(
                        c, state, viewer.user_id, require_current_profile=False
                    )
                    != expected_character
                ):
                    raise WorkflowError("This scene invitation belongs to its original character.")
            if scene_owner is not None:
                progress = period.progress.get(str(scene_owner))
                if progress and progress.observation and progress.scene:
                    from girlframe.engine.m3_observation import scene_roles

                    if not scene_roles(period, state, scene_owner, progress.scene.kind) <= set(
                        progress.scene.participants
                    ):
                        raise WorkflowError(
                            "Recover the changed NPC scene controller before confirmation."
                        )
            updated = (
                rules.acknowledge_handler_scene(period, expected, viewer.user_id)
                if scene_owner is None
                else rules.acknowledge_scene(period, expected, viewer.user_id, scene_owner)
            )
            resolved = []
            if scene_owner is None:
                scene = updated.handler_scene
                assert scene is not None
                if set(scene.participants) == set(scene.acknowledgements):
                    if scene.kind in ("npc_employment", "prisoner"):
                        self.missions.access.authorize(c, viewer, "world")
                        self._handler_entity(
                            state, scene.kind, updated.handler_context, scene.participants
                        )
                        context = updated.handler_context
                        assert context is not None
                        if scene.kind == "npc_employment" and context.operation in ("hire", "fire"):
                            assert state.world is not None
                            entity = (context.entity or "").removeprefix("npc:")
                            state.world = world_rules.update(
                                state.world,
                                npcs=tuple(
                                    x.model_copy(
                                        update={
                                            "employment": "foundation"
                                            if context.operation == "hire"
                                            else "unemployed"
                                        }
                                    )
                                    if x.id == entity
                                    else x
                                    for x in state.world.npcs
                                ),
                            )
                    if scene.kind in ("npc_employment", "prisoner", "exploit"):
                        state.facts.append(
                            {
                                "kind": "handler_off_duty_scene",
                                "period_id": period.id,
                                "scene_kind": scene.kind,
                                "entity": updated.handler_context.entity or ""
                                if updated.handler_context
                                else "",
                                "operation": updated.handler_context.operation or ""
                                if updated.handler_context
                                else "",
                                "subject": str(updated.handler_recipient or ""),
                            }
                        )
                    if scene.kind == "permission":
                        recipient = updated.handler_recipient
                        if recipient is None or recipient not in scene.participants:
                            raise WorkflowError("The actual award recipient must be in this scene.")
                        sheet = state.sheets[str(recipient)]
                        sheet.permissions += 1
                        sheet.revision += 1
                    resolved = [
                        x
                        for x in self.periods._pending(c, identity)
                        if x["kind"] == "off_duty_handler_scene"
                    ]
                    if scene.kind == "punish" and any(
                        x["id"] == updated.handler_work for x in self.periods._pending(c, identity)
                    ):
                        resolved = []
            return (
                updated,
                state,
                resolved,
                {
                    "source_pdf": 118,
                    "scene": updated.handler_scene.kind if updated.handler_scene else None,
                    "attestations": True,
                },
            )

        return self._change(
            viewer,
            key,
            identity,
            expected,
            game_revision,
            "m3.off_duty_scene_attested",
            {"scene_owner": scene_owner},
            change,
            director_response=scene_owner is not None,
        )

    def recover(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        game_revision: int,
        choice: rules.RecoveryChoice,
    ) -> dict[str, Any]:
        choice = rules.RecoveryChoice.model_validate_json(choice.model_dump_json())

        def change(c: Connection, period: rules.Period, state: GameState) -> Outcome:
            self._original(c, period, state, viewer.user_id)
            pending = frozenset(
                x["id"]
                for x in self.periods._pending(c, identity)
                if x["subject_id"] == str(viewer.user_id)
                and x["kind"] not in ("off_duty_handler_scene", "off_duty_status_review")
            )
            from girlframe.engine.m3_repairs import active as repair_shortages

            shortage = bool(repair_shortages(state, identity))
            # Required M2 mechanical debts are not generic narrative follow-throughs.
            if any(
                x.owner == viewer.user_id
                and x.state == "pending"
                and x.kind in ("punishment", "void_observation", "defeat", "helpless")
                and x.details.get("after_period") != identity
                for x in state.obligations
            ):
                raise WorkflowError(
                    "Resolve the actual compulsory sheet consequences before recovery."
                )
            trusted = Recovery(
                **choice.model_dump(),
                repair_limit=1 if shortage else None,
                allow_duplicate_labels=bool(
                    self.store.policy.owner_m3_rulings
                    and self.store.policy.owner_m3_rulings.identity_duplicate_labels
                    == "distinct_ids"
                ),
                replacement_id=str(
                    uuid5(NAMESPACE_URL, identity + ":embrace:" + str(viewer.user_id))
                )
                if choice.embrace_tag
                else None,
            )
            updated, sheet = rules.recovery(
                period,
                expected,
                viewer.user_id,
                state.sheets[str(viewer.user_id)],
                trusted,
                pending_effects=pending,
            )
            state.sheets[str(viewer.user_id)] = sheet
            if choice.embrace_tag:
                ChoiceEngine(self.game).tag_resolved(state, viewer.user_id, choice.embrace_tag)
            return updated, state, [], {}

        return self._change(
            viewer,
            key,
            identity,
            expected,
            game_revision,
            "m3.off_duty_recovered",
            {"choice": choice.model_dump(mode="json")},
            change,
        )

    def handler_scene(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        game_revision: int,
        kind: str,
        participants: tuple[int, ...],
        summary: str,
        recipient: int | None = None,
        context: rules.HandlerContext | None = None,
    ) -> dict[str, Any]:
        if context is not None:
            context = rules.HandlerContext.model_validate_json(context.model_dump_json())

        def change(c: Connection, period: rules.Period, state: GameState) -> Outcome:
            self.missions._handler(c, viewer)
            if kind not in rules.HANDLER_SCENES:
                raise WorkflowError("Choose a printed Handler scene.")
            extra: frozenset[int] = frozenset()
            if kind in ("npc_employment", "prisoner"):
                self.missions.access.authorize(c, viewer, "world")
                controller = self._handler_entity(state, kind, context, participants)
                extra = frozenset({controller})
                if not HandlerService(self.store)._member(c, controller):
                    raise WorkflowError(
                        "The actual NPC/Pilot role needs a current human participant."
                    )
            elif context is not None:
                raise WorkflowError("This scene does not take a world entity or NPC operation.")
            updated = rules.handler_scene(
                period,
                expected,
                viewer.user_id,
                kind,
                tuple(dict.fromkeys(participants + tuple(extra))),
                summary,
                extra_participants=extra,
            )
            if (
                kind in ("permission", "punish", "exploit")
                and (recipient not in participants or recipient not in period.pilots)
            ) or (kind not in ("permission", "punish", "exploit") and recipient is not None):
                raise WorkflowError(
                    "Choose an actual Girl participant only for the Permission award."
                )
            updated.handler_recipient = recipient
            updated.handler_context = context
            assert updated.handler_scene is not None
            self._bind_scene(c, state, updated.handler_scene)
            if kind == "punish":
                self.missions.access.authorize(c, viewer, "discipline")
                updated.handler_work = identity + ":handler-punishment"
            return updated, state, [], {}

        return self._change(
            viewer,
            key,
            identity,
            expected,
            game_revision,
            "m3.off_duty_handler_scene",
            {
                "kind": kind,
                "participants": participants,
                "summary": summary,
                "recipient": recipient,
                "context": context.model_dump(mode="json") if context else None,
            },
            change,
        )

    def review_status(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        game_revision: int,
        order: tuple[int, ...],
        account: str,
    ) -> dict[str, Any]:
        def change(c: Connection, period: rules.Period, state: GameState) -> Outcome:
            self.missions._handler(c, viewer)
            rules.current(period, expected)
            pending = self.periods._pending(c, identity)
            review = [x for x in pending if x["kind"] == "off_duty_status_review"]
            if (
                (period.status_review is None and len(review) != 1)
                or period.status_review_game_revision == state.revision
                or len(order) != len(state.order)
                or set(order) != set(state.order)
                or not account.strip()
                or len(account) > 1200
                or any(
                    not period.progress.get(str(uid), rules.Progress()).recovered
                    and str(uid) not in period.ended_characters
                    for uid in period.pilots
                )
                or any(x["kind"] != "off_duty_status_review" for x in pending)
            ):
                raise WorkflowError(
                    "Finish recovery and actual work, then review every "
                    "current Girl's performance once."
                )
            updated = rules.clone(period)
            updated.status_review = order
            updated.status_review_game_revision = state.revision + 1
            updated.revision += 1
            state.order = order
            return (
                updated,
                state,
                review,
                {"source_pdf": 118, "order": order, "account": account.strip()},
            )

        return self._change(
            viewer,
            key,
            identity,
            expected,
            game_revision,
            "m3.off_duty_status_reviewed",
            {"order": order, "account": account},
            change,
        )

    def review(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        from girlframe.services.m3_frame_rewards import needs_refresh

        with self.store.engine.connect() as c:
            period = self.periods._get(c, identity)
            self.periods._view(c, viewer, period)
            state = load_state(c, self.store.campaign_id)
            own = period.progress.get(str(viewer.user_id))
            scenes = [
                {"owner": int(uid), **progress.scene.model_dump(mode="json")}
                for uid, progress in period.progress.items()
                if progress.scene is not None and viewer.user_id in progress.scene.participants
            ]
            handler_scene = period.handler_scene
            observation_people: frozenset[int] = frozenset()
            if own is not None and own.observation is not None:
                from girlframe.engine.m3_observation import scene_roles

                observation_people = scene_roles(period, state, viewer.user_id)
            return {
                **self.periods.get(viewer, identity),
                "game_revision": state.revision,
                "handler": period.handler,
                "participants": tuple(
                    (str(uid), state.sheets[str(uid)].callsign) for uid in state.order
                ),
                "original_participants": tuple(
                    (
                        str(uid),
                        original_sheet(
                            state,
                            ActorRef(
                                kind="pilot",
                                entity=str(uid),
                                incarnation=period.character_ids[str(uid)],
                            ),
                        ).callsign,
                    )
                    for uid in period.pilots
                ),
                "ended_characters": dict(period.ended_characters),
                "own": own.model_dump(mode="json") if own else None,
                "pre_modifiers": [
                    {"source": "missed_supply", "amount": x.amount, "resource": x.resource}
                    for x in state.supply_losses
                    if x.period == identity
                    and x.action is None
                    and x.owner.entity == str(viewer.user_id)
                    and x.owner.incarnation == period.character_ids.get(str(viewer.user_id))
                ],
                "sheet": state.sheets[str(viewer.user_id)].model_dump(mode="json")
                if viewer.user_id in period.pilots
                and str(viewer.user_id) not in period.ended_characters
                else None,
                "invitations": scenes,
                "observation_participants": tuple(
                    (str(uid), "NPC controller " + str(uid))
                    for uid in sorted(observation_people)
                    if uid not in period.pilots and uid != period.handler
                ),
                "handler_scene": handler_scene.model_dump(mode="json")
                if handler_scene and viewer.user_id in handler_scene.participants
                else None,
                "status_reviewed": period.status_review is not None
                and period.status_review_game_revision == state.revision,
                "rewards_need_refresh": needs_refresh(c, self.store, state, period),
                "repair_limit": 1
                if any(x.period == identity and not x.closed for x in state.repair_shortages)
                else None,
            }

    def finish(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        game_revision: int,
        movements: tuple[world_rules.Movement, ...] = (),
        changes: tuple[world_rules.ClassChange, ...] = (),
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.missions._handler(c, viewer)
            self.missions.access.authorize(c, viewer, "world")
            period, state = self._current(c, viewer, identity, game_revision)
            if period.status_review_game_revision != state.revision:
                raise WorkflowError(
                    "Review current performance again after the intervening state change."
                )
            pending = frozenset(x["id"] for x in self.periods._pending(c, identity))
            # Prove actual completion before advancing any world entity.
            finished, updated = rules.finish(
                period,
                expected,
                state,
                pending_work=pending,
                handler_scene_complete=(
                    period.handler_scene is not None
                    and set(period.handler_scene.participants)
                    == set(period.handler_scene.acknowledgements)
                )
                or (not state.order and set(period.ended_characters) == set(period.character_ids)),
                status_review_complete=period.status_review is not None,
            )
            if updated.world is None or updated.strain is None:
                raise WorkflowError("Initialize the actual world and Strain before period end.")
            followups: tuple[world_rules.Followup, ...] = ()
            if identity not in updated.world.completed_off_duty:
                result = world_rules.end_off_duty(updated.world, identity, movements, changes)
                updated.world = result.world
                followups = result.followups
            elif movements or changes:
                raise WorkflowError("World movement is already saved; resume its pending effects.")
            severe = [x for x in followups if x.kind != "budget_structure_destroyed"]
            if severe:
                # Save actual destruction/movement, keep the period active and retain locks.
                finished = rules.clone(period)
                finished.revision += 1
                updated = GameState.model_validate_json(
                    state.model_copy(update={"world": updated.world}).model_dump_json()
                )
            event = str(uuid4())
            additions = tuple(
                Trigger(
                    id=identity + ":structure:" + x.entity,
                    kind="structure_destroyed",
                    entity=x.entity,
                    source_event=event,
                )
                for x in followups
                if x.kind == "budget_structure_destroyed"
            )
            if additions:
                assert updated.strain is not None
                updated.strain = updated.strain.model_copy(
                    update={"triggers": updated.strain.triggers + additions}
                )
            if not severe:
                from girlframe.engine.m3_repairs import close_period

                updated = close_period(updated, identity)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.off_duty_end",
                updated,
                event_id=event,
                period_id=identity,
                completed=not severe,
            )
            self.periods._save(c, finished, event)
            if severe:
                table = t.m3["m3_required_work"]
                anchor = (
                    c.execute(
                        sa.select(table)
                        .where(
                            table.c.campaign_id == self.store.campaign_id,
                            table.c.off_duty_id == identity,
                        )
                        .limit(1)
                    )
                    .mappings()
                    .first()
                )
                assert anchor is not None
                from girlframe.services.m3_work import related

                for item in severe:
                    related(
                        c,
                        self.store,
                        dict(anchor),
                        identity + ":world:" + item.kind + ":" + item.entity,
                        period.handler,
                        period.handler,
                        item.kind,
                        item.model_dump(mode="json"),
                        event,
                    )
            return {"id": identity, "revision": finished.revision, "phase": finished.phase}

        return self.missions._write(
            viewer,
            key,
            "m3.off_duty_end",
            {
                "id": identity,
                "expected": expected,
                "game_revision": game_revision,
                "movements": [x.model_dump(mode="json") for x in movements],
                "changes": [x.model_dump(mode="json") for x in changes],
            },
            operation,
            lambda c: self.missions.access.authorize(c, viewer, "plays"),
        )

    def _handler_entity(
        self,
        state: GameState,
        kind: str,
        context: rules.HandlerContext | None,
        participants: tuple[int, ...],
    ) -> int:
        world = state.world
        if world is None or context is None or not context.entity:
            raise WorkflowError("Choose an actual current world entity for this scene.")
        category, separator, identity = context.entity.partition(":")
        if not separator:
            raise WorkflowError("Choose a current NPC or prisoner from the scene's selectors.")
        if kind == "npc_employment":
            target = next((x for x in world.npcs if x.id == identity and x.alive), None)
            if category != "npc" or target is None or context.operation is None:
                raise WorkflowError(
                    "Choose a living NPC and the actual hiring/firing/request interaction."
                )
            if target.captive_of is not None:
                raise WorkflowError(
                    "An NPC in Gorgon custody is unavailable for this base interaction."
                )
            return target.controller
        if kind != "prisoner" or context.operation is not None:
            raise WorkflowError("Only NPC employment takes a hiring/firing/request operation.")
        if category == "npc":
            target = next((x for x in world.npcs if x.id == identity and x.alive), None)
            if target is None or "prisoner" not in target.jobs or target.captive_of is not None:
                raise WorkflowError("Choose an actual prisoner NPC; other custody is not inferred.")
            return target.controller
        prisoner = next((x for x in world.pilots if x.id == identity and x.alive), None)
        if (
            category != "pilot"
            or prisoner is None
            or prisoner.custody not in ("captured", "transported")
            or prisoner.custodian not in participants
        ):
            raise WorkflowError(
                "This Pilot needs actual current custody by a participating custodian."
            )
        return prisoner.controller
