"""Original Frantic Tag births and one-use private Strain consequences."""

from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_frantic_breakdown as breakdown_rules
from girlframe.engine import m3_frantic_crisis as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_collateral import stage_loss
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_promotional_opportunity import in_responsibility
from girlframe.engine.m3_strain import effective_levels, set_level
from girlframe.engine.m3_strain_state import Track, Trigger
from girlframe.engine.m3_world import destroy
from girlframe.engine.m3_world_state import Location
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_frantic_breakdown import FranticBreakdownService
from girlframe.services.m3_handler_book_orders import active_book
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def ruin_sites(state: GameState) -> tuple[Location, ...]:
    if state.world is None:
        return ()
    return tuple(
        x
        for x in state.world.locations
        if x.kind in ("city", "base")
        and x.condition != "destroyed"
        and not x.protection_sources
        and (not x.ship or not x.ship.armoured)
        and in_responsibility(state, x.cell)
    )


def observe_births(
    game: GameService, c: Connection, before: GameState, state: GameState, event: str
) -> None:
    persona = state.handler_persona
    if persona is None or persona.playbook != "Frantic":
        return
    already = {x.id for x in before.handler_tags}
    tags = [x for x in state.handler_tags if x.id not in already]
    if not tags:
        return
    owned = active_book(game, c, state, book="Frantic", rule=rules.RULE)
    if owned is None or active_handler(before) != owned[0]:
        return
    existing = {x.tag for x in rules.records(state) if x.handler == owned[0]}
    for tag in tags:
        if tag.id in existing:
            continue
        identity = str(uuid5(NAMESPACE_URL, "girlframe:crisis:" + owned[0].token + ":" + tag.id))
        rules.put(
            state, rules.Crisis(id=identity, handler=owned[0], tag=tag.id, source_event=event)
        )


