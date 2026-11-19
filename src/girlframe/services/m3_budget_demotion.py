"""Endgame succession binds separately owned Girl and Handler creation."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_budget_demotion as rules
from girlframe.engine.handler_setup import HandlerSetup
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_budget_tags import _selection
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

EVENT = "m3.budget_demotion_choice"


def _case(state: GameState, identity: str) -> rules.Demotion | None:
    return next((x for x in rules.demotions(state) if x.id == identity), None)


def _proof(c: Connection, game: GameService, event: str | None) -> Any:
    return c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == event,
        )
    ).first()


def due(
    c: Connection, strain: StrainService, state: GameState, period: str
) -> rules.Demotion | None:
    value = next(
        (x for x in rules.demotions(state) if x.period == period and x.accepted and not x.demoted),
        None,
    )
    if value is None:
        return None
    row, original = _selection(c, strain.game, value.id, rule=rules.RULE)
    proof = _proof(c, strain.game, value.accepted)
    if (
        proof is None
        or proof.kind != EVENT
        or proof.actor_id != str(value.successor)
        or json.loads(proof.payload_json).get("decision") != "accept"
        or json.loads(proof.payload_json).get("work_id") != value.id
        or row["off_duty_id"] != period
        or row["state"] != "pending"
        or active_handler(original) != value.handler
        or not same_handler_body(state, value.handler)
        or value.handler.entity in state.sheets
        or not HandlerService(strain.store)._member(c, value.successor)
    ):
        raise WorkflowError("Recover the original accepted succession before demoting the Handler")
    return value


def girl_slot(state: GameState, owner: int, setup: HandlerSetup) -> rules.Demotion | None:
    value = next(
        (
            x
            for x in rules.demotions(state)
            if x.handler.entity == str(owner) and x.demoted and not x.girl
        ),
        None,
    )
    if value is None:
        return None
    order = tuple(x.user_id for x in setup.status_order)
    if (
        owner not in order
        or owner in state.order
        or active_handler(state) is not None
        or tuple(x for x in order if x != owner) != state.order
        or not any(
            x.actor == value.handler and x.source_event == value.demoted and x.ending == "demoted"
            for x in state.handler_archives
        )
    ):
        raise WorkflowError("Review the original Girl's actual Status among the current Cadre")
    state.order = order
    return value


def visible(
    state: GameState, viewer: GuildViewer, *, administrator: bool = False
) -> tuple[rules.Demotion, ...]:
    return tuple(
        x
        for x in rules.demotions(state)
        if (
            x.handler.entity == str(viewer.user_id)
            or x.successor == viewer.user_id
            or administrator
            and viewer.is_administrator
            and x.girl is not None
            and x.new_appointment is None
        )
    )


class DemotionService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = _case(state, identity)
            if value is None or value.declined and value.handler.entity == str(viewer.user_id):
                _, original = _selection(c, self.game, identity, rule=rules.RULE)
                handler = active_handler(original)
                if (
                    handler is None
                    or handler.entity != str(viewer.user_id)
                    or not same_handler_body(state, handler)
                ):
                    raise WorkflowError(
                        "Only the original Handler can nominate a willing successor"
                    )
                if handler.entity in state.sheets:
                    raise WorkflowError(
                        "Review the original Handler's separate existing Girl before demotion"
                    )
                members = c.scalars(
                    sa.select(t.members.c.user_id).where(
                        t.members.c.campaign_id == self.store.campaign_id,
                        t.members.c.active.is_(True),
                        t.members.c.user_id != handler.entity,
                    )
                )
                nominees = tuple(
                    (uid, state.sheets[uid].callsign if uid in state.sheets else "Member " + uid)
                    for uid in members
                )
                return dict(revision=state.revision, phase="nomination", nominees=nominees)
            if value not in visible(
                state, viewer, administrator=self.store.policy.allow_guild_administrators
            ):
                raise WorkflowError("The original demotion belongs to its authorized participants")
            role = str(viewer.user_id)
            options: tuple[tuple[str, str], ...] = ()
            if value.completed:
                phase = "complete"
            elif value.new_appointment:
                phase = "handler_creation"
                if value.successor == viewer.user_id and active_handler(state) is not None:
                    options = (("complete", "Verify the new Handler and original Girl"),)
            elif value.girl:
                phase = "appointment"
                if viewer.is_administrator and self.store.policy.allow_guild_administrators:
                    options = (("appoint", "Appoint the consenting successor"),)
            elif value.demoted:
                phase = "girl_creation"
            elif value.accepted:
                phase = "demotion_due"
            elif value.declined:
                phase = "declined"
            else:
                phase = "offer"
                if value.successor == viewer.user_id:
                    options = (("accept", "Accept succession"), ("decline", "Decline succession"))
            return dict(
                revision=state.revision,
                phase=phase,
                options=options,
                account=value.account
                if viewer.user_id == value.successor or role == value.handler.entity
                else "",
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        decision: str,
        *,
        nominee: int | None = None,
        account: str = "",
    ) -> dict[str, Any]:
        account = account.strip()
        if (decision == "nominate") != (nominee is not None) or (
            decision == "nominate" and not 0 < len(account) <= 1200
        ):
            raise WorkflowError(
                "Nominate one actual joined successor with your account of the offer"
            )

        def authorize(c: Connection) -> None:
            self.strain.missions.access.authorize(c, viewer, "strain")
            self.game.unpaused(c)
            if decision == "appoint":
                self.store.administrator(viewer)

        def operation(c: Connection) -> dict[str, Any]:
            state = self.strain._state(c, revision)
            row, original = _selection(c, self.game, identity, rule=rules.RULE)
            value = _case(state, identity)
            handler = active_handler(original)
            period = self.strain.periods._get(c, row["off_duty_id"])
            members = HandlerService(self.store)
            if handler is None or row["state"] != "pending":
                raise WorkflowError("Recover the actual original pending demotion")
            if decision != "nominate" and (
                value is None
                or value
                not in visible(
                    state, viewer, administrator=self.store.policy.allow_guild_administrators
                )
            ):
                raise WorkflowError(
                    "Only authorized successors and original parties can change this demotion"
                )
            event = str(uuid4())
            kind = EVENT
            setup_update: tuple[int, HandlerSetup] | None = None
            if decision == "nominate":
                if (
                    nominee is None
                    or nominee == viewer.user_id
                    or handler.entity != str(viewer.user_id)
                    or not same_handler_body(state, handler)
                    or period.phase != "preparing"
                    or handler.entity in state.sheets
                    or not members._member(c, nominee)
                    or value is not None
                    and value.declined is None
                ):
                    raise WorkflowError(
                        "Choose one actual uncommitted successor to the original Handler"
                    )
                _, appointment = MedicalService(self.store)._handler(c)
                changed = rules.Demotion(
                    id=identity,
                    period=period.id,
                    source=row["event_id"],
                    handler=handler,
                    appointment=appointment,
                    successor=nominee,
                    offered=event,
                    account=account,
                )
            elif value is not None and decision in ("accept", "decline"):
                _, appointment = MedicalService(self.store)._handler(c)
                if (
                    viewer.user_id != value.successor
                    or value.accepted
                    or value.declined
                    or not same_handler_body(state, value.handler)
                    or value.appointment != appointment
                    or period.phase != "preparing"
                ):
                    raise WorkflowError(
                        "Only the original invited successor can answer this pending offer"
                    )
                changed = value.model_copy(
                    update={"accepted" if decision == "accept" else "declined": event}
                )
            elif value is not None and decision == "appoint":
                setup_revision, setup = members.current(c)
                girl_sheet = state.sheets.get(value.girl.entity) if value.girl else None
                if (
                    not value.accepted
                    or not value.demoted
                    or not value.girl
                    or not value.girl_activation
                    or value.new_appointment
                    or period.phase != "complete"
                    or active_handler(state) is not None
                    or str(setup.handler_id) != value.handler.entity
                    or state.handler != setup.handler_id
                    or not members._member(c, value.successor)
                    or girl_sheet is None
                    or girl_sheet.character_id != value.girl.incarnation
                ):
                    raise WorkflowError(
                        "Finish the original Girl's activation before the successor takes office"
                    )
                kind = "campaign.handler_appointed"
                state.handler = value.successor
                setup_update = (
                    setup_revision + 1,
                    setup.model_copy(update=dict(handler_id=value.successor)),
                )
                changed = value.model_copy(update=dict(new_appointment=event))
            elif value is not None and decision == "complete":
                successor = active_handler(state)
                persona = state.handler_persona
                handler_proof = _proof(c, self.game, persona.source_event) if persona else None
                girl_proof = _proof(c, self.game, value.girl_activation)
                if (
                    value.successor != viewer.user_id
                    or successor is None
                    or persona is None
                    or persona.appointment != value.new_appointment
                    or not value.girl
                    or state.sheets.get(value.girl.entity) is None
                    or state.sheets[value.girl.entity].character_id != value.girl.incarnation
                    or handler_proof is None
                    or handler_proof.kind != "m3.handler_activated"
                    or handler_proof.actor_id != str(value.successor)
                    or girl_proof is None
                    or girl_proof.kind != "m2.character_activated"
                    or girl_proof.actor_id != value.handler.entity
                    or value.completed
                ):
                    raise WorkflowError(
                        "Activate both original owned roles before finishing this Endgame"
                    )
                changed = value.model_copy(update=dict(replacement=successor, completed=event))
            else:
                raise WorkflowError("Use the original authorized action for the demotion")
            rules.save(state, changed)
            self.game.event(
                c,
                viewer.user_id,
                key,
                kind,
                state,
                event_id=event,
                work_id=identity,
                decision=decision,
            )
            if setup_update is not None:
                revision_out, setup_value = setup_update
                c.execute(
                    t.setup_revisions.insert().values(
                        campaign_id=self.store.campaign_id,
                        revision=revision_out,
                        event_id=event,
                        body_json=setup_value.model_dump_json(),
                    )
                )
            if changed.completed:
                self.strain._save(c, row, event, json.loads(row["body_json"]), resolved=True)
            return dict(id=identity, decision=decision)

        return self.strain.missions._write(
            viewer,
            key,
            EVENT,
            dict(
                id=identity, revision=revision, decision=decision, nominee=nominee, account=account
            ),
            operation,
            authorize,
        )
