"""The actual rules-table human reviews an original Sprite's movement before maturation."""

from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_mother_sprite as rules
from girlframe.engine.m2 import GameState
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

EVENT = "m3.mother_sprite_escape_reviewed"


def prove_travel(game: GameService, c: Connection, birth: rules.Birth, move: rules.Travel) -> None:
    from girlframe.services.m3_gorgon_play import GorgonPlayService

    action = game.action(c, birth.action)
    intent = GorgonPlayService(game).source(c, action)
    born = _history(c, game, birth.event)
    moved = _history(c, game, move.event)
    actual = (
        next((x for x in moved.world.gorgons if x.id == birth.sprite.entity), None)
        if moved.world
        else None
    )
    moved_kind = c.scalar(
        sa.select(t.events.c.kind).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == move.event
        )
    )
    if (
        action["state"] != "complete"
        or intent["kind"] != "mother_sprite"
        or intent["actor"] != birth.mother.model_dump(mode="json")
        or action["data"]["result"].get("sprite_birth") != birth.sprite.entity
        or birth not in rules.records(born)
        or move not in rules.moves(moved)
        or move.sprite != birth.sprite
        or move.origin == move.destination
        or moved_kind != "m3.physical_moved"
        or actual is None
        or not actual.alive
        or actual.cell != move.destination
    ):
        raise WorkflowError("Recover the original Mother's paid birth and real Sprite movement.")


def mature_at_start(
    game: GameService, c: Connection, state: GameState, period: str, event: str
) -> None:
    seen = {x.sprite for x in rules.maturities(state)}
    for source in rules.reviews(state):
        if source.adult is None or source.sprite in seen:
            continue
        born = _history(c, game, source.event)
        proof = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == source.event
            )
        ).first()
        if (
            source not in rules.reviews(born)
            or proof is None
            or proof.kind != EVENT
            or proof.actor_id != str(source.judge)
        ):
            raise WorkflowError("Recover the actual Sprite's original reviewed escape.")
    try:
        rules.mature(state, period, event)
    except ValueError as exc:
        raise WorkflowError(str(exc)) from None


class SpriteEscapeService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _judge(self, c: Connection, viewer: GuildViewer) -> str:
        access = Access(self.store)
        access.authorize(c, viewer, "world", director_response=True)
        access.authorize(c, viewer, "plays", director_response=True)
        assert access.registry is not None
        try:
            access.registry.require_available(rules.RULE)
        except ValueError as exc:
            raise WorkflowError(str(exc)) from None
        actual, appointment = MedicalService(self.store)._handler(c)
        if viewer.user_id != actual:
            raise WorkflowError("The original human table adjudicator reviews the Sprite's escape.")
        return appointment

    def options(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._judge(c, viewer)
            state = load_state(c, self.store.campaign_id)
            return dict(
                revision=state.revision,
                options=tuple(
                    (x.event, body.name, x.origin, x.destination)
                    for body, _, x in rules.pending(state)
                ),
            )

    def review(
        self,
        viewer: GuildViewer,
        key: str,
        expected: int,
        movement: str,
        account: str,
        adult: rules.Adult | None,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self._judge(c, viewer)

        def operation(c: Connection) -> dict[str, Any]:
            appointment = self._judge(c, viewer)
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            chosen = next((x for x in rules.pending(state) if x[2].event == movement), None)
            if state.revision != expected or chosen is None or self.game.pending_actions(c):
                raise WorkflowError("Reopen the private review for the Sprite's original move.")
            if not 1 <= len(account.strip()) <= 1200:
                raise WorkflowError("Record the table's actual escape ruling.")
            body, birth, move = chosen
            prove_travel(self.game, c, birth, move)
            event = str(uuid4())
            if adult is not None:
                try:
                    rules.adult_body(body, adult, event)
                except ValueError as exc:
                    raise WorkflowError(str(exc)) from None
            source = rules.Review(
                sprite=birth.sprite,
                movement=movement,
                judge=viewer.user_id,
                appointment=appointment,
                event=event,
                adult=adult,
                account=account.strip(),
            )
            state.facts.append(dict(kind=rules.REVIEW, id=event, body=source.model_dump_json()))
            self.game.event(c, viewer.user_id, key, EVENT, state, event_id=event)
            return dict(sprite=birth.sprite.entity, escaped=adult is not None, event=event)

        return self.store._write(
            viewer,
            key,
            EVENT,
            dict(
                revision=expected,
                movement=movement,
                account=account,
                adult=adult.model_dump(mode="json") if adult else None,
            ),
            operation,
            authorize=authorize,
            auto_audit=False,
        )
