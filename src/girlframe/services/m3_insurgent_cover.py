"""The original Insurgent's Off-Duty Cover roll and a Girl's owned evidence."""

import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_insurgent_cover as rules
from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_off_duty import Period
from girlframe.engine.rolls import D6Source, OsD6
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_handler_book_orders import active_book
from girlframe.services.m3_insurgent_loyalty import labels
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def stage_start(
    game: GameService, c: Connection, state: GameState, period: Period, event: str
) -> rules.Cover | None:
    owned = active_book(game, c, state, book="Insurgent", rule=rules.RULE)
    if owned is None or owned[0].entity != str(period.handler):
        return None
    living_npcs = state.world.npcs if state.world else ()
    if not (
        any(x.alive and any(tag.label == "Sympathizer" for tag in x.tags) for x in living_npcs)
        or any(
            x.status == "sympathizer"
            for uid in period.pilots
            for x in labels(state, current_ref(state, uid))
        )
    ):
        return None
    value = rules.Cover(
        id="cover:" + period.id,
        period=period.id,
        handler=owned[0],
        source_event=event,
    )
    rules.put(state, value)
    return value


def materialize(c: Connection, periods: OffDutyService, value: rules.Cover, event: str) -> None:
    owner = int(value.handler.entity)
    related(
        c,
        periods.store,
        dict(campaign_id=periods.store.campaign_id, off_duty_id=value.period),
        value.id,
        owner,
        owner,
        rules.WORK,
        dict(stage="die", source_pdf=136),
        event,
    )


