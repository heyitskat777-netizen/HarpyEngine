"""Human-authored travel attempts, real movement, and explicitly disclosed evidence."""

import hashlib
import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine import m3_vatgrown_travel as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access, digest
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _cast
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_movement import (
    MovementService,
    _apply_context,
    _physical_context,
    proposal_context,
)
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

_AUTHORIZED = (*_PHYSICAL, "source_sha256")


def _policy(game: GameService) -> str:
    return hashlib.sha256(
        json.dumps(game.store.policy.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()


def _joint_context(
    game: GameService, c: Connection, state: GameState, context: dict[str, Any]
) -> rules.Proposal:
    context = dict(context)
    scene = _cast(game, c, state, context["channel"])
    actor = ActorRef.model_validate_json(json.dumps(context["actor"]))
    if not any(
        role.actor == actor and role.controller == context["controller"] for role in scene.roles
    ):
        raise WorkflowError("Join the actual companion role; a controller is not a physical role")
    if context["vessel_id"] is None:
        raise WorkflowError(
            "SOURCE_BODY_VESSEL_REQUIRED: establish the actual companion body first"
        )
    context["cast"] = scene.model_dump(mode="json")
    return rules.Proposal.model_validate_json(json.dumps(context))


def _joint_shape(owner: rules.Proposal, companion: rules.Proposal) -> None:
    if (
        owner.actor == companion.actor
        or owner.origin == owner.destination
        or any(
            getattr(owner, key) != getattr(companion, key)
            for key in ("origin", "destination", "scene", "channel", "cast", "participants")
        )
    ):
        raise WorkflowError("Use two actual roles together throughout the same real journey")


def _same_context(first: rules.Proposal, second: rules.Proposal) -> None:
    if any(getattr(first, key) != getattr(second, key) for key in _AUTHORIZED):
        raise WorkflowError("STALE_CHAPERONED_TRAVEL: reopen both original physical contexts")


def _check_position(
    game: GameService, c: Connection, state: GameState, proposal: rules.Proposal
) -> None:
    actual = resolve(
        state,
        proposal.actor,
        profiles(c, game.store.campaign_id),
        require_alive=False,
        require_current_profile=False,
    )
    if (
        actual.cell != proposal.origin
        or actual.controller != proposal.controller
        or actual.vessel_id != proposal.vessel_id
        or actual.frame_instance != proposal.frame_instance
        or actual.position_sha256 != proposal.position_sha256
        or actual.source_sha256 != proposal.source_sha256
    ):
        raise WorkflowError("Preserve the actual original role, body and movement-source snapshot")


def _response(
    state: GameState, source: rules.ChaperonedProposal
) -> rules.ChaperonedResponse | None:
    matches = [
        value
        for value in rules.records(state, rules.ChaperonedResponse)
        if value.source == source.id
    ]
    if len(matches) > 1:
        raise WorkflowError("Recover the single actual journey response")
    return matches[0] if matches else None


def prove_chaperoned(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.ChaperonedProposal:
    source = _get(state, rules.ChaperonedProposal, identity)
    row = _event(game, c, source.event)
    before, born = _before(game, c, source.event), _history(c, game, source.event)
    if (
        row["kind"] != "m3.vatgrown_chaperoned_proposed"
        or row["actor_id"] != str(source.owner.controller)
        or json.loads(row["payload_json"]).get("id") != source.id
        or _get(born, rules.ChaperonedProposal, identity) != source
        or not _native(before, source.owner.actor)
        or source.owner.controller != int(source.owner.actor.entity)
        or source.owner.revision != before.revision
        or source.companion_snapshot.revision != before.revision
        or source.mutual_required != _native(before, source.companion_snapshot.actor)
        or source.mutual_required
        and not source.mutual
    ):
        raise WorkflowError(
            "Recover the actual original owner's exact joint-movement authorization"
        )
    _joint_shape(source.owner, source.companion_snapshot)
    for proposal in (source.owner, source.companion_snapshot):
        _check_position(game, c, before, proposal)
        _check_position(game, c, born, proposal)
    response = _response(state, source)
    if response is None:
        return source
    row = _event(game, c, response.event)
    at_response = _history(c, game, response.event)
    if (
        response.id != source.id + ":response"
        or _get(at_response, rules.ChaperonedResponse, response.id) != response
        or row["actor_id"] != str(response.controller)
        or not response.account.strip()
    ):
        raise WorkflowError("Recover the actual role's immutable journey response")
    if response.kind != "accepted":
        expected = (
            source.owner.controller
            if response.kind == "cancelled"
            else source.companion_snapshot.controller
        )
        if (
            row["kind"] != "m3.vatgrown_chaperoned_" + response.kind
            or response.controller != expected
            or response.proposal is not None
        ):
            raise WorkflowError("Only the actual owner cancels or invited companion declines")
        prior = _before(game, c, response.event)
        if prior.placements != at_response.placements or prior.world != at_response.world:
            raise WorkflowError("Decline and cancellation authorize no physical movement")
        return source
    receipt = _get(state, rules.JointMovement, source.id + ":movement")
    if (
        row["kind"] != "m3.physical_moved"
        or json.loads(row["payload_json"]).get("vatgrown_journey") != source.id
        or receipt.source != source.id
        or receipt.response != response.id
        or receipt.event != response.event
        or receipt.id != source.id + ":movement"
        or response.controller != source.companion_snapshot.controller
        or response.proposal != receipt.companion
        or receipt.companion.account != response.account
        or _get(at_response, rules.JointMovement, receipt.id) != receipt
        or source.mutual_required
        and not response.mutual
    ):
        raise WorkflowError(
            "Recover both actual authorizations and the real joint physical receipt"
        )
    _same_context(source.owner, receipt.owner)
    _same_context(source.companion_snapshot, receipt.companion)
    _joint_shape(receipt.owner, receipt.companion)
    prior = _before(game, c, receipt.event)
    expected_state = GameState.model_validate_json(prior.model_dump_json())
    for proposal in (receipt.owner, receipt.companion):
        if proposal.revision != prior.revision:
            raise WorkflowError("Use the actual joint reducer's original current revision")
        _check_position(game, c, prior, proposal)
        _apply_context(expected_state, proposal.model_dump(mode="json"), receipt.event)
    bound = profiles(c, game.store.campaign_id)
    for proposal in (receipt.owner, receipt.companion):
        expected_actor = resolve(
            expected_state,
            proposal.actor,
            bound,
            require_alive=False,
            require_current_profile=False,
        )
        actual_actor = resolve(
            at_response, proposal.actor, bound, require_alive=False, require_current_profile=False
        )
        if any(
            getattr(expected_actor, key) != getattr(actual_actor, key)
            for key in (
                "cell",
                "vessel_id",
                "frame_instance",
                "inside_frame",
                "piloting",
                "occupied_frame_instance",
                "position_sha256",
                "source_sha256",
            )
        ):
            raise WorkflowError("Only the real paired reducer can stamp both actual moved bodies")
    return source


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

    def _joint_write(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        kind: str,
        request: dict[str, Any],
        operation: Callable[[Connection, GameState, str], dict[str, Any]],
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            gate = Access(self.store)
            gate.authorize(c, viewer, "plays", director_response=True)
            gate.authorize(c, viewer, "world", director_response=True)
            assert gate.registry is not None
            gate.registry.require_available(rules.RULE)

        def run(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if type(revision) is not int or revision != state.revision:
                raise WorkflowError("Reopen the current paired journey before changing it")
            event = str(uuid4())
            result = operation(c, state, event)
            payload = dict(id=result["id"])
            if result.get("moved"):
                payload.update(
                    movement=event, vatgrown_journey=result["id"], actors=result["actors"]
                )
            self.game.event(c, viewer.user_id, key, kind, state, event_id=event, **payload)
            return result | dict(revision=state.revision)

        try:
            return self.store._write(
                viewer,
                key,
                kind,
                request | dict(revision=revision),
                run,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def propose_chaperoned(
        self,
        viewer: GuildViewer,
        key: str,
        channel: int,
        revision: int,
        actor: ActorRef,
        companion: ActorRef,
        destination: tuple[int, int],
        *,
        frame: bool = False,
        account: str,
        mutual: bool = False,
    ) -> dict[str, Any]:
        if type(frame) is not bool or type(mutual) is not bool:
            raise WorkflowError("Select actual movement and explicit mutual accompaniment")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            _vatgrown(self.game, c, state, actor, rules.RULE)
            if not _native(state, actor):
                raise WorkflowError("Recover the actual current original native Vatgrown source")
            if not any(
                row["id"] == companion.token
                for row in MovementService(self.game).menu(viewer, channel)["companions"]
            ):
                raise WorkflowError("Choose an actual visible joined companion with a known body")
            owner = _joint_context(
                self.game,
                c,
                state,
                proposal_context(
                    self.game,
                    c,
                    viewer,
                    state,
                    channel,
                    actor,
                    destination,
                    frame,
                    account,
                ),
            )
            actual = resolve(
                state, companion, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            snapshot = _joint_context(
                self.game,
                c,
                state,
                _physical_context(
                    self.game,
                    c,
                    state,
                    channel,
                    companion,
                    destination,
                    actual.piloting is True,
                    account,
                    controller=actual.controller,
                ),
            )
            _joint_shape(owner, snapshot)
            required = _native(state, companion)
            if required and not mutual:
                raise WorkflowError(
                    "MUTUAL_ACCOMPANIMENT_REQUIRED: explicitly authorize chaperoning this "
                    "other Experiment throughout the trip too"
                )
            source = rules.ChaperonedProposal(
                id=str(uuid4()),
                owner=owner,
                companion_snapshot=snapshot,
                mutual=mutual,
                mutual_required=required,
                policy_sha256=_policy(self.game),
                event=event,
            )
            rules.put(state, source)
            return dict(id=source.id, state="pending", moved=False)

        return self._joint_write(
            viewer,
            key,
            revision,
            "m3.vatgrown_chaperoned_proposed",
            dict(
                channel=channel,
                actor=actor.model_dump(mode="json"),
                companion=companion.model_dump(mode="json"),
                destination=list(destination),
                frame=frame,
                account=account,
                mutual=mutual,
            ),
            operation,
        )

    def respond_chaperoned(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        *,
        accept: bool,
        frame: bool = False,
        account: str,
        mutual: bool = False,
    ) -> dict[str, Any]:
        if (
            type(accept) is not bool
            or type(frame) is not bool
            or type(mutual) is not bool
            or not account.strip()
            or len(account) > 1200
        ):
            raise WorkflowError("The actual companion authors their movement or decline")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            source = prove_chaperoned(self.game, c, state, identity)
            snapshot = source.companion_snapshot
            actual = resolve(
                state,
                snapshot.actor,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
            if (
                viewer.user_id != snapshot.controller
                or actual.controller != viewer.user_id
                or _response(state, source) is not None
            ):
                raise WorkflowError("Only the actual invited role's controller answers once")
            companion: rules.Proposal | None = None
            owner: rules.Proposal | None = None
            if accept:
                if source.policy_sha256 != _policy(self.game) or not _native(
                    state, source.owner.actor
                ):
                    raise WorkflowError(
                        "Reauthorize the original owner's current source and policy"
                    )
                _vatgrown(self.game, c, state, source.owner.actor, rules.RULE)
                owner = _joint_context(
                    self.game,
                    c,
                    state,
                    _physical_context(
                        self.game,
                        c,
                        state,
                        source.owner.channel,
                        source.owner.actor,
                        source.owner.destination,
                        source.owner.frame,
                        source.owner.account,
                        controller=source.owner.controller,
                    ),
                )
                companion = _joint_context(
                    self.game,
                    c,
                    state,
                    proposal_context(
                        self.game,
                        c,
                        viewer,
                        state,
                        snapshot.channel,
                        snapshot.actor,
                        snapshot.destination,
                        frame,
                        account,
                    ),
                )
                _same_context(source.owner, owner)
                _same_context(snapshot, companion)
                _joint_shape(owner, companion)
                if (
                    source.mutual_required != _native(state, companion.actor)
                    or source.mutual_required
                    and not (source.mutual and mutual)
                ):
                    raise WorkflowError(
                        "Both Experiments must explicitly authorize mutual accompaniment"
                    )
            response = rules.ChaperonedResponse(
                id=source.id + ":response",
                source=source.id,
                kind="accepted" if accept else "declined",
                controller=viewer.user_id,
                account=account,
                mutual=mutual,
                proposal=companion,
                event=event,
            )
            rules.put(state, response)
            if owner is None or companion is None:
                return dict(id=source.id, state="declined", moved=False)
            # Both sources are proved before either reducer; one transaction and event owns both.
            _apply_context(state, owner.model_dump(mode="json"), event)
            _apply_context(state, companion.model_dump(mode="json"), event)
            rules.put(
                state,
                rules.JointMovement(
                    id=source.id + ":movement",
                    source=source.id,
                    response=response.id,
                    owner=owner,
                    companion=companion,
                    event=event,
                ),
            )
            return dict(
                id=source.id,
                state="accepted",
                moved=True,
                actors=[
                    owner.actor.model_dump(mode="json"),
                    companion.actor.model_dump(mode="json"),
                ],
                destination=list(owner.destination),
            )

        return self._joint_write(
            viewer,
            key,
            revision,
            "m3.physical_moved" if accept else "m3.vatgrown_chaperoned_declined",
            dict(id=identity, accept=accept, frame=frame, account=account, mutual=mutual),
            operation,
        )

    def cancel_chaperoned(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        account: str,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Record your actual proposal cancellation")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            source = prove_chaperoned(self.game, c, state, identity)
            if viewer.user_id != source.owner.controller or _response(state, source) is not None:
                raise WorkflowError("Only the original owner cancels before any companion response")
            rules.put(
                state,
                rules.ChaperonedResponse(
                    id=source.id + ":response",
                    source=source.id,
                    kind="cancelled",
                    controller=viewer.user_id,
                    account=account,
                    mutual=False,
                    event=event,
                ),
            )
            return dict(id=source.id, state="cancelled", moved=False)

        return self._joint_write(
            viewer,
            key,
            revision,
            "m3.vatgrown_chaperoned_cancelled",
            dict(id=identity, account=account),
            operation,
        )

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
        for joint_source in rules.records(state, rules.ChaperonedProposal):
            if viewer.user_id in (
                joint_source.owner.controller,
                joint_source.companion_snapshot.controller,
            ):
                response = _response(state, joint_source)
                result.append(
                    dict(
                        id=joint_source.id,
                        revision=state.revision,
                        label="Actual chaperoned joint travel",
                        phase="resolved" if response else "pending",
                        pending=response is None
                        and viewer.user_id == joint_source.companion_snapshot.controller,
                    )
                )
        return result

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            joint = next(
                (
                    value
                    for value in rules.records(state, rules.ChaperonedProposal)
                    if value.id == identity
                ),
                None,
            )
            if joint is not None:
                if viewer.user_id not in (
                    joint.owner.controller,
                    joint.companion_snapshot.controller,
                ):
                    raise WorkflowError(
                        "Only the actual two source authors read this paired journey"
                    )
                joint = prove_chaperoned(self.game, c, state, identity)
                response = _response(state, joint)
                return dict(
                    id=identity,
                    type="chaperoned",
                    revision=state.revision,
                    owner=joint.owner.actor.model_dump(mode="json"),
                    companion=joint.companion_snapshot.actor.model_dump(mode="json"),
                    origin=list(joint.owner.origin),
                    destination=list(joint.owner.destination),
                    owner_account=joint.owner.account,
                    companion_account=response.account
                    if response and response.kind != "cancelled"
                    else None,
                    closure_account=response.account if response else None,
                    status=response.kind if response else "pending",
                    mutual_required=joint.mutual_required,
                    companion_frame=joint.companion_snapshot.frame,
                    can_respond=response is None
                    and viewer.user_id == joint.companion_snapshot.controller,
                    can_cancel=response is None and viewer.user_id == joint.owner.controller,
                )
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
