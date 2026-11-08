"""Authentic held-award spending and exact actual new-location source history."""

from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_advancements as advancement
from girlframe.engine import m3_location_build as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_world_state import Cell, Location
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def prove_effect(game: GameService, c: Connection, effect: rules.Effect) -> None:
    gate = Access(game.store)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)
    after = _history(c, game, effect.event)
    sequence = c.scalar(
        sa.select(t.events.c.seq).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == effect.event
        )
    )
    history = t.m2["m2_state_history"]
    raw = (
        c.scalar(
            sa.select(history.c.body_json)
            .join(t.events, t.events.c.id == history.c.event_id)
            .where(
                history.c.campaign_id == game.store.campaign_id,
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.seq < sequence,
            )
            .order_by(t.events.c.seq.desc())
            .limit(1)
        )
        if sequence
        else None
    )
    before = GameState.model_validate_json(raw) if raw else None
    prior = (
        next((x for x in advancement.awards(before) if x.id == effect.award), None)
        if before
        else None
    )
    if (
        before is None
        or before.world is None
        or after.world is None
        or prior is None
        or prior.phase != "held"
        or (prior.handler, prior.appointment) != (effect.handler, effect.appointment)
    ):
        raise WorkflowError("Recover this exact original held award and actual new-location source")
    rules.require_site(before, effect.location.cell)
    expected = before.world.model_copy(
        update=dict(locations=before.world.locations + (effect.location,))
    )
    if expected != after.world:
        raise WorkflowError("Building cannot replace or modify previous world entities and sources")


class LocationBuildService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "economy", director_response=True)
        gate.authorize(c, viewer, "world", director_response=True)
        assert gate.registry is not None
        gate.registry.require_available(rules.RULE)

    def menu(self, viewer: GuildViewer, identity: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            if identity:
                _, _, handler, _, value = HandlerAdvancementService(self.store)._proof(c, identity)
                if (
                    handler.entity != str(viewer.user_id)
                    or value is None
                    or value.location_build is None
                ):
                    raise WorkflowError("This new location belongs to its original Handler's spend")
                return dict(
                    historical=True,
                    id=identity,
                    location=value.location_build.location.model_dump(mode="json"),
                )
            HandlerService(self.store).authorize(c, viewer)
            if state.world is None:
                raise WorkflowError("Initialize the actual world before building a new location")
            return dict(
                historical=False,
                revision=state.revision,
                awards=HandlerAdvancementService(self.store)._tasks(c, viewer),
                minimum=state.world.board.minimum,
                maximum=state.world.board.maximum,
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                revision=state.revision,
                label="Built location — " + x.location_build.location.name,
            )
            for x in advancement.awards(state)
            if x.handler.entity == str(viewer.user_id) and x.location_build is not None
        ]

    def build(
        self,
        viewer: GuildViewer,
        key: str,
        award_id: str,
        revision: int,
        kind: Literal["base", "city", "important"],
        name: str,
        cell: Cell,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _, state, handler, appointment, award = HandlerAdvancementService(self.store)._source(
                c, viewer, award_id
            )
            HandlerAdvancementService(self.store)._current(c, state, handler, appointment)
            if (
                state.revision != revision
                or award is None
                or award.phase != "held"
                or not account.strip()
            ):
                raise WorkflowError("Reopen this actual held award and current construction site")
            rules.require_site(state, cell)
            event = str(uuid4())
            location = Location(
                id="location:" + str(uuid4()), name=name.strip(), cell=cell, kind=kind
            )
            effect = rules.Effect(
                id="location-build:" + award_id,
                award=award_id,
                handler=handler,
                appointment=appointment,
                event=event,
                location=location,
            )
            rules.apply(state, effect)
            advancement.put(
                state,
                advancement.Award.model_validate_json(
                    award.model_copy(
                        update=dict(
                            phase="spent",
                            location_build=effect,
                            spend_event=event,
                            spend_account=account.strip(),
                        )
                    ).model_dump_json()
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_advancement_spent",
                state,
                event_id=event,
                award_id=award_id,
                rule_id=rules.RULE,
                location_id=location.id,
            )
            return dict(id=award_id, phase="spent", location=location.id)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.location_built",
                dict(
                    award=award_id,
                    revision=revision,
                    kind=kind,
                    name=name,
                    cell=cell,
                    account=account,
                ),
                operation,
                auto_audit=False,
                authorize=lambda c: self._access(c, viewer),
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
