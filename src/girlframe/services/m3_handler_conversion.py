"""Genuine captured Harpy treatment, real Mockingbird and ordinary advancement proof."""

from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_advancements as advancement
from girlframe.engine import m3_handler_conversion as rules
from girlframe.engine import m3_handler_ordinary as ordinary
from girlframe.engine import m3_harpy_physical as physical
from girlframe.engine.drafts import DraftInput
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_harpy_defeat import harpy
from girlframe.engine.m3_void_state import HarpyState
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.m3_handler_ordinary import HandlerOrdinaryService, _session
from girlframe.services.m3_handler_pr import _audit
from girlframe.services.m3_harpy_defeat import HarpyDefeatService
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _capture(game: GameService, c: Connection, state: GameState, value: rules.Repossession) -> None:
    source = _history(c, game, value.capture_event)
    body = HarpyDefeatService(game.store, game)._runtime(c, source, value.actor)
    effect = next((x for x in source.harpy_defeats if x.id == value.capture_effect), None)
    if (
        not isinstance(body, HarpyState)
        or effect is None
        or effect.actor != value.actor
        or effect.phase != "complete"
        or effect.choice not in ("foundation", "shutdown")
        or effect.cut_link
        or effect.factual_source != value.capture_event
        or body.custody != "captured"
        or body.custody_event != value.capture_event
        or effect.captor != body.custodian
        or not body.alive
        or body.original_archive != value.archive_id
        or body.origin != value.original_frame_owner
        or body.frame_instance != value.frame_instance
    ):
        raise WorkflowError("Recover genuine alive Harpy Defeat and its real Foundation capture")
    archive = next((x for x in source.career_archives if x.id == value.archive_id), None)
    if archive is None or archive.ending != "harpy" or archive.actor != body.origin:
        raise WorkflowError("Recover the original person's actual Harpy career source")


