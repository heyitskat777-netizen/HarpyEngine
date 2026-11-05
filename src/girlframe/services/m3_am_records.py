"""Human-authored complete records, private learned information and one answered query."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_am_code as code
from girlframe.engine import m3_am_records as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def subjects(game: GameService, c: Connection, state: GameState) -> list[dict[str, Any]]:
    bound = profiles(c, game.store.campaign_id)
    refs = [
        ActorRef(kind="pilot", entity=str(x), incarnation=state.sheets[str(x)].character_id)
        for x in state.order
    ]
    if state.world:
        refs.extend(
            ActorRef(kind="npc", entity=x.id) for x in state.world.npcs if x.revealed and x.alive
        )
        refs.extend(
            ActorRef(kind="external_pilot", entity=x.id)
            for x in state.world.pilots
            if x.revealed and x.alive
        )
    result = []
    for ref in refs:
        try:
            actual = resolve(state, ref, bound)
        except ValueError:
            continue
        result.append(dict(ref=ref.model_dump(mode="json"), token=ref.token, label=actual.label))
    return result


def request(
    game: GameService,
    c: Connection,
    state: GameState,
    value: code.Maintenance,
    subject: ActorRef,
    event: str,
) -> str:
    chosen = next(
        (x for x in subjects(game, c, state) if ActorRef.model_validate(x["ref"]) == subject), None
    )
    if chosen is None:
        raise WorkflowError("Select an actual introduced original person, never a controller proxy")
    identity = str(uuid4())
    rules.put(
        state,
        rules.Access(
            id=identity,
            maintenance=value.id,
            subject=subject,
            label=chosen["label"],
            learner=value.operator,
            controller=value.controller,
            requested_event=event,
        ),
    )
    return identity


def prepare(
    game: GameService,
    c: Connection,
    state: GameState,
    value: code.Maintenance,
    event: str,
    document: str | None,
    reference: str | None,
    complete: bool,
) -> None:
    from girlframe.services.m3_medical import MedicalService

    human, appointment = MedicalService(game.store)._handler(c)
    if (
        value.records_access is None
        or human != value.controller
        or complete is not True
        or not document
        or not document.strip()
        or len(document) > 1200
        or not reference
        or not reference.strip()
        or len(reference) > 1200
    ):
        raise WorkflowError(
            "Before dice the actual Handler must prepare the genuine complete unredacted "
            "dossier/reference; never a summary or private-note import"
        )
    record = rules.access(state, value.records_access)
    if record.phase != "requested" or record.maintenance != value.id:
        raise WorkflowError("Prepare only this actual requested dossier once")
    rules.put(
        state,
        record.model_copy(
            update=dict(
                phase="prepared",
                prepared_event=event,
                gm=human,
                appointment=appointment,
                document=document,
                reference=reference,
            )
        ),
    )


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Access:
    from girlframe.services.m3_am_scrutinized import _history

    value = rules.access(state, identity)
    original = rules.access(_history(game, c, value.requested_event), identity)
    frozen = ("id", "maintenance", "subject", "label", "learner", "controller", "requested_event")
    if any(getattr(value, x) != getattr(original, x) for x in frozen):
        raise WorkflowError("Recover the exact original requested subject/learner")
    if value.prepared_event:
        ready = rules.access(_history(game, c, value.prepared_event), identity)
        event = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == value.prepared_event,
            )
        ).first()
        if (
            event is None
            or event.kind != "m3.am_code_confirmed"
            or event.actor_id != str(value.gm)
            or any(
                getattr(value, x) != getattr(ready, x)
                for x in ("prepared_event", "gm", "appointment", "document", "reference")
            )
            or not value.document
            or not value.reference
            or not value.appointment
        ):
            raise WorkflowError(
                "Recover the actual complete source-Handler dossier, not a later summary"
            )
    if value.granted_event:
        saved = rules.access(_history(game, c, value.granted_event), identity)
        responses = t.m2["m2_responses"]
        choices = t.m2["m2_choices"]
        answer = c.execute(
            sa.select(responses.c.answer_json)
            .join(
                choices,
                sa.and_(
                    choices.c.campaign_id == responses.c.campaign_id,
                    choices.c.id == responses.c.choice_id,
                ),
            )
            .where(
                responses.c.campaign_id == game.store.campaign_id,
                responses.c.event_id == value.granted_event,
                choices.c.kind == "am_code_options",
                responses.c.actor_id == str(value.controller),
            )
        ).first()
        if (
            saved.granted_event != value.granted_event
            or answer is None
            or "records" not in json.loads(answer.answer_json).get("options", ())
        ):
            raise WorkflowError("Only the actual rolled operator's selection grants record access")
    for recorded_event, kind, human, field in (
        (value.question_event, "am_code_records_question", value.controller, "question"),
        (value.answer_event, "am_code_records_answer", value.gm, "answer"),
    ):
        if recorded_event is None:
            continue
        saved = rules.access(_history(game, c, recorded_event), identity)
        choices = t.m2["m2_choices"]
        responses = t.m2["m2_responses"]
        response = c.execute(
            sa.select(responses.c.answer_json)
            .join(
                choices,
                sa.and_(
                    choices.c.campaign_id == responses.c.campaign_id,
                    choices.c.id == responses.c.choice_id,
                ),
            )
            .where(
                responses.c.campaign_id == game.store.campaign_id,
                responses.c.event_id == recorded_event,
                choices.c.kind == kind,
                responses.c.actor_id == str(human),
            )
        ).first()
        if (
            getattr(saved, field) != getattr(value, field)
            or response is None
            or json.loads(response.answer_json).get("text") != getattr(value, field)
            or field == "answer"
            and json.loads(response.answer_json).get("flag") is not True
        ):
            raise WorkflowError(
                "Recover the one actual owned Foundation question and honest answer"
            )
    return value


def ready(game: GameService, c: Connection, state: GameState, value: code.Maintenance) -> None:
    if value.records_access:
        record = prove(game, c, state, value.records_access)
        if (
            record.phase != "prepared"
            or record.prepared_event != value.confirmed_event
            or record.maintenance != value.id
            or record.learner != value.operator
        ):
            raise WorkflowError("Prepare the actual complete dossier before this source can roll")


def grant(state: GameState, value: code.Maintenance, event: str) -> None:
    if value.records_access is None:
        raise WorkflowError("No genuine pre-RNG dossier source exists")
    record = rules.access(state, value.records_access)
    if record.phase != "prepared" or record.granted_event:
        raise WorkflowError("This original dossier was already granted or is unavailable")
    rules.put(state, record.model_copy(update=dict(phase="granted", granted_event=event)))


def unselected(state: GameState, value: code.Maintenance, event: str) -> None:
    if value.records_access:
        record = rules.access(state, value.records_access)
        if record.granted_event is None:
            rules.put(
                state, record.model_copy(update=dict(phase="not_granted", closed_event=event))
            )


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> None:
    value = code.session(state, action["data"]["am_code"]["maintenance"])
    record = prove(game, c, state, value.records_access or "")
    event = action["data"]["response_event"]
    if (
        answer.options
        or answer.denied
        or answer.fields
        or answer.number is not None
        or answer.member is not None
        or not answer.text.strip()
    ):
        raise WorkflowError("Write the actual one question or the honest source-Handler answer")
    if row["kind"] == "am_code_records_question":
        if record.phase != "granted" or record.question_event or answer.flag is not None:
            raise WorkflowError("The actual operator asks exactly one original question")
        rules.put(state, record.model_copy(update=dict(question=answer.text, question_event=event)))
        game.request(c, action, record.gm or 0, "am_code_records_answer")
        return
    if row["kind"] != "am_code_records_answer" or answer.flag is not True:
        raise WorkflowError(
            "The actual Handler must supply and affirm the honest Foundation answer"
        )
    from girlframe.services.m3_medical import MedicalService

    human, appointment = MedicalService(game.store)._handler(c)
    if (
        human != record.gm
        or appointment != record.appointment
        or not record.question_event
        or record.answer_event
        or record.phase != "granted"
    ):
        raise WorkflowError("Use the original actual records-Handler and unanswered question")
    rules.put(
        state,
        record.model_copy(
            update=dict(
                phase="answered", answer=answer.text, answer_event=event, closed_event=event
            )
        ),
    )


def projection(
    game: GameService, c: Connection, state: GameState, value: code.Maintenance, kind: str
) -> dict[str, Any]:
    record = prove(game, c, state, value.records_access or "")
    if (
        kind not in ("am_code_records_question", "am_code_records_answer")
        or not record.granted_event
    ):
        raise WorkflowError("This source choice has no right to the private dossier")
    return dict(
        subject=record.label,
        question=record.question,
        reference=record.reference,
        document=record.document,
        answer=record.answer,
    )


class RecordsService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def document(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            try:
                learner = resolve(
                    state, value.learner, profiles(c, self.store.campaign_id), require_alive=False
                )
            except ValueError:
                raise WorkflowError("Recover the actual original record learner") from None
            if viewer.user_id != learner.controller or not value.granted_event:
                raise WorkflowError("These records belong to the actual original learner")
            return dict(
                id=identity,
                subject=value.label,
                reference=value.reference,
                document=value.document,
                question=value.question,
                answer=value.answer,
            )
