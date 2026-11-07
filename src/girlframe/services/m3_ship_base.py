"""Genuine Ship-Base acquisition, physical cargo, ram dice and required low effects."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_ship_base as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_collateral import loss as loss_record
from girlframe.engine.m3_engage import Maneuver
from girlframe.engine.m3_handler_play_state import HandlerPlay
from girlframe.engine.m3_work_scope import WorkScope
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Cell, Location, ShipAuthority, ShipHull
from girlframe.engine.rolls import DiceSource, OsDice
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_advancement_acquisition import held, prove, record_spend
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.m3_incarnations import proof as character_proof
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def paid(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Acquisition:
    return prove(
        game,
        c,
        state,
        identity,
        rule=rules.RULE,
        receipts=rules.acquisitions,
        missing="Recover the actual Ship-Base acquisition",
        failure="Preserve the genuine original award and existing Base purchase",
    )


def boarding_proof(
    game: GameService, c: Connection, state: GameState, entry: rules.Boarding
) -> None:
    born = next(
        (
            x
            for x in rules.records(_history(c, game, entry.event), rules.Boarding)
            if x.id == entry.id
        ),
        None,
    )
    if born is None or any(
        getattr(born, k) != getattr(entry, k)
        for k in rules.Boarding.model_fields
        if k != "left_event"
    ):
        raise WorkflowError("Preserve the actual original human's source-proved physical boarding")
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == entry.event
        )
    ).first()
    if (
        audit is None
        or audit.kind != "m3.ship_boarded"
        or audit.actor_id != str(entry.controller)
        or json.loads(audit.payload_json).get("boarding") != entry.id
    ):
        raise WorkflowError("Only the real original human's boarding source controls this cargo")
    paid(game, c, state, entry.acquisition)
    if entry.left_event:
        if entry not in rules.records(_history(c, game, entry.left_event), rules.Boarding):
            raise WorkflowError("Recover this body's actual source-owned departure")


def ram_proof(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Ram:
    value = next((x for x in rules.records(state, rules.Ram) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual original Ship-Base ram receipt")
    receipt = paid(game, c, state, value.acquisition)
    born = _history(c, game, value.event)
    original = next((x for x in rules.records(born, rules.Ram) if x.id == identity), None)
    audit = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
        )
    ).first()
    hull = Location.model_validate_json(value.ship_before)
    expected_modifier = {"plain": 0, "opportunity": 2, "armoured": 4}[value.basis]
    expected_tier = "low" if value.total <= 7 else "mid" if value.total <= 10 else "high"
    if (
        original is None
        or any(
            getattr(original, k) != getattr(value, k)
            for k in rules.Ram.model_fields
            if k not in ("phase", "completed_event")
        )
        or audit != ("m3.ship_rammed", value.handler.entity)
        or (receipt.handler, receipt.appointment, receipt.base)
        != (value.handler, value.appointment, value.ship)
        or any(type(x) is not int or not 1 <= x <= 6 for x in value.faces)
        or value.modifier != expected_modifier
        or value.total != sum(value.faces) + expected_modifier
        or value.tier != expected_tier
        or hull.ship is None
        or value.basis == "armoured"
        and not hull.ship.armoured
    ):
        raise WorkflowError(
            "Preserve actual faces, single modifier, prior armour and original ram source"
        )
    from girlframe.services.m3_girl_insurance import _before

    before = _before(game, c, value.event)
    prior_ship = rules.base(before, value.ship)
    born_ship = rules.base(born, value.ship)
    prior_threat = (
        next((x for x in before.world.gorgons if x.id == value.threat.entity), None)
        if before.world
        else None
    )
    born_threat = (
        next((x for x in born.world.gorgons if x.id == value.threat.entity), None)
        if born.world
        else None
    )
    if (
        prior_ship.model_dump_json() != value.ship_before
        or prior_threat is None
        or prior_threat.model_dump_json() != value.threat_before
        or receipt not in rules.acquisitions(before)
        or prior_ship.ship is None
        or born_ship.ship is None
        or born_threat is None
    ):
        raise WorkflowError("Recover the actual pre-ram Base, threat and prior acquisition")
    captain = next(
        (
            x
            for x in rules.records(before, rules.Boarding)
            if x.actor == value.handler and x.ship == value.ship and x.left_event is None
        ),
        None,
    )
    if captain is None:
        raise WorkflowError(
            "Prove the actual original Handler was genuinely boarded before ramming"
        )
    boarding_proof(game, c, before, captain)
    damaged = value.basis == "armoured" or value.tier in ("low", "high")
    damage_count = prior_ship.ship.damage_count + int(damaged and prior_ship.ship.armoured)
    destroyed = value.tier == "high" and (value.basis == "armoured" or not prior_ship.ship.armoured)
    if (
        born_ship.ship.damage_count != damage_count
        or born_ship.ship.armoured != (prior_ship.ship.armoured and not damaged)
        or (born_ship.condition == "destroyed") != destroyed
        or value.tier != "low"
        and not born_threat.exposed
        or value.tier == "high"
        and not any(x.id == value.asset and x.damaged for x in born_threat.assets)
    ):
        raise WorkflowError("Preserve actual armour expenditure and the printed real ram effects")
    if value.basis == "opportunity":
        opportunity(game, c, before, value.opportunity or "", value.threat)
    if value.tier == "low" and value.phase == "complete":
        if not value.completed_event:
            raise WorkflowError("A low ram requires its actual completed Handler consequence")
        ended = _history(c, game, value.completed_event)
        if value not in rules.records(ended, rules.Ram) or not any(
            x.id == value.low_grant
            and x.state == "complete"
            and x.completed_event == value.completed_event
            for x in ended.handler_plays
        ):
            raise WorkflowError("An acknowledgment cannot close the actual low Handler effect")
    return value


def prove_low_grant(
    game: GameService, c: Connection, state: GameState, grant: HandlerPlay
) -> rules.Ram:
    value = ram_proof(game, c, state, grant.source_action or "")
    original = _history(c, game, value.event)
    born = next((x for x in original.handler_plays if x.id == grant.id), None)
    if (
        value.tier != "low"
        or value.low_grant != grant.id
        or born is None
        or grant.source != "required"
        or grant.clause != "ship_base.low"
        or grant.source_action != value.id
        or grant.source_choice != value.id + ":low"
        or grant.chooser_actor is not None
        or grant.chooser_controller != value.judge
        or grant.appointment != value.judge_appointment
        or grant.targets != value.cadre
        or grant.scope != born.scope
        or grant.target_controllers != born.target_controllers
        or any(
            getattr(born, k) != getattr(grant, k)
            for k in ("source_event", "source", "clause", "source_action", "source_choice")
        )
    ):
        raise WorkflowError(
            "Use the actual low ram's mandatory procedural GM Play against its original Cadre"
        )
    return value


def complete_low(
    game: GameService, c: Connection, state: GameState, grant: HandlerPlay, event: str
) -> None:
    value = prove_low_grant(game, c, state, grant)
    if grant.state != "complete" or grant.completed_event != event or grant.effect is None:
        raise WorkflowError("Finish the actual required Handler effect before closing the low ram")
    if value.phase == "complete" and value.completed_event != event:
        raise WorkflowError("The actual low consequence already completed once")
    rules.put(state, value.model_copy(update=dict(phase="complete", completed_event=event)))


def _current(
    game: GameService, c: Connection, state: GameState, receipt: rules.Acquisition
) -> Location:
    HandlerAdvancementService(game.store)._current(c, state, receipt.handler, receipt.appointment)
    ship = rules.base(state, receipt.base)
    if (
        ship.ship is None
        or ship.ship.acquisition != receipt.id
        or not ship.operational
        or ship.allegiance != "foundation"
    ):
        raise WorkflowError("Use the actual operational source-owned Foundation Ship-Base")
    actor = resolve(
        state, receipt.handler, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if actor.rules != "handler" or actor.offstage_source or actor.custody not in (None, "free"):
        raise WorkflowError("This Ship-Base needs its actual original available native Handler")
    return ship


def opportunity(
    game: GameService, c: Connection, state: GameState, identity: str, threat: ActorRef
) -> Maneuver:
    value = next(
        (
            Maneuver.model_validate_json(x["body"])
            for x in state.facts
            if x.get("kind") == "engage_maneuver"
            and x.get("event") == identity
            and Maneuver.model_validate_json(x["body"]).opponent == threat
        ),
        None,
    )
    if (
        value is None
        or value.actor.kind != "pilot"
        or current_ref(state, int(value.actor.entity)) != value.actor
    ):
        raise WorkflowError(
            "Use the original Cadre's actual completed opening against this exact threat"
        )
    born = _history(c, game, identity)
    action = game.action(c, value.source_action)
    if (
        value
        not in [
            Maneuver.model_validate_json(x["body"])
            for x in born.facts
            if x.get("kind") == "engage_maneuver"
        ]
        or action["state"] != "complete"
        or not action["data"].get("receipt")
        or action["data"].get("result", {}).get("maneuvers", {}).get(value.kind) != value.asset
        or not value.circumstances.strip()
    ):
        raise WorkflowError("An acknowledgment cannot replace the actual owned Cadre maneuver")
    return value


class ShipBaseService:
    def __init__(self, store: OnboardingStore, *, dice: DiceSource | None = None):
        self.store, self.game = store, GameService(store)
        self.dice = dice if dice is not None else OsDice()
        self.rng = "os" if dice is None else "test_injected"

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "world")
        assert gate.registry is not None
        gate.registry.require_available(rules.RULE)

    def _write(
        self, viewer: GuildViewer, key: str, kind: str, body: dict[str, Any], operation: Any
    ) -> dict[str, Any]:
        return self.store._write(
            viewer,
            key,
            kind,
            body,
            operation,
            authorize=lambda c: self._access(c, viewer),
            auto_audit=False,
        )

    def _safe(self, c: Connection, revision: int) -> GameState:
        from girlframe.services.m3_handler_plays import _ordinary_scene_idle

        self.game.unpaused(c)
        _ordinary_scene_idle(c, self.game)
        state = load_state(c, self.store.campaign_id)
        if state.revision != revision or any(
            x.phase == "awaiting_play" for x in rules.records(state, rules.Ram)
        ):
            raise WorkflowError(
                "Finish the actual required ship consequence and reopen current state"
            )
        return state

    def buy(
        self, viewer: GuildViewer, key: str, award: str, revision: int, base: str, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self._safe(c, revision)
            source = held(
                self.game,
                c,
                viewer,
                award,
                revision,
                account,
                failure="Spend one actual held award on an existing Foundation Base",
            )
            state = source.state
            location = (
                next((x for x in state.world.locations if x.id == base), None)
                if state.world
                else None
            )
            if (
                location is None
                or location.kind != "base"
                or location.allegiance != "foundation"
                or not location.operational
                or location.ship is not None
                or any(x.handler == source.handler for x in rules.acquisitions(state))
            ):
                raise WorkflowError(
                    "Choose one genuine existing operational unmodified Foundation Base"
                )
            event = str(uuid4())
            receipt = rules.Acquisition(
                id="ship:" + award,
                award=award,
                handler=source.handler,
                appointment=source.appointment,
                event=event,
                account=account.strip(),
                base=base,
                original_base_json=location.model_dump_json(),
            )
            rules.put(state, receipt)
            record_spend(state, source.award, receipt, rules.RULE)
            assert state.world is not None
            state.world = update(
                state.world,
                ship_sources=state.world.ship_sources
                + (ShipAuthority(acquisition=receipt.id, base=base, source_event=event),),
                locations=tuple(
                    x.model_copy(
                        update=dict(ship=ShipHull(acquisition=receipt.id, source_event=event))
                    )
                    if x.id == base
                    else x
                    for x in state.world.locations
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_advancement_spent",
                state,
                event_id=event,
                acquisition=receipt.id,
                award=award,
                rule=rules.RULE,
            )
            return dict(id=receipt.id, base=base)

        return self._write(
            viewer,
            key,
            "m3.ship_acquired",
            dict(award=award, revision=revision, base=base, account=account),
            operation,
        )

    def board(
        self,
        viewer: GuildViewer,
        key: str,
        acquisition: str,
        revision: int,
        actor: ActorRef,
        parts: Literal["body", "frame", "both"],
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._safe(c, revision)
            receipt = paid(self.game, c, state, acquisition)
            ship = rules.base(state, receipt.base)
            actual = resolve(
                state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if (
                not ship.operational
                or ship.ship is None
                or ship.ship.airborne
                or actual.controller != viewer.user_id
                or actual.offstage_source
                or actual.custody not in (None, "free")
                or not account.strip()
                or actor.kind not in ("pilot", "handler", "npc")
            ):
                raise WorkflowError(
                    "Your actual available original body boards the grounded source ship"
                )
            for old in rules.records(state, rules.Boarding):
                if (
                    old.actor == actor
                    and old.left_event is None
                    and (parts == "both" or old.parts == "both" or parts == old.parts)
                ):
                    raise WorkflowError(
                        "This actual body/Frame already has a source boarding record"
                    )
            vessel = frame = None
            if actor.kind == "pilot":
                character_proof(
                    c, self.store.campaign_id, state, viewer.user_id, require_current_profile=True
                )
                body = next((x for x in state.placements if x.actor == actor), None)
                if (
                    state.sheets[actor.entity].girl == "AM"
                    or body is None
                    or actual.vessel_id != body.vessel_id
                    or body.occupied_frame_owner is not None
                    or body.mode != "outside_frame"
                    and parts != "both"
                    or parts in ("body", "both")
                    and body.girl_cell != ship.cell
                    or parts in ("frame", "both")
                    and body.frame_cell != ship.cell
                    or body.custody is not None
                    or not body.vitals_active
                    or body.subsumed
                ):
                    raise WorkflowError(
                        "Record actual original body/Frame placement at this Base before boarding"
                    )
                vessel, frame = body.vessel_id, body.frame_instance
            elif (
                parts != "body"
                or actual.rules not in ("handler", "npc")
                or "director" in actual.jobs
                or actual.vessel_id is not None
            ):
                raise WorkflowError(
                    "Only this ordinary actual body has the finite boarding adapter"
                )
            elif actual.cell != ship.cell and not (actor.kind == "handler" and actual.cell is None):
                raise WorkflowError(
                    "Use real movement for a known body elsewhere; same-cell is not boarding"
                )
            if actor.kind == "handler" and actor != receipt.handler:
                raise WorkflowError("This finite source boards its original native Handler")
            event = str(uuid4())
            entry = rules.Boarding(
                id="ship-boarding:" + str(uuid4()),
                acquisition=receipt.id,
                ship=ship.id,
                actor=actor,
                controller=viewer.user_id,
                parts=parts,
                vessel=vessel,
                frame=frame,
                event=event,
                account=account.strip(),
            )
            rules.put(state, entry)
            if actor.kind == "handler":
                rules.position_fact(state, entry, ship.cell, event, account)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.ship_boarded",
                state,
                event_id=event,
                boarding=entry.id,
                ship=ship.id,
                actor_ref=actor.model_dump(mode="json"),
            )
            return dict(id=entry.id)

        return self._write(
            viewer,
            key,
            "m3.ship_boarded",
            dict(
                acquisition=acquisition,
                revision=revision,
                actor=actor.model_dump(mode="json"),
                parts=parts,
                account=account,
            ),
            operation,
        )

    def leave(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._safe(c, revision)
            entry = next(
                (x for x in rules.records(state, rules.Boarding) if x.id == identity), None
            )
            if (
                entry is None
                or entry.controller != viewer.user_id
                or entry.left_event
                or not account.strip()
            ):
                raise WorkflowError("Only the actual boarded human leaves this original body/Frame")
            boarding_proof(self.game, c, state, entry)
            ship = rules.base(state, entry.ship)
            if ship.ship is not None and ship.ship.airborne and ship.condition != "destroyed":
                raise WorkflowError("Actually land before this finite ordinary disembarkation")
            event = str(uuid4())
            rules.put(state, entry.model_copy(update=dict(left_event=event)))
            if entry.actor.kind == "handler":
                rules.position_fact(state, entry, ship.cell, event, account)
            self.game.event(
                c, viewer.user_id, key, "m3.ship_left", state, event_id=event, boarding=entry.id
            )
            return dict(id=entry.id)

        return self._write(
            viewer,
            key,
            "m3.ship_left",
            dict(identity=identity, revision=revision, account=account),
            operation,
        )

    def fly(
        self,
        viewer: GuildViewer,
        key: str,
        acquisition: str,
        revision: int,
        destination: Cell,
        airborne: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._safe(c, revision)
            source = paid(self.game, c, state, acquisition)
            _current(self.game, c, state, source)
            if source.handler.entity != str(viewer.user_id):
                raise WorkflowError("The original source Handler controls its actual flying Base")
            entries = [
                x
                for x in rules.records(state, rules.Boarding)
                if x.ship == source.base and x.left_event is None
            ]
            if not any(x.actor == source.handler and x.parts == "body" for x in entries):
                raise WorkflowError("Actually board the original Handler at the ship controls")
            for entry in entries:
                boarding_proof(self.game, c, state, entry)
            event, identity = str(uuid4()), "ship-flight:" + str(uuid4())
            try:
                result = rules.move(
                    state,
                    profiles(c, self.store.campaign_id),
                    source,
                    destination,
                    airborne,
                    identity,
                    event,
                    account,
                )
            except ValueError as error:
                raise WorkflowError(str(error)) from None
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.ship_flown",
                result,
                event_id=event,
                flight=identity,
                ship=source.base,
                destination=destination,
            )
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.ship_flown",
            dict(
                acquisition=acquisition,
                revision=revision,
                destination=destination,
                airborne=airborne,
                account=account,
            ),
            operation,
        )

    def ram(
        self,
        viewer: GuildViewer,
        key: str,
        acquisition: str,
        revision: int,
        threat: ActorRef,
        basis: Literal["plain", "opportunity", "armoured"],
        asset: str,
        account: str,
        *,
        opening: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = self._safe(c, revision)
            receipt = paid(self.game, c, state, acquisition)
            ship = _current(self.game, c, state, receipt)
            if (
                viewer.user_id != int(receipt.handler.entity)
                or threat.kind != "gorgon"
                or state.world is None
                or not account.strip()
            ):
                raise WorkflowError("The actual original Handler rams a real present threat")
            target = resolve(state, threat, ())
            gorgon = next(x for x in state.world.gorgons if x.id == threat.entity)
            captain = next(
                (
                    x
                    for x in rules.records(state, rules.Boarding)
                    if x.ship == ship.id and x.actor == receipt.handler and x.left_event is None
                ),
                None,
            )
            if (
                ship.ship is None
                or not ship.ship.airborne
                or captain is None
                or resolve(state, receipt.handler, (), require_current_profile=False).cell
                != ship.cell
                or target.cell != ship.cell
                or target.offstage_source
                or gorgon.gorgon_class in ("dormant", "benevolent")
                or gorgon.flesh_layers is not None
                or gorgon.protected_asset is not None
                and any(x.id == gorgon.protected_asset and not x.damaged for x in gorgon.assets)
                or not any(x.id == asset and not x.damaged for x in gorgon.assets)
            ):
                raise WorkflowError(
                    "Prove actual flying controls/reach and the ordinary threat's available Asset; "
                    "special Core/dormancy ports remain required"
                )
            boarding_proof(self.game, c, state, captain)
            if basis == "opportunity":
                opportunity(self.game, c, state, opening or "", threat)
            elif opening is not None:
                raise WorkflowError("Use only the chosen actual ram modifier source")
            if basis == "armoured" and not ship.ship.armoured:
                raise WorkflowError("Spend actual remaining Armoured before the dice")
            if basis not in ("plain", "opportunity", "armoured"):
                raise WorkflowError("Choose exactly one printed ram basis")
            judge, appointment = MedicalService(self.store)._handler(c)
            if target.controller != judge:
                raise WorkflowError(
                    "This finite normal threat uses its actual procedural GM controller"
                )
            if basis == "armoured":
                rules.damage_armour(state, ship.id)
            faces = self.dice.roll()
            if len(faces) != 2 or any(type(x) is not int or not 1 <= x <= 6 for x in faces):
                raise WorkflowError("The actual source must return two real d6 faces")
            modifier = {"plain": 0, "opportunity": 2, "armoured": 4}[basis]
            total = sum(faces) + modifier
            tier = "low" if total <= 7 else "mid" if total <= 10 else "high"
            event, identity = str(uuid4()), "ship-ram:" + str(uuid4())
            value = rules.Ram.model_validate(
                dict(
                    id=identity,
                    acquisition=receipt.id,
                    ship=ship.id,
                    handler=receipt.handler,
                    appointment=receipt.appointment,
                    threat=threat,
                    threat_controller=target.controller,
                    ship_before=ship.model_dump_json(),
                    threat_before=gorgon.model_dump_json(),
                    basis=basis,
                    opportunity=opening,
                    faces=faces,
                    modifier=modifier,
                    total=total,
                    tier=tier,
                    rng=self.rng,
                    asset=asset,
                    event=event,
                    account=account.strip(),
                    judge=judge,
                    judge_appointment=appointment,
                    cadre=tuple(current_ref(state, uid) for uid in state.order),
                    low_grant=rules.low_grant_id(identity) if tier == "low" else None,
                    phase="awaiting_play" if tier == "low" else "complete",
                    completed_event=None if tier == "low" else event,
                )
            )
            result = rules.apply_ram(state, value)
            actual = next(x for x in rules.records(result, rules.Ram) if x.id == identity)
            if tier == "low":
                assert actual.low_grant is not None
                result.handler_plays.append(
                    HandlerPlay(
                        id=actual.low_grant,
                        source="required",
                        source_event=event,
                        source_action=identity,
                        source_choice=identity + ":low",
                        clause="ship_base.low",
                        chooser_actor=None,
                        chooser_controller=judge,
                        appointment=appointment,
                        targets=actual.cadre,
                        target_controllers={x.token: int(x.entity) for x in actual.cadre},
                        scope=WorkScope(campaign_context=True),
                    )
                )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.ship_rammed",
                result,
                event_id=event,
                ram=identity,
                ship=ship.id,
                threat=threat.model_dump(mode="json"),
                faces=faces,
                modifier=modifier,
            )
            if actual.loss:
                from girlframe.services.m3_quadrant_loss import materialize_loss

                materialize_loss(self.game, c, loss_record(result, actual.loss), event)
            return dict(id=identity, tier=tier, total=total, low_grant=actual.low_grant)

        return self._write(
            viewer,
            key,
            "m3.ship_rammed",
            dict(
                acquisition=acquisition,
                revision=revision,
                threat=threat.model_dump(mode="json"),
                basis=basis,
                asset=asset,
                account=account,
                opening=opening,
            ),
            operation,
        )

    def menu(self, viewer: GuildViewer, identity: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            ram = next((x for x in rules.records(state, rules.Ram) if x.id == identity), None)
            if ram:
                ram_proof(self.game, c, state, ram.id)
                if viewer.user_id not in (int(ram.handler.entity), ram.judge):
                    raise WorkflowError(
                        "This actual ram history belongs to its original source people"
                    )
                return dict(kind="ram", revision=state.revision, body=ram.model_dump(mode="json"))
            receipt = next(
                (
                    x
                    for x in rules.acquisitions(state)
                    if x.id == identity
                    or identity is None
                    and x.handler.entity == str(viewer.user_id)
                ),
                None,
            )
            if receipt:
                paid(self.game, c, state, receipt.id)
                ship = rules.base(state, receipt.base)
                owner = receipt.handler.entity == str(viewer.user_id)
                bound = profiles(c, self.store.campaign_id)
                own_refs = []
                if str(viewer.user_id) in state.sheets:
                    own_refs.append(current_ref(state, viewer.user_id))
                if state.handler == viewer.user_id:
                    own_refs.append(current_ref(state, viewer.user_id))
                if state.world:
                    own_refs += [
                        ActorRef(kind="npc", entity=x.id)
                        for x in state.world.npcs
                        if x.alive and x.controller == viewer.user_id and "director" not in x.jobs
                    ]
                return dict(
                    kind="ship",
                    revision=state.revision,
                    acquisition=receipt.id,
                    ship=dict(
                        id=ship.id,
                        name=ship.name,
                        cell=ship.cell,
                        condition=ship.condition,
                        armoured=ship.ship.armoured if ship.ship else False,
                        airborne=ship.ship.airborne if ship.ship else False,
                    ),
                    owner=owner,
                    actors=[
                        dict(
                            ref=x.model_dump(mode="json"),
                            label=resolve(state, x, bound, require_current_profile=False).label,
                        )
                        for x in own_refs
                    ],
                    boardings=[
                        x.model_dump(mode="json")
                        for x in rules.records(state, rules.Boarding)
                        if x.ship == ship.id
                        and x.controller == viewer.user_id
                        and x.left_event is None
                    ],
                    threats=[
                        dict(
                            ref=ActorRef(kind="gorgon", entity=x.id).model_dump(mode="json"),
                            name=x.name,
                            assets=[dict(id=a.id, name=a.name) for a in x.assets if not a.damaged],
                        )
                        for x in state.world.gorgons
                        if x.alive
                        and x.cell == ship.cell
                        and x.gorgon_class not in ("dormant", "benevolent")
                    ]
                    if state.world and owner
                    else [],
                    opportunities=[
                        dict(
                            id=x["event"],
                            label=Maneuver.model_validate_json(x["body"]).circumstances[:100],
                        )
                        for x in state.facts
                        if x.get("kind") == "engage_maneuver"
                    ]
                    if owner
                    else [],
                )
            if identity:
                source = HandlerAdvancementService(self.store)._source(c, viewer, identity)
                if source[-1] is None or source[-1].phase != "held":
                    raise WorkflowError("Choose an actual held Handler award")
                return dict(
                    kind="buy",
                    revision=state.revision,
                    award=identity,
                    bases=[
                        dict(id=x.id, name=x.name)
                        for x in state.world.locations
                        if x.kind == "base"
                        and x.allegiance == "foundation"
                        and x.operational
                        and x.ship is None
                    ]
                    if state.world
                    else [],
                )
            return dict(
                kind="ships",
                revision=state.revision,
                ships=[dict(id=x.id, name=x.base) for x in rules.acquisitions(state)],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        rows = [
            dict(
                id=x.id,
                revision=state.revision,
                label="Actual Ship-Base",
                phase="acquired",
                pending=False,
            )
            for x in rules.acquisitions(state)
        ]
        rows += [
            dict(
                id=x.id,
                revision=state.revision,
                label="Actual Ship-Base ram",
                phase=x.phase,
                pending=x.phase == "awaiting_play" and viewer.user_id == x.judge,
            )
            for x in rules.records(state, rules.Ram)
            if viewer.user_id in (int(x.handler.entity), x.judge)
        ]
        return rows