def prove_repossession(
    game: GameService, c: Connection, state: GameState, identity: str, *, ready: bool = False
) -> rules.Repossession:
    value = rules.get(state, identity)
    opened = rules.get(_history(c, game, value.open_event), identity)
    _audit(game, c, value.open_event, "m3.handler_conversion_opened", value.handler.entity)
    if any(
        getattr(opened, k) != getattr(value, k)
        for k in (
            "id",
            "actor",
            "handler",
            "appointment",
            "judge",
            "judge_appointment",
            "capture_event",
            "capture_effect",
            "archive_id",
            "original_frame_owner",
            "frame_instance",
            "open_event",
            "initial_harpy_json",
        )
    ):
        raise WorkflowError("Preserve the original captured person, Handler and physical source")
    _capture(game, c, state, value)
    for item in value.physicals:
        recorded = rules.get(_history(c, game, item.event), identity)
        _audit(
            game,
            c,
            item.event,
            "m3.handler_conversion_physical",
            str(
                resolve(
                    _history(c, game, item.event),
                    item.performer,
                    profiles(c, game.store.campaign_id),
                    require_current_profile=False,
                ).controller
            ),
        )
        if not any(
            x.event == item.event
            and x.model_dump(exclude={"review_event", "accepted"})
            == item.model_dump(exclude={"review_event", "accepted"})
            for x in recorded.physicals
        ):
            raise WorkflowError("Recover the actual custodian's performed physical source")
        if item.review_event:
            reviewed = rules.get(_history(c, game, item.review_event), identity)
            _audit(
                game,
                c,
                item.review_event,
                "m3.handler_conversion_physical_reviewed",
                str(value.judge),
            )
            if item not in reviewed.physicals:
                raise WorkflowError("Recover the actual original physical review")
            if item.accepted:
                endpoint = (
                    reviewed.extraction_event
                    if item.operation == "extract"
                    else reviewed.transport_event
                )
                if endpoint != item.review_event:
                    raise WorkflowError("Recover the physical source's actual transition event")
                physical_fact = next(
                    (
                        x
                        for x in _history(c, game, item.review_event).facts
                        if x.get("kind") == "harpy_physical"
                        and x.get("event") == item.review_event
                        and x.get("actor") == value.actor.model_dump_json()
                    ),
                    None,
                )
                if physical_fact is None:
                    raise WorkflowError("A review alone cannot replace actual extraction/transport")
    steps = (
        (
            value.treatment_event,
            "m3.handler_conversion_treated",
            str(value.judge),
            ("treatment_event", "accounts"),
        ),
        (
            value.package_event,
            "m3.handler_conversion_packaged",
            str(HarpyState.model_validate_json(value.initial_harpy_json).controller),
            ("package_event", "package", "resulting_actor"),
        ),
        (
            value.review_event,
            "m3.handler_conversion_reviewed",
            str(value.judge),
            ("review_event", "status_position"),
        ),
    )
    for event, kind, actor, fields in steps:
        if event:
            recorded = rules.get(_history(c, game, event), identity)
            _audit(game, c, event, kind, actor)
            if any(getattr(recorded, k) != getattr(value, k) for k in fields if k != "accounts"):
                raise WorkflowError("Preserve the real treatment and exact original-owner package")
            if event == value.treatment_event and any(
                recorded.accounts.get(k) != value.accounts.get(k)
                for k in ("purge", "organs", "conditioning")
            ):
                raise WorkflowError("Preserve all three actual medical treatment outcomes")
    if ready or value.phase == "complete":
        if (
            value.phase not in ("ready", "complete")
            or value.review_event is None
            or value.package is None
            or value.resulting_actor is None
            or not value.final_harpy_json
            or value.status_position is None
            or not all(
                (
                    value.extraction_event,
                    value.transport_event,
                    value.treatment_event,
                    value.package_event,
                )
            )
        ):
            raise WorkflowError(
                "Complete actual extraction, transport, treatment and owned package"
            )
        reviewed_state = _history(c, game, value.review_event)
        reviewed = rules.get(reviewed_state, identity)
        if reviewed.phase != "ready" or reviewed.final_harpy_json != value.final_harpy_json:
            raise WorkflowError(
                "Recover the exact actual ready conversion and final Harpy resources"
            )
        body = HarpyState.model_validate_json(value.final_harpy_json)
        if (
            body.linked
            or body.custody != "transported"
            or not body.alive
            or body.cell != value.destination
            or body.frame_instance != value.frame_instance
            or body.frame_shutdown != value.shutdown
        ):
            raise WorkflowError("Preserve the actual transported body and independent Frame fate")
        if value.phase == "ready" and (
            str(body.controller) in state.sheets
            or harpy(state, value.actor).model_dump_json() != value.final_harpy_json
        ):
            raise WorkflowError("No active successor or changed original body may be overwritten")
    if value.phase == "complete":
        born = rules.completed(_history(c, game, value.completion_event or ""), identity)
        _audit(
            game,
            c,
            value.completion_event or "",
            "m3.handler_conversion_completed",
            str(HarpyState.model_validate_json(value.initial_harpy_json).controller),
        )
        if any(
            getattr(born, k) != getattr(value, k)
            for k in (
                "completion_event",
                "resulting_actor",
                "final_harpy_json",
                "result_sheet_json",
                "package",
                "status_position",
                "shutdown",
            )
        ):
            raise WorkflowError(
                "Recover actual installed Mockingbird conversion, not an award note"
            )
    return value


def _slot(
    game: GameService, c: Connection, state: GameState, handler: ActorRef
) -> tuple[ordinary.Session | None, str | None]:
    if not same_handler_body(state, handler):
        return None, "original_handler_unavailable"
    if game.pending_actions(c):
        return None, "finish_pending_play"
    marks = [x for x in ordinary.marks(state) if same_handler_body(state, x.handler)]
    if any(x.trigger == "capture_convert" for x in marks):
        return None, "criterion_marked"
    session = next(
        (
            x
            for x in ordinary.sessions(state)
            if x.end_event is None and x.facilitator == int(handler.entity)
        ),
        None,
    )
    if session is None:
        return None, "no_active_session"
    _session(game, c, state, session.id)
    if any(x.session == session.id for x in marks):
        return None, "session_slot_used"
    return session, None


