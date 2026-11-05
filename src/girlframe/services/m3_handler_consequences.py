"""Source-owned Handler replacement choices and exact held-action completion."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_consequences as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequence_state import Choice, HandlerArchive, HandlerConsequence
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService

KINDS = ("handler_consequence", "enforcer_handler_consequence", "combat_handler_consequence")


def end_body_reviews(game: "GameService", c: Connection, archive: HandlerArchive) -> None:
    """End only proved old-body reviews; never claim the actual Director departed."""
    work = t.m3["m3_required_work"]
    latest = {
        row["id"]: dict(row)
        for row in c.execute(
            sa.select(work)
            .where(
                work.c.campaign_id == game.store.campaign_id,
                work.c.kind == "director_presence",
                work.c.subject_id == archive.actor.entity,
            )
            .order_by(work.c.revision)
        ).mappings()
    }
    state = load_state(c, game.store.campaign_id)
    for row in latest.values():
        if row["state"] == "resolved":
            continue
        body = json.loads(row["body_json"])
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == row["event_id"],
            )
        )
        event = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == row["event_id"]
            )
        ).first()
        source = GameState.model_validate_json(raw) if raw else None
        original = rules.active_handler(source) if source else None
        if original is None or event != (
            "m3.observation_npc_answered",
            str(body.get("controller")),
        ):
            continue
        try:
            actual_body = rules.body_original(state, original)
        except ValueError:
            continue
        if actual_body != archive.body:
            continue
        c.execute(
            work.insert().values(
                **{
                    key: value
                    for key, value in row.items()
                    if key not in ("revision", "state", "body_json", "event_id")
                },
                revision=row["revision"] + 1,
                state="resolved",
                event_id=archive.source_event,
                body_json=json.dumps(
                    body
                    | dict(
                        resolution="original_handler_body_ended",
                        handler_archive=archive.id,
                        death_event=archive.source_event,
                    ),
                    sort_keys=True,
                ),
            )
        )


def supported(state: GameState, actor: ActorRef, trigger: str) -> bool:
    return trigger in ("asset_damage", "helpless") and rules.same_handler_body(state, actor)


def require(
    game: "GameService",
    c: Connection,
    state: GameState,
    handler: ActorRef,
    *,
    trigger: str,
    source_action: str | None,
    source_event: str,
    opponent: ActorRef | None,
    source_request: str | None = None,
    source_work: str | None = None,
    choice_kind: str = "handler_consequence",
    occurrence: str = "0",
) -> tuple[GameState, str]:
    if choice_kind not in KINDS:
        raise WorkflowError("Use an actual supported source Handler consequence request.")
    appointment = MedicalService(game.store)._handler(c)[1]
    state, identity = rules.require(
        state,
        handler,
        trigger=trigger,
        source_action=source_action,
        source_event=source_event,
        opponent=opponent,
        appointment=appointment,
        source_work=source_work,
        source_request=source_request,
        occurrence=occurrence,
    )
    record = next(x for x in state.handler_consequences if x.id == identity)
    if source_action and record.source_request is None:
        action = game.action(c, source_action)
        choice = game.request(
            c,
            action,
            int(handler.entity),
            choice_kind,
            dict(consequence=identity, handler=handler.model_dump(mode="json"), trigger=trigger),
        )
        state.handler_consequences = [
            x.model_copy(update={"source_request": choice}) if x.id == identity else x
            for x in state.handler_consequences
        ]
    return state, identity


def finish_callback(
    game: "GameService",
    c: Connection,
    record: HandlerConsequence,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    if record.state == "pending" or not record.effect_event:
        raise WorkflowError("The actual Handler must choose the source replacement effect first.")
    from girlframe.services.m3_handler_void import synchronize_endings

    synchronize_endings(game, c, event, viewer, key)
    from girlframe.services.m3_handler_girl_void import synchronize_endings as sync_girl_void

    sync_girl_void(game, c, event, viewer, key)
    if not record.source_request:
        from girlframe.services.m3_battle import complete_handler_consequence as complete_battle

        complete_battle(game, c, record, event, viewer, key)
        return
    choices = t.m2["m2_choices"]
    row = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.id == record.source_request,
            )
        )
        .mappings()
        .first()
    )
    if (
        row is None
        or row["action_id"] != record.source_action
        or row["actor_id"] != (record.actor.entity)
        or row["kind"] not in KINDS
        or json.loads(row["body_json"]).get("consequence") != record.id
    ):
        raise WorkflowError("Recover the actual original Handler consequence's source linkage.")
    if row["state"] not in ("pending", "submitted"):
        if json.loads(row["body_json"]).get("effect_event") != record.effect_event:
            raise WorkflowError("The actual source Handler effect was completed differently.")
        return
    c.execute(
        choices.update()
        .where(
            choices.c.campaign_id == game.store.campaign_id, choices.c.id == record.source_request
        )
        .values(
            state="completed_by_work",
            revision=row["revision"] + 1,
            body_json=json.dumps(
                json.loads(row["body_json"])
                | dict(
                    effect_event=record.effect_event, choice=record.choice, ended_by=record.ended_by
                ),
                sort_keys=True,
            ),
        )
    )
    action = game.action(c, row["action_id"])
    action["data"].setdefault("handler_consequences", {})[record.id] = dict(
        choice=record.choice or "already_dead",
        effect_event=record.effect_event,
        original_handler=record.actor.model_dump(mode="json"),
        account=record.account,
    )
    if action["data"].get("enforcement") is not None:
        from girlframe.services.m3_enforcement_initiative import complete_handler_consequence

        complete_handler_consequence(game, c, action, record, event, viewer, key)
        return
    state = load_state(c, game.store.campaign_id)
    staged = any(
        fact.get("kind") == "battle_damage_stage"
        and fact.get("requirement")
        and json.loads(fact["requirement"]).get("details", {}).get("consequence") == record.id
        for fact in state.facts
    )
    if staged:
        from girlframe.services.m3_battle import complete_handler_consequence as complete_battle

        game.save_action(c, action)
        if not complete_battle(game, c, record, event, viewer, key):
            raise WorkflowError("Recover the actual staged Handler source consequence.")
        return
    if not game.pending(c, action["id"]):
        from girlframe.services.m2_choices import ChoiceEngine

        ChoiceEngine(game).finish(c, load_state(c, game.store.campaign_id), action)
    game.save_action(c, action)


class HandlerConsequenceService:
    def __init__(self, store: OnboardingStore):
        from girlframe.services.m2_game import GameService

        self.store, self.game = store, GameService(store)

    def _source(self, c: Connection, identity: str) -> tuple[GameState, HandlerConsequence]:
        state = load_state(c, self.store.campaign_id)
        record = next((x for x in state.handler_consequences if x.id == identity), None)
        if record is None:
            raise WorkflowError("This actual Handler body consequence is unavailable.")
        history = t.m2["m2_state_history"]
        raw = c.scalar(
            sa.select(history.c.body_json).where(
                history.c.campaign_id == self.store.campaign_id,
                history.c.event_id == record.source_event,
            )
        )
        proof = GameState.model_validate_json(raw) if raw else None
        original = (
            next((x for x in proof.handler_consequences if x.id == identity), None)
            if proof
            else None
        )
        expected = record.model_copy(
            update={
                "state": "pending",
                "choice": None,
                "account": "",
                "effect_event": None,
                "ended_by": None,
            }
        )
        if original is None or original != expected:
            raise WorkflowError("Recover the actual source event and frozen Handler trigger.")
        return state, record

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                kind="handler_consequence",
                trigger=x.trigger,
                actor=x.actor.model_dump(mode="json"),
            )
            for x in state.handler_consequences
            if x.actor.entity == str(viewer.user_id) and x.state == "pending"
        ]

    def tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            return self._tasks(c, viewer)

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state, record = self._source(c, identity)
            if viewer.user_id != int(record.actor.entity):
                raise WorkflowError(
                    "Only the actual Handler's human chooses these body consequences."
                )
            return dict(
                id=record.id,
                trigger=record.trigger,
                state=record.state,
                game_revision=state.revision,
                actor=record.actor.model_dump(mode="json"),
                choice=record.choice,
                account=record.account,
                can_act=record.state == "pending" and rules.same_handler_body(state, record.actor),
                injuries=[
                    dict(id=x.id, description=x.description)
                    for x in state.handler_injuries
                    if (
                        x.actor == record.actor
                        or (
                            rules.same_handler_body(state, record.actor)
                            and rules.same_handler_body(state, x.actor)
                        )
                    )
                    and x.recovery_event is None
                ],
                opportunities=[
                    dict(id=x.id, kind=x.kind, description=x.description)
                    for x in state.handler_opportunities
                    if (
                        x.actor == record.actor
                        or (
                            rules.same_handler_body(state, record.actor)
                            and rules.same_handler_body(state, x.actor)
                        )
                    )
                    and x.ended_event is None
                ],
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        choice: Choice,
        account: str,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays", director_response=True)
            HandlerService(self.store).authorize(c, viewer)
            _, record = self._source(c, identity)
            if record.actor.entity != str(viewer.user_id):
                raise WorkflowError(
                    "The actual original Handler chooses its own replacement consequence."
                )
            if MedicalService(self.store)._handler(c)[1] != record.appointment:
                raise WorkflowError("Recover the actual source Handler appointment first.")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, record = self._source(c, identity)
            if state.revision != revision or record.state != "pending":
                raise WorkflowError("STALE_HANDLER_CONSEQUENCE: reopen the actual current body.")
            source = str(uuid4())
            updated = rules.apply(state, identity, choice, account, source)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_consequence_applied",
                updated,
                event_id=source,
                consequence=identity,
                choice=choice,
                original_handler=record.actor.model_dump(mode="json"),
            )
            for archive in updated.handler_archives:
                if archive.source_event == source:
                    end_body_reviews(self.game, c, archive)
            for result in updated.handler_consequences:
                if result.effect_event == source:
                    finish_callback(self.game, c, result, source, viewer, key)
            return dict(id=identity, state="resolved", choice=choice)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.handler_consequence_applied",
                dict(identity=identity, revision=revision, choice=choice, account=account),
                operation,
                authorize=authorize,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None


def force_end_handler(
    game: "GameService",
    c: Connection,
    state: GameState,
    actor: ActorRef,
    *,
    source_action: str,
    source_choice: str | None,
    clause: str,
    event: str,
    account: str,
) -> GameState:
    from girlframe.engine.m3_handler_consequence_state import HandlerFatalSource

    action = game.action(c, source_action)
    if action["data"].get("play") != "go_for_the_core":
        raise WorkflowError(
            "A compulsory Handler death needs the actual printed fatal Play source."
        )
    if source_choice is not None:
        choices = t.m2["m2_choices"]
        if not c.scalar(
            sa.select(choices.c.id).where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.id == source_choice,
                choices.c.action_id == source_action,
            )
        ):
            raise WorkflowError("Recover the actual source death decision.")
    try:
        fatal = HandlerFatalSource.model_validate_json(
            json.dumps(
                dict(
                    id="handler-fatal:" + source_action + ":" + (source_choice or clause),
                    actor=actor.model_dump(mode="json"),
                    source_event=event,
                    source_action=source_action,
                    source_choice=source_choice,
                    clause=clause,
                    appointment=MedicalService(game.store)._handler(c)[1],
                    account=account,
                )
            )
        )
        return rules.force_end(state, fatal)
    except ValueError as error:
        raise WorkflowError(str(error)) from None
