"""Private Handler authorization for actual authored Strain effects."""

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_custom_strain as custom
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_promotional_opportunity import in_responsibility
from girlframe.engine.m3_strain import copy
from girlframe.engine.m3_strain_state import Track
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

EVENT = "m3.custom_strain_authored"

if TYPE_CHECKING:
    from girlframe.services.m3_strain import StrainService


def _source(
    c: Connection, strain: "StrainService", event: str, controller: int
) -> tuple[GameState, dict[str, Any]]:
    history = t.m2["m2_state_history"]
    source = c.execute(
        sa.select(history.c.body_json, t.events.c.payload_json)
        .join(
            t.events,
            (t.events.c.campaign_id == history.c.campaign_id)
            & (t.events.c.id == history.c.event_id),
        )
        .where(
            history.c.campaign_id == strain.store.campaign_id,
            history.c.event_id == event,
            t.events.c.kind == EVENT,
            t.events.c.actor_id == str(controller),
        )
    ).first()
    if source is None:
        raise WorkflowError("Recover the actual authored Strain source")
    return GameState.model_validate_json(source.body_json), json.loads(source.payload_json)


def prove_slot(c: Connection, strain: "StrainService", value: custom.Replacement) -> None:
    registry = strain.missions.access.registry
    if registry is None:
        raise WorkflowError("Recover the actual custom Strain rules registry")
    registry.require_available(custom.RULE)
    if value.actor.kind == "npc":
        from girlframe.services.m3_director_strain import prove_replacement

        prove_replacement(c, strain, value)
        return
    original, audit = _source(c, strain, value.id, value.controller)
    if value not in custom.replacements(original):
        raise WorkflowError("Recover the original saved amendment to this Strain slot")
    if audit.get("mode") != "replace_slot" or audit.get("source_work") != value.roll:
        raise WorkflowError("Recover the original rolled slot and its actual replacement source")


def completed_replacements(
    c: Connection, strain: "StrainService", state: GameState, period: str
) -> tuple[custom.Occurrence, ...]:
    verified = []
    for value in custom.occurrences(state):
        if (
            value.mode != "instead_of_roll"
            or value.period != period
            or value.source_work != period + ":strain:" + str(value.track)
        ):
            continue
        source, audit = _source(c, strain, value.id, value.controller)
        assert value.source_work is not None
        row = strain._row(c, value.source_work)
        if (
            value not in custom.occurrences(source)
            or audit.get("mode") != value.mode
            or audit.get("source_work") != value.source_work
            or row["state"] != "resolved"
            or row["event_id"] != value.id
            or json.loads(row["body_json"]).get("custom_event") != value.id
            or not source.world
            or not any(
                x.id == value.design.npc and any(tag.id == value.id for tag in x.tags)
                for x in source.world.npcs
            )
        ):
            raise WorkflowError("Recover the completed custom effect replacing the actual die")
        verified.append(value)
    return tuple(verified)


