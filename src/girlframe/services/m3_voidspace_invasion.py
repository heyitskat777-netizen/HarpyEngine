"""Voidspace Invasion starts only once the same actual Cadre crosses a real Rift."""

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_voidspace_invasion as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_harpy_defeat import offstage_travel
from girlframe.engine.m3_harpy_defeat_state import Rift, Travel
from girlframe.engine.m3_intracadre_marriage import status_groups
from girlframe.engine.m3_janus_storage import effective_assets
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_harpy_defeat import HarpyDefeatService
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _saved(
    game: GameService, c: Connection, event: str, kind: str, actor: int | None = None
) -> GameState | None:
    table = t.m2["m2_state_history"]
    conditions = [
        table.c.campaign_id == game.store.campaign_id,
        table.c.event_id == event,
        t.events.c.campaign_id == game.store.campaign_id,
        t.events.c.kind == kind,
    ]
    if actor is not None:
        conditions.append(t.events.c.actor_id == str(actor))
    raw = c.scalar(
        sa.select(table.c.body_json)
        .join(t.events, t.events.c.id == table.c.event_id)
        .where(*conditions)
    )
    return GameState.model_validate_json(raw) if raw else None


def _proved(game: GameService, c: Connection, value: rules.Invasion) -> None:
    initial = _saved(game, c, value.id, "m3.voidspace_invasion_roll", value.gm)
    if initial is None or value.model_copy(
        update=dict(route=None, discovery=None)
    ) not in rules.records(initial):
        raise WorkflowError("Recover the original Cadre’s exact Voidspace roll")
    if value.discovery:
        proof = _saved(game, c, value.discovery, "m3.voidspace_invasion_route", value.gm)
        if proof is None or value not in rules.records(proof):
            raise WorkflowError("Recover the actual discoverable route")


def navigation(
    game: GameService, c: Connection, state: GameState, discovery: str, prior: Travel
) -> str:
    value = next((x for x in rules.records(state) if x.discovery == discovery), None)
    if (
        value is None
        or not value.route
        or prior.state != "offstage"
        or value.rift != prior.rift
        or not any(
            x.actor == prior.actor and x.controller == prior.controller and x.travel == prior.id
            for x in value.cadre
        )
        or not value.discovery
        or MedicalService(game.store)._handler(c) != (value.gm, value.appointment)
    ):
        raise WorkflowError("Use the original actor’s discovered Voidspace route")
    try:
        Access(game.store).require_specialist_rule(rules.RULE)
    except ValueError as error:
        raise WorkflowError(str(error)) from None
    _proved(game, c, value)
    return value.route


