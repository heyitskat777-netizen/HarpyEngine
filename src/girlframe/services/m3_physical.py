"""Owned original physical facts, facilitator review and no placement reset command."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_physical as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, owned_refs, resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_physical_state import CockpitAction, FrameLock, InitialPlacement, Review
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KIND = "physical_initial"
Decision = Literal["accept", "decline", "withdraw"]


class PhysicalService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        Access(self.store).authorize(c, viewer, "world", director_response=True)

    def _handler(self, c: Connection, viewer: GuildViewer) -> None:
        HandlerService(self.store).authorize(c, viewer)
        if load_state(c, self.store.campaign_id).handler != viewer.user_id:
            raise WorkflowError("Recover the actual Handler appointment before physical review.")

    def _rows(self, c: Connection) -> list[dict[str, Any]]:
        table = t.m3["m3_required_work"]
        return list(
            {
                row["id"]: dict(row)
                for row in c.execute(
                    sa.select(table)
                    .where(table.c.campaign_id == self.store.campaign_id, table.c.kind == KIND)
                    .order_by(table.c.revision)
                ).mappings()
            }.values()
        )

    def _row(self, c: Connection, identity: str) -> dict[str, Any]:
        row = next((x for x in self._rows(c) if x["id"] == identity), None)
        if row is None:
            raise WorkflowError("Unknown physical setup request.")
        return row

    def _review(self, c: Connection, row: dict[str, Any]) -> Review:
        body = Review.model_validate_json(row["body_json"])
        source = (
            c.execute(
                sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == body.proposed_event,
                )
            )
            .mappings()
            .first()
        )
        if (
            source is None
            or row["campaign_id"] != self.store.campaign_id
            or row["state"] not in ("pending", "resolved")
            or (row["state"] == "pending") != (body.decision == "pending")
            or source["kind"] != "m3.initial_placement_proposed"
            or source["actor_id"] != body.proposal.actor.entity
            or json.loads(source["payload_json"]).get("work_id") != row["id"]
            or row["owner_id"] != str(body.handler)
            or row["subject_id"] != body.proposal.actor.entity
            or not row["campaign_context"]
            or any(row[x] is not None for x in ("mission_id", "off_duty_id", "scene_id"))
        ):
            raise WorkflowError("SOURCE_PLACEMENT_MISSING: recover the original factual proposal.")
        return body

    def _party(self, c: Connection, viewer: GuildViewer, body: Review) -> bool:
        return viewer.user_id == int(body.proposal.actor.entity) or (
            viewer.user_id == body.handler
            and HandlerService(self.store).current(c)[1].handler_id == body.handler
            and load_state(c, self.store.campaign_id).handler == body.handler
        )

    def _idle(self, c: Connection) -> None:
        locks = t.m2["m2_locks"]
        if self.game.pending_actions(c) or c.scalar(
            sa.select(locks.c.channel_id)
            .where(
                locks.c.campaign_id == self.store.campaign_id,
                locks.c.state != "released",
            )
            .limit(1)
        ):
            raise WorkflowError(
                "Finish pending Plays and restore chat before confirming physical facts."
            )

    def preview(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            ref = ActorRef(
                kind="pilot",
                entity=str(viewer.user_id),
                incarnation=self.game.character_binding(
                    c, state, viewer.user_id, require_current_profile=False
                ),
            )
            actor = resolve(
                state, ref, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            placement = next((x for x in state.placements if x.actor == ref), None)
            return dict(
                game_revision=state.revision,
                pending_id=next(
                    (
                        row["id"]
                        for row in self._rows(c)
                        if row["state"] == "pending" and self._review(c, row).proposal.actor == ref
                    ),
                    None,
                ),
                actor=ref.model_dump(mode="json"),
                label=actor.label,
                frame_instance=actor.frame_instance,
                placement=placement.model_dump(mode="json") if placement else None,
                locations=[
                    dict(id=x.id, name=x.name, cell=list(x.cell)) for x in state.world.locations
                ]
                if state.world
                else [],
                position_sha256=actor.position_sha256,
                actual_cell=list(actor.cell) if actor.cell is not None else None,
                occupied_frame_instance=actor.occupied_frame_instance,
                frame_locks=[
                    x.id
                    for x in state.frame_locks
                    if (x.active or (placement and placement.subsumed))
                    and (
                        (x.owner == ref and x.frame_instance == actor.frame_instance)
                        or (
                            placement
                            and rules.occupied_frame(placement) == (x.owner, x.frame_instance)
                        )
                    )
                ],
                can_record_unknown=placement is not None
                and placement.custody is None
                and placement.occupied_frame_owner is None
                and not any(
                    (x.active and ref in (x.traveler, x.supervisor)) or ref in x.offstage_refs
                    for x in state.escort_journeys
                )
                and (
                    placement.girl_cell is None
                    or placement.frame_cell is None
                    or (
                        placement.frame_instance != actor.frame_instance
                        and placement.mode == "outside_frame"
                    )
                ),
            )

    def operate(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        command: CockpitAction,
    ) -> dict[str, Any]:
        command = CockpitAction.model_validate_json(command.model_dump_json())

        def access(c: Connection) -> None:
            self._access(c, viewer)
            if command.actor.entity != str(viewer.user_id):
                raise WorkflowError(
                    "Only the actual original Girl's owner performs this operation."
                )

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            self._idle(c)
            state = load_state(c, self.store.campaign_id)
            if type(revision) is not int or state.revision != revision:
                raise WorkflowError("STALE_COCKPIT: refresh the actual physical state.")
            if self.game.immediate_work(c, viewer.user_id):
                raise WorkflowError(
                    "Resolve the actual immediate consequence before ordinary cockpit operations."
                )
            if (
                self.game.character_binding(c, state, viewer.user_id, require_current_profile=False)
                != command.actor.incarnation
            ):
                raise WorkflowError(
                    "STALE_ACTOR: this cockpit action belongs to the original Girl."
                )
            bindings = profiles(c, self.store.campaign_id)
            actual = resolve(state, command.actor, bindings, require_current_profile=False)
            if actual.position_sha256 != command.expected_position:
                raise WorkflowError("STALE_COCKPIT: the original physical position changed.")
            placement = next((x for x in state.placements if x.actor == command.actor), None)
            frames = {(command.actor, actual.frame_instance)}
            occupied = rules.occupied_frame(placement) if placement is not None else None
            if occupied is not None:
                frames.add(occupied)
            for owner, instance in frames:
                latest = next(
                    (
                        x
                        for x in reversed(state.frame_locks)
                        if x.owner == owner and x.frame_instance == instance
                    ),
                    None,
                )
                if latest is not None:
                    self._frame_lock(c, viewer, latest.id)
            source = str(uuid4())
            if command.operation == "exit":
                updated = rules.cockpit_exit(
                    state, bindings, command.actor, source, command.account
                )
            else:
                updated = rules.cockpit_enter(
                    state,
                    bindings,
                    command.actor,
                    source,
                    command.account,
                    pilot=command.operation == "pilot",
                )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.cockpit_operated",
                updated,
                event_id=source,
                operation=command.operation,
            )
            void_works = []
            if command.operation != "exit" and occupied != (command.actor, actual.frame_instance):
                sheet = updated.sheets[command.actor.entity]
                from girlframe.engine.m3_janus_storage import effective_assets

                for family in ("girl", "frame"):
                    assets = [
                        x for x in effective_assets(updated, command.actor) if x.family == family
                    ]
                    if (
                        not assets
                        or not all(x.void for x in assets)
                        or (
                            family == "girl"
                            and has_rule(sheet, "girl.mockingbird.risk-factor", "MOCKINGBIRD")
                        )
                    ):
                        continue
                    identity = str(uuid4())
                    related(
                        c,
                        self.store,
                        dict(campaign_id=self.store.campaign_id, campaign_context=True),
                        identity,
                        viewer.user_id,
                        viewer.user_id,
                        "void_threshold",
                        dict(
                            owner=command.actor.model_dump(mode="json"),
                            character=command.actor.incarnation,
                            frame=actual.frame_instance,
                            source_action=None,
                            source_pdf=19,
                            details=dict(family=family),
                            reason="physical_entry",
                            immediate=True,
                        ),
                        source,
                    )
                    void_works.append(identity)
            return dict(
                operation=command.operation, revision=updated.revision, void_works=void_works
            )

        try:
            return self.store._write(
                viewer,
                key,
                "m3.cockpit_operated",
                dict(
                    revision=revision,
                    command=command.model_dump(mode="json"),
                ),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def journey_tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            return self._journey_tasks(c, viewer)

    def _journey_tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        bindings = profiles(c, self.store.campaign_id)
        result = []
        for journey in state.escort_journeys:
            for participant in journey.offstage_refs:
                try:
                    actual = resolve(state, participant, bindings, require_current_profile=False)
                except ValueError:
                    continue
                if actual.controller == viewer.user_id:
                    result.append(
                        dict(
                            id=journey.id,
                            participant=participant.model_dump(mode="json"),
                            label=actual.label,
                            revision=state.revision,
                            expected=fingerprint(journey),
                        )
                    )
        return result

    def journey(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            selected = next(
                (x for x in self._journey_tasks(c, viewer) if x["id"] == identity), None
            )
            if selected is None:
                raise WorkflowError(
                    "This interrupted journey belongs to its actual surviving role."
                )
            state = load_state(c, self.store.campaign_id)
            return selected | dict(
                locations=[
                    dict(id=x.id, name=x.name, cell=list(x.cell)) for x in state.world.locations
                ]
                if state.world
                else []
            )

    def recover_journey(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        participant: ActorRef,
        expected: str,
        revision: int,
        cell: tuple[int, int] | None,
        account: str,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            actual = resolve(
                state,
                participant,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
            if actual.controller != viewer.user_id:
                raise WorkflowError("Only the actual surviving role's human records its recovery.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            self._idle(c)
            state = load_state(c, self.store.campaign_id)
            journey = next((x for x in state.escort_journeys if x.id == identity), None)
            if (
                type(revision) is not int
                or revision != state.revision
                or journey is None
                or fingerprint(journey) != expected
            ):
                raise WorkflowError("STALE_JOURNEY: refresh the actual interrupted recovery.")
            source = str(uuid4())
            updated = rules.recover_interrupted_journey(
                state,
                profiles(c, self.store.campaign_id),
                identity,
                participant,
                cell,
                source,
                account,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.interrupted_party_recovered",
                updated,
                event_id=source,
                journey_id=identity,
            )
            return dict(id=identity, recovered=True)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.interrupted_party_recovered",
                dict(
                    id=identity,
                    participant=participant.model_dump(mode="json"),
                    expected=expected,
                    revision=revision,
                    cell=cell,
                    account=account,
                ),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _frame_lock(
        self,
        c: Connection,
        viewer: GuildViewer,
        identity: str,
    ) -> tuple[GameState, FrameLock, GameState]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        lock = next((x for x in state.frame_locks if x.id == identity), None)
        if lock is None:
            raise WorkflowError("This original Frame cockpit is unavailable.")
        if lock.owner.kind != "pilot" or lock.subject.kind != "pilot":
            raise WorkflowError("Use the actual Harpy body's dedicated cockpit controls.")
        try:
            voice = rules.frame_voice(state, lock.owner, lock.frame_instance)
        except ValueError:
            voice = None
        permitted = {int(lock.owner.entity), int(lock.subject.entity), voice}
        permitted.update(
            int(x.actor.entity)
            for x in state.placements
            if rules.occupied_frame(x) == (lock.owner, lock.frame_instance)
        )
        permitted.update(x.controller for x in lock.consents)
        if viewer.user_id not in permitted:
            bindings = profiles(c, self.store.campaign_id)
            target = next((x for x in state.placements if x.actor == lock.subject), None)
            scenes = t.m2["m2_scenes"]
            shared_scene = any(
                {viewer.user_id, int(lock.subject.entity)} <= set(json.loads(raw))
                for raw in c.scalars(
                    sa.select(scenes.c.participants_json).where(
                        scenes.c.campaign_id == self.store.campaign_id, scenes.c.open.is_(True)
                    )
                )
            )
            if target is not None and shared_scene:
                actual_target = resolve(
                    state, lock.subject, bindings, require_current_profile=False
                )
                if actual_target.cell is not None and any(
                    resolve(state, ref, bindings, require_current_profile=False).cell
                    == actual_target.cell
                    for ref in owned_refs(state, viewer.user_id, bindings)
                    if ref != lock.subject
                ):
                    permitted.add(viewer.user_id)
        if viewer.user_id not in permitted:
            raise WorkflowError("This actual cockpit belongs to its original participants.")
        history = t.m2["m2_state_history"]

        def source(event: str) -> GameState | None:
            body = c.scalar(
                sa.select(history.c.body_json).where(
                    history.c.campaign_id == self.store.campaign_id,
                    history.c.event_id == event,
                )
            )
            return GameState.model_validate_json(body) if body else None

        original = source(lock.source_event)
        first = (
            next((x for x in original.frame_locks if x.id == identity), None) if original else None
        )
        stable = ("id", "owner", "frame_instance", "subject", "source_event", "core_id")
        if (
            first is None
            or original is None
            or not first.active
            or first.consents
            or any(getattr(first, field) != getattr(lock, field) for field in stable)
        ):
            raise WorkflowError("SOURCE_COCKPIT_MISSING: recover the original subsumption event.")
        latest_by_actor = {x.actor: x for x in lock.consents}
        for latest in latest_by_actor.values():
            answered = source(latest.source_event)
            recorded = (
                next((x for x in answered.frame_locks if x.id == identity), None)
                if answered
                else None
            )
            reply = (
                next((x for x in recorded.consents if x.source_event == latest.source_event), None)
                if recorded
                else None
            )
            response_actor = c.scalar(
                sa.select(t.events.c.actor_id).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == latest.source_event,
                )
            )
            if (
                reply is None
                or reply.model_copy(update={"used_event": latest.used_event}) != latest
                or response_actor != str(latest.controller)
            ):
                raise WorkflowError(
                    "SOURCE_FRAME_CONSENT_MISSING: recover the actual Frame response."
                )
        if not lock.active:
            released = source(lock.released_event or "")
            recorded = (
                next((x for x in released.frame_locks if x.id == identity), None)
                if released
                else None
            )
            if (
                recorded is None
                or recorded.active
                or recorded.released_event != lock.released_event
            ):
                raise WorkflowError(
                    "SOURCE_COCKPIT_RELEASE_MISSING: recover the Frame's actual opening."
                )
        return state, lock, original

    def frame(
        self, viewer: GuildViewer, identity: str, target: ActorRef | None = None
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            return self._frame(c, viewer, identity, target)

    def _frame(
        self, c: Connection, viewer: GuildViewer, identity: str, target: ActorRef | None = None
    ) -> dict[str, Any]:
        state, lock, original = self._frame_lock(c, viewer, identity)
        occupants = [
            x.actor
            for x in state.placements
            if rules.occupied_frame(x) == (lock.owner, lock.frame_instance)
        ]
        if target is None:
            target = next((x for x in occupants if x.entity == str(viewer.user_id)), lock.subject)
        if target != lock.subject and target not in occupants:
            raise WorkflowError("Choose an actual original body in this cockpit.")
        body = next((x for x in state.placements if x.actor == target), None)
        present = body is not None and rules.occupied_frame(body) == (
            lock.owner,
            lock.frame_instance,
        )
        try:
            voice = rules.frame_voice(state, lock.owner, lock.frame_instance)
        except ValueError:
            voice = None
        latest = next((x for x in reversed(lock.consents) if x.actor == target), None)
        allowed = bool(latest and latest.allowed and latest.used_event is None)
        extractors = []
        if present and (not lock.active or allowed):
            bindings = profiles(c, self.store.campaign_id)
            target_view = resolve(state, target, bindings, require_current_profile=False)
            for ref in owned_refs(state, viewer.user_id, bindings):
                if ref == target:
                    continue
                actual = resolve(state, ref, bindings, require_current_profile=False)
                placement = next((x for x in state.placements if x.actor == ref), None)
                if (
                    actual.cell is None
                    or actual.cell != target_view.cell
                    or actual.custody not in (None, "free")
                    or (
                        placement is not None
                        and (
                            placement.incapacitated
                            or placement.subsumed
                            or not placement.vitals_active
                        )
                    )
                ):
                    continue
                extractors.append(
                    dict(ref=ref.model_dump(mode="json"), token=ref.token, label=actual.label)
                )
        sheet = (
            original.sheets.get(target.entity)
            if target == lock.subject
            else state.sheets.get(target.entity)
        )
        return dict(
            id=identity,
            active=lock.active,
            subject=target.model_dump(mode="json"),
            occupants=[
                dict(
                    ref=x.model_dump(mode="json"),
                    token=x.token,
                    label=state.sheets[x.entity].callsign,
                )
                for x in occupants
                if x.entity in state.sheets
            ],
            label=sheet.callsign if sheet else "Original Girl",
            can_voice=lock.active and viewer.user_id == voice,
            present=present,
            allowed=allowed,
            extractors=extractors,
            expected=fingerprint(lock),
            revision=state.revision,
            vitals_active=body.vitals_active if body else None,
        )

    def frame_tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            result = []
            for lock in state.frame_locks:
                try:
                    result.append(self._frame(c, viewer, lock.id))
                except WorkflowError:
                    continue
            return result

    def respond_frame(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: str,
        revision: int,
        response: Literal["allow", "refuse", "open"],
        account: str,
        *,
        target: ActorRef | None = None,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self._access(c, viewer)
            state, lock, _ = self._frame_lock(c, viewer, identity)
            if rules.frame_voice(state, lock.owner, lock.frame_instance) != viewer.user_id:
                raise WorkflowError("Only the actual Frame's human voice can give this response.")
            represented_core = state.world is not None and any(
                x.id == lock.core_id for x in (*state.world.npcs, *state.world.pilots)
            )
            represented_core = represented_core or any(
                x.id == lock.core_id
                and x.alive
                and x.custody == "core"
                and x.core_frame_owner == lock.owner
                and x.core_frame_instance == lock.frame_instance
                for x in state.harpy_states
            )
            if not represented_core:
                self._handler(c, viewer)
            policy = self.store.policy.owner_m3_rulings
            if (
                policy is None
                or getattr(policy, "physical_frame_voice", None) != "controller_or_handler"
            ):
                raise WorkflowError("UNRESOLVED_RULING: record the actual Frame voice ownership.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, lock, _ = self._frame_lock(c, viewer, identity)
            if (
                type(revision) is not int
                or state.revision != revision
                or fingerprint(lock) != expected
            ):
                raise WorkflowError("STALE_COCKPIT: reopen the actual Frame decision.")
            source = str(uuid4())
            selected = ActorRef.model_validate_json(
                json.dumps(self._frame(c, viewer, identity, target)["subject"])
            )
            if response == "open":
                updated = rules.open_cockpit(
                    state, lock.owner, lock.frame_instance, viewer.user_id, source, account
                )
            elif response in ("allow", "refuse"):
                updated = rules.consent_to_extract(
                    state,
                    profiles(c, self.store.campaign_id),
                    selected,
                    viewer.user_id,
                    source,
                    account,
                    allowed=response == "allow",
                )
            else:
                raise WorkflowError("Choose the actual Frame's response.")
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.frame_cockpit_response",
                updated,
                event_id=source,
                cockpit_id=identity,
                response=response,
            )
            return dict(id=identity, response=response)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.frame_cockpit_response",
                dict(
                    id=identity,
                    expected=expected,
                    revision=revision,
                    response=response,
                    account=account,
                    target=target.model_dump(mode="json") if target else None,
                ),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def extract_body(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: str,
        revision: int,
        extractor: ActorRef,
        account: str,
        *,
        target: ActorRef | None = None,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self._access(c, viewer)
            self._frame_lock(c, viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            self._idle(c)
            state, lock, _ = self._frame_lock(c, viewer, identity)
            data = self._frame(c, viewer, identity, target)
            if (
                type(revision) is not int
                or state.revision != revision
                or data["expected"] != expected
                or extractor.model_dump(mode="json") not in [x["ref"] for x in data["extractors"]]
            ):
                raise WorkflowError(
                    "STALE_EXTRACTION: choose your actual present role and recorded consent."
                )
            source = str(uuid4())
            subject = ActorRef.model_validate_json(json.dumps(data["subject"]))
            updated = rules.extract(
                state, profiles(c, self.store.campaign_id), subject, source, account
            )
            updated.facts.append(
                dict(
                    kind="actual_body_extraction",
                    actor=extractor.model_dump_json(),
                    subject=subject.model_dump_json(),
                    source_event=source,
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.body_extracted",
                updated,
                event_id=source,
                cockpit_id=identity,
            )
            return dict(id=identity, extracted=True)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.body_extracted",
                dict(
                    id=identity,
                    expected=expected,
                    revision=revision,
                    extractor=extractor.model_dump(mode="json"),
                    account=account,
                    target=target.model_dump(mode="json") if target else None,
                ),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def propose(
        self, viewer: GuildViewer, key: str, expected: int, proposal: InitialPlacement
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self._access(c, viewer)
            if proposal.actor.kind != "pilot" or proposal.actor.entity != str(viewer.user_id):
                raise WorkflowError("Propose only your own original Girl's actual physical facts.")

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            if type(expected) is not int or state.revision != expected:
                raise WorkflowError("STALE_PLACEMENT: refresh the current original physical facts.")
            self.game.character_binding(c, state, viewer.user_id, require_current_profile=False)
            actor = rules.validate(state, profiles(c, self.store.campaign_id), proposal)
            handler = HandlerService(self.store).current(c)[1].handler_id
            if (
                handler is None
                or state.handler != handler
                or not HandlerService(self.store)._member(c, handler)
            ):
                raise WorkflowError("Recover the actual Handler appointment before physical setup.")
            if any(
                self._review(c, row).proposal.actor == proposal.actor
                for row in self._rows(c)
                if row["state"] != "resolved"
            ):
                raise WorkflowError("Resume or withdraw your existing original physical proposal.")
            identity, source = str(uuid4()), str(uuid4())
            body = Review(
                proposal=proposal,
                label=actor.label,
                handler=handler,
                proposed_event=source,
                origin=next((x for x in state.placements if x.actor == proposal.actor), None),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.initial_placement_proposed",
                event_id=source,
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
                body.model_dump(mode="json"),
                source,
            )
            return {"id": identity, "revision": 1}

        try:
            proposal = InitialPlacement.model_validate_json(proposal.model_dump_json())
            return self.store._write(
                viewer,
                key,
                "m3.initial_placement_proposed",
                dict(expected=expected, proposal=proposal.model_dump(mode="json")),
                operation,
                auto_audit=False,
                authorize=access,
            )
        except ValidationError:
            raise WorkflowError("Invalid physical facts; reopen your original review.") from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            return self._tasks(c, viewer)

    def _tasks(
        self, c: Connection, viewer: GuildViewer, *, history: bool = False
    ) -> list[dict[str, Any]]:
        return [
            dict(
                id=row["id"],
                revision=row["revision"],
                label=body.label,
                incoming=viewer.user_id == body.handler,
                state=row["state"],
            )
            for row in self._rows(c)
            if (history or row["state"] != "resolved")
            and str(viewer.user_id) in (row["owner_id"], row["subject_id"])
            and self._party(c, viewer, body := self._review(c, row))
        ]

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            row = self._row(c, identity)
            body = self._review(c, row)
            if not self._party(c, viewer, body):
                raise WorkflowError("These physical facts belong to their actual participants.")
            return dict(
                id=identity,
                revision=row["revision"],
                state=row["state"],
                review=body.model_dump(mode="json"),
                own=viewer.user_id == int(body.proposal.actor.entity),
                can_review=viewer.user_id == body.handler,
            )

    def decide(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        decision: Decision,
        account: str,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self._access(c, viewer)
            body = self._review(c, self._row(c, identity))
            if decision == "withdraw":
                if viewer.user_id != int(body.proposal.actor.entity):
                    raise WorkflowError("Only the actual proposing human can withdraw these facts.")
            elif decision in ("accept", "decline"):
                self._handler(c, viewer)
                if body.handler != viewer.user_id:
                    raise WorkflowError("Recover the original physical review's changed Handler.")
            else:
                raise WorkflowError("Choose an available physical review action.")

        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            body = self._review(c, row)
            if (
                type(expected) is not int
                or row["state"] != "pending"
                or row["revision"] != expected
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "STALE_PLACEMENT: reopen the pending actual review and respond."
                )
            event, vessel = str(uuid4()), None
            state = None
            if decision == "accept":
                self.game.unpaused(c)
                self._idle(c)
                if not HandlerService(self.store)._member(c, int(body.proposal.actor.entity)):
                    raise WorkflowError(
                        "The original proposing human must still be a campaign member."
                    )
                state = load_state(c, self.store.campaign_id)
                current = next(
                    (x for x in state.placements if x.actor == body.proposal.actor), None
                )
                if current != body.origin:
                    raise WorkflowError(
                        "STALE_PLACEMENT: the original body facts changed after this proposal."
                    )
                vessel = current.vessel_id if current else "vessel:" + identity
                state = rules.initial(
                    state,
                    profiles(c, self.store.campaign_id),
                    body.proposal,
                    vessel,
                    body.proposed_event,
                    event,
                )
                from girlframe.engine.m3_appearance_matrix import actual_return

                actual_return(state, body.proposal.actor, event)
            status = {"accept": "accepted", "decline": "declined", "withdraw": "withdrawn"}[
                decision
            ]
            body = Review.model_validate_json(
                body.model_copy(
                    update=dict(
                        decision=status, vessel_id=vessel, review_event=event, response=account
                    )
                ).model_dump_json()
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.initial_placement_reviewed",
                state,
                event_id=event,
                work_id=identity,
                decision=status,
            )
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("revision", "state", "body_json", "event_id")
                    },
                    revision=expected + 1,
                    state="resolved",
                    body_json=body.model_dump_json(),
                    event_id=event,
                )
            )
            return {"id": identity, "revision": expected + 1, "decision": status}

        try:
            return self.store._write(
                viewer,
                key,
                "m3.initial_placement_reviewed",
                dict(id=identity, expected=expected, decision=decision, account=account),
                operation,
                auto_audit=False,
                authorize=access,
            )
        except ValidationError:
            raise WorkflowError(
                "Invalid actual physical review; reopen the saved request."
            ) from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None
