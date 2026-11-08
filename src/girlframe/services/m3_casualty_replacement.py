"""Actual Handler-supplied components, original-body installation and exact payment."""

from collections.abc import Callable
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_casualty as casualty
from girlframe.engine import m3_casualty_replacement as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_intracadre_marriage import debit, marriage_for, wallet
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_casualty import _access, _before, _post, prove_parts
from girlframe.services.m3_dose_up import _native
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_intracadre_marriage import prepare_payment, prove_flow
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

PRODUCT = rules.PRODUCT


def _text(value: str) -> None:
    if not value.strip() or len(value) > 1200:
        raise WorkflowError("Record the actual performed procurement, delivery or installation")


def _event(game: GameService, c: Connection, event: str, kind: str, author: int) -> None:
    row = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == event,
        )
    ).first()
    if row is None or row.kind != kind or row.actor_id != str(author):
        raise WorkflowError("Recover the actual canonical replacement event and original human")


def _live(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> casualty.Body:
    actual = _native(game, c, state, actor)
    body = prove_parts(game, c, state, actor)
    if (
        not actual.alive
        or actual.vessel_id != body.vessel
        or casualty.part_state(state, actor, "brain") in ("destroyed", "removed")
    ):
        raise WorkflowError(
            "Replacement needs the same living original body, never a new brain/person"
        )
    return body


def _source_body(
    game: GameService, c: Connection, born: GameState, actor: ActorRef
) -> casualty.Body:
    # Called only on the immutable event snapshots below, never to authorize a write.
    actual = resolve(
        born, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    body = prove_parts(game, c, born, actor)
    if (
        actor.kind != "pilot"
        or actual.rules != "girl_frame"
        or not actual.alive
        or actual.offstage_source
        or actual.custody not in (None, "free")
        or born.sheets[actor.entity].character_id != actor.incarnation
        or born.sheets[actor.entity].medical_state != "fit"
        or actual.vessel_id != body.vessel
        or casualty.part_state(born, actor, "brain") in ("destroyed", "removed")
    ):
        raise WorkflowError("Recover the original living body's actual source-time hardware")
    return body


def prove_request(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Request:
    value = rules.get(state, rules.Request, identity)
    born = _history(c, game, value.event)
    if rules.get(born, rules.Request, identity) != value:
        raise WorkflowError("Preserve the actual original missing-part request")
    _event(game, c, value.event, "m3.casualty_component_requested", int(value.actor.entity))
    body = _source_body(game, c, born, value.actor)
    part = next((x for x in body.parts if x.id == value.part), None)
    causes = [
        x
        for x in casualty.records(born, casualty.PartChange)
        if x.actor == value.actor and x.part == value.part
    ]
    handler = active_handler(born)
    if (
        body.vessel != value.vessel
        or part is None
        or value.part == "brain"
        or part.condition not in ("destroyed", "removed")
        or (part.condition, part.component) != (value.condition, value.previous_component)
        or not causes
        or causes[-1].id != value.cause
        or handler != value.handler
        or resolve(
            born, handler, profiles(c, game.store.campaign_id), require_current_profile=False
        ).controller
        != value.handler_controller
    ):
        raise WorkflowError("Retain the real original missing component, vessel and source Handler")
    return value


def prove_quote(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Quote:
    value = rules.get(state, rules.Quote, identity)
    request = prove_request(game, c, state, value.request)
    born = _history(c, game, value.event)
    _event(game, c, value.event, "m3.casualty_component_quoted", request.handler_controller)
    source = resolve(
        born, request.actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if (
        rules.get(born, rules.Quote, identity) != value
        or (value.actor, value.vessel, value.part) != (request.actor, request.vessel, request.part)
        or value.component != str(uuid5(NAMESPACE_URL, "casualty-component:" + value.id))
        or source.vessel_id != value.vessel
        or source.cell != value.cell
        or active_handler(born) != request.handler
        or sum(x.request == request.id for x in rules.records(born, rules.Quote)) != 1
    ):
        raise WorkflowError(
            "Recover the actual supplied component, source-priced package and location"
        )
    body = _source_body(game, c, born, value.actor)
    _missing_condition(born, body, request)
    return value


def _missing(
    game: GameService, c: Connection, state: GameState, request: rules.Request
) -> casualty.Body:
    body = _live(game, c, state, request.actor)
    _missing_condition(state, body, request)
    return body


def _missing_condition(state: GameState, body: casualty.Body, request: rules.Request) -> None:
    part = next((x for x in body.parts if x.id == request.part), None)
    changes = [
        x
        for x in casualty.records(state, casualty.PartChange)
        if x.actor == request.actor and x.part == request.part
    ]
    if (
        body.vessel != request.vessel
        or part is None
        or (part.condition, part.component) != (request.condition, request.previous_component)
        or not changes
        or changes[-1].id != request.cause
        or any(x.request == request.id for x in rules.records(state, rules.Installation))
    ):
        raise WorkflowError(
            "STALE_COMPONENT: preserve the same actual missing site and original cause"
        )


def quote_price(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, quote_id: str
) -> int:
    value = prove_quote(game, c, state, quote_id)
    if value.actor != actor:
        raise WorkflowError("This actual component price belongs to another original body")
    return value.price


def prove_replacement(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Installation:
    value = rules.get(state, rules.Installation, identity)
    born, prior = _history(c, game, value.event), _before(game, c, value.event)
    quote = prove_quote(game, c, prior, value.quote)
    request = prove_request(game, c, prior, quote.request)
    _event(game, c, value.event, "m3.casualty_component_installed", int(value.actor.entity))
    _missing_condition(prior, _source_body(game, c, prior, request.actor), request)
    body = casualty.body(born, value.actor)
    part = next((x for x in body.parts if x.id == value.part), None) if body else None
    changes = [x for x in casualty.records(born, casualty.PartChange) if x.id == value.change]
    if (
        rules.get(born, rules.Installation, identity) != value
        or (value.actor, value.vessel, value.part, value.request, value.component)
        != (quote.actor, quote.vessel, quote.part, request.id, quote.component)
        or value.change != str(uuid5(NAMESPACE_URL, "casualty-component:" + value.id))
        or body is None
        or body.vessel != value.vessel
        or part is None
        or part.condition != "intact"
        or part.component != quote.component
        or len(changes) != 1
        or sum(x.component == value.component for x in rules.records(born, rules.Installation)) != 1
    ):
        raise WorkflowError(
            "Preserve the exact real one-component installation and source transition"
        )
    change = changes[0]
    if (
        change.actor != value.actor
        or change.vessel != value.vessel
        or change.part != value.part
        or change.before != request.condition
        or change.after != "intact"
        or change.reason != "replacement"
        or change.event != value.event
        or change.inflictor != value.actor
        or change.account != value.account
        or change.source_action is not None
        or change.source_work is not None
        or change.source_choice is not None
    ):
        raise WorkflowError(
            "Replacement is its own real source, never a fabricated Play/work/repair"
        )
    actual = resolve(
        prior, value.actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if actual.vessel_id != value.vessel or actual.cell != quote.cell:
        raise WorkflowError("Prove actual delivery to the same original body's known position")
    flow = prove_flow(game, c, prior, born, value.actor, value.event, value.id, quote.price)
    payer = wallet(prior, value.actor)
    if (
        prior.sheets[payer.entity].permissions - born.sheets[payer.entity].permissions
        != quote.price
        or (flow.approval if flow else None) != value.payment
        or flow is not None
        and (flow.product != PRODUCT or flow.detail != quote.id)
    ):
        raise WorkflowError(
            "Preserve the exact actual component purchase and original wallet source"
        )
    return value


class ReplacementService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        kind: str,
        request: dict[str, Any],
        operation: Callable[[Connection, GameState, str], dict[str, Any]],
    ) -> dict[str, Any]:
        def run(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            if self.game.pending_actions(c):
                raise WorkflowError(
                    "Finish actual Plays and restore chat before replacing hardware"
                )
            state = load_state(c, self.store.campaign_id)
            if state.revision != request["revision"]:
                raise WorkflowError(
                    "STALE_COMPONENT: reopen the actual original replacement source"
                )
            return operation(c, state, str(uuid4()))

        try:
            return self.store._write(
                viewer,
                key,
                kind,
                request,
                run,
                auto_audit=False,
                authorize=lambda c: _access(self.game, c, viewer, casualty.GOD),
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def request(
        self, viewer: GuildViewer, key: str, revision: int, part: str, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            _text(account)
            actor = current_ref(state, viewer.user_id)
            body = _live(self.game, c, state, actor)
            entry = next((x for x in body.parts if x.id == part), None)
            changes = [
                x
                for x in casualty.records(state, casualty.PartChange)
                if x.actor == actor and x.part == part
            ]
            if (
                entry is None
                or entry.condition not in ("destroyed", "removed")
                or part == "brain"
                or not changes
            ):
                raise WorkflowError(
                    "Request one actual missing non-Brain component, not broken-part repair"
                )
            for old in rules.records(state, rules.Request):
                if old.actor == actor and old.part == part and old.cause == changes[-1].id:
                    raise WorkflowError("Reopen the already saved original component request")
            handler = active_handler(state)
            if handler is None:
                raise WorkflowError("Recover the actual original living Handler source")
            value = rules.Request(
                id=event,
                actor=actor,
                vessel=body.vessel,
                part=part,
                cause=changes[-1].id,
                condition=entry.condition,
                previous_component=entry.component,
                handler=handler,
                handler_controller=resolve(
                    state, handler, profiles(c, self.store.campaign_id)
                ).controller,
                event=event,
                account=account.strip(),
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.casualty_component_requested",
                state,
                event_id=event,
                request=value.id,
                part=part,
            )
            return dict(id=value.id, revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.casualty_component_requested",
            dict(revision=revision, part=part, account=account),
            operation,
        )

    def quote(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        request_id: str,
        name: str,
        description: str,
        procurement: str,
        price: int,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            request = prove_request(self.game, c, state, request_id)
            if (
                viewer.user_id != request.handler_controller
                or active_handler(state) != request.handler
                or any(x.request == request_id for x in rules.records(state, rules.Quote))
                or type(price) is not int
                or price < 0
            ):
                raise WorkflowError(
                    "The original actual Handler supplies and prices this one real component"
                )
            _missing(self.game, c, state, request)
            for text in (name, description, procurement):
                _text(text)
            actual = resolve(state, request.actor, profiles(c, self.store.campaign_id))
            if actual.cell is None:
                raise WorkflowError(
                    "Record the original body's actual known delivery position first"
                )
            value = rules.Quote(
                id=event,
                request=request_id,
                actor=request.actor,
                vessel=request.vessel,
                part=request.part,
                component=str(uuid5(NAMESPACE_URL, "casualty-component:" + event)),
                name=name.strip(),
                description=description.strip(),
                procurement=procurement.strip(),
                price=price,
                cell=actual.cell,
                event=event,
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.casualty_component_quoted",
                state,
                event_id=event,
                quote=value.id,
                request=request_id,
                price=price,
            )
            return dict(id=value.id, revision=state.revision)

        return self._write(
            viewer,
            key,
            "m3.casualty_component_quoted",
            dict(
                revision=revision,
                request=request_id,
                name=name,
                description=description,
                procurement=procurement,
                price=price,
            ),
            operation,
        )

    def install(
        self, viewer: GuildViewer, key: str, revision: int, quote_id: str, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            _text(account)
            value = prove_quote(self.game, c, state, quote_id)
            if current_ref(state, viewer.user_id) != value.actor:
                raise WorkflowError(
                    "Only the original body human confirms this actual installation"
                )
            request = prove_request(self.game, c, state, value.request)
            _missing(self.game, c, state, request)
            actual = resolve(state, value.actor, profiles(c, self.store.campaign_id))
            if actual.cell != value.cell:
                raise WorkflowError(
                    "SOURCE_DELIVERY_REQUIRED: supply this component at the body's actual position"
                )
            payment = prepare_payment(
                self.game, c, state, viewer, value.actor, PRODUCT, value.price, value.id
            )
            identity = str(uuid4())
            debit(state, value.actor, value.price, event=event, source=identity, payment=payment)
            installed = rules.Installation(
                id=identity,
                quote=value.id,
                request=value.request,
                actor=value.actor,
                vessel=value.vessel,
                part=value.part,
                component=value.component,
                change=str(uuid5(NAMESPACE_URL, "casualty-component:" + identity)),
                event=event,
                payment=payment.approval,
                account=account.strip(),
            )
            rules.install_component(state, installed, value, request)
            state.sheets[value.actor.entity].revision += 1
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.casualty_component_installed",
                state,
                event_id=event,
                installation=identity,
                quote=quote_id,
                price=value.price,
            )
            _post(self.game, c, value.actor, event, viewer, key)
            return dict(id=identity, revision=load_state(c, self.store.campaign_id).revision)

        return self._write(
            viewer,
            key,
            "m3.casualty_component_installed",
            dict(revision=revision, quote=quote_id, account=account),
            operation,
        )

    def request_payment(
        self, viewer: GuildViewer, key: str, revision: int, quote_id: str, account: str
    ) -> dict[str, Any]:
        from girlframe.services.m3_intracadre_marriage import MarriageService

        with self.store.engine.connect() as c:
            _access(self.game, c, viewer, casualty.GOD)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            quote_price(self.game, c, state, actor, quote_id)
            quote = rules.get(state, rules.Quote, quote_id)
            _missing(self.game, c, state, prove_request(self.game, c, state, quote.request))
            source = marriage_for(state, actor)
            if source is None or source.financial == actor:
                raise WorkflowError("Your own actual installation decides your own-wallet payment")
        return MarriageService(self.store, self.game).request_payment(
            viewer,
            key,
            source.id,
            revision,
            PRODUCT,
            quote_id,
            account,
        )

    def _visible(self, c: Connection, viewer: GuildViewer, request: rules.Request) -> None:
        _access(self.game, c, viewer, casualty.GOD)
        if viewer.user_id not in (int(request.actor.entity), request.handler_controller):
            raise WorkflowError(
                "Only the original body human and source Handler can read this package"
            )

    def _view(
        self, c: Connection, viewer: GuildViewer, state: GameState, request: rules.Request
    ) -> dict[str, Any]:
        self._visible(c, viewer, request)
        prove_request(self.game, c, state, request.id)
        quoted = next(
            (x for x in rules.records(state, rules.Quote) if x.request == request.id), None
        )
        installed = next(
            (x for x in rules.records(state, rules.Installation) if x.request == request.id), None
        )
        if quoted:
            prove_quote(self.game, c, state, quoted.id)
        if installed:
            prove_replacement(self.game, c, state, installed.id)
        owner = viewer.user_id == int(request.actor.entity)
        sheet = state.sheets.get(request.actor.entity)
        own_source = owner and sheet is not None and sheet.character_id == request.actor.incarnation
        handler = (
            viewer.user_id == request.handler_controller
            and active_handler(state) == request.handler
        )
        blocked = None
        if installed is None:
            try:
                _missing(self.game, c, state, request)
            except (WorkflowError, ValueError) as error:
                blocked = str(error)
        return dict(
            blocked=blocked,
            id=request.id,
            revision=state.revision,
            part=request.part,
            label=casualty.LABELS[request.part],
            request=request.model_dump(mode="json"),
            quote=quoted.model_dump(mode="json") if quoted else None,
            installation=installed.model_dump(mode="json") if installed else None,
            phase="complete" if installed else "install" if quoted else "quote",
            can_quote=handler and quoted is None and blocked is None,
            can_install=own_source and quoted is not None and installed is None and blocked is None,
            can_request_payment=own_source
            and blocked is None
            and quoted is not None
            and installed is None
            and marriage_for(state, request.actor) is not None
            and wallet(state, request.actor) != request.actor,
        )

    def menu(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer, casualty.GOD)
            state = load_state(c, self.store.campaign_id)
            missing = []
            own = state.sheets.get(str(viewer.user_id))
            if own and own.character_id:
                actor = current_ref(state, viewer.user_id)
                body = casualty.body(state, actor)
                if body:
                    _live(self.game, c, state, actor)
                    missing = [
                        dict(id=x.id, label=casualty.LABELS[x.id])
                        for x in body.parts
                        if x.id != "brain"
                        and x.condition in ("destroyed", "removed")
                        and not any(
                            r.actor == actor
                            and r.part == x.id
                            and not any(
                                i.request == r.id for i in rules.records(state, rules.Installation)
                            )
                            for r in rules.records(state, rules.Request)
                        )
                    ]
            return dict(
                revision=state.revision,
                missing=missing,
                records=[
                    self._view(c, viewer, state, x)
                    for x in rules.records(state, rules.Request)
                    if viewer.user_id in (int(x.actor.entity), x.handler_controller)
                ],
            )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            request = next(
                (x for x in rules.records(state, rules.Request) if x.id == identity), None
            )
            if request is None:
                quote = next(
                    (x for x in rules.records(state, rules.Quote) if x.id == identity), None
                )
                installed = next(
                    (x for x in rules.records(state, rules.Installation) if x.id == identity), None
                )
                if quote is None and installed is None:
                    raise WorkflowError("Recover the actual original replacement request")
                request = rules.get(
                    state,
                    rules.Request,
                    quote.request if quote else installed.request if installed else "",
                )
            return self._view(c, viewer, state, request)

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        for request in rules.records(state, rules.Request):
            if viewer.user_id not in (int(request.actor.entity), request.handler_controller):
                continue
            value = self._view(c, viewer, state, request)
            result.append(
                dict(
                    id=request.id,
                    revision=state.revision,
                    label="Casualty replacement: " + value["label"],
                    phase=value["phase"],
                    pending=bool(value["can_quote"] or value["can_install"]),
                    waiting=value["phase"] != "complete"
                    and not (value["can_quote"] or value["can_install"]),
                )
            )
        return result