class InvasionService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _gate(self, c: Connection, viewer: GuildViewer) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "plays", director_response=True)
        access.authorize(c, viewer, "world", director_response=True)
        access.require_specialist_rule(rules.RULE)

    def _crossing(
        self,
        c: Connection,
        state: GameState,
        rift: str,
    ) -> tuple[Rift, tuple[rules.Traversal, ...], tuple[ActorRef, ...]]:
        portal = next((x for x in state.void_rifts if x.id == rift), None)
        groups = status_groups(state)
        if portal is None or not groups or not state.order or state.world is None:
            raise WorkflowError("Recover the actual Rift and original Cadre")
        actual = []
        service = HarpyDefeatService(self.store, self.game)
        gm, appointment = MedicalService(self.store)._handler(c)
        for owner in state.order:
            actor = current_ref(state, owner)
            travel = offstage_travel(state, actor)
            if (
                travel is None
                or travel.rift != rift
                or not travel.response_event
                or travel.controller != owner
                or travel.state != "offstage"
                or (travel.judge, travel.appointment) != (gm, appointment)
            ):
                raise WorkflowError("The whole original Cadre must actually traverse this Rift")
            service._travel_proof(c, travel)
            final = _saved(self.game, c, travel.response_event, "m3.harpy_route_reviewed", gm)
            if final is None or travel not in final.harpy_travels:
                raise WorkflowError("Recover each original Girl’s actual offstage traversal")
            actual.append(rules.Traversal(actor=actor, controller=owner, travel=travel.id))
        return portal, tuple(actual), tuple(current_ref(state, uid) for uid in groups[0])

    def tasks(
        self,
        c: Connection,
        state: GameState,
        viewer: GuildViewer,
    ) -> tuple[tuple[str, str], ...]:
        if not state.harpy_travels:
            return ()
        try:
            self._gate(c, viewer)
            gm, appointment = MedicalService(self.store)._handler(c)
        except (WorkflowError, ValueError):
            return ()
        items = []
        cases = rules.records(state)
        if gm == viewer.user_id:
            for rift in state.void_rifts:
                if any(x.rift == rift.id for x in cases):
                    continue
                try:
                    self._crossing(c, state, rift.id)
                except (WorkflowError, ValueError):
                    continue
                items.append((rift.id, "roll"))
        for case in cases:
            if (case.gm, case.appointment) != (gm, appointment):
                continue
            if case.discovery:
                if any(x.controller == viewer.user_id for x in case.cadre):
                    items.append((case.id, "route"))
            elif case.gm == viewer.user_id:
                items.append((case.id, "review"))
        return tuple(items)

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._gate(c, viewer)
            state = load_state(c, self.store.campaign_id)
            step = dict(self.tasks(c, state, viewer)).get(identity)
            if step is None:
                raise WorkflowError("This original private Invasion is unavailable")
            if step == "roll":
                _, _, aces = self._crossing(c, state, identity)
                return dict(
                    step=step,
                    revision=state.revision,
                    aces={x.token: state.sheets[x.entity].callsign for x in aces},
                )
            case = next(x for x in rules.records(state) if x.id == identity)
            _proved(self.game, c, case)
            traveler = (
                next((x for x in case.cadre if x.controller == viewer.user_id), None)
                if step == "route"
                else None
            )
            prior = offstage_travel(state, traveler.actor) if traveler else None
            return dict(
                step=step,
                revision=state.revision,
                tier=case.result,
                faces=case.faces,
                modifier=len(case.void_assets),
                route=case.route if step == "route" else None,
                discovery=case.discovery if step == "route" else None,
                traveler=(
                    traveler.actor.model_dump(mode="json")
                    if traveler and prior and prior.id == traveler.travel
                    else None
                ),
            )

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        payload: dict[str, Any],
        operation: Callable[[Connection], dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            return self.store._write(
                viewer,
                key,
                "m3.voidspace_invasion",
                payload,
                operation,
                authorize=lambda c: self._gate(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def start(
        self,
        viewer: GuildViewer,
        key: str,
        rift: str,
        revision: int,
        ace: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            state = load_state(c, self.store.campaign_id)
            gm, appointment = MedicalService(self.store)._handler(c)
            portal, cadre, aces = self._crossing(c, state, rift)
            chosen = next((x for x in aces if x.token == ace), None)
            if (
                gm != viewer.user_id
                or chosen is None
                or revision != state.revision
                or not 0 < len(account.strip()) <= 1200
                or any(x.rift == portal.id for x in rules.records(state))
            ):
                raise WorkflowError("Record one actual original Cadre's traversal and its Ace")
            event = str(uuid4())
            value = rules.Invasion(
                id=event,
                rift=rift,
                scene=portal.scene,
                gm=gm,
                appointment=appointment,
                cadre=cadre,
                ace=chosen,
                faces=self.game.dice.roll(),
                void_assets=tuple(x.id for x in effective_assets(state, chosen) if x.void),
                account=account.strip(),
            )
            rules.put(state, value)
            self.game.event(
                c, viewer.user_id, key, "m3.voidspace_invasion_roll", state, event_id=event
            )
            return dict(id=event, tier=value.result)

        return self._write(
            viewer, key, dict(rift=rift, revision=revision, ace=ace, account=account), operation
        )

    def route(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            state = load_state(c, self.store.campaign_id)
            case = next((x for x in rules.records(state) if x.id == identity), None)
            if (
                case is None
                or case.result != "mid"
                or case.discovery
                or MedicalService(self.store)._handler(c) != (case.gm, case.appointment)
                or viewer.user_id != case.gm
                or revision != state.revision
                or not 0 < len(account.strip()) <= 1200
            ):
                raise WorkflowError("Use this original mid result and its actual found route")
            _proved(self.game, c, case)
            _, cadre, _ = self._crossing(c, state, case.rift)
            if cadre != case.cadre:
                raise WorkflowError("Recover the entire original Cadre still making this journey")
            event = str(uuid4())
            rules.put(state, case.model_copy(update=dict(route=account.strip(), discovery=event)))
            self.game.event(
                c, viewer.user_id, key, "m3.voidspace_invasion_route", state, event_id=event
            )
            return dict(id=identity, discovery=event)

        return self._write(
            viewer, key, dict(id=identity, revision=revision, account=account), operation
        )
