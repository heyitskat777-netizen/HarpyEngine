"""Private sponsorship and independently authored participation in the saved event."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_rebel_funding as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_rebel_ambush import _cast
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

EVENT = "m3.strain_rebel_participation"


def for_row(state: GameState, row: dict[str, Any]) -> rules.Influence | None:
    original = json.loads(row["body_json"]).get("source_work")
    return next((x for x in rules.influences(state) if x.id == original), None)


def available(state: GameState, value: rules.Influence) -> dict[str, tuple[ActorRef, int, str]]:
    rules.group(state, value.group)
    assert state.world is not None
    candidates = []
    for x in state.world.npcs:
        if x.faction == value.group and x.revealed and x.alive and not x.captive_of:
            candidates.append((ActorRef(kind="npc", entity=x.id), x.controller, x.name))
    for body in state.world.pilots:
        if (
            body.faction == value.group
            and body.kind == "rebel"
            and body.revealed
            and body.alive
            and body.custody == "free"
        ):
            candidates.append(
                (ActorRef(kind="external_pilot", entity=body.id), body.controller, body.name)
            )
    return {
        actor.token: (actor, owner, name)
        for actor, owner, name in candidates
        if str(owner) != value.sponsor.entity
    }


def visible(state: GameState, viewer: GuildViewer) -> tuple[rules.Influence, ...]:
    return tuple(
        x
        for x in rules.influences(state)
        if x.controller == viewer.user_id and x.nominated and not x.declined
    )


def require_participation(
    c: Connection, strain: StrainService, state: GameState, row: dict[str, Any]
) -> None:
    value = for_row(state, row)
    if value is None:
        return
    if value.participation is None or value.candidate is None or value.controller is None:
        raise WorkflowError(
            "Confirm the original insurgent's actual participation before applying this effect"
        )
    events = t.events
    query = sa.select(events.c.kind, events.c.actor_id, events.c.payload_json, events.c.seq).where(
        events.c.campaign_id == strain.store.campaign_id,
    )
    proof = c.execute(query.where(events.c.id == value.participation)).first()
    roll = c.execute(query.where(events.c.id == value.roll_event)).first()
    if (
        proof is None
        or proof.kind != EVENT
        or proof.actor_id != str(value.controller)
        or roll is None
        or roll.kind != "m3.strain_die_saved"
        or proof.seq <= roll.seq
        or json.loads(roll.payload_json).get("work_id") != value.id
        or json.loads(proof.payload_json).get("work_id") != value.id
        or json.loads(proof.payload_json).get("decision") != "participate"
        or value.period != row["off_duty_id"]
        or not same_handler_body(state, value.sponsor)
    ):
        raise WorkflowError("Recover the actual original signed participation for this saved roll")


class FundingService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def _case(self, state: GameState, viewer: GuildViewer, identity: str) -> rules.Influence:
        value = next((x for x in rules.influences(state) if x.id == identity), None)
        if value is None or not (
            value in visible(state, viewer)
            or value.sponsor.entity == str(viewer.user_id)
            and same_handler_body(state, value.sponsor)
        ):
            raise WorkflowError(
                "Only the original parties can open this event's private participation"
            )
        return value

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            value = self._case(state, viewer, identity)
            sponsor = value.sponsor.entity == str(viewer.user_id)
            choices: tuple[tuple[str, str], ...] = ()
            candidates: tuple[tuple[str, str], ...] = ()
            if value.participation is None:
                if sponsor and (not value.nominated or value.declined):
                    candidates = tuple(
                        (token, entry[2])
                        for token, entry in available(state, value).items()
                        if HandlerService(self.store)._member(c, entry[1])
                    )
                elif not sponsor and not value.declined:
                    choices = (
                        ("participate", "Record your part in the actual event"),
                        ("decline", "Decline the invitation"),
                    )
            return dict(
                revision=state.revision,
                sponsor=sponsor,
                candidates=candidates,
                choices=choices,
                completed=bool(value.participation),
                invited=bool(value.nominated) and not value.declined,
                account=value.account if not sponsor else "",
            )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        channel: int,
        decision: str,
        *,
        nominee: str | None = None,
        account: str = "",
    ) -> dict[str, Any]:
        account = account.strip()
        if (
            decision not in ("nominate", "participate", "decline")
            or (decision == "nominate") != (nominee is not None)
            or (decision == "participate" and not 0 < len(account) <= 1200)
        ):
            raise WorkflowError("Choose the original part you are actually playing in this event")

        def authorize(c: Connection) -> None:
            for scope in ("strain", "world"):
                self.strain.missions.access.authorize(c, viewer, scope)
            self.game.unpaused(c)
            self._case(load_state(c, self.store.campaign_id), viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_strain_effects import EffectService

            state = self.strain._state(c, revision)
            value = self._case(state, viewer, identity)
            row = EffectService(self.strain)._row(c, value.id + ":effect")
            members = HandlerService(self.store)
            if (
                row["state"] != "pending"
                or for_row(state, row) != value
                or value.participation
                or self.strain.periods._get(c, value.period).phase != "preparing"
                or not same_handler_body(state, value.sponsor)
            ):
                raise WorkflowError("Reopen the original outstanding Strain effect")
            event = str(uuid4())
            if decision == "nominate":
                candidate = available(state, value).get(nominee or "")
                if (
                    str(viewer.user_id) != value.sponsor.entity
                    or value.nominated
                    and not value.declined
                    or candidate is None
                    or not members._member(c, candidate[1])
                ):
                    raise WorkflowError("Choose the original eligible insurgent controller once")
                updated = value.model_copy(
                    update=dict(
                        candidate=candidate[0],
                        controller=candidate[1],
                        nominated=event,
                        declined=None,
                    )
                )
            else:
                actor = value.candidate
                if (
                    actor is None
                    or value.controller != viewer.user_id
                    or value.declined
                    or not value.nominated
                ):
                    raise WorkflowError(
                        "Only the original invited actor can answer the participation offer"
                    )
                if decision == "decline":
                    updated = value.model_copy(update=dict(declined=event))
                else:
                    cast = _cast(self.game, c, state, channel)
                    entry = available(state, value).get(actor.token)
                    if (
                        entry is None
                        or entry[1] != viewer.user_id
                        or cast is None
                        or not any(
                            x.actor == actor and x.controller == viewer.user_id for x in cast.roles
                        )
                        or resolve(state, actor, ()).offstage_source is not None
                    ):
                        raise WorkflowError("Join the original insurgent in the actual event scene")
                    updated = value.model_copy(
                        update=dict(scene=cast.id, participation=event, account=account)
                    )
            rules.save(state, updated)
            self.game.event(
                c,
                viewer.user_id,
                key,
                EVENT,
                state,
                event_id=event,
                work_id=identity,
                decision=decision,
            )
            return dict(id=identity, decision=decision)

        return self.strain.missions._write(
            viewer,
            key,
            EVENT,
            dict(
                id=identity,
                revision=revision,
                channel=channel,
                decision=decision,
                nominee=nominee,
                account=account,
            ),
            operation,
            authorize,
        )
