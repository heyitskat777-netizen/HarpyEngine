"""Human-authored travel attempts, real movement, and explicitly disclosed evidence."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine import m3_vatgrown_travel as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access, digest
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_movement import MovementService, proposal_context
from girlframe.services.m3_vatgrown_plays import (
    VatgrownPlaysService,
    _vatgrown,
    prove_violation,
)
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _get[T: Model](state: GameState, model: type[T], identity: str) -> T:
    try:
        return rules.get(state, model, identity)
    except ValueError as error:
        raise WorkflowError(str(error)) from None


def _native(state: GameState, actor: ActorRef) -> bool:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    return bool(
        sheet
        and sheet.character_id == actor.incarnation
        and sheet.girl == "VATGROWN"
        and has_rule(sheet, rules.RULE, "VATGROWN")
    )


def _enabled(game: GameService) -> bool:
    approval = game.store.policy.m3_approval
    if approval is None or "plays" not in approval.subsystems:
        return False
    gate = Access(game.store)
    registry = gate.registry
    if (
        registry is None
        or approval.registry_sha256 != digest(registry)
        or game.store.policy.owner_m3_rulings is None
    ):
        return False
    try:
        registry.require_available(rules.RULE)
    except ValueError:
        return False
    return True


def _event(game: GameService, c: Connection, identity: str) -> Any:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == identity
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise WorkflowError("Recover the actual canonical travel event")
    return row


def _before(game: GameService, c: Connection, identity: str) -> GameState:
    row = _event(game, c, identity)
    history = t.m2["m2_state_history"]
    raw = c.scalar(
        sa.select(history.c.body_json)
        .join(t.events, history.c.event_id == t.events.c.id)
        .where(
            history.c.campaign_id == game.store.campaign_id,
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.seq < row["seq"],
        )
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    if raw is None:
        raise WorkflowError("Recover the original physical proposal's prior state")
    return GameState.model_validate_json(raw)


def _pose(state: GameState, proposal: rules.Proposal, destination: bool = False) -> None:
    pose = next((value for value in state.placements if value.actor == proposal.actor), None)
    cell = proposal.destination if destination else proposal.origin
    if (
        pose is None
        or pose.vessel_id != proposal.vessel_id
        or pose.frame_instance != proposal.frame_instance
        or pose.mode != proposal.mode
        or pose.girl_cell != cell
        or proposal.frame
        and pose.frame_cell != cell
    ):
        raise WorkflowError("Preserve the actual original free body, Frame and physical endpoints")


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Attempt:
    value = _get(state, rules.Attempt, identity)
    event = _event(game, c, value.event)
    born = _history(c, game, value.event)
    before = _before(game, c, value.event)
    if (
        event["kind"] != "m3.vatgrown_travel_attempted"
        or event["actor_id"] != str(value.proposal.controller)
        or json.loads(event["payload_json"]).get("id") != value.id
        or _get(born, rules.Attempt, identity) != value
        or value.proposal.actor.kind != "pilot"
        or value.proposal.controller != int(value.proposal.actor.entity)
        or not _native(before, value.proposal.actor)
        or value.proposal.revision != before.revision
        or not value.proposal.account.strip()
        or rules.bases(before, value.proposal.origin) != value.origin_bases
        or rules.bases(before, value.proposal.destination) != value.destination_bases
        or not rules.outside(before, value.proposal)
    ):
        raise WorkflowError("Recover the genuine original unchaperoned physical attempt")
    _pose(before, value.proposal)
    _pose(born, value.proposal)
    return value


def prove_violation_source(
    game: GameService, c: Connection, state: GameState, value: vat.Violation
) -> rules.Attempt:
    source = prove(game, c, state, value.source)
    if (
        value.id != source.violation
        or value.kind != "unchaperoned_attempt"
        or value.actor != source.proposal.actor
        or value.counterpart is not None
        or value.author != source.proposal.controller
        or value.event != source.event
        or value.account != source.proposal.account
        or value.witnesses
    ):
        raise WorkflowError("Use the actual original travel attempt as rule evidence")
    if value.performed_event:
        movement = _get(state, rules.Movement, source.id + ":movement")
        row = _event(game, c, movement.event)
        born = _history(c, game, movement.event)
        if (
            movement.attempt != source.id
            or movement.event != value.performed_event
            or row["kind"] != "m3.physical_moved"
            or row["actor_id"] != str(source.proposal.controller)
            or _get(born, rules.Movement, movement.id) != movement
            or any(
                getattr(movement.proposal, key) != getattr(source.proposal, key)
                for key in _PHYSICAL
            )
        ):
            raise WorkflowError("Recover actual physical movement, not a performed checkbox")
        _pose(_before(game, c, movement.event), movement.proposal)
        _pose(born, movement.proposal, True)
    return source


_PHYSICAL = (
    "actor",
    "controller",
    "channel",
    "scene",
    "cast",
    "participants",
    "origin",
    "destination",
    "frame",
    "mode",
    "vessel_id",
    "frame_instance",
    "position_sha256",
)


def before_move(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    context: dict[str, Any],
    *,
    travel: str | None = None,
) -> None:
    actor = ActorRef.model_validate_json(json.dumps(context["actor"]))
    if travel is None and (not _native(state, actor) or not _enabled(game)):
        return
    proposal = rules.Proposal.model_validate_json(json.dumps(context))
    try:
        outside = rules.outside(state, proposal)
    except ValueError as error:
        raise WorkflowError(str(error)) from None
    if travel is None:
        if outside:
            raise WorkflowError(
                "UNCHAPERONED_SOURCE_REQUIRED: record your actual unchaperoned attempt; "
                "joint chaperoned travel needs its real journey adapter"
            )
        return
    source = prove(game, c, state, travel)
    value = prove_violation(game, c, state, source.violation)
    if (
        not outside
        or value.performed_event
        or viewer.user_id != source.proposal.controller
        or not _enabled(game)
        or not _native(state, source.proposal.actor)
        or any(getattr(proposal, key) != getattr(source.proposal, key) for key in _PHYSICAL)
    ):
        raise WorkflowError("Reopen the same actual unperformed original travel proposal")
    _vatgrown(game, c, state, proposal.actor, rules.RULE)
    _pose(state, proposal)


def stage_movement(
    game: GameService,
    c: Connection,
    before: GameState,
    after: GameState,
    context: dict[str, Any],
    travel: str | None,
    event: str,
) -> None:
    if travel is None:
        return
    source = prove(game, c, before, travel)
    proposal = rules.Proposal.model_validate_json(json.dumps(context))
    _pose(before, proposal)
    _pose(after, proposal, True)
    if any(getattr(proposal, key) != getattr(source.proposal, key) for key in _PHYSICAL):
        raise WorkflowError("Only the genuine original proposed movement fulfills this source")
    value = vat.find(after, vat.Violation, source.violation)
    if value.performed_event:
        raise WorkflowError("This actual source already has its physical receipt")
    rules.put(
        after,
        rules.Movement(
            id=source.id + ":movement",
            attempt=source.id,
            proposal=proposal,
            event=event,
        ),
    )
    vat.put(after, value.model_copy(update=dict(performed_event=event)))


class VatgrownTravelService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def attempt(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        revision: int,
        actor: ActorRef,
        destination: tuple[int, int],
        *,
        frame: bool = False,
        account: str,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            gate = Access(self.store)
            gate.authorize(c, viewer, "plays", director_response=True)
            assert gate.registry is not None
            gate.registry.require_available(rules.RULE)

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            if type(revision) is not int or state.revision != revision:
                raise WorkflowError("Reopen current actual movement before recording your attempt")
            actual = _vatgrown(self.game, c, state, actor, rules.RULE)
            if actual.controller != viewer.user_id or not _native(state, actor):
                raise WorkflowError(
                    "Only the actual original native Vatgrown declares this attempt"
                )
            proposal = rules.Proposal.model_validate_json(
                json.dumps(
                    proposal_context(
                        self.game, c, viewer, state, channel, actor, destination, frame, account
                    )
                )
            )
            try:
                outside = rules.outside(state, proposal)
            except ValueError as error:
                raise WorkflowError(str(error)) from None
            if not outside:
                raise WorkflowError(
                    "Use an actual outside-base route, not an invented interior exit"
                )
            event, identity, violation = str(uuid4()), str(uuid4()), str(uuid4())
            rules.put(
                state,
                rules.Attempt(
                    id=identity,
                    proposal=proposal,
                    event=event,
                    violation=violation,
                    origin_bases=rules.bases(state, proposal.origin),
                    destination_bases=rules.bases(state, proposal.destination),
                ),
            )
            vat.put(
                state,
                vat.Violation(
                    id=violation,
                    actor=actor,
                    kind="unchaperoned_attempt",
                    source=identity,
                    author=viewer.user_id,
                    event=event,
                    account=account,
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.vatgrown_travel_attempted",
                state,
                event_id=event,
                id=identity,
            )
            return dict(id=identity, violation=violation, revision=state.revision, moved=False)

        return self.store._write(
            viewer,
            key,
            "m3.vatgrown_travel_attempted",
            dict(
                revision=revision,
                channel=channel,
                actor=actor.model_dump(mode="json"),
                destination=list(destination),
                frame=frame,
                account=account,
            ),
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def perform(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            source = prove(self.game, c, load_state(c, self.store.campaign_id), identity)
            if viewer.user_id != source.proposal.controller:
                raise WorkflowError("Only the original actual traveler performs this proposal")
        proposal = source.proposal
        return MovementService(self.game).move(
            viewer,
            key,
            revision,
            proposal.channel,
            proposal.actor,
            proposal.destination,
            frame=proposal.frame,
            account=proposal.account,
            vatgrown_travel=identity,
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        for source in rules.records(state, rules.Attempt):
            value = vat.find(state, vat.Violation, source.violation)
            handler = bool(
                value.disclosed_event
                and value.disclosed_handler
                and value.disclosed_handler.entity == str(viewer.user_id)
            )
            owner = viewer.user_id == source.proposal.controller
            if owner or handler:
                result.append(
                    dict(
                        id=source.id,
                        revision=state.revision,
                        label="Actual unchaperoned travel",
                        phase="resolved" if value.judgment_event else "pending",
                        pending=bool(
                            (owner and not value.disclosed_event)
                            or (handler and not value.judgment_event)
                        ),
                    )
                )
        return result

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            source = _get(state, rules.Attempt, identity)
            value = vat.find(state, vat.Violation, source.violation)
            owner = viewer.user_id == source.proposal.controller
            handler = bool(
                value.disclosed_event
                and value.disclosed_handler
                and value.disclosed_handler.entity == str(viewer.user_id)
            )
            if not (owner or handler):
                raise WorkflowError(
                    "Only the actual author or explicitly addressed Handler reads this"
                )
            value = prove_violation(self.game, c, state, value.id)
            source = prove_violation_source(self.game, c, state, value)
            return dict(
                id=identity,
                violation=value.id,
                revision=state.revision,
                origin=source.proposal.origin,
                destination=source.proposal.destination,
                frame=source.proposal.frame,
                account=value.account,
                performed_event=value.performed_event,
                disclosed_event=value.disclosed_event,
                judgment_event=value.judgment_event,
                discipline=value.discipline,
                can_perform=owner and not value.performed_event,
                can_disclose=owner and not value.disclosed_event,
                can_judge=handler and not value.judgment_event,
            )

    def disclose(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        account: str,
    ) -> dict[str, Any]:
        value = self.view(viewer, identity)
        return VatgrownPlaysService(self.game).disclose(
            viewer,
            key,
            value["violation"],
            revision,
            account,
        )

    def menu(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            return self._tasks(c, viewer)
