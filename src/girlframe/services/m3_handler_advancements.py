"""Genuine Void6/7 awards, original Handler ownership and atomic group grants."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_advancements as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_budget_tags import _selection, _work
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _history(c: Connection, game: GameService, event: str) -> GameState:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    if raw is None:
        raise WorkflowError("Recover this actual advancement's immutable source history")
    return GameState.model_validate_json(raw)


def _appointment_at(c: Connection, game: GameService, event: str, handler: ActorRef) -> str:
    sequence = c.scalar(
        sa.select(t.events.c.seq).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    )
    row = (
        c.execute(
            sa.select(t.setup_revisions.c.event_id, t.setup_revisions.c.body_json)
            .join(t.events, t.events.c.id == t.setup_revisions.c.event_id)
            .where(
                t.setup_revisions.c.campaign_id == game.store.campaign_id,
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.kind == "campaign.handler_appointed",
                t.events.c.seq <= sequence,
            )
            .order_by(t.setup_revisions.c.revision.desc())
            .limit(1)
        ).first()
        if sequence
        else None
    )
    if row is None or json.loads(row.body_json).get("handler_id") != int(handler.entity):
        raise WorkflowError("Recover the actual original Handler appointment at source selection")
    return str(row.event_id)


class HandlerAdvancementService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer, rule: str) -> None:
        gate = Access(self.store)
        gate.authorize(
            c, viewer, "strain" if rule in rules.RULES else "playbooks", director_response=True
        )
        gate.authorize(c, viewer, "economy", director_response=True)
        assert gate.registry is not None
        gate.registry.require_available(rule)

    def _spent(self, c: Connection, value: rules.Award, handler: ActorRef) -> None:
        identity = value.id
        if value.phase == "spent":
            assert value.spend_event is not None
            spent = _history(c, self.game, value.spend_event)
            recorded = next((x for x in rules.awards(spent) if x.id == identity), None)
            audit = c.execute(
                sa.select(t.events.c.kind, t.events.c.actor_id).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == value.spend_event,
                )
            ).first()
            if (
                recorded != value
                or audit is None
                or audit.kind != "m3.handler_advancement_spent"
                or audit.actor_id != handler.entity
                or value.acquired_rule is None
                and any(
                    effect.actor.entity not in spent.sheets
                    or spent.sheets[effect.actor.entity].character_id != effect.actor.incarnation
                    for effect in value.effects
                )
            ):
                raise WorkflowError("Recover this actual consumed advancement and group effects")
            from girlframe.services.m3_intracadre_marriage import prove_flow

            for index, effect in enumerate(value.effects):
                flow = prove_flow(
                    self.game,
                    c,
                    spent,
                    spent,
                    effect.actor,
                    value.spend_event,
                    "award:" + str(index),
                    effect.amount,
                )
                if flow is None:
                    if spent.sheets[effect.actor.entity].permissions != effect.after:
                        raise WorkflowError("Recover the actual original Permission grant")
                elif (flow.before, flow.after, flow.kind) != (effect.before, effect.after, "grant"):
                    raise WorkflowError("Recover the actual conserved shared Permission grant")
            if value.location_rebuild is not None:
                from girlframe.services.m3_location_rebuild import prove_effect

                prove_effect(self.game, c, value.location_rebuild)
            if value.location_build is not None:
                from girlframe.services.m3_location_build import prove_effect as prove_build

                prove_build(self.game, c, value.location_build)
            if value.acquired_rule is not None:
                receipts: tuple[Any, ...]
                if value.acquired_rule == "handler-advancement.handler-advancement.cute-uniforms":
                    from girlframe.engine.m3_cute_uniforms import (
                        acquisitions as uniform_acquisitions,
                    )

                    receipts = uniform_acquisitions(spent)
                elif (
                    value.acquired_rule == "handler-advancement.handler-advancement.girl-insurance"
                ):
                    from girlframe.engine.m3_girl_insurance import (
                        acquisitions as insurance_acquisitions,
                    )

                    receipts = insurance_acquisitions(spent)
                elif (
                    value.acquired_rule
                    == "handler-advancement.handler-advancement.deep-brain-spikes"
                ):
                    from girlframe.engine.m3_deep_brain_spikes import (
                        acquisitions as spike_acquisitions,
                    )

                    receipts = spike_acquisitions(spent)
                elif value.acquired_rule == "handler-advancement.handler-advancement.bomb-collar":
                    from girlframe.engine.m3_bomb_collar import acquisitions as collar_acquisitions

                    receipts = collar_acquisitions(spent)
                elif (
                    value.acquired_rule == "handler-advancement.handler-advancement.hidden-sidearm"
                ):
                    from girlframe.engine.m3_hidden_sidearm import (
                        acquisitions as sidearm_acquisitions,
                    )

                    receipts = sidearm_acquisitions(spent)
                elif (
                    value.acquired_rule == "handler-advancement.handler-advancement.reign-of-terror"
                ):
                    from girlframe.engine.m3_reign_terror import acquisitions as reign_acquisitions

                    receipts = reign_acquisitions(spent)
                elif (
                    value.acquired_rule
                    == "handler-advancement.handler-advancement.tracker-implants"
                ):
                    from girlframe.engine.m3_tracker_implants import (
                        acquisitions as tracker_acquisitions,
                    )

                    receipts = tracker_acquisitions(spent)
                elif (
                    value.acquired_rule
                    == "handler-advancement.handler-advancement.contaminant-zone"
                ):
                    from girlframe.engine.m3_contaminant_zone import (
                        acquisitions as zone_acquisitions,
                    )

                    receipts = zone_acquisitions(spent)
                elif (
                    value.acquired_rule
                    == "handler-advancement.handler-advancement.politician-bribery-fund"
                ):
                    from girlframe.engine.m3_politician_bribery import (
                        acquisitions as bribery_acquisitions,
                    )

                    receipts = bribery_acquisitions(spent)
                elif value.acquired_rule == "handler-advancement.handler-advancement.ship-base":
                    from girlframe.engine.m3_ship_base import acquisitions as ship_acquisitions

                    receipts = ship_acquisitions(spent)
                elif value.acquired_rule == "handler-advancement.handler-advancement.a-bomb":
                    from girlframe.engine.m3_a_bomb import acquisitions as bomb_acquisitions

                    receipts = bomb_acquisitions(spent)
                elif (
                    value.acquired_rule
                    == "handler-advancement.handler-advancement.gender-designation-request"
                ):
                    from girlframe.engine.m3_gender_designation import (
                        acquisitions as gender_acquisitions,
                    )

                    receipts = gender_acquisitions(spent)
                elif (
                    value.acquired_rule
                    == "handler-advancement.handler-advancement.intracadre-marriage"
                ):
                    from girlframe.engine.m3_intracadre_marriage import (
                        acquisitions as marriage_acquisitions,
                    )

                    receipts = marriage_acquisitions(spent)
                elif value.acquired_rule == "handler-advancement.handler-advancement.secretary":
                    from girlframe.engine.m3_secretary import acquisitions as secretary_acquisitions

                    receipts = secretary_acquisitions(spent)
                else:
                    from girlframe.engine.m3_supply_drop import (
                        acquisitions as drop_acquisitions,
                    )

                    receipts = drop_acquisitions(spent)
                receipt = next((x for x in receipts if x.id == value.acquisition), None)
                if (
                    receipt is None
                    or receipt.award != identity
                    or receipt.event != value.spend_event
                ):
                    raise WorkflowError(
                        "Recover the actual acquired advancement rule source receipt"
                    )

    def _proof(
        self, c: Connection, identity: str
    ) -> tuple[dict[str, Any] | None, GameState, ActorRef, str, rules.Award | None]:
        current = load_state(c, self.store.campaign_id)
        ordinary = next(
            (
                x
                for x in rules.awards(current)
                if x.id == identity and x.ordinary_source is not None
            ),
            None,
        )
        if ordinary is not None:
            from girlframe.services.m3_handler_ordinary import prove_award

            prove_award(self.game, c, current, ordinary)
            self._spent(c, ordinary, ordinary.handler)
            return None, current, ordinary.handler, ordinary.appointment, ordinary
        row = _work(c, self.store, identity)
        rule = json.loads(row["body_json"]).get("rule_id")
        if rule not in rules.RULES:
            raise WorkflowError("Only a genuine selected Void Endgame6or7 grants this advancement")
        row, original = _selection(c, self.game, identity, rule=rule)
        handler = active_handler(original)
        if handler is None or row["owner_id"] != handler.entity:
            raise WorkflowError("Only this actual original Handler owns the advancement source")
        state = load_state(c, self.store.campaign_id)
        first = (
            c.execute(
                sa.select(t.m3["m3_required_work"])
                .where(
                    t.m3["m3_required_work"].c.campaign_id == self.store.campaign_id,
                    t.m3["m3_required_work"].c.id == identity,
                )
                .order_by(t.m3["m3_required_work"].c.revision)
                .limit(1)
            )
            .mappings()
            .one()
        )
        appointment = _appointment_at(c, self.game, first["event_id"], handler)
        if original.handler_persona and original.handler_persona.appointment != appointment:
            raise WorkflowError("Recover this original Handler persona's real appointment")
        value = next((x for x in rules.awards(state) if x.id == identity), None)
        if value:
            source = _history(c, self.game, value.award_event)
            born = next((x for x in rules.awards(source) if x.id == identity), None)
            event = c.execute(
                sa.select(t.events.c.kind, t.events.c.actor_id).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == value.award_event,
                )
            ).first()
            if (
                born is None
                or born.phase != "held"
                or event is None
                or event.kind != "m3.handler_advancement_awarded"
                or event.actor_id != handler.entity
                or (
                    value.handler,
                    value.rule,
                    value.appointment,
                    value.source_event,
                    value.source_work,
                )
                != (handler, rule, appointment, first["event_id"], identity)
                or any(
                    getattr(born, k) != getattr(value, k)
                    for k in (
                        "id",
                        "rule",
                        "handler",
                        "appointment",
                        "source_work",
                        "source_event",
                        "award_event",
                        "account",
                    )
                )
                or row["state"] != "resolved"
                or row["event_id"] != value.award_event
            ):
                raise WorkflowError("Recover the actual original finite advancement award")
            self._spent(c, value, handler)
        elif row["state"] != "pending":
            raise WorkflowError("A resolved advancement source needs its actual saved award")
        return row, state, handler, appointment, value

    def _source(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[dict[str, Any] | None, GameState, ActorRef, str, rules.Award | None]:
        result = self._proof(c, identity)
        source_rule = (
            result[4].rule
            if result[4] is not None
            else json.loads(result[0]["body_json"])["rule_id"]
            if result[0] is not None
            else None
        )
        if source_rule is None:
            raise WorkflowError("Recover this genuine advancement source")
        self._access(c, viewer, source_rule)
        if viewer.user_id != int(result[2].entity):
            raise WorkflowError("Only this actual original Handler owns the advancement source")
        return result

    def _authorize_source(self, c: Connection, viewer: GuildViewer, identity: str) -> None:
        self._source(c, viewer, identity)

    def _current(
        self, c: Connection, state: GameState, handler: ActorRef, appointment: str
    ) -> None:
        if (
            not same_handler_body(state, handler)
            or HandlerCreationService(self.store)._appointment_source(c, int(handler.entity))
            != appointment
        ):
            raise WorkflowError("This award belongs to its original Handler and appointment")
        if self.game.pending_actions(c):
            raise WorkflowError("Finish the actual pending Play before awarding or spending")

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row, state, handler, appointment, value = self._source(c, viewer, identity)
            try:
                self._current(c, state, handler, appointment)
                current = True
            except WorkflowError:
                current = False
            return dict(
                id=identity,
                revision=state.revision,
                work_revision=row["revision"] if row is not None else None,
                phase=value.phase if value else "claim",
                current=current,
                rule=value.rule
                if value
                else json.loads(row["body_json"])["rule_id"]
                if row
                else None,
                ordinary_source=value.ordinary_source.model_dump(mode="json")
                if value and value.ordinary_source
                else None,
                handler=handler.model_dump(mode="json"),
                account=value.account if value else None,
                spend_account=value.spend_account if value else None,
                acquired_rule=value.acquired_rule if value else None,
                acquisition=value.acquisition if value else None,
                location_rebuild=value.location_rebuild.model_dump(mode="json")
                if value and value.location_rebuild
                else None,
                location_build=value.location_build.model_dump(mode="json")
                if value and value.location_build
                else None,
                effects=[
                    dict(
                        actor=x.actor.model_dump(mode="json"),
                        label=x.label,
                        amount=x.amount,
                        before=x.before,
                        after=x.after,
                    )
                    for x in value.effects
                ]
                if value
                else [],
                candidates=[
                    dict(
                        actor=current_ref(state, uid).model_dump(mode="json"),
                        token=current_ref(state, uid).token,
                        label=state.sheets[str(uid)].callsign,
                        permissions=state.sheets[str(uid)].permissions,
                    )
                    for uid in state.order
                ]
                if current
                else [],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                phase=x.phase,
                label="Handler advancement — grant Permissions",
                revision=state.revision,
                rule=x.rule,
            )
            for x in rules.awards(state)
            if x.phase == "held" and x.handler.entity == str(viewer.user_id)
        ]

    def claim_void(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected_game: int,
        work_revision: int,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row, state, handler, appointment, value = self._source(c, viewer, identity)
            self._current(c, state, handler, appointment)
            if (
                row is None
                or state.revision != expected_game
                or row["revision"] != work_revision
                or row["state"] != "pending"
                or value is not None
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError("Reopen this actual unclaimed Handler advancement source")
            assert row is not None
            event = str(uuid4())
            value = rules.Award(
                id=identity,
                rule=json.loads(row["body_json"])["rule_id"],
                handler=handler,
                appointment=appointment,
                source_work=identity,
                source_event=row["event_id"],
                award_event=event,
                account=account.strip(),
            )
            rules.grant(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_advancement_awarded",
                state,
                event_id=event,
                award_id=identity,
                rule_id=value.rule,
            )
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{k: v for k, v in row.items() if k not in ("revision", "state", "event_id")},
                    revision=row["revision"] + 1,
                    state="resolved",
                    event_id=event,
                )
            )
            return dict(id=identity, phase="held")

        return self.store._write(
            viewer,
            key,
            "m3.handler_advancement_awarded",
            dict(
                id=identity,
                expected_game=expected_game,
                work_revision=work_revision,
                account=account,
            ),
            operation,
            auto_audit=False,
            authorize=lambda c: self._authorize_source(c, viewer, identity),
        )

    def spend_permissions(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected_game: int,
        grants: tuple[rules.PermissionGrant, ...],
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row, state, handler, appointment, value = self._source(c, viewer, identity)
            self._current(c, state, handler, appointment)
            if (
                state.revision != expected_game
                or value is None
                or value.phase != "held"
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError("Reopen this actual unspent Handler advancement")
            for choice in grants:
                self.game.character_binding(
                    c, state, int(choice.actor.entity), require_current_profile=False
                )
            event = str(uuid4())
            changed = rules.spend(state, identity, grants, event, account)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_advancement_spent",
                changed,
                event_id=event,
                award_id=identity,
                rule_id=value.rule,
            )
            return dict(id=identity, phase="spent", recipients=len(grants))

        try:
            return self.store._write(
                viewer,
                key,
                "m3.handler_advancement_spent",
                dict(
                    id=identity,
                    expected_game=expected_game,
                    grants=[x.model_dump(mode="json") for x in grants],
                    account=account,
                ),
                operation,
                auto_audit=False,
                authorize=lambda c: self._authorize_source(c, viewer, identity),
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
