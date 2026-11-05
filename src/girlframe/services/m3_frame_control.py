"""Owned actual spinal contact, factual review and real unplug; no inferred occupancy."""

from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_frame_control as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_frame_control_state import NeuralConnection
from girlframe.engine.m3_janus import find as find_core
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def _copy(target: GameState, source: GameState) -> None:
    for name in GameState.model_fields:
        setattr(target, name, getattr(source, name))


def _put(state: GameState, value: NeuralConnection) -> None:
    state.neural_connections = [value if x.id == value.id else x for x in state.neural_connections]


def _history(game: "GameService", c: Connection, event: str) -> GameState:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    if raw is None:
        raise WorkflowError("Recover the actual original neural-contact source event")
    return GameState.model_validate_json(raw)


def _event(
    game: "GameService", c: Connection, event: str, human: int, kind: str, identity: str
) -> None:
    import json

    actual = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == event,
            )
        )
        .mappings()
        .first()
    )
    if (
        actual is None
        or actual["kind"] != kind
        or actual["actor_id"] != str(human)
        or json.loads(actual["payload_json"]).get("connection_id") != identity
    ):
        raise WorkflowError(
            "Only the authenticated original human's actual source action proves contact"
        )


def prove(game: "GameService", c: Connection, state: GameState, identity: str) -> NeuralConnection:
    value = rules.connection(state, identity)
    source = rules.connection(_history(game, c, value.proposed_event), identity)
    stable = (
        "id",
        "caster",
        "caster_controller",
        "battery",
        "battery_controller",
        "frame_owner",
        "frame_instance",
        "cast",
        "judge",
        "judge_actor",
        "appointment",
        "proposed_event",
        "account",
        "access",
        "access_source",
        "port_access",
    )
    if any(getattr(value, k) != getattr(source, k) for k in stable):
        raise WorkflowError(
            "Preserve the actual original bodies, Frame and proposed contact source"
        )
    _event(
        game,
        c,
        value.proposed_event,
        value.caster_controller,
        "m3.neural_contact_proposed",
        identity,
    )
    if value.connected_event:
        accepted = rules.connection(_history(game, c, value.connected_event), identity)
        if (
            accepted.phase != "connected"
            or accepted.review_event != value.connected_event
            or accepted.connected_event != value.connected_event
            or any(getattr(accepted, k) != getattr(value, k) for k in stable)
            or accepted.target_event != value.target_event
            or accepted.port_source != value.port_source
            or value.port_access == "reviewed_port"
            and value.port_source != value.review_event
        ):
            raise WorkflowError(
                "Actual contact needs the original factual review, not a phase label"
            )
        _event(game, c, value.connected_event, value.judge, "m3.neural_contact_reviewed", identity)
        if value.access == "consensual":
            if not value.target_event:
                raise WorkflowError("The actual other original body owns optional contact consent")
            _event(
                game,
                c,
                value.target_event,
                value.battery_controller,
                "m3.neural_contact_answered",
                identity,
            )
            consent = rules.connection(_history(game, c, value.target_event), identity)
            if consent.phase != "review":
                raise WorkflowError("Use actual accepted contact, never a refusal")
    return value


def _bodies(game: "GameService", c: Connection, state: GameState, value: NeuralConnection) -> None:
    bound = profiles(c, game.store.campaign_id)
    caster = resolve(state, value.caster, bound, require_current_profile=False)
    battery = resolve(state, value.battery, bound, require_current_profile=False)
    if (
        not caster.alive
        or not battery.alive
        or caster.controller != value.caster_controller
        or battery.controller != value.battery_controller
    ):
        raise WorkflowError(
            "No successor or controller account substitutes for these actual original bodies"
        )
    if caster.offstage_source or battery.offstage_source:
        raise WorkflowError("Recover actual physical reach before a spinal connection")
    if caster.cell is not None and battery.cell is not None and caster.cell != battery.cell:
        raise WorkflowError("Actual separated bodies have no proved spinal reach")
    core = find_core(state, value.battery)
    if core is not None:
        from girlframe.services.m3_janus import prove_core

        prove_core(c, game, state, value.battery)
        # Combat exposure is separate from the spinal jack inside the real cockpit.
        # Unknown access stays a proposed fact until the actual source judge reviews it.
    if value.access == "source_force":
        condition = next(
            (
                x
                for x in state.helpless_conditions
                if x.active
                and x.subject == value.battery
                and x.foe == value.caster
                and value.access_source in x.source_events
            ),
            None,
        )
        if condition is None:
            raise WorkflowError("Recover the actual original opposing-person force source")