class CrisisService:
    def __init__(self, store: OnboardingStore, game: GameService | None = None):
        self.store, self.game = store, game or GameService(store)
        self.strain = StrainService(OffDutyService(MissionService(store)))

    def _current(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[GameState, rules.Crisis, str]:
        state = load_state(c, self.store.campaign_id)
        value = next((x for x in rules.records(state) if x.id == identity), None)
        if (
            value is None
            or value.handler != active_handler(state)
            or value.handler.entity != str(viewer.user_id)
        ):
            raise WorkflowError("This private Crisis belongs to its original Frantic")
        history = t.m2["m2_state_history"]
        snapshot = c.scalar(
            sa.select(history.c.body_json).where(
                history.c.campaign_id == self.store.campaign_id,
                history.c.event_id == value.source_event,
            )
        )
        original = GameState.model_validate_json(snapshot) if snapshot else None
        proof = (
            next((x for x in rules.records(original) if x.id == identity), None)
            if original
            else None
        )
        tag = (
            next((x for x in original.handler_tags if x.id == value.tag), None)
            if original
            else None
        )
        if (
            original is None
            or active_handler(original) != value.handler
            or tag is None
            or proof is None
            or proof.slot is not None
            or proof.handler != value.handler
            or proof.tag != value.tag
            or proof.source_event != value.source_event
        ):
            raise WorkflowError("Recover the original committed Tag gain")
        return state, value, tag.label

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[str]:
        state = load_state(c, self.store.campaign_id)
        current = active_handler(state)
        if current is None or current.entity != str(viewer.user_id):
            return []
        return [x.id for x in rules.records(state) if x.handler == current and x.slot is None]

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state, value, label = self._current(c, viewer, identity)
            used = {x.slot for x in rules.records(state) if x.handler == value.handler}
            return dict(
                id=identity,
                revision=state.revision,
                tag=label,
                slot=value.slot,
                track=value.track,
                breakdown=value.breakdown,
                location=value.location,
                available=tuple(x for x in rules.RAISE_SLOTS if x not in used),
                immediate=tuple(x for x in rules.BREAK_SLOTS if x not in used),
                ruins=tuple(
                    (
                        slot,
                        tuple(
                            (x.id, x.name)
                            for x in ruin_sites(state)
                            if x.kind == ("city" if slot == "city" else "base")
                        ),
                    )
                    for slot in rules.RUIN_SLOTS
                    if slot not in used
                ),
                low=tuple(x for x, y in state.strain.levels.items() if y == "low")
                if state.strain
                else (),
            )

    def raise_track(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        slot: rules.RaiseSlot,
        track: Track,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "strain")
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            state, value, _ = self._current(c, viewer, identity)
            if state.revision != expected or value.slot is not None:
                raise WorkflowError("STALE_STATE: reopen the actual remaining Crisis choice")
            owned = active_book(self.game, c, state, book="Frantic", rule=rules.RULE)
            if (
                owned is None
                or owned[0] != value.handler
                or slot not in rules.RAISE_SLOTS
                or any(x.handler == value.handler and x.slot == slot for x in rules.records(state))
                or state.strain is None
                or state.strain.levels.get(track) != "low"
            ):
                raise WorkflowError("Choose an unused printed raise and an actual Low Strain track")
            state.strain, changed = set_level(state.strain, track, "high")
            if effective_levels(state.strain)[track] != "high":
                raise WorkflowError(
                    "Resolve the independent Strain relief before this printed escalation"
                )
            event = str(uuid4())
            rules.put(
                state, value.model_copy(update=dict(slot=slot, track=track, effect_event=event))
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.frantic_crisis_raised",
                state,
                event_id=event,
                crisis=identity,
                track=track,
            )
            self.strain.save_unrolled_levels(c, changed, event)
            return dict(id=identity, state="complete", revision=state.revision)

        return self.store._write(
            viewer,
            key,
            "m3.frantic_crisis_raised",
            dict(id=identity, expected=expected, slot=slot, track=track),
            operation,
            authorize=access,
            auto_audit=False,
        )

    def break_now(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        slot: rules.BreakSlot,
        channel: int,
        account: str,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "plays")
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            state, value, _ = self._current(c, viewer, identity)
            if state.revision != expected or value.slot is not None:
                raise WorkflowError("STALE_STATE: reopen the actual remaining Crisis choice")
            owned = active_book(self.game, c, state, book="Frantic", rule=rules.RULE)
            if (
                owned is None
                or owned[0] != value.handler
                or slot not in rules.BREAK_SLOTS
                or any(x.handler == value.handler and x.slot == slot for x in rules.records(state))
                or not 1 <= len(account.strip()) <= 1200
            ):
                raise WorkflowError("Choose an unused immediate Break Down slot as its Frantic")
            roll = FranticBreakdownService(self.store, self.game).plan_roll(
                c, state, viewer, channel, account
            )
            breakdown_rules.put(state, roll)
            rules.put(
                state,
                value.model_copy(
                    update=dict(slot=slot, breakdown=roll.id, effect_event=roll.source_event)
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.frantic_breakdown_rolled",
                state,
                event_id=roll.source_event,
                crisis=identity,
                breakdown=roll.id,
            )
            return dict(id=identity, breakdown=roll.id, revision=state.revision)

        return self.store._write(
            viewer,
            key,
            "m3.frantic_breakdown_rolled",
            dict(id=identity, expected=expected, slot=slot, channel=channel, account=account),
            operation,
            authorize=access,
            auto_audit=False,
        )

    def ruin(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        slot: rules.RuinSlot,
        location: str,
        account: str,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            gate = Access(self.store)
            gate.authorize(c, viewer, "plays")
            gate.authorize(c, viewer, "world")
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            state, value, _ = self._current(c, viewer, identity)
            if state.revision != expected or value.slot is not None:
                raise WorkflowError("STALE_STATE: reopen the actual remaining Crisis choice")
            owned = active_book(self.game, c, state, book="Frantic", rule=rules.RULE)
            site = next((x for x in ruin_sites(state) if x.id == location), None)
            if (
                owned is None
                or owned[0] != value.handler
                or slot not in rules.RUIN_SLOTS
                or any(x.handler == value.handler and x.slot == slot for x in rules.records(state))
                or site is None
                or site.kind != ("city" if slot == "city" else "base")
                or not 1 <= len(account.strip()) <= 1200
                or state.world is None
                or state.strain is None
            ):
                raise WorkflowError("Choose an unused printed ruin and a suitable original site")
            if self.game.pending_actions(c):
                raise WorkflowError("Finish the pending Play before destroying this site")
            changed = state.model_copy(deep=True)
            outcome = destroy(state.world, location, gorgon_cause=False)
            changed.world = outcome.world
            event = str(uuid4())
            judge, appointment = MedicalService(self.store)._handler(c)
            loss = stage_loss(
                state,
                changed,
                source="frantic-crisis:" + identity,
                event=event,
                judge=judge,
                appointment=appointment,
                handler=value.handler,
            )
            triggers = tuple(
                Trigger(
                    id=identity + ":structure:" + x.entity,
                    kind="structure_destroyed",
                    entity=x.entity,
                    source_event=event,
                )
                for x in outcome.followups
                if x.kind == "budget_structure_destroyed"
            )
            changed.strain = state.strain.model_copy(
                update=dict(triggers=state.strain.triggers + triggers)
            )
            rules.put(
                changed,
                value.model_copy(update=dict(slot=slot, location=location, effect_event=event)),
            )
            changed.facts.append(
                dict(kind="frantic_crisis_ruin", id=identity, event=event, account=account.strip())
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.frantic_crisis_ruin",
                changed,
                event_id=event,
                crisis=identity,
                location=location,
            )
            if loss is not None:
                from girlframe.services.m3_quadrant_loss import materialize_loss

                materialize_loss(self.game, c, loss, event)
            return dict(id=identity, state="complete", location=location, revision=changed.revision)

        return self.store._write(
            viewer,
            key,
            "m3.frantic_crisis_ruin",
            dict(id=identity, expected=expected, slot=slot, location=location, account=account),
            operation,
            authorize=access,
            auto_audit=False,
        )
