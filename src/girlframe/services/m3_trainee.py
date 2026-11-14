"""Unrolled original-Mentor teaching, actual choices and source-bound discipline."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_trainee as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_work_scope import WorkScope
from girlframe.services.m2_choices import ChoiceEngine
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_dose_up import _cast, _native, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_role_punishments import open_case, synchronize
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _record[T: Model](state: GameState, model: type[T], identity: str) -> T:
    value = next((x for x in rules.records(state, model) if x.model_dump()["id"] == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual original Trainee source")
    return value


def _access(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)


def _relation(
    game: GameService,
    c: Connection,
    state: GameState,
    learner: ActorRef,
    selected: ActorRef | None = None,
) -> tuple[ActorRef, str]:
    from girlframe.services.m3_mentorship import original_mentor

    return original_mentor(game, c, state, learner, required_rule=rules.RULE, selected=selected)


def _mentor(
    game: GameService,
    c: Connection,
    state: GameState,
    learner: ActorRef,
    selected: ActorRef | None = None,
) -> tuple[ActorRef, str]:
    mentor, source = _relation(game, c, state, learner, selected)
    _native(game, c, state, learner)
    _native(game, c, state, mentor)
    return mentor, source


def _idle(game: GameService, c: Connection, scene: str) -> None:
    from girlframe.services.m3_recovery import pending

    if pending(game, c, include_unrolled=True):
        raise WorkflowError(
            "REQUIRED_RECOVERY: restore the actual interrupted Play before teaching"
        )
    actions = t.m2["m2_actions"]
    if c.scalar(
        sa.select(actions.c.id).where(
            actions.c.campaign_id == game.store.campaign_id,
            actions.c.scene_id == scene,
            actions.c.state.not_in(("complete", "aborted")),
        )
    ):
        raise WorkflowError("Finish the actual pending scene Play before this Trainee outcome")
    table = t.m2["m2_scenes"]
    channel = c.scalar(
        sa.select(table.c.channel_id).where(
            table.c.id == scene, table.c.campaign_id == game.store.campaign_id
        )
    )
    lock = game.lock(c, int(channel)) if channel else None
    if lock and lock["state"] != "released":
        raise WorkflowError("Restore the actual scene chat lock before this source outcome")


def _event(game: GameService, c: Connection, event: str, kind: str, actor: int) -> None:
    actual = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    if actual is None or actual["kind"] != kind or actual["actor_id"] != str(actor):
        raise WorkflowError("Recover the original human-authored Trainee source event")


def _before(game: GameService, c: Connection, event: str) -> GameState:
    seq = c.scalar(
        sa.select(t.events.c.seq).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    )
    body = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json)
        .join(t.events, t.events.c.id == t.m2["m2_state_history"].c.event_id)
        .where(t.events.c.campaign_id == game.store.campaign_id, t.events.c.seq < seq)
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    if body is None:
        raise WorkflowError("Recover the actual state preceding this Trainee effect")
    return GameState.model_validate_json(body)


def _tags(
    game: GameService, c: Connection, state: GameState, lesson: rules.Teaching
) -> tuple[Any, ...]:
    result = tuple(
        x
        for x in state.sheets[lesson.learner.entity].tags
        if x.giver_actor == lesson.mentor and x.gm_setter_appointment is None
    )
    for value in result:
        ChoiceEngine(game).prove_tag_setter(c, state, int(lesson.learner.entity), value)
    return result


def _performed(game: GameService, c: Connection, lesson: rules.Teaching, identity: str) -> None:
    action = game.action(c, identity)
    rolled, _ = _roll_source(game, c, action)
    a = c.scalar(sa.select(t.events.c.seq).where(t.events.c.id == rolled))
    b = c.scalar(sa.select(t.events.c.seq).where(t.events.c.id == lesson.event))
    if (
        action["state"] != "complete"
        or action["actor_id"] != lesson.learner.entity
        or action["scene_id"] != lesson.cast.id
        or a is None
        or b is None
        or a <= b
        or action["data"]["character_ids"].get(lesson.learner.entity) != lesson.learner.incarnation
    ):
        raise WorkflowError(
            "Use a genuine completed original-Newgirl Play performed after this teaching"
        )


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Teaching:
    lesson = _record(state, rules.Teaching, identity)
    born = _history(c, game, lesson.event)
    _event(game, c, lesson.event, "m3.trainee_taught", int(lesson.learner.entity))
    if lesson not in rules.records(born, rules.Teaching):
        raise WorkflowError("Preserve the immutable actual teaching account and original people")
    mentor, source = _relation(game, c, born, lesson.learner, lesson.mentor)
    if (
        mentor != lesson.mentor
        or source != lesson.relation_source
        or lesson.handler != active_handler(born)
        or lesson.cast not in born.scene_casts
        or not all(
            any(x.actor == ref for x in lesson.cast.roles)
            for ref in (lesson.learner, lesson.mentor)
        )
    ):
        raise WorkflowError("Recover the original actual teaching context and assigned Mentor")
    selection = next(
        (x for x in rules.records(state, rules.Selection) if x.teaching == identity), None
    )
    if selection:
        _event(game, c, selection.event, "m3.trainee_selected", int(lesson.learner.entity))
        after = _history(c, game, selection.event)
        before = _before(game, c, selection.event)
        if selection not in rules.records(after, rules.Selection):
            raise WorkflowError("Preserve the actual selected Trainee outcome")
        old, new = before.sheets[lesson.learner.entity], after.sheets[lesson.learner.entity]
        if selection.branch == "erase":
            if selection.identity is None:
                raise WorkflowError("Recover the actual erased contradictory Identity")
            expected, erased, tag, embraced = rules.erase(
                old,
                selection.identity.id,
                selection.tag.id if selection.tag else None,
                _tags(game, c, before, lesson),
                identity,
                duplicates=ChoiceEngine(game).duplicate_labels(),
            )
            if (
                new != expected
                or erased != selection.identity
                or tag != selection.tag
                or embraced != selection.embraced
            ):
                raise WorkflowError(
                    "Recover the exact atomic Identity erasure and Mentor Tag embrace"
                )
        elif selection.branch == "act":
            if selection.heat not in (1, 2, 3):
                raise WorkflowError("Use the printed actual1–3 Heat grant")
            expected = old.model_copy(deep=True)
            expected.heat += selection.heat
            expected.revision += 1
            if new != expected:
                raise WorkflowError(
                    "Recover the real one-time Heat grant for actual immediate acting"
                )
            if selection.source_action:
                _performed(game, c, lesson, selection.source_action)
        elif old != new:
            raise WorkflowError(
                "A challenge records the real duty without fabricated bodily effects"
            )
    return lesson


def _duty(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Duty:
    value = _record(state, rules.Duty, identity)
    lesson = prove(game, c, state, value.teaching)
    born = _history(c, game, value.source_event)
    first = _record(born, rules.Duty, identity)
    if any(
        getattr(value, k) != getattr(first, k)
        for k in ("id", "teaching", "learner", "mentor", "handler", "source_event")
    ) or (value.learner, value.mentor, value.handler) != (
        lesson.learner,
        lesson.mentor,
        lesson.handler,
    ):
        raise WorkflowError("Preserve the original immediate mentorship duty")
    if value.report_event:
        _event(game, c, value.report_event, "m3.trainee_shirk_reported", int(value.learner.entity))
        report = _record(_history(c, game, value.report_event), rules.Duty, identity)
        if (
            report.report_account != value.report_account
            or report.report_event != value.report_event
        ):
            raise WorkflowError("Preserve the actual original Newgirl's factual shirk report")
    if value.reviewed_event:
        _event(
            game, c, value.reviewed_event, "m3.trainee_shirk_confirmed", int(value.handler.entity)
        )
        review = _record(_history(c, game, value.reviewed_event), rules.Duty, identity)
        if review.review_account != value.review_account or review.case != value.case:
            raise WorkflowError(
                "Preserve the original Handler's actual attributed shirking finding"
            )
    phase_event: str | None
    if value.phase == "mentor":
        phase_event = value.source_event
    elif value.phase == "reported":
        phase_event = value.report_event
    elif value.phase == "complete":
        phase_event = value.completed_event
    else:
        case = next((x for x in state.role_punishments if x.id == value.case), None)
        phase_event = case.source_event if case else None
    if phase_event is None or value != _record(
        _history(c, game, phase_event), rules.Duty, identity
    ):
        raise WorkflowError(
            "Recover the canonical actual progress of this original mentorship duty"
        )
    return value


def validate_role_case(c: Connection, game: GameService, state: GameState, case: Any) -> None:
    from girlframe.services.m3_intracadre_marriage import original_offender

    value = _duty(game, c, state, case.source_work or "")
    original = original_offender(game, c, state, case.id, case.source_event, case.subject)
    expected = (
        (value.handler, value.mentor, value.reviewed_event)
        if value.reviewed_event
        else (value.mentor, value.learner, case.source_event)
    )
    if (
        case.source_kind != "trainee"
        or case.action is not None
        or value.case != case.id
        or (case.executor, original, case.source_event) != expected
        or case.chooser != case.executor
    ):
        raise WorkflowError(
            "Recover the actual immediate Mentor or reported-shirking discipline cause"
        )
    _event(
        game,
        c,
        case.source_event,
        "m3.trainee_shirk_confirmed" if value.reviewed_event else "m3.trainee_punishment_started",
        case.executor_controller,
    )
    born = _history(c, game, case.source_event)
    original_duty = _record(born, rules.Duty, value.id)
    if original_duty.case != case.id or original_duty.phase not in (
        "mentor_punishment",
        "handler_punishment",
    ):
        raise WorkflowError("Preserve the canonical actual case birth and original Mentor duty")


def role_scope(c: Connection, game: GameService, case: Any) -> WorkScope:

    state = load_state(c, game.store.campaign_id)
    validate_role_case(c, game, state, case)
    lesson = prove(game, c, state, case.source_work)
    return WorkScope(scene_id=lesson.cast.id)


def _work(game: GameService, c: Connection, identity: str, event: str) -> None:
    table = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == identity)
            .order_by(table.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None:
        raise WorkflowError("Recover the real pending original mentorship duty")
    if row["state"] == "resolved":
        return
    c.execute(
        table.insert().values(
            **{k: v for k, v in row.items() if k not in ("revision", "event_id", "state")},
            revision=row["revision"] + 1,
            event_id=event,
            state="resolved",
        )
    )


def complete_role_case(c: Connection, game: GameService, case: Any, event: str) -> None:
    state = load_state(c, game.store.campaign_id)
    validate_role_case(c, game, state, case)
    if not case.effect_event or not case.completion_event:
        raise WorkflowError("Complete the actual Punishment and its mandatory children first")
    value = _duty(game, c, state, case.source_work)
    if value.phase == "complete":
        return
    completed_event = str(uuid4())
    rules.put(
        state, value.model_copy(update=dict(phase="complete", completed_event=completed_event))
    )
    game.event(
        c,
        case.executor_controller,
        "trainee-complete:" + event,
        "m3.trainee_completed",
        state,
        event_id=completed_event,
        teaching_id=value.teaching,
    )
    _work(game, c, value.id, completed_event)


class TraineeService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _write(
        self, viewer: GuildViewer, key: str, kind: str, body: dict[str, Any], operation: Any
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            _access(self.game, c, viewer)
            self.game.unpaused(c)

        try:
            return self.store._write(
                viewer, key, kind, body, operation, auto_audit=False, authorize=access
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def record_teaching(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        revision: int,
        account: str,
        mentor: ActorRef | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision or not account.strip() or len(account) > 1200:
                raise WorkflowError("Refresh the actual scene and author the factual teaching")
            learner = current_ref(state, viewer.user_id)
            selected, source = _mentor(self.game, c, state, learner, mentor)
            cast = _cast(self.game, c, state, channel)
            if not all(any(x.actor == ref for x in cast.roles) for ref in (learner, selected)):
                raise WorkflowError("Use the real original Mentor and Newgirl in this actual scene")
            _idle(self.game, c, cast.id)
            if not any(x.id == cast.id for x in state.scene_casts):
                state.scene_casts.append(cast)
            handler = active_handler(state)
            if handler is None:
                raise WorkflowError("Recover the original current Handler")
            identity, event = str(uuid4()), str(uuid4())
            rules.put(
                state,
                rules.Teaching(
                    id=identity,
                    learner=learner,
                    mentor=selected,
                    handler=handler,
                    cast=cast,
                    relation_source=source,
                    event=event,
                    account=account.strip(),
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.trainee_taught",
                state,
                event_id=event,
                teaching_id=identity,
            )
            return dict(id=identity, revision=state.revision, phase="choice")

        return self._write(
            viewer,
            key,
            "m3.trainee_taught",
            dict(
                channel=channel,
                revision=revision,
                account=account,
                **({"mentor": mentor.model_dump(mode="json")} if mentor is not None else {}),
            ),
            operation,
        )

    def choose(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        branch: Literal["erase", "act", "challenge"],
        *,
        identity_id: str | None = None,
        tag: str | None = None,
        heat: int = 0,
        account: str = "",
        source_action: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            lesson = prove(self.game, c, state, identity)
            self._current(c, state, lesson, viewer, lesson.learner)
            if (
                state.revision != revision
                or not account.strip()
                or len(account) > 1200
                or any(x.teaching == identity for x in rules.records(state, rules.Selection))
            ):
                raise WorkflowError(
                    "Refresh the actual unselected teaching and author your performed choice"
                )
            _idle(self.game, c, lesson.cast.id)
            event = str(uuid4())
            old = embraced = selected_tag = None
            if branch == "erase":
                if identity_id is None or heat or source_action:
                    raise WorkflowError(
                        "Select the actual contradictory Identity and original Mentor Tag"
                    )
                changed, old, selected_tag, embraced = rules.erase(
                    state.sheets[lesson.learner.entity],
                    identity_id,
                    tag,
                    _tags(self.game, c, state, lesson),
                    identity,
                    duplicates=ChoiceEngine(self.game).duplicate_labels(),
                )
                state.sheets[lesson.learner.entity] = changed
                if selected_tag is not None:
                    ChoiceEngine(self.game).tag_resolved(
                        state, int(lesson.learner.entity), selected_tag.id
                    )
            elif branch == "act":
                if heat not in (1, 2, 3) or identity_id or tag:
                    raise WorkflowError(
                        "Choose the printed1–3 Heat after actually acting on the teaching"
                    )
                if source_action:
                    _performed(self.game, c, lesson, source_action)
                state.sheets[lesson.learner.entity].heat += heat
                state.sheets[lesson.learner.entity].revision += 1
            elif branch == "challenge":
                if heat or identity_id or tag or source_action:
                    raise WorkflowError(
                        "Record the actual challenge without inventing another resource effect"
                    )
                rules.put(
                    state,
                    rules.Duty(
                        id=identity,
                        teaching=identity,
                        learner=lesson.learner,
                        mentor=lesson.mentor,
                        handler=lesson.handler,
                        source_event=event,
                        phase="mentor",
                    ),
                )
            else:
                raise WorkflowError("Select one actual printed Trainee choice")
            rules.put(
                state,
                rules.Selection(
                    id=identity,
                    teaching=identity,
                    branch=branch,
                    event=event,
                    account=account.strip(),
                    identity=old,
                    tag=selected_tag,
                    embraced=embraced,
                    heat=heat,
                    source_action=source_action,
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.trainee_selected",
                state,
                event_id=event,
                teaching_id=identity,
            )
            if branch == "challenge":
                related(
                    c,
                    self.store,
                    dict(campaign_id=self.store.campaign_id, scene_id=lesson.cast.id),
                    identity,
                    int(lesson.mentor.entity),
                    int(lesson.learner.entity),
                    "trainee_duty",
                    dict(
                        teaching=identity,
                        source_event=event,
                        immediate=True,
                        learner=lesson.learner.model_dump(mode="json"),
                        mentor=lesson.mentor.model_dump(mode="json"),
                    ),
                    event,
                )
            return dict(
                id=identity,
                revision=state.revision,
                phase="mentor" if branch == "challenge" else "complete",
            )

        return self._write(
            viewer,
            key,
            "m3.trainee_selected",
            dict(
                id=identity,
                revision=revision,
                branch=branch,
                identity=identity_id,
                tag=tag,
                heat=heat,
                account=account,
                source_action=source_action,
            ),
            operation,
        )

    def _current(
        self,
        c: Connection,
        state: GameState,
        lesson: rules.Teaching,
        viewer: GuildViewer,
        expected: ActorRef,
    ) -> None:
        if current_ref(state, viewer.user_id) != expected:
            raise WorkflowError(
                "Only this original person's current human owns this source decision"
            )
        # A later genuine Mentor swap does not erase an already owed teaching duty.
        _native(self.game, c, state, lesson.learner)
        _native(self.game, c, state, lesson.mentor)
        if active_handler(state) != lesson.handler:
            raise WorkflowError(
                "Recover the original Mentor and Handler; never substitute their replacements"
            )

    def punish(self, viewer: GuildViewer, key: str, identity: str, revision: int) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = _duty(self.game, c, state, identity)
            lesson = prove(self.game, c, state, identity)
            self._current(c, state, lesson, viewer, value.mentor)
            if state.revision != revision or value.phase != "mentor":
                raise WorkflowError("Refresh the real pending immediate Mentor duty")
            _idle(self.game, c, lesson.cast.id)
            return self._case(c, state, value, viewer, key, False, "")

        return self._write(
            viewer,
            key,
            "m3.trainee_punishment_started",
            dict(id=identity, revision=revision),
            operation,
        )

    def _case(
        self,
        c: Connection,
        state: GameState,
        value: rules.Duty,
        viewer: GuildViewer,
        key: str,
        shirk: bool,
        account: str,
    ) -> dict[str, Any]:
        from girlframe.services.m3_actors import profiles

        event, case = str(uuid4()), str(uuid4())
        state, _ = open_case(
            state,
            profiles(c, self.store.campaign_id),
            actor=value.handler if shirk else value.mentor,
            target=value.mentor if shirk else value.learner,
            chooser=value.handler if shirk else value.mentor,
            source_kind="trainee",
            action=None,
            source_work=value.id,
            source_event=event,
            identity=case,
        )
        rules.put(
            state,
            value.model_copy(
                update=dict(
                    case=case,
                    phase="handler_punishment" if shirk else "mentor_punishment",
                    **(dict(reviewed_event=event, review_account=account.strip()) if shirk else {}),
                )
            ),
        )
        kind = "m3.trainee_shirk_confirmed" if shirk else "m3.trainee_punishment_started"
        self.game.event(c, viewer.user_id, key, kind, state, event_id=event, teaching_id=value.id)
        synchronize(self.game, c, None, event)
        return dict(
            id=value.id,
            revision=load_state(c, self.store.campaign_id).revision,
            phase="handler_punishment" if shirk else "mentor_punishment",
            case=case,
        )

    def report_shirking(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            lesson = prove(self.game, c, state, identity)
            value = _duty(self.game, c, state, identity)
            self._current(c, state, lesson, viewer, value.learner)
            if (
                state.revision != revision
                or value.phase != "mentor"
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "Report the actual source-attributed shirking, without inventing a timeout"
                )
            event = str(uuid4())
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        phase="reported", report_event=event, report_account=account.strip()
                    )
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.trainee_shirk_reported",
                state,
                event_id=event,
                teaching_id=identity,
            )
            return dict(id=identity, revision=state.revision, phase="reported")

        return self._write(
            viewer,
            key,
            "m3.trainee_shirk_reported",
            dict(id=identity, revision=revision, account=account),
            operation,
        )

    def resolve_report(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            lesson = prove(self.game, c, state, identity)
            value = _duty(self.game, c, state, identity)
            self._current(c, state, lesson, viewer, value.handler)
            if (
                state.revision != revision
                or value.phase != "reported"
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "Truthfully attribute this actual Mentor shirking before real discipline"
                )
            _idle(self.game, c, lesson.cast.id)
            return self._case(c, state, value, viewer, key, True, account)

        return self._write(
            viewer,
            key,
            "m3.trainee_shirk_confirmed",
            dict(id=identity, revision=revision, account=account),
            operation,
        )

    def menu(self, viewer: GuildViewer, channel: int) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            mentors: list[dict[str, Any]] = []
            if str(viewer.user_id) in state.sheets:
                learner = current_ref(state, viewer.user_id)
                try:
                    from girlframe.services.m3_mentorship import original_mentors

                    assigned, _ = original_mentors(
                        self.game, c, state, learner, required_rule=rules.RULE
                    )
                    cast = _cast(self.game, c, state, channel)
                    _native(self.game, c, state, learner)
                    for ref in assigned:
                        _native(self.game, c, state, ref)
                        if all(
                            any(x.actor == actor for x in cast.roles) for actor in (learner, ref)
                        ):
                            mentors.append(
                                dict(
                                    ref=ref.model_dump(mode="json"),
                                    label=state.sheets[ref.entity].callsign,
                                )
                            )
                except (WorkflowError, ValueError):
                    pass
            return dict(
                revision=state.revision,
                can_teach=bool(mentors),
                mentor=", ".join(x["label"] for x in mentors),
                mentors=mentors,
                history=self._tasks(c, viewer),
            )

    @staticmethod
    def _visible(state: GameState, lesson: rules.Teaching, viewer: GuildViewer) -> bool:
        if viewer.user_id in (int(lesson.learner.entity), int(lesson.mentor.entity)):
            return True
        if viewer.user_id != int(lesson.handler.entity):
            return False
        observed = any(
            x.actor == lesson.handler and x.controller == viewer.user_id for x in lesson.cast.roles
        )
        reported = any(
            x.teaching == lesson.id and x.report_event is not None
            for x in rules.records(state, rules.Duty)
        )
        return observed or reported

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        result = []
        for lesson in rules.records(state, rules.Teaching):
            if not self._visible(state, lesson, viewer):
                continue
            value = self._view(c, state, viewer, lesson.id)
            result.append(
                dict(
                    id=lesson.id,
                    revision=state.revision,
                    phase=value["phase"],
                    label="Your actual Trainee teaching and source outcome",
                    pending=value["actionable"],
                )
            )
        return result

    def _view(
        self, c: Connection, state: GameState, viewer: GuildViewer, identity: str
    ) -> dict[str, Any]:
        lesson = prove(self.game, c, state, identity)
        if not self._visible(state, lesson, viewer):
            raise WorkflowError(
                "This private teaching needs actual participation or an addressed report"
            )
        selection = next(
            (x for x in rules.records(state, rules.Selection) if x.teaching == identity), None
        )
        duty = (
            _duty(self.game, c, state, identity)
            if selection and selection.branch == "challenge"
            else None
        )
        phase = duty.phase if duty else "complete" if selection else "choice"
        owner = (
            lesson.learner
            if phase == "choice"
            else (lesson.mentor if phase in ("mentor", "mentor_punishment") else lesson.handler)
        )
        current = False
        try:
            self._current(c, state, lesson, viewer, current_ref(state, viewer.user_id))
            current = current_ref(state, viewer.user_id) in (
                lesson.learner,
                lesson.mentor,
                lesson.handler,
            )
        except (WorkflowError, ValueError):
            pass
        own_learner = viewer.user_id == int(lesson.learner.entity)
        identities, tags = [], []
        if own_learner and phase == "choice" and current:
            sheet = state.sheets[lesson.learner.entity]
            identities = [
                dict(id=x.id, name=x.name)
                for x in sheet.identities
                if not x.protected
                and not x.paired
                and not x.am_limiter
                and x.id not in sheet.sedation_locked
                and not x.obsession_sources
            ]
            tags = [dict(id=x.id, label=x.label) for x in _tags(self.game, c, state, lesson)]
        actions = []
        if own_learner and phase == "choice" and current:
            table = t.m2["m2_actions"]
            for row in c.execute(
                sa.select(table.c.id, table.c.body_json).where(
                    table.c.campaign_id == self.store.campaign_id,
                    table.c.actor_id == lesson.learner.entity,
                    table.c.scene_id == lesson.cast.id,
                    table.c.state == "complete",
                )
            ).mappings():
                try:
                    _performed(self.game, c, lesson, row["id"])
                except WorkflowError:
                    continue
                actions.append(dict(id=row["id"], label=json.loads(row["body_json"])["play"]))
        return dict(
            actions=actions,
            id=identity,
            revision=state.revision,
            phase=phase,
            channel=lesson.cast.channel,
            teaching=lesson.account
            if viewer.user_id in (int(lesson.learner.entity), int(lesson.mentor.entity))
            or any(
                x.actor == lesson.handler and x.controller == viewer.user_id
                for x in lesson.cast.roles
            )
            else "",
            learner=int(lesson.learner.entity),
            mentor=int(lesson.mentor.entity),
            handler=int(lesson.handler.entity),
            branch=selection.branch if selection else None,
            selected_account=selection.account if selection and own_learner else None,
            identity=selection.identity.name
            if selection and selection.identity and own_learner
            else None,
            embraced=selection.embraced.name
            if selection and selection.embraced and own_learner
            else None,
            heat=selection.heat if selection and own_learner else None,
            identities=identities,
            tags=tags,
            case=duty.case if duty else None,
            report=duty.report_account if duty else None,
            review=duty.review_account if duty else None,
            actionable=current and phase != "complete" and viewer.user_id == int(owner.entity),
            can_report=current and own_learner and phase == "mentor",
        )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            return self._view(c, load_state(c, self.store.campaign_id), viewer, identity)
