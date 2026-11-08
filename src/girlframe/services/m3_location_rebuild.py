"""Owned direct advancement spending with actual same-location restoration proof."""

import hashlib
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_advancements as advancement
from girlframe.engine import m3_location_rebuild as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_world_state import Location
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def fingerprint(value: Location) -> str:
    return hashlib.sha256(value.model_dump_json().encode()).hexdigest()


def prove_effect(game: GameService, c: Connection, effect: rules.Effect) -> None:
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
    gate = Access(game.store)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)
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
        or next((x for x in before.world.locations if x.id == effect.before.id), None)
        != effect.before
        or next((x for x in after.world.locations if x.id == effect.after.id), None) != effect.after
    ):
        raise WorkflowError("Recover the exact held award and actual same-location rebuild effect")
    expected = before.world.model_copy(
        update=dict(
            locations=tuple(
                effect.after if x.id == effect.before.id else x for x in before.world.locations
            )
        )
    )
    if expected != after.world:
        raise WorkflowError("Rebuilding cannot edit unrelated world resources or location identity")


class LocationRebuildService:
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
                    or value.location_rebuild is None
                ):
                    raise WorkflowError("This actual rebuild belongs to its original Handler")
                effect = value.location_rebuild
                return dict(
                    historical=True,
                    id=identity,
                    location=effect.after.name,
                    before=effect.before.condition,
                    after=effect.after.condition,
                    account=value.spend_account,
                )
            HandlerService(self.store).authorize(c, viewer)
            awards = HandlerAdvancementService(self.store)._tasks(c, viewer)
            return dict(
                historical=False,
                revision=state.revision,
                awards=awards,
                locations=[
                    dict(
                        id=x.id,
                        label=x.name,
                        condition=x.condition,
                        cell=x.cell,
                        fingerprint=fingerprint(x),
                        blocked=bool(x.blocked_by),
                    )
                    for x in state.world.locations
                    if x.condition != "intact"
                ]
                if state.world
                else [],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                revision=state.revision,
                label="Rebuilt location — " + x.location_rebuild.after.name,
            )
            for x in advancement.awards(state)
            if x.handler.entity == str(viewer.user_id) and x.location_rebuild is not None
        ]

    def rebuild(
        self,
        viewer: GuildViewer,
        key: str,
        award_id: str,
        revision: int,
        location_id: str,
        expected_location_fingerprint: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _, state, handler, appointment, award = HandlerAdvancementService(self.store)._source(
                c, viewer, award_id
            )
            HandlerAdvancementService(self.store)._current(c, state, handler, appointment)
            location = (
                next((x for x in state.world.locations if x.id == location_id), None)
                if state.world
                else None
            )
            if (
                state.revision != revision
                or award is None
                or award.phase != "held"
                or location is None
                or location.condition == "intact"
                or fingerprint(location) != expected_location_fingerprint
                or not account.strip()
            ):
                raise WorkflowError(
                    "Reopen one actual held award and this existing non-intact location"
                )
            event = str(uuid4())
            effect = rules.Effect(
                id="location-rebuild:" + award_id,
                award=award_id,
                handler=handler,
                appointment=appointment,
                event=event,
                before=location,
                after=location.model_copy(update=dict(condition="intact")),
            )
            rules.apply(state, effect)
            advancement.put(
                state,
                advancement.Award.model_validate_json(
                    award.model_copy(
                        update=dict(
                            phase="spent",
                            location_rebuild=effect,
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
                location_id=location_id,
            )
            return dict(id=award_id, phase="spent", location=location_id)

        return self.store._write(
            viewer,
            key,
            "m3.location_rebuilt",
            dict(
                award=award_id,
                revision=revision,
                location=location_id,
                fingerprint=expected_location_fingerprint,
                account=account,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: self._access(c, viewer),
        )