def prepare_battery(
    game: "GameService",
    c: Connection,
    state: GameState,
    caster: ActorRef,
    battery: ActorRef,
    channel: int,
    *,
    identity: str | None = None,
) -> dict[str, Any]:
    from girlframe.services.m3_actor_plays import ActorPlayService

    values = [
        x
        for x in state.neural_connections
        if x.phase == "connected"
        and x.caster == caster
        and x.battery == battery
        and (identity is None or x.id == identity)
    ]
    if len(values) != 1:
        raise WorkflowError("Establish and review this actual original spinal contact first")
    value = prove(game, c, state, values[0].id)
    _bodies(game, c, state, value)
    cast, _ = ActorPlayService(game).actors(c, state, channel)
    if cast.channel != value.cast.channel or fingerprint(cast) != fingerprint(value.cast):
        raise WorkflowError("Recover this original neural source's actual cast before rolling")
    return dict(
        connection=value.id,
        caster_frame_owner=value.frame_owner.model_dump(mode="json"),
        caster_frame=value.frame_instance,
        source_event=value.connected_event,
    )


def synchronize_endings(game: "GameService", c: Connection, event: str) -> None:
    from girlframe.services.m3_harpy_defeat import ended_actor_source

    state = _history(game, c, event)
    for value in state.neural_connections:
        if value.phase != "ended" or value.ended_event != event:
            continue
        prove(game, c, state, value.id)
        if value.ended_by is None or ended_actor_source(game, c, state, value.ended_by) != event:
            raise WorkflowError(
                "Only the actual original ending can interrupt this source connection"
            )
        from girlframe.services.m3_janus_play import complete_ended_link

        for link in state.battery_links:
            if link.connection == value.id and link.phase == "ended" and link.end_event == event:
                complete_ended_link(game, c, link, event)


def synchronize_birth_controls(game: "GameService", c: Connection, event: str) -> GameState:
    import json

    from girlframe.services.m3_harpy_defeat import HarpyDefeatService

    proof = _history(game, c, event)
    state = load_state(c, game.store.campaign_id)
    recovered = []
    for born in proof.harpy_states:
        if born.source_event != event or not born.linked:
            continue
        actor = ActorRef(kind="external_pilot", entity=born.id)
        address = rules.frame_address(proof, actor, born.frame_instance)
        matching = [
            x
            for x in state.frame_commands
            if not x.active
            and x.frame_owner == address[0]
            and x.frame_instance == address[1]
            and x.ended_event == event
            and x.recovered_event is None
        ]
        if (
            not matching
            or address[0] == actor
            or rules.active_takeover(state, actor, born.frame_instance) is not None
        ):
            continue
        for command in matching:
            actual_wire = prove(game, c, proof, command.connection)
            source_link = next(
                (x for x in proof.battery_links if x.id == command.battery_link), None
            )
            if (
                actual_wire.phase != "ended"
                or actual_wire.ended_event != event
                or actual_wire.ended_by != born.origin
                or actual_wire.caster != born.origin
                or actual_wire.frame_owner != address[0]
                or actual_wire.frame_instance != address[1]
                or source_link is None
                or source_link.connection != actual_wire.id
                or source_link.phase != "ended"
                or source_link.end_event != event
                or source_link.battery != command.actor
            ):
                raise WorkflowError("A birth label cannot restore an unrelated old control source")
        HarpyDefeatService(game.store, game)._runtime(c, state, actor)
        birth = next(
            x
            for x in proof.void_thresholds
            if x.resulting_actor == actor and x.response_event == event and x.stage == "converted"
        )
        audit = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
                )
            )
            .mappings()
            .first()
        )
        payload = json.loads(audit["payload_json"]) if audit else {}
        if (
            audit is None
            or audit["kind"] != "m3.void_response"
            or audit["actor_id"] != str(born.controller)
            or payload.get("operation") != "rebirth"
            or payload.get("threshold") != birth.id
        ):
            raise WorkflowError(
                "Prove the original owner's actual performed rebirth before new brain control"
            )
        state = rules.recover_control(state, actor, born.frame_instance, event)
        recovered.append(actor.model_dump(mode="json"))
    if recovered:
        audit = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
                )
            )
            .mappings()
            .one()
        )
        prior = c.scalar(
            sa.select(sa.func.max(t.events.c.event_index)).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.command_key == audit["command_key"],
            )
        )
        game.event(
            c,
            audit["actor_id"],
            audit["command_key"],
            "m3.frame_birth_control_recorded",
            state,
            event_index=1 if prior is None else prior + 1,
            birth_event=event,
            actors=recovered,
        )
    return state