class CustomStrainService:
    def __init__(self, strain: "StrainService"):
        self.strain = strain
        self.game, self.store = strain.game, strain.store

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        self.strain._authorize(c, viewer)
        self.strain.missions.access.authorize(c, viewer, "world")
        registry = self.strain.missions.access.registry
        if registry is None:
            raise WorkflowError("Recover the actual custom Strain rules registry")
        try:
            registry.require_available(custom.RULE)
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _period(self, c: Connection, viewer: GuildViewer, state: GameState, period: str) -> None:
        current = self.strain.periods._get(c, period)
        if (
            current.phase != "preparing"
            or current.handler != viewer.user_id
            or state.strain is None
            or period not in state.strain.periods
        ):
            raise WorkflowError("Prepare the actual Off-Duty Strain tables before authoring events")

    @staticmethod
    def _targets(state: GameState) -> tuple[tuple[str, str], ...]:
        return (
            tuple(
                (x.id, x.name)
                for x in state.world.npcs
                if x.alive
                and x.controller == state.handler
                and "director" not in x.jobs
                and x.cell is not None
                and in_responsibility(state, x.cell)
            )
            if state.world
            else ()
        )

    def view(self, viewer: GuildViewer, period: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            self._period(c, viewer, state, period)
            assert state.strain is not None
            return dict(
                revision=state.revision,
                targets=self._targets(state),
                rolled=tuple(
                    (x.id, f"{x.severity.title()} {x.track.title()} · {x.face}")
                    for x in state.strain.events
                    if x.period_id == period or x.column is not None
                ),
                pending=tuple(
                    (x.id, f"{x.severity.title()} {x.track.title()}")
                    for x in state.strain.requests
                    if x.period_id == period and x.kind == "roll" and x.severity
                ),
            )

    def author(
        self,
        viewer: GuildViewer,
        key: str,
        period: str,
        expected: int,
        mode: custom.Mode,
        design: custom.Design,
        *,
        work: str | None = None,
        column: int | None = None,
        track: Track | None = None,
    ) -> dict[str, Any]:
        if not (
            (mode == "additional" and work is None and column is None)
            or (mode == "instead_of_roll" and work and column is None and track is None)
            or (
                mode == "replace_slot"
                and work
                and type(column) is int
                and column in (1, 2)
                and track is None
            )
        ):
            raise WorkflowError("Choose the exact place for this custom Strain event")

        def authorize(c: Connection) -> None:
            self._access(c, viewer)
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            state = self.strain._state(c, expected)
            self._period(c, viewer, state, period)
            assert state.strain is not None
            handler = active_handler(state)
            if handler is None or design.npc not in dict(self._targets(state)):
                raise WorkflowError("Choose the actual local NPC under the original Handler")
            event, row = str(uuid4()), None
            if mode == "replace_slot":
                assert column is not None
                rolled = next((x for x in state.strain.events if x.id == work), None)
                if rolled is None:
                    raise WorkflowError("Choose the exact face from an actual saved Strain die")
                custom.register(
                    state,
                    custom.Replacement(
                        id=event,
                        slot=custom.Slot(
                            track=rolled.track,
                            severity=rolled.severity,
                            face=rolled.face,
                            column=1 if column == 1 else 2,
                        ),
                        actor=handler,
                        controller=viewer.user_id,
                        period=period,
                        roll=rolled.id,
                        target_controller=viewer.user_id,
                        design=design,
                    ),
                )
            else:
                actual_track = track
                if mode == "instead_of_roll":
                    assert work is not None
                    row = self.strain._row(c, work)
                    self.strain._check(c, viewer, row, row["revision"])
                    pending = next((x for x in state.strain.requests if x.id == work), None)
                    if pending is None or pending.kind != "roll" or pending.period_id != period:
                        raise WorkflowError(
                            "A saved die or an Endgame cannot be replaced before rolling"
                        )
                    actual_track = pending.track
                    state.strain = copy(
                        state.strain,
                        requests=tuple(x for x in state.strain.requests if x != pending),
                    )
                custom.apply(
                    state,
                    custom.Occurrence(
                        id=event,
                        mode=mode,
                        actor=handler,
                        controller=viewer.user_id,
                        period=period,
                        track=actual_track,
                        source_work=work,
                        target_controller=viewer.user_id,
                        design=design,
                    ),
                )
            self.game.event(
                c,
                viewer.user_id,
                key,
                EVENT,
                state,
                event_id=event,
                period_id=period,
                mode=mode,
                source_work=work,
            )
            if row is not None:
                self.strain._save(
                    c,
                    row,
                    event,
                    json.loads(row["body_json"]) | {"custom_event": event},
                    resolved=True,
                )
            return dict(id=event, state="registered" if mode == "replace_slot" else "resolved")

        return self.strain.missions._write(
            viewer,
            key,
            EVENT,
            dict(
                period=period,
                expected=expected,
                mode=mode,
                design=design.model_dump(mode="json"),
                work=work,
                column=column,
                track=track,
            ),
            operation,
            authorize,
        )