def _award(
    state: GameState, value: rules.Repossession, session: ordinary.Session, event: str
) -> rules.Repossession:
    identity = "ordinary:" + value.id
    ordinary.put(
        state,
        ordinary.Mark(
            id="conversion-mark:" + value.handler.token,
            handler=value.handler,
            session=session.id,
            review=value.id,
            award=identity,
            event=event,
            trigger="capture_convert",
        ),
    )
    advancement.grant(
        state,
        advancement.Award(
            id=identity,
            rule=ordinary.RULE,
            handler=value.handler,
            appointment=value.appointment,
            source_work=None,
            source_event=value.completion_event or event,
            award_event=event,
            account="Actual captured Harpy repossessed into a real Mockingbird",
            ordinary_source=ordinary.AwardSource(
                session=session.id, review=value.id, trigger="capture_convert"
            ),
        ),
    )
    return value.model_copy(
        update=dict(award=identity, award_session=session.id, award_event=event, award_blocked=None)
    )


def prove_award(
    game: GameService, c: Connection, state: GameState, award: advancement.Award
) -> None:
    source = award.ordinary_source
    if source is None or source.trigger != "capture_convert" or award.source_work is not None:
        raise WorkflowError("Recover the exact actual capture/conversion award source")
    birth = _history(c, game, award.award_event)
    value = prove_repossession(game, c, birth, source.review)
    session = _session(game, c, birth, source.session)
    saved = next((x for x in advancement.awards(birth) if x.id == award.id), None)
    if (
        saved is None
        or saved.phase != "held"
        or value.phase != "complete"
        or value.handler != award.handler
        or value.appointment != award.appointment
        or value.award != award.id
        or value.award_event != award.award_event
        or value.award_session != source.session
        or session.end_event
        or value.completion_event != award.source_event
        or saved.model_dump(exclude={"phase", "spend_event", "effects", "acquired_rule"})
        != award.model_dump(exclude={"phase", "spend_event", "effects", "acquired_rule"})
    ):
        raise WorkflowError("Preserve real completed conversion and its genuine ordinary award")
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == award.award_event,
        )
    ).first()
    owner = str(HarpyState.model_validate_json(value.initial_harpy_json).controller)
    if audit not in (
        ("m3.handler_conversion_completed", owner),
        ("m3.handler_conversion_claimed", value.handler.entity),
    ):
        raise WorkflowError("Recover the actual original source-owned conversion award event")
    relevant = [x for x in ordinary.marks(birth) if x.handler == value.handler]
    if (
        len([x for x in relevant if x.session == source.session]) != 1
        or len([x for x in relevant if x.trigger == "capture_convert"]) != 1
        or not any(x.award == award.id and x.review == value.id for x in relevant)
    ):
        raise WorkflowError("Preserve common Session cap and separate permanent conversion mark")