def expire_returned_assets(state: GameState, actor: ActorRef, event: str) -> GameState:
    from girlframe.engine.m3_janus_link import expire_link_assets

    for link in state.battery_links:
        if link.caster == actor and link.phase in ("unplugged", "ended"):
            state = expire_link_assets(state, link, event)
    return state


class FrameControlService:
    def __init__(self, game: "GameService"):
        self.game, self.store = game, game.store

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        Access(self.store).authorize(c, viewer, "plays", director_response=True)

    def _can_act(self, c: Connection, viewer: GuildViewer) -> bool:
        try:
            self._access(c, viewer)
            self.game.unpaused(c)
        except WorkflowError:
            return False
        return True

    def control(self, viewer: GuildViewer, actor: ActorRef) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            actual = resolve(
                state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if (
                actual.controller != viewer.user_id
                or not actual.alive
                or actual.frame_instance is None
            ):
                raise WorkflowError("Choose your actual original body and Frame")
            core = find_core(state, actor)
            owner = core.frame_owner if core else actor
            current = rules.controller(
                state, owner, actual.frame_instance, profiles(c, self.store.campaign_id)
            )
            takeover = rules.active_takeover(state, owner, actual.frame_instance)
            return dict(
                actor=actor.model_dump(mode="json"),
                revision=state.revision,
                frame=actual.frame_instance,
                controller=current.model_dump(mode="json") if current else None,
                label="Your original body"
                if current == actor
                else "Another original body"
                if current
                else "No current controller",
                can_relink=core is None
                and takeover is None
                and current != actor
                and self._can_act(c, viewer),
            )

    def _write(
        self, viewer: GuildViewer, key: str, kind: str, payload: dict[str, Any], operation: Any
    ) -> dict[str, Any]:
        try:
            return self.store._write(
                viewer,
                key,
                kind,
                payload,
                operation,
                auto_audit=False,
                authorize=lambda c: self._access(c, viewer),
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def propose(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        caster: ActorRef,
        battery: ActorRef,
        account: str,
        *,
        force_source: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_actor_plays import ActorPlayService
            from girlframe.services.m3_medical import MedicalService

            self.game.unpaused(c)
            if self.game.pending_actions(c):
                raise WorkflowError(
                    "Finish and restore the pending Play before a new ordinary neural contact"
                )
            state = load_state(c, self.store.campaign_id)
            cast, actors = ActorPlayService(self.game).actors(c, state, channel)
            actual = next(
                (x for x in actors if x.ref == caster and x.controller == viewer.user_id), None
            )
            target = resolve(
                state, battery, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if (
                actual is None
                or caster == battery
                or not actual.alive
                or not target.alive
                or not actual.frame_instance
                or actual.rules not in ("girl_frame", "external_pilot")
            ):
                raise WorkflowError(
                    "Use the actual original caster, distinct battery and real assigned Frame"
                )
            if not account.strip() or len(account) > 1200:
                raise WorkflowError(
                    "Describe the actual jack, exposure, reach and performed spinal contact"
                )
            if any(
                x.phase in ("target", "review", "connected") and caster in (x.caster, x.battery)
                for x in state.neural_connections
            ):
                raise WorkflowError(
                    "Resolve this original body's existing actual neural connection"
                )
            judge = ActorPlayService(self.game)._judge(c, state, cast, caster)
            _, appointment = MedicalService(self.store)._handler(c)
            core = find_core(state, battery)
            caster_core = find_core(state, caster)
            frame_owner = (
                caster_core.frame_owner
                if caster_core is not None
                else rules.frame_address(state, caster, actual.frame_instance)[0]
            )
            from girlframe.engine.m3_janus import has_tag

            access: Literal["core_port", "consensual", "source_force"] = (
                "core_port"
                if core is not None and has_tag(core, "restrained")
                else "source_force"
                if force_source
                else "consensual"
            )
            event, identity = str(uuid4()), str(uuid4())
            source = core.source_event if core is not None else force_source or event
            port_access: Literal["exposed_spine", "own_cockpit", "reviewed_port"] = "reviewed_port"
            port_source = event
            if (
                core is not None
                and actual.inside_frame is True
                and actual.frame_instance == core.frame_instance
                and actual.occupied_frame_instance in (None, core.frame_instance)
            ):
                port_access = "own_cockpit"
                placement = next((x for x in state.placements if x.actor == caster), None)
                port_source = placement.source_event if placement else core.state_event
            elif core is not None and core.exposed:
                port_access = "exposed_spine"
                port_source = core.state_event
            value = NeuralConnection(
                id=identity,
                caster=caster,
                caster_controller=viewer.user_id,
                battery=battery,
                battery_controller=target.controller,
                frame_owner=frame_owner,
                frame_instance=actual.frame_instance,
                cast=cast,
                judge=judge.controller,
                judge_actor=judge.ref,
                appointment=appointment,
                proposed_event=event,
                account=account.strip(),
                access=access,
                access_source=source,
                port_access=port_access,
                port_source=port_source,
                phase="review" if access != "consensual" else "target",
            )
            _bodies(self.game, c, state, value)
            state.neural_connections.append(value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.neural_contact_proposed",
                state,
                event_id=event,
                connection_id=identity,
            )
            return dict(id=identity, phase=value.phase)

        return self._write(
            viewer,
            key,
            "m3.neural_contact_proposed",
            dict(
                channel=channel,
                caster=caster.model_dump(mode="json"),
                battery=battery.model_dump(mode="json"),
                account=account,
                force_source=force_source,
            ),
            operation,
        )

    def decide(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        allowed: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_actor_plays import ActorPlayService
            from girlframe.services.m3_medical import MedicalService

            self.game.unpaused(c)
            if self.game.pending_actions(c):
                raise WorkflowError(
                    "Finish the actual pending Play before changing ordinary contact"
                )
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            if (
                state.revision != revision
                or not account.strip()
                or len(account) > 1200
                or type(allowed) is not bool
            ):
                raise WorkflowError("Reopen the actual current owned contact decision")
            expected = value.battery_controller if value.phase == "target" else value.judge
            if value.phase not in ("target", "review") or viewer.user_id != expected:
                raise WorkflowError(
                    "Only the actual other body or frozen source judge owns this question"
                )
            _bodies(self.game, c, state, value)
            cast, _ = ActorPlayService(self.game).actors(c, state, value.cast.channel)
            if (
                fingerprint(cast) != fingerprint(value.cast)
                or MedicalService(self.store)._handler(c)[1] != value.appointment
            ):
                raise WorkflowError("Recover the original source cast and procedural appointment")
            event = str(uuid4())
            if value.phase == "target":
                changed = value.model_copy(
                    update=dict(phase="review" if allowed else "refused", target_event=event)
                )
                kind = "m3.neural_contact_answered"
            else:
                changed = value.model_copy(
                    update=dict(
                        phase="connected" if allowed else "refused",
                        review_event=event,
                        review=account.strip(),
                        connected_event=event if allowed else None,
                        port_source=event
                        if allowed and value.port_access == "reviewed_port"
                        else value.port_source,
                    )
                )
                kind = "m3.neural_contact_reviewed"
            _put(state, changed)
            self.game.event(
                c,
                viewer.user_id,
                key,
                kind,
                state,
                event_id=event,
                connection_id=identity,
                allowed=allowed,
                account=account.strip(),
            )
            return dict(id=identity, phase=changed.phase)

        return self._write(
            viewer,
            key,
            "m3.neural_contact_decided",
            dict(id=identity, revision=revision, allowed=allowed, account=account),
            operation,
        )

    def unplug(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            if self.game.pending_actions(c):
                raise WorkflowError("Resolve the actual immediate Play before ordinary unplugging")
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            actor = (
                value.caster
                if viewer.user_id == value.caster_controller
                else value.battery
                if viewer.user_id == value.battery_controller
                else None
            )
            if actor is None or state.revision != revision:
                raise WorkflowError(
                    "Only an actual original participant performs this current unplug"
                )
            _bodies(self.game, c, state, value)
            if value.access == "core_port" and actor == value.battery:
                from girlframe.engine.m3_janus import has_tag

                core = find_core(state, actor)
                if core is not None and has_tag(core, "restrained"):
                    raise WorkflowError(
                        "The actual restrained Core cannot perform a voluntary physical unplug"
                    )
            event = str(uuid4())
            state = rules.unplug(state, identity, actor, event, account)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.neural_unplugged",
                state,
                event_id=event,
                connection_id=identity,
                original_actor=actor.model_dump(mode="json"),
            )
            return dict(id=identity, phase="unplugged")

        return self._write(
            viewer,
            key,
            "m3.neural_unplugged",
            dict(id=identity, revision=revision, account=account),
            operation,
        )

    def relink(
        self, viewer: GuildViewer, key: str, actor: ActorRef, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.engine import m3_physical
            from girlframe.engine.m3_harpy_defeat import harpy, update

            self.game.unpaused(c)
            if self.game.pending_actions(c) or self.game.immediate_work(c, viewer.user_id):
                raise WorkflowError(
                    "Resolve the actual pending source work before ordinary relinking"
                )
            state = load_state(c, self.store.campaign_id)
            actual = resolve(
                state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if (
                state.revision != revision
                or actual.controller != viewer.user_id
                or not actual.alive
                or not actual.frame_instance
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError("Reopen this original body's actual current neural control")
            if rules.active_takeover(state, actor, actual.frame_instance) is not None:
                raise WorkflowError("An ordinary relink cannot overwrite actual source takeover")
            event = str(uuid4())
            if actor.kind == "pilot":
                state = m3_physical.cockpit_enter(
                    state, profiles(c, self.store.campaign_id), actor, event, account, pilot=True
                )
            elif (
                actor.kind == "external_pilot"
                and actual.girl == "harpy"
                and find_core(state, actor) is None
            ):
                body = harpy(state, actor)
                if (
                    body.body_incapacitated
                    or body.frame_shutdown
                    or body.custody != "free"
                    or actual.offstage_source
                ):
                    raise WorkflowError(
                        "The original body and Frame must actually be able to relink"
                    )
                if not body.linked:
                    if (
                        body.subsumed
                        or not body.vitals_active
                        or body.cell is None
                        or body.frame_cell is None
                        or body.cell != body.frame_cell
                        or m3_physical.cockpit_lock(state, actor, body.frame_instance) is not None
                    ):
                        raise WorkflowError(
                            "Prove actual reach and cockpit permission before physically relinking"
                        )
                if not any(x.family == "frame" and not x.damaged for x in actual.assets):
                    raise WorkflowError("An unavailable Frame cannot resume actual piloting")
                state = update(state, actor, linked=True, physical_source_event=event)
                state = rules.recover_control(state, actor, body.frame_instance, event)
                state.facts.append(
                    dict(
                        kind="frame_neural_relinked",
                        actor=actor.model_dump_json(),
                        frame=body.frame_instance,
                        event=event,
                        account=account.strip(),
                    )
                )
            else:
                raise WorkflowError(
                    "Only the original Pilot or Harpy can resume ordinary owned Frame control"
                )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.frame_neural_relinked",
                state,
                event_id=event,
                original_actor=actor.model_dump(mode="json"),
            )
            return dict(actor=actor.model_dump(mode="json"), state="relinked")

        return self._write(
            viewer,
            key,
            "m3.frame_neural_relinked",
            dict(actor=actor.model_dump(mode="json"), revision=revision, account=account),
            operation,
        )

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = prove(self.game, c, state, identity)
            if viewer.user_id not in (
                value.caster_controller,
                value.battery_controller,
                value.judge,
            ):
                raise WorkflowError("The actual spinal source is private to its original people")
            expected = (
                value.battery_controller
                if value.phase == "target"
                else value.judge
                if value.phase == "review"
                else None
            )
            core = find_core(state, value.battery)
            from girlframe.engine.m3_janus import has_tag

            can_unplug = (
                value.phase == "connected"
                and viewer.user_id in (value.caster_controller, value.battery_controller)
                and not (
                    viewer.user_id != value.caster_controller
                    and core is not None
                    and has_tag(core, "restrained")
                )
                and self._can_act(c, viewer)
            )
            return dict(
                id=identity,
                revision=state.revision,
                connection=value.model_dump(mode="json"),
                can_act=viewer.user_id == expected and self._can_act(c, viewer),
                can_unplug=can_unplug,
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        result = []
        for value in state.neural_connections:
            if value.phase not in ("target", "review", "connected") or viewer.user_id not in (
                value.caster_controller,
                value.battery_controller,
                value.judge,
            ):
                continue
            prove(self.game, c, state, value.id)
            expected = (
                value.battery_controller
                if value.phase == "target"
                else value.judge
                if value.phase == "review"
                else None
            )
            result.append(
                dict(
                    id=value.id,
                    phase=value.phase,
                    can_act=viewer.user_id == expected and self._can_act(c, viewer),
                    label="Actual spinal contact: " + value.phase,
                )
            )
        return result
