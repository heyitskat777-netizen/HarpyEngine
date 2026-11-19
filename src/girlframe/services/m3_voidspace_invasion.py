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
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_harpy_defeat import offstage_travel
from girlframe.engine.m3_harpy_defeat_state import Rift, Travel
from girlframe.engine.m3_intracadre_marriage import status_groups
from girlframe.engine.m3_janus_storage import alter, effective_assets
from girlframe.engine.m3_void import FINAL
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_harpy_defeat import HarpyDefeatService
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

VOID = "voidspace_invasion_gain"


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
    base = value.model_copy(update=dict(encounter=None, gains=()))
    if initial is None or base.model_copy(
        update=dict(route=None, discovery=None)
    ) not in rules.records(initial):
        raise WorkflowError("Recover the original Cadre’s exact Voidspace roll")
    if value.discovery:
        proof = _saved(game, c, value.discovery, "m3.voidspace_invasion_route", value.gm)
        if proof is None or base not in rules.records(proof):
            raise WorkflowError("Recover the actual discoverable route")
    if value.encounter:
        proof = _saved(game, c, value.encounter.event, "m3.voidspace_invasion_encounter", value.gm)
        if proof is None or value.model_copy(update=dict(gains=())) not in rules.records(proof):
            raise WorkflowError("Recover the actual original Voidspace encounter")
    for index, gain in enumerate(value.gains, start=1):
        proof = _saved(game, c, gain.event, "m3.voidspace_invasion_gain", int(gain.actor.entity))
        if proof is None or value.model_copy(
            update=dict(gains=value.gains[:index])
        ) not in rules.records(proof):
            raise WorkflowError("Recover the actual original actor’s Void gain")


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
        or (value.result == "high" and value.encounter is None)
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

    def _settled(self, c: Connection, case: rules.Invasion) -> bool:
        if len(case.gains) != len(case.cadre):
            return False
        table = t.m3["m3_required_work"]
        return all(
            gain.work is None
            or c.scalar(
                sa.select(table.c.state)
                .where(table.c.campaign_id == self.store.campaign_id, table.c.id == gain.work)
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            == "resolved"
            for gain in case.gains
        )

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
            member = next((x for x in case.cadre if x.controller == viewer.user_id), None)
            if case.result == "low" and case.encounter:
                if member and not any(x.actor == member.actor for x in case.gains):
                    items.append((case.id, "gain"))
                elif member:
                    items.append((case.id, "settled" if self._settled(c, case) else "report"))
            elif case.result == "high" and case.discovery and not case.encounter:
                if case.gm == viewer.user_id:
                    items.append((case.id, "encounter"))
            elif case.discovery:
                if member:
                    items.append((case.id, "route"))
            elif case.result == "low" and case.gm == viewer.user_id:
                items.append((case.id, "encounter"))
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
            member = next((x for x in case.cadre if x.controller == viewer.user_id), None)
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
                encounters={
                    key: label
                    for key, (_actor, label, _source) in self._encounters(c, state, case).items()
                }
                if step == "encounter"
                else {},
                encounter=case.encounter.label
                if case.encounter and step in ("gain", "report", "route", "settled")
                else None,
                assets=self._assets(c, state, member) if step == "gain" and member else {},
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
                or case.result not in ("mid", "high")
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

    def _encounters(
        self, c: Connection, state: GameState, case: rules.Invasion
    ) -> dict[str, tuple[ActorRef, str, str]]:
        portal = next((x for x in state.void_rifts if x.id == case.rift), None)
        if portal is None or state.world is None:
            return {}
        service = HarpyDefeatService(self.store, self.game)
        people: dict[ActorRef, str] = {
            ActorRef(kind="external_pilot", entity=x.id): x.kind
            for x in state.world.pilots
            if x.kind in ("harpy", "rebel") and x.alive
        }
        people.update(
            {ActorRef(kind="gorgon", entity=x.id): "gorgon" for x in state.world.gorgons if x.alive}
        )
        result = {}
        bound = profiles(c, self.store.campaign_id)
        for actor, kind in people.items():
            actual = resolve(state, actor, bound, require_current_profile=False)
            if actual.cell is not None or not actual.alive or actual.custody not in (None, "free"):
                continue
            travel = offstage_travel(state, actor)
            if travel and travel.rift == case.rift and travel.response_event:
                service._travel_proof(c, travel)
                saved = _saved(
                    self.game, c, travel.response_event, "m3.harpy_route_reviewed", travel.judge
                )
                if saved and travel in saved.harpy_travels:
                    result[actor.token] = actor, actual.label, travel.id
            elif kind == "harpy" and actor == portal.owner:
                original = self.game.action(c, portal.action)
                declared = service._declaration(c, original)
                if (
                    original["state"] == "complete"
                    and declared.actor == actor
                    and any(
                        x.action == portal.action
                        and x.source_event == portal.source_event
                        and x.actor == actor
                        and x.choice == "rift"
                        and x.escaped
                        for x in state.harpy_defeats
                    )
                ):
                    result[actor.token] = actor, actual.label, portal.source_event
        return result

    def encounter(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, target: str, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            state = load_state(c, self.store.campaign_id)
            step = dict(self.tasks(c, state, viewer)).get(identity)
            if (
                step != "encounter"
                or state.revision != revision
                or not 0 < len(account.strip()) <= 1200
            ):
                raise WorkflowError("Recover the original permitted encounter choice")
            case = next(x for x in rules.records(state) if x.id == identity)
            _proved(self.game, c, case)
            _, current, _ = self._crossing(c, state, case.rift)
            actual = self._encounters(c, state, case).get(target)
            if current != case.cadre or actual is None:
                raise WorkflowError("Choose a genuine original encounter in this Rift")
            actor, label, source = actual
            event = str(uuid4())
            finding = rules.Encounter(
                actor=actor, label=label, event=event, source=source, account=account.strip()
            )
            rules.put(state, case.model_copy(update=dict(encounter=finding)))
            self.game.event(
                c, viewer.user_id, key, "m3.voidspace_invasion_encounter", state, event_id=event
            )
            return dict(id=identity, event=event)

        return self._write(
            viewer,
            key,
            dict(id=identity, revision=revision, target=target, account=account),
            operation,
        )

    def _assets(self, c: Connection, state: GameState, member: rules.Traversal) -> dict[str, str]:
        sheet = state.sheets.get(member.actor.entity)
        if sheet is None or sheet.character_id != member.actor.incarnation:
            return {}
        actual = resolve(
            state, member.actor, profiles(c, self.store.campaign_id), require_current_profile=False
        )
        return {
            x.id: x.name
            for x in effective_assets(state, member.actor)
            if not x.void and (x.family == "girl" or actual.piloting is True)
        }

    def gain(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, asset: str, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            MedicalService(self.store)._idle(c)
            state = load_state(c, self.store.campaign_id)
            if (
                dict(self.tasks(c, state, viewer)).get(identity) != "gain"
                or state.revision != revision
                or not 0 < len(account.strip()) <= 1200
            ):
                raise WorkflowError("Use your original Cadre member’s exact Void choice")
            case = next(x for x in rules.records(state) if x.id == identity)
            _proved(self.game, c, case)
            member = next(x for x in case.cadre if x.controller == viewer.user_id)
            travel = offstage_travel(state, member.actor)
            if (
                travel is None
                or travel.id != member.travel
                or asset not in self._assets(c, state, member)
                or any(
                    x.actor == member.actor and x.stage not in FINAL for x in state.void_thresholds
                )
            ):
                raise WorkflowError("Choose your actual clean eligible Asset in this traversal")
            original = next(x for x in state.sheets[member.actor.entity].assets if x.id == asset)
            actual = resolve(
                state,
                member.actor,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
            event = str(uuid4())
            state, effects = alter(
                state,
                member.actor,
                asset,
                account.strip(),
                case.id,
                event,
                piloting=actual.piloting is True,
            )
            applied = any(x.id == asset and x.void for x in effective_assets(state, member.actor))
            family = original.family
            work = (
                f"{event}:invasion:{family}"
                if applied
                and any(
                    x.kind == f"{family}_void_threshold"
                    or family == "frame"
                    and x.kind == "mockingbird_resist"
                    for x in effects
                )
                else None
            )
            changed = rules.Gain(
                actor=member.actor, event=event, asset=asset if applied else None, work=work
            )
            rules.put(state, case.model_copy(update=dict(gains=(*case.gains, changed))))
            self.game.event(
                c, viewer.user_id, key, "m3.voidspace_invasion_gain", state, event_id=event
            )
            if work:
                related(
                    c,
                    self.store,
                    dict(campaign_id=self.store.campaign_id, scene_id=case.scene),
                    work,
                    viewer.user_id,
                    viewer.user_id,
                    "void_threshold",
                    dict(
                        owner=member.actor.model_dump(mode="json"),
                        character=member.actor.incarnation,
                        source_action=None,
                        source_pdf=19,
                        reason=VOID,
                        case=case.id,
                        details=dict(family=family),
                    ),
                    event,
                )
            return dict(id=identity, event=event, work=work)

        return self._write(
            viewer,
            key,
            dict(id=identity, revision=revision, asset=asset, account=account),
            operation,
        )


def prove_void(
    game: GameService,
    c: Connection,
    state: GameState,
    row: dict[str, Any],
    body: dict[str, Any],
    actor: ActorRef,
) -> None:
    value = next((x for x in rules.records(state) if x.id == body.get("case")), None)
    if (
        value is None
        or value.result != "low"
        or not value.encounter
        or value.scene != row["scene_id"]
        or not any(
            x.actor == actor
            and x.event == row["event_id"]
            and x.work == row["id"]
            and any(a.id == x.asset and a.void for a in effective_assets(state, actor))
            for x in value.gains
        )
    ):
        raise WorkflowError("Recover the original verified whole-Cadre Void source")
    _proved(game, c, value)


def audience(game: GameService, c: Connection, state: GameState, body: dict[str, Any]) -> list[int]:
    value = next((x for x in rules.records(state) if x.id == body.get("case")), None)
    actor = ActorRef.model_validate(body["owner"])
    if (
        value is None
        or not any(x.actor == actor for x in value.cadre)
        or MedicalService(game.store)._handler(c) != (value.gm, value.appointment)
    ):
        raise WorkflowError("Recover the original Cadre Void consequence’s scope")
    return sorted({int(actor.entity), value.gm})
