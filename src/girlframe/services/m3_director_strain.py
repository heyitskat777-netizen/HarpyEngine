"""Let the original fictional Director exercise independently scoped Strain powers."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_custom_strain as custom
from girlframe.engine import m3_director_strain as rules
from girlframe.engine import m3_named_strain as named
from girlframe.engine import m3_void_rift as rift_rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_civic_directive import director
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_strain import PAGES, effective_levels, set_level
from girlframe.engine.m3_strain_state import Request
from girlframe.services.m2_state import load_state
from girlframe.services.m3_battle import _cast, _visible
from girlframe.services.m3_custom_strain import CustomStrainService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

EVENT = "m3.fictional_director_strain_call"


def _proof(c: Connection, strain: StrainService, identity: str, controller: int) -> GameState:
    history = t.m2["m2_state_history"]
    born = c.scalar(
        sa.select(history.c.body_json)
        .join(
            t.events,
            (t.events.c.campaign_id == history.c.campaign_id)
            & (t.events.c.id == history.c.event_id),
        )
        .where(
            history.c.campaign_id == strain.store.campaign_id,
            history.c.event_id == identity,
            t.events.c.kind == EVENT,
            t.events.c.actor_id == str(controller),
        )
    )
    if born is None:
        raise WorkflowError("Recover the actual original signed phone call")
    return GameState.model_validate_json(born)


def prove_trigger(
    c: Connection, strain: StrainService, state: GameState, row: dict[str, Any]
) -> None:
    body = json.loads(row["body_json"])
    call = next((x for x in rules.calls(state) if x.id == body.get("director_call")), None)
    if (
        call is None
        or call.command.mode != "trigger"
        or call.command.target_rule != body.get("rule_id")
        or call.effect != row["id"]
        or call.period != row["off_duty_id"]
        or not same_handler_body(state, call.handler)
        or call not in rules.calls(_proof(c, strain, call.id, call.controller))
    ):
        raise WorkflowError("Recover the original fictional Director call and its named effect")


def prove_replacement(c: Connection, strain: StrainService, value: custom.Replacement) -> None:
    registry = strain.missions.access.registry
    assert registry is not None
    registry.require_available(rules.RULE)
    birth = _proof(c, strain, value.id, value.controller)
    call = next((x for x in rules.calls(birth) if x.id == value.id), None)
    if (
        call is None
        or call.sender != value.actor
        or call.command.mode != "replace"
        or call.command.slot != value.slot
        or call.command.design != value.design
        or value not in custom.replacements(birth)
    ):
        raise WorkflowError("Recover the actual Director-authored replacement for this slot")


class DirectorStrainService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def _authorize(
        self, c: Connection, viewer: GuildViewer, channel: int, sender: ActorRef
    ) -> tuple[GameState, SceneCast]:
        access = self.strain.missions.access
        access.authorize(c, viewer, "world", director_response=True)
        access.authorize(c, viewer, "strain", director_response=True)
        assert access.registry is not None
        try:
            access.registry.require_available(rules.RULE)
            state = load_state(c, self.store.campaign_id)
            body = director(state, sender.entity if sender.kind == "npc" else None)
        except ValueError as error:
            raise WorkflowError(str(error)) from None
        cast = _cast(self.game, c, state, channel)
        if (
            body.controller != viewer.user_id
            or state.handler != self.strain.missions._current_handler(c)
            or not any(x.actor == sender and x.controller == viewer.user_id for x in cast.roles)
        ):
            raise WorkflowError("Only the original joined fictional Director controls this call")
        return state, cast

    def _preparing(self, c: Connection, state: GameState) -> str | None:
        work = t.m3["m3_off_duty"]
        value = c.scalar(
            sa.select(work.c.id).where(
                work.c.campaign_id == self.store.campaign_id, work.c.phase == "preparing"
            )
        )
        return (
            str(value)
            if value is not None and state.strain and value in state.strain.periods
            else None
        )

    def view(self, viewer: GuildViewer, channel: int, sender: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state, _ = self._authorize(c, viewer, channel, sender)
            if state.strain is None or active_handler(state) is None:
                raise WorkflowError("Initialize the Strain tracks and original Handler")
            return dict(
                revision=state.revision,
                levels=effective_levels(state.strain),
                period=self._preparing(c, state),
                targets=self._targets(state, viewer),
            )

    @staticmethod
    def _targets(state: GameState, viewer: GuildViewer) -> tuple[tuple[str, str], ...]:
        return tuple(
            (identity, label)
            for identity, label in CustomStrainService._targets(state)
            if _visible(state, ActorRef(kind="npc", entity=identity), viewer.user_id)
        )

    def receipt(self, viewer: GuildViewer, identity: str) -> rules.Call:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            call = next((x for x in rules.calls(state) if x.id == identity), None)
            if call is None or viewer.user_id not in (call.controller, int(call.handler.entity)):
                raise WorkflowError("This call belongs to its original participants")
            return call

    def call(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        expected: int,
        sender: ActorRef,
        command: rules.Command,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self._authorize(c, viewer, channel, sender)
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            state = self.strain._state(c, expected)
            _, cast = self._authorize(c, viewer, channel, sender)
            handler = active_handler(state)
            lock = self.game.lock(c, channel)
            if handler is None or state.strain is None or lock and lock["state"] != "released":
                raise WorkflowError("Recover the actual open source scene and original Handler")
            event = str(uuid4())
            changed: tuple[Request, ...] = ()
            period, effect, root = None, None, None
            rolled = None
            arrivals: tuple[tuple[str, rift_rules.Arrival], ...] = ()
            if command.mode == "severity":
                assert command.track is not None and command.severity is not None
                state.strain, changed = set_level(state.strain, command.track, command.severity)
            elif command.mode in ("replace", "create_track"):
                registry = self.strain.missions.access.registry
                assert registry is not None
                registry.require_available(custom.RULE)
                design = command.design or command.new_track
                assert design is not None
                if design.npc not in dict(self._targets(state, viewer)):
                    raise WorkflowError("Only a known eligible NPC can be the custom event target")
                period = self._preparing(c, state)
                if command.mode == "replace":
                    assert command.slot is not None and command.design is not None
                    custom.register(
                        state,
                        custom.Replacement(
                            id=event,
                            slot=command.slot,
                            actor=sender,
                            controller=viewer.user_id,
                            period=period,
                            roll=None,
                            target_controller=int(handler.entity),
                            design=command.design,
                        ),
                    )
                else:
                    assert command.new_track is not None
                    if period is None and any(
                        len(x.arrivals) <= x.duration for x in rift_rules.rifts(state)
                    ):
                        raise WorkflowError(
                            "A live sky rift needs an actual preparation for its arrival"
                        )
                    named.register(
                        state,
                        named.Table(
                            id=event,
                            director=sender,
                            controller=viewer.user_id,
                            target_controller=int(handler.entity),
                            design=command.new_track,
                            account=command.account.strip(),
                        ),
                    )
                    effect = event + ":die"
                    rolled = named.SavedRoll(
                        id=effect,
                        period_id=period,
                        track=event,
                        handler=handler,
                        source=event,
                        rng_source=self.strain.rng_source,
                        face=self.strain.dice.roll_d6(),
                    )
                    named.save_roll(state, rolled)
                    root = (
                        self.strain._row(c, period + ":off_duty_strain_start:" + handler.entity)
                        if period
                        else dict(campaign_id=self.store.campaign_id, campaign_context=True)
                    )
                    if period:
                        arrivals = rift_rules.upcoming(state, effect, period, event)
            else:
                period = self._preparing(c, state)
                if period is None or command.target_rule not in rules.DIRECT_EVENTS:
                    raise WorkflowError(
                        "Choose a supported actual source event in a preparing period"
                    )
                root = self.strain._row(c, period + ":off_duty_strain_start:" + handler.entity)
                if root["owner_id"] != handler.entity or root["state"] != "pending":
                    raise WorkflowError("Recover the original Handler's active Strain preparation")
                effect = event + ":effect"
            rules.save(
                state,
                rules.Call(
                    id=event,
                    sender=sender,
                    controller=viewer.user_id,
                    handler=handler,
                    scene=cast.id,
                    channel=channel,
                    command=command,
                    period=period,
                    effect=effect,
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                EVENT,
                state,
                event_id=event,
                scene_id=cast.id,
                mode=command.mode,
                effect=effect,
            )
            self.strain.save_unrolled_levels(c, changed, event)
            if rolled is not None and root is not None:
                owner = int(handler.entity)
                related(
                    c,
                    self.store,
                    root,
                    rolled.id,
                    owner,
                    owner,
                    "named_strain_roll",
                    dict(
                        track=rolled.track, stage="column", face=rolled.face, source_pdf=rules.PAGE
                    ),
                    event,
                )
                self.strain._rift_work(c, root, owner, arrivals, event)
            elif effect is not None and root is not None:
                assert command.track is not None and command.severity is not None
                related(
                    c,
                    self.store,
                    root,
                    effect,
                    int(handler.entity),
                    int(handler.entity),
                    "strain_event",
                    dict(
                        rule_id=command.target_rule,
                        source_pdf=PAGES[(command.track, command.severity)],
                        source_work=event,
                        director_call=event,
                    ),
                    event,
                )
            result = dict(id=event, effect=effect, revision=state.revision)
            if rolled is not None:
                result["face"] = rolled.face
            return result

        return self.strain.missions._write(
            viewer,
            key,
            EVENT,
            dict(
                channel=channel,
                expected=expected,
                sender=sender.model_dump(mode="json"),
                command=command.model_dump(mode="json"),
            ),
            operation,
            authorize,
            director_response=True,
        )
