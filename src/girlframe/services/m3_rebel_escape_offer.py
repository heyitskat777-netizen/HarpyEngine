"""Private Rebel NPC-authored escape offers with an original recipient."""

import json
from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine import m3_rebel_escape_offer as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def stage(
    c: Connection,
    strain: StrainService,
    state: GameState,
    row: dict[str, Any],
    npc: str | None,
    event: str,
) -> None:
    rebel = rules.speaker(state, npc)
    period = strain.periods._get(c, row["off_duty_id"])
    if (
        not HandlerService(strain.store)._member(c, rebel.controller)
        or any(x.id == row["id"] for x in rules.offers(state))
        or not period.character_ids
    ):
        raise WorkflowError("Recover the actual rebel controller and original Cadre")
    rules.put(
        state,
        rules.Offer(
            id=row["id"],
            period=period.id,
            source_event=event,
            rebel=rebel.id,
            controller=rebel.controller,
            handler=period.handler,
            eligible=tuple(
                ActorRef(kind="pilot", entity=owner, incarnation=character)
                for owner, character in period.character_ids.items()
                if owner not in period.ended_characters
            ),
        ),
    )


def visible(state: GameState, owner: int) -> tuple[rules.Offer, ...]:
    return tuple(
        x
        for x in rules.offers(state)
        if x.controller == owner or (x.recipient is not None and x.recipient.entity == str(owner))
    )


class EscapeOfferService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def _view(self, state: GameState, viewer: GuildViewer, identity: str) -> rules.Offer:
        case = next((x for x in visible(state, viewer.user_id) if x.id == identity), None)
        if case is None:
            raise WorkflowError("This offer belongs only to the original rebel and recipient")
        return case

    def _recipients(self, c: Connection, state: GameState, offer: rules.Offer) -> dict[str, str]:
        setup = HandlerService(self.store)
        return {
            actor.entity: sheet.callsign
            for actor in offer.eligible
            if (sheet := state.sheets.get(actor.entity)) is not None
            and sheet.character_id == actor.incarnation
            and setup._member(c, int(actor.entity))
            and actor.entity != str(state.handler)
        }

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            offer = self._view(state, viewer, identity)
            return dict(
                revision=state.revision,
                delivered=offer.delivered_event is not None,
                account=offer.account,
                recipients=self._recipients(c, state, offer) if not offer.delivered_event else {},
            )

    def send(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        recipient: str,
        account: str,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.strain.missions.access.authorize(c, viewer, "strain")
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            offer = self._view(state, viewer, identity)
            if (
                offer.controller != viewer.user_id
                or rules.speaker(state, offer.rebel).controller != viewer.user_id
            ):
                raise WorkflowError("Only the actual rebel controller makes this offer")

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_strain_effects import EffectService

            state = self.strain._state(c, expected)
            offer = self._view(state, viewer, identity)
            row = EffectService(self.strain)._row(c, identity)
            period = self.strain.periods._get(c, offer.period)
            body = json.loads(row["body_json"])
            if (
                offer.delivered_event is not None
                or row["state"] != "pending"
                or period.phase != "preparing"
                or period.handler != offer.handler
                or row["off_duty_id"] != period.id
                or body["rule_id"] != rules.RULE
                or body.get("offer_requested") != offer.source_event
            ):
                raise WorkflowError("Reopen the actual pending Rebel offer")
            if (
                recipient not in self._recipients(c, state, offer)
                or not 0 < len(account.strip()) <= 1200
            ):
                raise WorkflowError("Choose one actual original Girl and describe the escape offer")
            target = next(x for x in offer.eligible if x.entity == recipient)
            event = str(uuid4())
            rules.put(
                state,
                offer.model_copy(
                    update={
                        "recipient": target,
                        "account": account.strip(),
                        "delivered_event": event,
                    }
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.strain_rebel_offer_delivered",
                state,
                event_id=event,
                work_id=identity,
            )
            self.strain._save(c, row, event, body | {"offer_delivered": True}, resolved=True)
            return dict(id=identity, delivered=True)

        return self.strain.missions._write(
            viewer,
            key,
            "m3.strain_rebel_offer_delivered",
            dict(id=identity, expected=expected, recipient=recipient, account=account),
            operation,
            authorize,
        )
