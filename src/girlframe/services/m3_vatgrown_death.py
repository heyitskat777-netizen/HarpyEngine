"""Distinct Vatgrown replacement, actual reviewed kit issuance and owned noticing replies."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_vatgrown_death as rules
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.creation_review import ReviewSheet
from girlframe.engine.drafts import DraftInput
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_career_state import CareerArchive
from girlframe.engine.m3_careers import binding
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_physical_state import Placement
from girlframe.engine.m3_vatgrown_travel import bases
from girlframe.services.creation_review import CreationReviewService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _access(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "playbooks", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)


def _audit(game: GameService, c: Connection, event: str, kind: str, author: int) -> None:
    actual = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    if actual is None or actual["kind"] != kind or actual["actor_id"] != str(author):
        raise WorkflowError("Recover this source's actual canonical human author")


def _archive(game: GameService, c: Connection, state: GameState, identity: str) -> CareerArchive:
    archive = next((x for x in state.career_archives if x.id == identity), None)
    if (
        archive is None
        or not rules.required(archive)
        or archive not in _history(c, game, archive.source_event).career_archives
    ):
        raise WorkflowError("Require the actual original Vatgrown's genuine death archive")
    return archive


def validate_replacement(
    game: GameService, c: Connection, state: GameState, archive: CareerArchive, draft: DraftInput
) -> None:
    if not rules.required(archive):
        return
    _archive(game, c, state, archive.id)
    if draft.girl_playbook != "VATGROWN":
        raise WorkflowError("The actual dead Vatgrown must be replaced by another Vatgrown")


def bind_replacement(
    game: GameService,
    c: Connection,
    state: GameState,
    archive: CareerArchive,
    new_actor: ActorRef,
    event: str,
) -> None:
    if not rules.required(archive):
        return
    _archive(game, c, state, archive.id)
    handler = active_handler(state)
    if handler is None or state.handler is None:
        raise WorkflowError("Require the actual current Handler for fresh replacement supply")
    rules.put(
        state,
        rules.Replacement(
            id=rules.identity("replacement", archive.id, str(new_actor.incarnation)),
            archive=archive.id,
            original=archive.actor,
            new_actor=new_actor,
            started_event=event,
            handler=handler,
            handler_controller=state.handler,
        ),
    )


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Replacement:
    value = next((x for x in rules.records(state, rules.Replacement) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the original distinct replacement source")
    born = _history(c, game, value.started_event)
    archive = _archive(game, c, born, value.archive)
    expected = value.model_copy(update={"activated_event": None})
    current = binding(born, int(value.new_actor.entity))
    _audit(
        game,
        c,
        value.started_event,
        "m3.replacement_character_started",
        int(value.new_actor.entity),
    )
    if (
        expected not in rules.records(born, rules.Replacement)
        or value.original != archive.actor
        or value.original == value.new_actor
        or value.original.entity != value.new_actor.entity
        or current is None
        or current.character != value.new_actor.incarnation
        or current.previous_archive != archive.id
        or current.source_event != value.started_event
    ):
        raise WorkflowError("Preserve the actual archive, new incarnation and source binding")
    if value.activated_event:
        activated = _history(c, game, value.activated_event)
        _audit(
            game, c, value.activated_event, "m2.character_activated", int(value.new_actor.entity)
        )
        if value not in rules.records(activated, rules.Replacement):
            raise WorkflowError("Recover the actual new Vatgrown activation")
        issued = _issue(game, c, activated, value)
        request = _request(game, c, activated, issued.request)
        sheet = activated.sheets.get(value.new_actor.entity)
        pose = next((x for x in activated.placements if x.actor == value.new_actor), None)
        if (
            sheet is None
            or sheet.character_id != value.new_actor.incarnation
            or sheet.girl != "VATGROWN"
            or sheet.source_fingerprint != request.fingerprint
            or pose is None
            or pose.vessel_id != issued.body_vessel
            or pose.frame_instance != issued.frame_instance
            or pose.girl_cell != issued.cell
            or pose.frame_cell != issued.cell
            or pose.proposed_event != issued.event
            or pose.source_event != value.activated_event
        ):
            raise WorkflowError("Prove the distinct new person and actual issued physical kit")
    return value


def _request(game: GameService, c: Connection, state: GameState, identity: str) -> rules.KitRequest:
    request = next((x for x in rules.records(state, rules.KitRequest) if x.id == identity), None)
    if request is None or request not in rules.records(
        _history(c, game, request.event), rules.KitRequest
    ):
        raise WorkflowError("Recover the actual owner's immutable reviewed-kit request")
    _audit(game, c, request.event, "m3.vatgrown_kit_requested", int(request.actor.entity))
    actual = (
        c.execute(
            sa.select(t.creation_reviews).where(
                t.creation_reviews.c.campaign_id == game.store.campaign_id,
                t.creation_reviews.c.user_id == request.actor.entity,
                t.creation_reviews.c.dependency_hash == request.fingerprint,
                t.creation_reviews.c.body_json == request.review_json,
            )
        )
        .mappings()
        .first()
    )
    review = ReviewSheet.model_validate_json(request.review_json)
    parent = prove(game, c, _history(c, game, request.event), request.replacement)
    if (
        request.actor != parent.new_actor
        or actual is None
        or not review.ready_for_rules_review
        or review.creation.girl_playbook != "VATGROWN"
        or review.character_revision != request.profile_revision
        or tuple(review.creation.identities) != tuple(CATALOG["VATGROWN"]["identities"])
    ):
        raise WorkflowError("Use the actual saved complete fresh standard Vatgrown review")
    return request


def _issue(
    game: GameService, c: Connection, state: GameState, source: rules.Replacement
) -> rules.Issue:
    issues = [x for x in rules.records(state, rules.Issue) if x.replacement == source.id]
    if len(issues) != 1:
        raise WorkflowError("The actual Handler must issue one distinct reviewed physical kit")
    value = issues[0]
    request = _request(game, c, state, value.request)
    _audit(game, c, value.event, "m3.vatgrown_kit_issued", source.handler_controller)
    if (
        value not in rules.records(_history(c, game, value.event), rules.Issue)
        or value.actor != source.new_actor
        or value.handler != source.handler
        or value.controller != source.handler_controller
        or request.actor != source.new_actor
        or request.replacement != source.id
        or value.frame_instance != "initial:" + str(source.new_actor.incarnation)
        or value.body_vessel != "vatgrown-body:" + str(source.new_actor.incarnation)
    ):
        raise WorkflowError("Preserve the distinct real kit and original actual issuing Handler")
    return value


def stage_activation(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, event: str
) -> bool:
    source = rules.activation_source(state, actor)
    if source is None:
        return False
    prove(game, c, state, source.id)
    if source.activated_event:
        raise WorkflowError("This distinct replacement is already active")
    issued = _issue(game, c, state, source)
    request = _request(game, c, state, issued.request)
    review = ReviewSheet.model_validate_json(request.review_json)
    sheet = state.sheets[actor.entity]
    career = binding(state, int(actor.entity))
    if (
        sheet.girl != "VATGROWN"
        or sheet.review != review
        or sheet.source_fingerprint != request.fingerprint
        or sheet.source_profile_revision != request.profile_revision
        or tuple(x.name for x in sheet.identities) != tuple(CATALOG["VATGROWN"]["identities"])
        or any(x.marked or x.am_limiter or x.paired for x in sheet.identities)
        or sheet.frame != review.creation.frame_playbook
        or sheet.permissions != 0
        or career is None
        or career.status_position is None
        or career.status_event is None
        or int(actor.entity) in state.order
        or state.world is None
        or not state.world.board.contains(issued.cell)
        or not bases(state, issued.cell)
        or any(
            x.actor == actor
            or x.vessel_id == issued.body_vessel
            or x.frame_instance == issued.frame_instance
            for x in state.placements
        )
    ):
        raise WorkflowError(
            "Activate only the fresh reviewed person, reset baseline and actual supplied kit"
        )
    expected = [
        (x.name, x.description)
        for x in (*review.creation.girl_assets, *review.creation.frame_assets)
    ]
    expected += [
        (name, "")
        for name in review.creation.intrinsic_frame_assets
        if not (review.creation.frame_playbook == "WYVERN 0.4" and name == "Enormous")
    ]
    actual = [(x.name, x.description) for x in sheet.assets if x.intrinsic is None]
    if actual != expected:
        raise WorkflowError(
            "The actual new body and Frame must match the reviewed supplied components"
        )
    state.placements.append(
        Placement(
            actor=actor,
            vessel_id=issued.body_vessel,
            frame_instance=issued.frame_instance,
            girl_cell=issued.cell,
            frame_cell=issued.cell,
            mode="outside_frame",
            proposed_event=issued.event,
            source_event=event,
            account=issued.account,
        )
    )
    position = career.status_position
    if not 0 <= position <= len(state.order):
        raise WorkflowError("Refresh the actual Handler's new starting Status assignment")
    state.order = state.order[:position] + (int(actor.entity),) + state.order[position:]
    rules.put(state, source.model_copy(update={"activated_event": event}))
    archive = _archive(game, c, state, source.archive)
    old = _history(c, game, archive.source_event)
    people = [
        (ActorRef(kind="pilot", entity=str(uid), incarnation=identity), int(uid))
        for uid, identity in json.loads(archive.links_json)["counterparts"].items()
    ]
    handler = active_handler(old)
    if handler is not None and old.handler is not None:
        people.append((handler, old.handler))
    for recipient, controller in people:
        rules.put(
            state,
            rules.Notice(
                id=rules.identity("notice", source.id, recipient.token),
                replacement=source.id,
                recipient=recipient,
                controller=controller,
                event=event,
            ),
        )
    return True


def _is_person(state: GameState, actor: ActorRef, user: int) -> bool:
    if actor.kind == "pilot":
        sheet = state.sheets.get(actor.entity)
        return (
            actor.entity == str(user)
            and sheet is not None
            and sheet.character_id == actor.incarnation
        )
    return actor.kind == "handler" and active_handler(state) == actor and state.handler == user


def _current_person(state: GameState, actor: ActorRef, viewer: GuildViewer) -> None:
    if actor.kind == "pilot":
        if actor.entity != str(viewer.user_id) or current_ref(state, viewer.user_id) != actor:
            raise WorkflowError("Only this actual original person may answer")
    elif actor.kind == "handler":
        if active_handler(state) != actor or state.handler != viewer.user_id:
            raise WorkflowError("Only the actual original Handler person may answer")
    else:
        raise WorkflowError("This source has no proxy-person reply adapter")


class VatgrownDeathService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def start(
        self, viewer: GuildViewer, key: str, archive: str, revision: int, draft: DraftInput
    ) -> dict[str, Any]:
        from girlframe.services.m3_careers import CareerService

        if draft.girl_playbook != "VATGROWN":
            raise WorkflowError("Choose a genuinely distinct Vatgrown")
        return CareerService(self.store).begin_replacement(viewer, key, archive, revision, draft)

    def request_issue(
        self, viewer: GuildViewer, key: str, identity: str, revision: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            source = prove(self.game, c, state, identity)
            if (
                viewer.user_id != int(source.new_actor.entity)
                or source.activated_event
                or state.revision != revision
                or any(x.replacement == identity for x in rules.records(state, rules.Issue))
            ):
                raise WorkflowError("Refresh the actual original owner's unissued replacement")
            review = CreationReviewService(self.store)._current(c, viewer)
            if not review.sheet.ready_for_rules_review or not review.saved_current:
                raise WorkflowError("Save the actual complete fresh creation review first")
            event = str(uuid4())
            request = rules.KitRequest(
                id=rules.identity("kit", identity, event),
                replacement=identity,
                actor=source.new_actor,
                profile_revision=review.sheet.character_revision,
                fingerprint=review.fingerprint,
                review_json=review.sheet.model_dump_json(),
                event=event,
            )
            rules.put(state, request)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.vatgrown_kit_requested",
                state,
                event_id=event,
                replacement=identity,
            )
            return dict(id=request.id)

        return self.store._write(
            viewer,
            key,
            "m3.vatgrown_kit_requested",
            dict(id=identity, revision=revision),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def issue(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        request: str,
        cell: tuple[int, int],
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            source = prove(self.game, c, state, identity)
            _current_person(state, source.handler, viewer)
            actual = _request(self.game, c, state, request)
            requests = [
                x for x in rules.records(state, rules.KitRequest) if x.replacement == identity
            ]
            if (
                state.revision != revision
                or source.activated_event
                or not account.strip()
                or len(account) > 1200
                or actual.replacement != identity
                or requests[-1].id != request
                or any(x.replacement == identity for x in rules.records(state, rules.Issue))
                or state.world is None
                or not state.world.board.contains(cell)
                or not bases(state, cell)
            ):
                raise WorkflowError(
                    "Refresh the actual requested kit and record its real physical supply"
                )
            event = str(uuid4())
            value = rules.Issue(
                id=rules.identity("issue", identity),
                replacement=identity,
                request=request,
                actor=source.new_actor,
                handler=source.handler,
                controller=viewer.user_id,
                frame_instance="initial:" + str(source.new_actor.incarnation),
                body_vessel="vatgrown-body:" + str(source.new_actor.incarnation),
                cell=cell,
                account=account.strip(),
                event=event,
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.vatgrown_kit_issued",
                state,
                event_id=event,
                replacement=identity,
            )
            return dict(id=value.id)

        return self.store._write(
            viewer,
            key,
            "m3.vatgrown_kit_issued",
            dict(id=identity, revision=revision, request=request, cell=cell, account=account),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def answer(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        notice: str,
        answer: Literal["yes", "no", "uncertain"],
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            source = prove(self.game, c, state, identity)
            value = next((x for x in rules.records(state, rules.Notice) if x.id == notice), None)
            if (
                value is None
                or value.replacement != identity
                or not source.activated_event
                or state.revision != revision
                or value.response_event
                or not account.strip()
                or len(account) > 1200
                or answer not in ("yes", "no", "uncertain")
            ):
                raise WorkflowError("Answer only your actual pending replacement-noticing question")
            _current_person(state, value.recipient, viewer)
            self._prove_notice(c, state, source, value)
            event = str(uuid4())
            rules.put(
                state,
                value.model_copy(
                    update={"answer": answer, "account": account.strip(), "response_event": event}
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.vatgrown_noticed",
                state,
                event_id=event,
                replacement=identity,
                notice=notice,
            )
            return dict(id=notice)

        return self.store._write(
            viewer,
            key,
            "m3.vatgrown_noticed",
            dict(id=identity, revision=revision, notice=notice, answer=answer, account=account),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )

    def _prove_notice(
        self, c: Connection, state: GameState, source: rules.Replacement, value: rules.Notice
    ) -> None:
        if (
            value.model_copy(update={"answer": None, "account": None, "response_event": None})
            not in rules.records(_history(c, self.game, value.event), rules.Notice)
            or value.event != source.activated_event
        ):
            raise WorkflowError("Recover the actual addressed source question")
        if value.response_event:
            _audit(self.game, c, value.response_event, "m3.vatgrown_noticed", value.controller)
            if value not in rules.records(
                _history(c, self.game, value.response_event), rules.Notice
            ):
                raise WorkflowError("Recover this actual original respondent's answer")

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            source = prove(self.game, c, state, identity)
            owner = viewer.user_id == int(source.new_actor.entity)
            issuer = (
                viewer.user_id == source.handler_controller
                and active_handler(state) == source.handler
            )
            notices = [x for x in rules.records(state, rules.Notice) if x.replacement == identity]
            own = [
                x
                for x in notices
                if x.controller == viewer.user_id and _is_person(state, x.recipient, viewer.user_id)
            ]
            if not owner and not issuer and not own:
                raise WorkflowError("Only actual original source parties read this private card")
            for value in own:
                _current_person(state, value.recipient, viewer)
            visible = notices if owner else own
            for value in visible:
                self._prove_notice(c, state, source, value)
            requests = [
                _request(self.game, c, state, x.id)
                for x in rules.records(state, rules.KitRequest)
                if x.replacement == identity
            ]
            issues = [x for x in rules.records(state, rules.Issue) if x.replacement == identity]
            issued = _issue(self.game, c, state, source) if issues else None
            latest = requests[-1] if requests else None
            review = ReviewSheet.model_validate_json(latest.review_json) if latest else None
            archive = _archive(self.game, c, state, source.archive)
            original = _history(c, self.game, archive.source_event)
            labels = {str(uid): sheet.callsign for uid, sheet in original.sheets.items()}
            return dict(
                id=identity,
                revision=state.revision,
                source=source.model_dump(mode="json"),
                owner=owner,
                can_request=owner and not issued and not source.activated_event,
                can_issue=issuer and latest is not None and not issued,
                request=latest.id if latest and (owner or issuer) else None,
                kit=dict(
                    frame=review.creation.frame_playbook,
                    frame_name=review.creation.frame_name,
                    girl_assets=[x.model_dump(mode="json") for x in review.creation.girl_assets],
                    frame_assets=[x.model_dump(mode="json") for x in review.creation.frame_assets],
                )
                if review and (owner or issuer)
                else None,
                issue=issued.model_dump(mode="json") if issued and (owner or issuer) else None,
                notices=[
                    x.model_dump(mode="json")
                    | dict(
                        label=(
                            labels.get(x.recipient.entity, "Original Girl")
                            if x.recipient.kind == "pilot"
                            else "Original Handler"
                        )
                    )
                    for x in visible
                ],
                pending=[x.id for x in own if not x.response_event],
                phase="noticing"
                if source.activated_event and any(not x.response_event for x in notices)
                else "complete"
                if source.activated_event
                else "issued"
                if issued
                else "creation",
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        rows = []
        for source in rules.records(state, rules.Replacement):
            notices = [x for x in rules.records(state, rules.Notice) if x.replacement == source.id]
            owner = source.new_actor.entity == str(viewer.user_id)
            issuer = (
                source.handler_controller == viewer.user_id
                and active_handler(state) == source.handler
            )
            own = [
                x
                for x in notices
                if x.controller == viewer.user_id and _is_person(state, x.recipient, viewer.user_id)
            ]
            if not owner and not issuer and not own:
                continue
            pending = bool(any(not x.response_event for x in own))
            if not source.activated_event:
                pending = (
                    owner
                    or issuer
                    and (
                        any(
                            x.replacement == source.id
                            for x in rules.records(state, rules.KitRequest)
                        )
                        and not any(
                            x.replacement == source.id for x in rules.records(state, rules.Issue)
                        )
                    )
                )
            rows.append(
                dict(
                    id=source.id,
                    revision=state.revision,
                    label="Distinct Vatgrown replacement / own noticing",
                    phase="noticing" if source.activated_event else "creation",
                    pending=pending,
                    waiting=not pending
                    and (not source.activated_event or any(not x.response_event for x in notices)),
                )
            )
        return rows