def _source(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Cover:
    value = next((x for x in rules.records(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual original Cover Strain work")
    history = t.m2["m2_state_history"]
    snapshot = c.scalar(
        sa.select(history.c.body_json)
        .join(t.events, t.events.c.id == history.c.event_id)
        .where(
            history.c.campaign_id == game.store.campaign_id,
            history.c.event_id == value.source_event,
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind == "m3.off_duty_preparing",
            t.events.c.actor_id == value.handler.entity,
        )
    )
    original = (
        next(
            (x for x in rules.records(GameState.model_validate_json(snapshot)) if x.id == identity),
            None,
        )
        if snapshot
        else None
    )
    if (
        original is None
        or original.period != value.period
        or original.handler != value.handler
        or original.source_event != value.source_event
        or original.face is not None
    ):
        raise WorkflowError("Recover the actual original Off-Duty Cover source")
    return value


def prove_held(
    game: GameService,
    c: Connection,
    state: GameState,
    handler: ActorRef,
    girl: ActorRef,
    tag: str,
) -> None:
    value = next((x for x in rules.records(state) if x.handler == handler and x.tag == tag), None)
    if value is None:
        return
    _source(game, c, state, value.id)
    if value.holder != girl or value.lost_event is not None:
        raise WorkflowError("Only the actual original Girl holding this evidence can use its Tag")
    event = c.execute(
        sa.select(t.events.c.actor_id, t.events.c.kind).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == value.evidence_event,
        )
    ).first()
    if (
        event is None
        or event.kind != "m3.insurgent_evidence_found"
        or event.actor_id != girl.entity
    ):
        raise WorkflowError("Recover this Girl's actual evidence acquisition")


class CoverService:
    def __init__(self, periods: OffDutyService, dice: D6Source | None = None):
        self.periods, self.store, self.game = periods, periods.store, periods.game
        self.strain = StrainService(periods)
        self.dice = dice or OsD6()
        self.rng_source = "os" if dice is None else "test_injected"

    def _row(self, c: Connection, identity: str) -> dict[str, Any]:
        work = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(work)
                .where(
                    work.c.campaign_id == self.store.campaign_id,
                    work.c.id == identity,
                    work.c.kind == rules.WORK,
                )
                .order_by(work.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None:
            raise WorkflowError("Recover the actual original Cover Strain work")
        return dict(row)

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        kind: str,
        payload: dict[str, Any],
        change: Callable[[Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "strain")
            self.game.unpaused(c)

        try:
            return self.store._write(
                viewer,
                key,
                kind,
                payload,
                change,
                authorize=access,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _current(
        self, c: Connection, identity: str, expected: int, stage: str
    ) -> tuple[GameState, rules.Cover, Period, dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        value = _source(self.game, c, state, identity)
        owned = active_book(self.game, c, state, book="Insurgent", rule=rules.RULE)
        period = self.periods._get(c, value.period)
        row = self._row(c, value.id)
        if (
            state.revision != expected
            or owned is None
            or owned[0] != value.handler
            or period.phase != "preparing"
            or row["state"] != "pending"
            or json.loads(row["body_json"]).get("stage") != stage
        ):
            raise WorkflowError("STALE_COVER: reopen the original Cover Strain decision")
        return state, value, period, row

    def roll(self, viewer: GuildViewer, key: str, identity: str, expected: int) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state, value, _, row = self._current(c, identity, expected, "die")
            if viewer.user_id != int(value.handler.entity):
                raise WorkflowError("Only the original Insurgent can roll this Cover Strain")
            face = self.dice.roll_d6()
            if type(face) is not int or not 1 <= face <= 6:
                raise WorkflowError("The actual Cover die result must be from one to six")
            next_face = rules.effective(state, value.handler, face)
            event = str(uuid4())
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        face=face,
                        effective_face=next_face,
                        roll_event=event,
                        rng_source=self.rng_source,
                    )
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.insurgent_cover_rolled",
                state,
                event_id=event,
                cover=identity,
            )
            self.strain._save(c, row, event, json.loads(row["body_json"]) | dict(stage="column"))
            return dict(id=identity, face=face, effective_face=next_face, revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.insurgent_cover_rolled",
            dict(id=identity, expected=expected),
            operation,
        )

    def choose_evidence(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        target: ActorRef,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state, value, period, row = self._current(c, identity, expected, "column")
            if (
                viewer.user_id != int(value.handler.entity)
                or value.effective_face != 1
                or target.kind != "pilot"
                or period.character_ids.get(target.entity) != target.incarnation
                or current_ref(state, int(target.entity)) != target
            ):
                raise WorkflowError(
                    "Cover 1.2 needs its original Insurgent and an actual original Girl"
                )
            event = str(uuid4())
            rules.put(state, value.model_copy(update=dict(holder=target, choice_event=event)))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.insurgent_cover_evidence_selected",
                state,
                event_id=event,
                cover=identity,
            )
            self.strain._save(c, row, event, json.loads(row["body_json"]) | dict(stage="evidence"))
            return dict(id=identity, state="awaiting_evidence", revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.insurgent_cover_evidence_selected",
            dict(
                id=identity,
                expected=expected,
                target=target.model_dump(mode="json"),
            ),
            operation,
        )

    def acquire(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state, value, _, row = self._current(c, identity, expected, "evidence")
            if (
                value.holder is None
                or value.holder.entity != str(viewer.user_id)
                or current_ref(state, viewer.user_id) != value.holder
                or not 1 <= len(account.strip()) <= 1200
            ):
                raise WorkflowError(
                    "Only the original Girl chooses how she actually finds evidence"
                )
            event = str(uuid4())
            tag = TagState(
                id=identity + ":evidence",
                label="Evidence of Rebel Activity",
                giver=viewer.user_id,
                observers=(viewer.user_id,),
                giver_actor=value.holder,
            )
            state.handler_tags.append(tag)
            rules.put(state, value.model_copy(update=dict(tag=tag.id, evidence_event=event)))
            state.facts.append(
                dict(
                    kind="insurgent_evidence_account",
                    cover=identity,
                    event=event,
                    account=account.strip(),
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.insurgent_evidence_found",
                state,
                event_id=event,
                cover=identity,
            )
            self.strain._save(
                c, row, event, json.loads(row["body_json"]) | dict(stage="resolved"), resolved=True
            )
            return dict(id=identity, state="resolved", revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.insurgent_evidence_found",
            dict(
                id=identity,
                expected=expected,
                account=account,
            ),
            operation,
        )

    def lose(self, viewer: GuildViewer, key: str, identity: str, expected: int) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            value = _source(self.game, c, state, identity)
            if (
                value.holder is None
                or value.holder.entity != str(viewer.user_id)
                or current_ref(state, viewer.user_id) != value.holder
                or value.tag is None
                or value.lost_event is not None
                or state.revision != expected
            ):
                raise WorkflowError(
                    "Only the original holder can record loss of her actual evidence"
                )
            prove_held(self.game, c, state, value.handler, value.holder, value.tag)
            event = str(uuid4())
            state.handler_tags = [x for x in state.handler_tags if x.id != value.tag]
            rules.put(state, value.model_copy(update=dict(lost_event=event)))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.insurgent_evidence_lost",
                state,
                event_id=event,
                cover=identity,
            )
            return dict(id=identity, state="lost", revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.insurgent_evidence_lost",
            dict(
                id=identity,
                expected=expected,
            ),
            operation,
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, str]]:
        state = load_state(c, self.store.campaign_id)
        current = state.sheets.get(str(viewer.user_id))
        return [
            dict(id=x.id, stage="held" if x.tag else "evidence")
            for x in rules.records(state)
            if current is not None
            and x.holder is not None
            and x.holder.entity == str(viewer.user_id)
            and x.holder.incarnation == current.character_id
            and x.lost_event is None
        ]

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = _source(self.game, c, state, identity)
            own = (
                value.holder is not None
                and value.holder.entity == str(viewer.user_id)
                and current_ref(state, viewer.user_id) == value.holder
            )
            handler = active_handler(state) == value.handler and value.handler.entity == str(
                viewer.user_id
            )
            if not own and not handler:
                raise WorkflowError("Cover is private to its original decision owners")
            period = self.periods._get(c, value.period)
            row = self._row(c, identity)
            stage = json.loads(row["body_json"])["stage"]
            return dict(
                id=identity,
                revision=state.revision,
                stage="lost" if own and value.lost_event else stage,
                owned_evidence=own,
                face=value.face,
                effective_face=value.effective_face,
                targets=tuple(
                    dict(
                        ref=current_ref(state, uid).model_dump(mode="json"),
                        token=current_ref(state, uid).token,
                        name=state.sheets[str(uid)].callsign,
                    )
                    for uid in period.pilots
                    if str(uid) in state.sheets
                    and state.sheets[str(uid)].character_id == period.character_ids.get(str(uid))
                )
                if handler and stage == "column" and value.effective_face == 1
                else (),
            )
