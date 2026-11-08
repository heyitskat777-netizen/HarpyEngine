"""Source-proved Budget Endgame selection, original Girl gift and immutable use proof."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_budget_tags as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _work(c: Connection, store: OnboardingStore, identity: str) -> dict[str, Any]:
    work = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(work)
            .where(work.c.campaign_id == store.campaign_id, work.c.id == identity)
            .order_by(work.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None:
        raise WorkflowError("Unknown original Budget Tag work")
    return dict(row)


def _selection(
    c: Connection, game: GameService, identity: str, *, rule: str = "strain.budget.endgame.5"
) -> tuple[dict[str, Any], GameState]:
    row = _work(c, game.store, identity)
    work = t.m3["m3_required_work"]
    first = (
        c.execute(
            sa.select(work)
            .where(work.c.campaign_id == game.store.campaign_id, work.c.id == identity)
            .order_by(work.c.revision)
            .limit(1)
        )
        .mappings()
        .one()
    )
    if any(
        row[k] != first[k] for k in ("kind", "body_json", "owner_id", "subject_id", "off_duty_id")
    ):
        raise WorkflowError("Recover the original unaltered Budget Tag source")
    body = json.loads(first["body_json"])
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == first["event_id"]
            )
        )
        .mappings()
        .first()
    )
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == first["event_id"],
        )
    )
    original = GameState.model_validate_json(raw) if raw else None
    payload = json.loads(event["payload_json"]) if event else {}
    chosen = (
        next((x for x in original.strain.endgames if x.id == body.get("source_work")), None)
        if original and original.strain
        else None
    )
    if (
        row["kind"] != "strain_endgame_effect"
        or event is None
        or original is None
        or event["kind"] != "m3.strain_option_saved"
        or chosen is None
        or body.get("rule_id") != rule
        or chosen.rule_id != body["rule_id"]
        or chosen.period_id != row["off_duty_id"]
        or payload.get("work_id") != chosen.id
        or payload.get("rule_id") != chosen.rule_id
        or event["actor_id"] != str(original.handler)
    ):
        raise WorkflowError("Recover the actual selected Budget Endgame source")
    return row, original


def _nomination(c: Connection, game: GameService, gift: rules.Gift) -> None:
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == gift.nominated_event,
            )
        )
        .mappings()
        .first()
    )
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == gift.nominated_event,
        )
    )
    original = GameState.model_validate_json(raw) if raw else None
    saved = next((x for x in rules.gifts(original) if x.id == gift.id), None) if original else None
    fields = ("id", "source_work", "source_event", "handler", "girl", "nominated_event")
    if (
        event is None
        or event["kind"] != "m3.budget_handler_tag_nominated"
        or event["actor_id"] != gift.handler.entity
        or saved is None
        or saved.stage != "awaiting_girl"
        or any(getattr(saved, k) != getattr(gift, k) for k in fields)
        or json.loads(event["payload_json"]).get("girl") != gift.girl.model_dump(mode="json")
        or json.loads(event["payload_json"]).get("gift") != gift.id
    ):
        raise WorkflowError("Recover the actual immutable original Girl nomination")


def prove_persistent(
    c: Connection, game: GameService, state: GameState, handler: ActorRef, tag: str
) -> bool:
    if not rules.persistent(state, handler, tag):
        return False
    gift = next(
        x
        for x in rules.gifts(state)
        if x.stage == "given" and x.tag == tag and same_handler_body(state, x.handler)
    )
    _, original = _selection(c, game, gift.source_work)
    _nomination(c, game, gift)
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == gift.given_event,
        )
    )
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == gift.given_event
            )
        )
        .mappings()
        .first()
    )
    born = GameState.model_validate_json(raw) if raw else None
    saved = next((x for x in rules.gifts(born) if x.id == gift.id), None) if born else None
    current_tag = next((x for x in state.handler_tags if x.id == tag), None)
    source_tag = next((x for x in born.handler_tags if x.id == tag), None) if born else None
    if (
        event is None
        or event["kind"] != "m3.budget_handler_tag_given"
        or born is None
        or event["actor_id"] != gift.girl.entity
        or saved != gift
        or active_handler(original) != gift.handler
        or current_tag is None
        or source_tag is None
        or current_tag.label != source_tag.label
        or current_tag.giver_actor != source_tag.giver_actor
        or current_tag.giver_actor != gift.girl
        or current_tag.giver != source_tag.giver
        or source_tag.label != gift.label
        or json.loads(event["payload_json"]).get("gift") != gift.id
    ):
        raise WorkflowError("Recover the actual immutable persistent Handler Tag gift")
    return True


class BudgetTagService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer, *, write: bool) -> None:
        Access(self.store).authorize(c, viewer, "strain")
        if write:
            self.game.unpaused(c)

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        try:
            with self.store.engine.connect() as c:
                self._access(c, viewer, write=False)
                state = load_state(c, self.store.campaign_id)
                gift = next(
                    (
                        x
                        for x in rules.gifts(state)
                        if x.id == identity or x.source_work == identity
                    ),
                    None,
                )
                row, original = _selection(c, self.game, gift.source_work if gift else identity)
                handler = active_handler(original)
                if handler is None:
                    raise WorkflowError("Recover the actual original Handler body")
                if viewer.user_id != int(handler.entity) and (
                    (gift is None or viewer.user_id != int(gift.girl.entity))
                    and not (
                        viewer.user_id == state.handler and not same_handler_body(state, handler)
                    )
                ):
                    raise WorkflowError(
                        "This private Endgame gift belongs to its original two humans"
                    )
                candidates = [
                    dict(
                        ref=ActorRef(
                            kind="pilot", entity=str(uid), incarnation=sheet.character_id
                        ).model_dump(mode="json"),
                        name=sheet.callsign,
                    )
                    for uid in original.order
                    if (sheet := original.sheets.get(str(uid))) is not None
                    and sheet.character_id is not None
                ]
                return dict(
                    id=gift.id if gift else identity,
                    revision=row["revision"],
                    game_revision=state.revision,
                    state=row["state"],
                    gift=gift.model_dump(mode="json") if gift else None,
                    girls=candidates,
                    original_alive=same_handler_body(state, handler),
                    girl_alive=rules.original_girl_alive(state, gift.girl) if gift else True,
                )
        except ValidationError:
            raise WorkflowError("Recover the original private Budget Tag source records") from None

    def _write(
        self, viewer: GuildViewer, key: str, kind: str, body: dict[str, Any], operation: Any
    ) -> dict[str, Any]:
        try:
            return self.store._write(
                viewer,
                key,
                kind,
                body,
                operation,
                auto_audit=False,
                authorize=lambda c: self._access(c, viewer, write=True),
            )
        except ValidationError:
            raise WorkflowError("Recover the original private Budget Tag source records") from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def nominate(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        expected: int,
        girl: ActorRef,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            row, original = _selection(c, self.game, identity)
            state = load_state(c, self.store.campaign_id)
            handler = active_handler(original)
            sheet = state.sheets.get(girl.entity)
            old = original.sheets.get(girl.entity)
            if (
                row["state"] != "pending"
                or row["revision"] != revision
                or state.revision != expected
            ):
                raise WorkflowError("STALE_BUDGET_TAG: reopen the original Endgame")
            if (
                handler is None
                or viewer.user_id != int(handler.entity)
                or not same_handler_body(state, handler)
            ):
                raise WorkflowError("Only this actual original Handler selects the Girl")
            if (
                girl.kind != "pilot"
                or int(girl.entity) not in original.order
                or old is None
                or sheet is None
                or old.character_id != girl.incarnation
                or sheet.character_id != girl.incarnation
                or int(girl.entity) not in state.order
                or not account.strip()
            ):
                raise WorkflowError("Choose a living original Cadre Girl from this actual Endgame")
            if any(x.source_work == identity for x in rules.gifts(state)):
                raise WorkflowError("The actual original Girl has already been selected")
            event, gift_id = str(uuid4()), identity + ":girl-gift"
            gift = rules.Gift(
                id=gift_id,
                revision=1,
                source_work=identity,
                source_event=row["event_id"],
                handler=handler,
                girl=girl,
                nominated_event=event,
                stage="awaiting_girl",
                account=account,
            )
            rules.save(state, gift)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.budget_handler_tag_nominated",
                state,
                event_id=event,
                gift=gift_id,
                source_work=identity,
                girl=girl.model_dump(mode="json"),
            )
            related(
                c,
                self.store,
                row,
                gift_id,
                int(girl.entity),
                int(handler.entity),
                "budget_handler_tag",
                dict(gift=gift_id, source_work=identity, immediate=True),
                event,
            )
            return dict(id=gift_id, state="awaiting_girl")

        return self._write(
            viewer,
            key,
            "m3.budget_handler_tag_nominated",
            dict(
                id=identity,
                revision=revision,
                expected=expected,
                girl=girl.model_dump(mode="json"),
                account=account,
            ),
            operation,
        )

    def give(
        self, viewer: GuildViewer, key: str, identity: str, expected: int, label: str, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            gift = rules.pending(state, identity)
            if state.revision != expected:
                raise WorkflowError("STALE_BUDGET_TAG: reopen your original gift")
            if viewer.user_id != int(gift.girl.entity):
                raise WorkflowError("Only the selected original Girl names her Tag")
            parent, original = _selection(c, self.game, gift.source_work)
            _nomination(c, self.game, gift)
            if any(x.actor == gift.girl for x in state.career_archives):
                from girlframe.services.m3_harpy_defeat import ended_actor_source

                if ended_actor_source(self.game, c, state, gift.girl) is None:
                    raise WorkflowError("Recover the actual original Girl's career source")
            row = _work(c, self.store, identity)
            nomination = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == self.store.campaign_id,
                        t.events.c.id == gift.nominated_event,
                    )
                )
                .mappings()
                .first()
            )
            if (
                parent["state"] != "pending"
                or row["state"] != "pending"
                or nomination is None
                or nomination["kind"] != "m3.budget_handler_tag_nominated"
                or nomination["actor_id"] != str(original.handler)
                or active_handler(original) != gift.handler
            ):
                raise WorkflowError("Recover the original nominated Girl and immutable source")
            event = str(uuid4())
            state = rules.give(state, identity, label, account, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.budget_handler_tag_given",
                state,
                event_id=event,
                gift=identity,
                source_work=gift.source_work,
            )
            for work in (parent, row):
                c.execute(
                    t.m3["m3_required_work"]
                    .insert()
                    .values(
                        **(
                            work
                            | dict(revision=work["revision"] + 1, state="resolved", event_id=event)
                        )
                    )
                )
            return dict(
                id=identity,
                state="given",
                tag=next(x.tag for x in rules.gifts(state) if x.id == identity),
            )

        return self._write(
            viewer,
            key,
            "m3.budget_handler_tag_given",
            dict(id=identity, expected=expected, label=label, account=account),
            operation,
        )

    def close_original(
        self, viewer: GuildViewer, key: str, identity: str, expected: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_harpy_defeat import ended_actor_source

            state = load_state(c, self.store.campaign_id)
            gift = next(
                (x for x in rules.gifts(state) if x.id == identity or x.source_work == identity),
                None,
            )
            parent, original = _selection(c, self.game, gift.source_work if gift else identity)
            handler = active_handler(original)
            owners = {original.handler, state.handler} | (
                {int(gift.girl.entity)} if gift else set()
            )
            if viewer.user_id not in owners or handler is None:
                raise WorkflowError(
                    "Only the actual source humans or current facilitator review this ending"
                )
            if (
                state.revision != expected
                or parent["state"] != "pending"
                or (gift and gift.stage != "awaiting_girl")
            ):
                raise WorkflowError("STALE_BUDGET_TAG: reopen the actual original request")
            ended = (
                handler
                if not same_handler_body(state, handler)
                else (
                    gift.girl if gift and not rules.original_girl_alive(state, gift.girl) else None
                )
            )
            ending = ended_actor_source(self.game, c, state, ended) if ended else None
            if ended is None or ending is None:
                raise WorkflowError(
                    "Prove the actual original's ending; a changed human or label is insufficient"
                )
            event = str(uuid4())
            if gift:
                _nomination(c, self.game, gift)
                rules.save(
                    state,
                    gift.model_copy(
                        update={"revision": gift.revision + 1, "stage": "original_ended"}
                    ),
                )
            state.facts.append(
                dict(
                    kind="budget_tag_original_ended",
                    source_work=parent["id"],
                    actor=ended.model_dump_json(),
                    ending_event=ending,
                    event=event,
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.budget_handler_tag_original_ended",
                state,
                event_id=event,
                source_work=parent["id"],
                original=ended.model_dump(mode="json"),
                ending_event=ending,
            )
            for work in (parent, *([_work(c, self.store, gift.id)] if gift else [])):
                c.execute(
                    t.m3["m3_required_work"]
                    .insert()
                    .values(
                        **(
                            work
                            | dict(revision=work["revision"] + 1, state="resolved", event_id=event)
                        )
                    )
                )
            return dict(id=identity, state="original_ended", ending_event=ending)

        return self._write(
            viewer,
            key,
            "m3.budget_handler_tag_original_ended",
            dict(id=identity, expected=expected),
            operation,
        )