class HandlerConversionService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)
        self.ordinary = HandlerOrdinaryService(store)

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

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        self.ordinary._access(c, viewer)
        gate = Access(self.store)
        assert gate.registry is not None
        gate.registry.require_available(rules.RULE)

    def _value(
        self, c: Connection, viewer: GuildViewer, identity: str, revision: int | None = None
    ) -> tuple[GameState, rules.Repossession]:
        state = load_state(c, self.store.campaign_id)
        value = prove_repossession(self.game, c, state, identity)
        body = HarpyState.model_validate_json(value.initial_harpy_json)
        if viewer.user_id not in (body.controller, int(value.handler.entity), value.judge):
            custodian = harpy(state, value.actor).custodian if value.phase != "complete" else None
            if (
                custodian is None
                or resolve(
                    state,
                    custodian,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                ).controller
                != viewer.user_id
            ):
                raise WorkflowError("This original repossession belongs to its actual participants")
        if revision is not None and state.revision != revision:
            raise WorkflowError("STALE_CONVERSION: reopen the actual original repossession")
        return state, value

    def _judge(self, c: Connection, viewer: GuildViewer, value: rules.Repossession) -> None:
        if (viewer.user_id, MedicalService(self.store)._handler(c)[1]) != (
            value.judge,
            value.judge_appointment,
        ):
            raise WorkflowError("Only the original appointed human GM reviews actual treatment")

    def open(self, viewer: GuildViewer, key: str, revision: int, actor: ActorRef) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            handler = active_handler(state)
            if (
                handler is None
                or handler.entity != str(viewer.user_id)
                or state.revision != revision
            ):
                raise WorkflowError("Use the actual original Handler and current captured Harpy")
            judge, appointment = MedicalService(self.store)._handler(c)
            if judge != viewer.user_id:
                raise WorkflowError("Recover the actual source Handler appointment")
            body = HarpyDefeatService(self.store, self.game)._runtime(c, state, actor)
            if (
                not isinstance(body, HarpyState)
                or not body.alive
                or body.custody != "captured"
                or body.controller in state.order
                or str(body.controller) in state.sheets
                or any(x.actor == actor for x in rules.records(state))
            ):
                raise WorkflowError(
                    "Use one genuinely captured reborn original PC without successor"
                )
            effect = next(
                (
                    x
                    for x in state.harpy_defeats
                    if x.actor == actor
                    and x.phase == "complete"
                    and x.factual_source == body.custody_event
                ),
                None,
            )
            if effect is None:
                raise WorkflowError("Actual completed Harpy Defeat capture is required")
            event, identity = str(uuid4()), str(uuid4())
            value = rules.Repossession(
                id=identity,
                actor=actor,
                handler=handler,
                appointment=appointment,
                judge=judge,
                judge_appointment=appointment,
                capture_event=body.custody_event or "",
                capture_effect=effect.id,
                archive_id=body.original_archive,
                original_frame_owner=body.origin,
                frame_instance=body.frame_instance,
                open_event=event,
                initial_harpy_json=body.model_dump_json(),
                shutdown=body.frame_shutdown,
            )
            _capture(self.game, c, state, value)
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_conversion_opened",
                state,
                event_id=event,
                conversion=identity,
            )
            return dict(id=identity, phase=value.phase)

        return self._write(
            viewer,
            key,
            "m3.handler_conversion_opened",
            dict(revision=revision, actor=actor.model_dump(mode="json")),
            operation,
        )

    def physical(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        operation: Literal["extract", "transport"],
        account: str,
        destination: tuple[int, int] | None = None,
    ) -> dict[str, Any]:
        def perform(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, value = self._value(c, viewer, identity, revision)
            body = harpy(state, value.actor)
            custodian = body.custodian
            if (
                custodian is None
                or resolve(
                    state,
                    custodian,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                ).controller
                != viewer.user_id
                or operation not in ("extract", "transport")
                or value.phase != ("captured" if operation == "extract" else "extracted")
                or any(x.accepted is None for x in value.physicals)
            ):
                raise WorkflowError(
                    "Only the actual custodian records its performed physical action"
                )
            if operation == "transport" and destination is None:
                raise WorkflowError("Name the actual destination Base")
            event = str(uuid4())
            item = rules.PhysicalProof(
                event=event,
                operation=operation,
                performer=custodian,
                account=account.strip(),
                destination=destination,
            )
            value = value.model_copy(update=dict(physicals=value.physicals + (item,)))
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_conversion_physical",
                state,
                event_id=event,
                conversion=identity,
            )
            return dict(id=identity, phase=value.phase)

        return self._write(
            viewer,
            key,
            "m3.handler_conversion_physical",
            dict(
                id=identity,
                revision=revision,
                operation=operation,
                account=account,
                destination=destination,
            ),
            perform,
        )

    def review_physical(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        accepted: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, value = self._value(c, viewer, identity, revision)
            self._judge(c, viewer, value)
            item = value.physicals[-1] if value.physicals else None
            if item is None or item.accepted is not None or not account.strip():
                raise WorkflowError(
                    "Review the actual pending custodian source and factual outcome"
                )
            event = str(uuid4())
            if accepted:
                if item.operation == "extract":
                    state = physical.extract_captured(
                        state,
                        profiles(c, self.store.campaign_id),
                        value.actor,
                        item.performer,
                        event,
                        account,
                        repossession=identity,
                    )
                    value = value.model_copy(
                        update=dict(
                            phase="extracted", extraction_event=event, extractor=item.performer
                        )
                    )
                else:
                    assert item.destination is not None
                    state = physical.transport_captured(
                        state,
                        profiles(c, self.store.campaign_id),
                        value.actor,
                        item.destination,
                        event,
                        account,
                        repossession=identity,
                    )
                    value = value.model_copy(
                        update=dict(
                            phase="transported", transport_event=event, destination=item.destination
                        )
                    )
            value = value.model_copy(
                update=dict(
                    physicals=value.physicals[:-1]
                    + (item.model_copy(update=dict(accepted=accepted, review_event=event)),),
                    accounts=value.accounts | {"physical:" + event: account.strip()},
                )
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_conversion_physical_reviewed",
                state,
                event_id=event,
                conversion=identity,
                accepted=accepted,
            )
            return dict(id=identity, phase=value.phase)

        return self._write(
            viewer,
            key,
            "m3.handler_conversion_physical_reviewed",
            dict(id=identity, revision=revision, accepted=accepted, account=account),
            operation,
        )

    def treat(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        purge: str,
        organs: str,
        conditioning: str,
        recovered: bool = False,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, value = self._value(c, viewer, identity, revision)
            self._judge(c, viewer, value)
            body = harpy(state, value.actor)
            if (
                value.phase != "transported"
                or body.linked
                or body.custody != "transported"
                or body.cell != value.destination
                or not all(x.strip() for x in (purge, organs, conditioning))
            ):
                raise WorkflowError(
                    "Record actually completed purge, organ treatment and reprogramming"
                )
            event = str(uuid4())
            if recovered:
                state = physical.recover(
                    state,
                    value.actor,
                    event,
                    "Actual completed medical waking and recovery after institutional treatment",
                )
            value = value.model_copy(
                update=dict(
                    phase="treated",
                    treatment_event=event,
                    accounts=value.accounts
                    | dict(
                        purge=purge.strip(),
                        organs=organs.strip(),
                        conditioning=conditioning.strip(),
                        recovery="actual_medical_recovery" if recovered else "incapacity_preserved",
                    ),
                )
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_conversion_treated",
                state,
                event_id=event,
                conversion=identity,
            )
            return dict(id=identity, phase=value.phase)

        return self._write(
            viewer,
            key,
            "m3.handler_conversion_treated",
            dict(
                id=identity,
                revision=revision,
                purge=purge,
                organs=organs,
                conditioning=conditioning,
                recovered=recovered,
            ),
            operation,
        )

    def package(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        package: rules.MockingbirdPackage,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, value = self._value(c, viewer, identity, revision)
            body = harpy(state, value.actor)
            if viewer.user_id != body.controller or value.phase != "treated":
                raise WorkflowError(
                    "Only the original human authors its resulting Mockingbird choices"
                )
            if package.girl_bond.kind != "pilot" or package.girl_bond not in (
                current_ref(state, uid) for uid in state.order
            ):
                raise WorkflowError("Choose an actual current Girl for the printed Personal Bond")
            if (
                len({x[0] for x in package.npc_bonds}) != len(package.npc_bonds)
                or len({x[1] for x in package.npc_bonds}) != len(package.npc_bonds)
                or not set(x[0] for x in package.npc_bonds) <= {0, 1, 2, 3}
            ):
                raise WorkflowError("Choose one or two distinct printed NPC roles and real people")
            for _, ref in package.npc_bonds:
                if ref.kind != "npc":
                    raise WorkflowError("Bind the printed NPC Bond to an actual NPC")
                resolve(
                    state, ref, profiles(c, self.store.campaign_id), require_current_profile=False
                )
            event = str(uuid4())
            value = value.model_copy(
                update=dict(
                    phase="package",
                    package=package,
                    package_event=event,
                    resulting_actor=ActorRef(
                        kind="pilot",
                        entity=str(body.controller),
                        incarnation="repossession:" + value.id,
                    ),
                )
            )
            # Validate concrete Girl assets through the existing creation catalog now.
            rules.build_sheet(
                state, value.model_copy(update=dict(final_harpy_json=body.model_dump_json())), 1
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_conversion_packaged",
                state,
                event_id=event,
                conversion=identity,
            )
            return dict(id=identity, phase=value.phase)

        return self._write(
            viewer,
            key,
            "m3.handler_conversion_packaged",
            dict(id=identity, revision=revision, package=package.model_dump(mode="json")),
            operation,
        )

    def review(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        position: int,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, value = self._value(c, viewer, identity, revision)
            self._judge(c, viewer, value)
            body = harpy(state, value.actor)
            if (
                value.phase != "package"
                or not isinstance(body, HarpyState)
                or str(body.controller) in state.sheets
                or not 0 <= position <= len(state.order)
                or not account.strip()
            ):
                raise WorkflowError(
                    "Review the exact actual resulting package and real Status slot"
                )
            event = str(uuid4())
            value = value.model_copy(
                update=dict(
                    phase="ready",
                    review_event=event,
                    final_harpy_json=body.model_dump_json(),
                    shutdown=body.frame_shutdown,
                    status_position=position,
                    accounts=value.accounts | dict(review=account.strip()),
                )
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_conversion_reviewed",
                state,
                event_id=event,
                conversion=identity,
            )
            return dict(id=identity, phase=value.phase)

        return self._write(
            viewer,
            key,
            "m3.handler_conversion_reviewed",
            dict(id=identity, revision=revision, position=position, account=account),
            operation,
        )

    def complete(
        self, viewer: GuildViewer, key: str, identity: str, revision: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, value = self._value(c, viewer, identity, revision)
            value = prove_repossession(self.game, c, state, identity, ready=True)
            body = HarpyState.model_validate_json(value.final_harpy_json or "")
            if viewer.user_id != body.controller or value.phase != "ready":
                raise WorkflowError("Only the original human confirms its exact ready Mockingbird")
            profile = (
                c.execute(
                    sa.select(t.characters).where(
                        t.characters.c.campaign_id == self.store.campaign_id,
                        t.characters.c.user_id == str(body.controller),
                    )
                )
                .mappings()
                .one()
            )
            sheet = rules.build_sheet(state, value, profile["revision"] + 1)
            event = str(uuid4())
            assert value.status_position is not None
            assert value.package is not None
            public = dict(
                callsign=sheet.callsign, girl_playbook=sheet.girl, frame_playbook=sheet.frame
            )
            private = dict(
                creation=dict(
                    girl_playbook="MOCKINGBIRD",
                    frame_playbook=sheet.frame,
                    girl_assets=[x.model_dump(mode="json") for x in value.package.assets],
                    void_asset=value.package.void_asset,
                    girl_appearance=value.package.appearance,
                ),
                repossession=identity,
            )
            from girlframe.services.m3_careers import activate_repossessed_in_transaction

            state = activate_repossessed_in_transaction(
                c,
                self.game,
                state,
                conversion=value,
                harpy=value.actor,
                sheet=sheet,
                position=value.status_position,
                event=event,
                public=public,
                private=private,
            )
            value = value.model_copy(
                update=dict(
                    phase="complete",
                    completion_event=event,
                    result_sheet_json=state.sheets[str(body.controller)].model_dump_json(),
                )
            )
            session, reason = _slot(self.game, c, state, value.handler)
            if session:
                value = _award(state, value, session, event)
            else:
                value = value.model_copy(update=dict(award_blocked=reason))
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_conversion_completed",
                state,
                event_id=event,
                conversion=identity,
            )
            current_profile = (
                c.execute(
                    sa.select(t.characters).where(
                        t.characters.c.campaign_id == self.store.campaign_id,
                        t.characters.c.user_id == str(body.controller),
                    )
                )
                .mappings()
                .one()
            )
            c.execute(
                t.snapshots.insert().values(
                    campaign_id=self.store.campaign_id,
                    user_id=str(body.controller),
                    revision=sheet.source_profile_revision,
                    character_id=current_profile["id"],
                    event_id=event,
                    public_json=current_profile["public_json"],
                    private_json=current_profile["private_json"],
                )
            )
            self.store._enqueue_sync(
                c,
                body.controller,
                sheet.source_profile_revision,
                DraftInput(
                    callsign=sheet.callsign, girl_playbook=sheet.girl, frame_playbook=sheet.frame
                ),
            )
            return dict(
                id=identity, phase="complete", award=value.award, character=sheet.character_id
            )

        return self._write(
            viewer,
            key,
            "m3.handler_conversion_completed",
            dict(id=identity, revision=revision),
            operation,
        )

    def claim(self, viewer: GuildViewer, key: str, identity: str, revision: int) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, value = self._value(c, viewer, identity, revision)
            HandlerAdvancementService(self.store)._current(
                c, state, value.handler, value.appointment
            )
            if (
                viewer.user_id != int(value.handler.entity)
                or value.phase != "complete"
                or value.award
            ):
                raise WorkflowError("Only the original Handler claims this completed source once")
            session, reason = _slot(self.game, c, state, value.handler)
            if session is None:
                raise WorkflowError(
                    "Actual conversion saved; ordinary award unavailable: " + str(reason)
                )
            event = str(uuid4())
            value = _award(state, value, session, event)
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_conversion_claimed",
                state,
                event_id=event,
                conversion=identity,
            )
            return dict(id=identity, phase="complete", award=value.award)

        return self._write(
            viewer,
            key,
            "m3.handler_conversion_claimed",
            dict(id=identity, revision=revision),
            operation,
        )

    def menu(self, viewer: GuildViewer, identity: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            if identity is None:
                handler = active_handler(state)
                if handler is None or handler.entity != str(viewer.user_id):
                    raise WorkflowError(
                        "The actual Handler selects a genuinely captured original Harpy"
                    )
                return dict(
                    revision=state.revision,
                    candidates=[
                        dict(
                            actor=ActorRef(kind="external_pilot", entity=x.id).model_dump(
                                mode="json"
                            ),
                            token=x.id,
                            label=x.name,
                        )
                        for x in state.harpy_states
                        if x.alive
                        and x.custody == "captured"
                        and str(x.controller) not in state.sheets
                        and not any(v.actor.entity == x.id for v in rules.records(state))
                    ],
                )
            state, value = self._value(c, viewer, identity)
            body = HarpyState.model_validate_json(value.initial_harpy_json)
            current = harpy(state, value.actor) if value.phase != "complete" else None
            custodian = current.custodian if current else None
            owns_physical = (
                custodian is not None
                and resolve(
                    state,
                    custodian,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                ).controller
                == viewer.user_id
            )
            if viewer.user_id not in (body.controller, value.judge):
                projected = value.model_copy(update={"package": None, "accounts": {}})
            else:
                projected = value
            return projected.model_dump(
                mode="json", exclude={"initial_harpy_json", "final_harpy_json", "result_sheet_json"}
            ) | dict(
                revision=state.revision,
                owner=body.controller == viewer.user_id,
                judge=value.judge == viewer.user_id,
                host=value.handler.entity == str(viewer.user_id),
                owns_physical=owns_physical,
                pending_physical=bool(value.physicals and value.physicals[-1].accepted is None),
                bases=[
                    dict(cell=x.cell, id=x.id, label=x.name)
                    for x in state.world.locations
                    if x.kind == "base" and x.allegiance == "foundation" and x.condition == "intact"
                ]
                if state.world
                else [],
                girls=[
                    dict(
                        ref=current_ref(state, uid).model_dump(mode="json"),
                        token=current_ref(state, uid).token,
                        label=state.sheets[str(uid)].callsign,
                    )
                    for uid in state.order
                ],
                npcs=[
                    dict(
                        ref=ActorRef(kind="npc", entity=x.id).model_dump(mode="json"),
                        token=x.id,
                        label=x.name,
                    )
                    for x in state.world.npcs
                    if x.alive
                ]
                if state.world
                else [],
                claimable=value.phase == "complete"
                and value.award is None
                and viewer.user_id == int(value.handler.entity)
                and _slot(self.game, c, state, value.handler)[0] is not None,
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        for value in rules.records(state):
            body = HarpyState.model_validate_json(value.initial_harpy_json)
            if viewer.user_id not in (body.controller, value.judge, int(value.handler.entity)):
                custodian = (
                    harpy(state, value.actor).custodian if value.phase != "complete" else None
                )
                if (
                    custodian is None
                    or resolve(
                        state,
                        custodian,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    ).controller
                    != viewer.user_id
                ):
                    continue
            pending = (
                (value.phase in ("treated", "ready") and viewer.user_id == body.controller)
                or (value.phase in ("transported", "package") and viewer.user_id == value.judge)
                or (
                    bool(value.physicals and value.physicals[-1].accepted is None)
                    and viewer.user_id == value.judge
                )
            )
            result.append(
                dict(
                    id=value.id,
                    revision=state.revision,
                    label="Original Harpy repossession — " + value.phase,
                    phase=value.phase,
                    pending=pending,
                )
            )
        return result
