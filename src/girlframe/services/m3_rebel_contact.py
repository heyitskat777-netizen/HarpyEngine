"""Original Girl-authored contact and NPC-owned confirmation; no generated dialogue."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_rebel_contact as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle import category
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class ContactService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _proof(self, c: Connection, state: GameState, identity: str) -> rules.Contact:
        value = rules.get(state, identity)

        def saved(event: str) -> tuple[Any, rules.Contact | None]:
            row = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == self.store.campaign_id, t.events.c.id == event
                    )
                )
                .mappings()
                .first()
            )
            raw = c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json).where(
                    t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_state_history"].c.event_id == event,
                )
            )
            return row, rules.get(GameState.model_validate_json(raw), identity) if raw else None

        event, original = saved(value.source_event)
        if (
            event is None
            or original is None
            or event["kind"] != "m3.strain_effect_applied"
            or event["actor_id"] != value.handler.entity
            or json.loads(event["payload_json"]).get("rule_id") != rules.RULE
            or json.loads(event["payload_json"]).get("work_id") != value.source_work
            or any(
                getattr(original, k) != getattr(value, k)
                for k in (
                    "id",
                    "source_work",
                    "source_event",
                    "period",
                    "handler",
                    "people",
                    "city",
                    "account",
                )
            )
        ):
            raise WorkflowError("Recover the original nearby-city contact source")
        if value.claim_event:
            claimed, prior = saved(value.claim_event)
            if (
                claimed is None
                or prior is None
                or value.girl is None
                or claimed["kind"] != "m3.rebel_contact_claimed"
                or claimed["actor_id"] != value.girl.entity
                or json.loads(claimed["payload_json"]).get("contact") != identity
                or any(
                    getattr(prior, k) != getattr(value, k)
                    for k in ("girl", "npc", "controller", "method", "claim_event")
                )
            ):
                raise WorkflowError("Recover the actual original Girl's authored contact")
        if value.response_event:
            answered, prior = saved(value.response_event)
            if (
                answered is None
                or prior is None
                or prior != value
                or answered["kind"] != "m3.rebel_contact_response"
                or answered["actor_id"] != str(value.controller)
            ):
                raise WorkflowError("Recover the actual NPC controller's original response")
        return value

    def _girl(self, state: GameState, value: rules.Contact, user: int) -> ActorRef | None:
        sheet = state.sheets.get(str(user))
        return next(
            (
                x
                for x in value.people
                if x.entity == str(user)
                and sheet
                and sheet.character_id == x.incarnation
                and user in state.order
            ),
            None,
        )

    def _npc(self, state: GameState, value: rules.Contact, user: int) -> bool:
        return bool(
            value.npc
            and value.controller == user
            and state.world
            and any(
                x.id == value.npc.entity and x.alive and x.controller == user
                for x in state.world.npcs
            )
        )

    def _choices(
        self, state: GameState, value: rules.Contact, girl: ActorRef
    ) -> list[dict[str, str]]:
        city = (
            next((x for x in state.world.locations if x.id == value.city), None)
            if state.world
            else None
        )
        return (
            [
                dict(id=x.id, name=x.name)
                for x in state.world.npcs
                if x.alive
                and city
                and x.cell == city.cell
                and category(state, ActorRef(kind="npc", entity=x.id)) == "npc"
                and (x.revealed or depth(state, girl, ActorRef(kind="npc", entity=x.id)) > 0)
            ]
            if state.world
            else []
        )

    def available(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        for value in rules.contacts(state):
            girl = self._girl(state, value, viewer.user_id)
            if (
                (value.phase == "choose" and girl)
                or (value.girl == girl and girl)
                or self._npc(state, value, viewer.user_id)
            ):
                actionable = (
                    bool(girl)
                    if value.phase == "choose"
                    else self._npc(state, value, viewer.user_id)
                    if value.phase == "confirm"
                    else girl == value.girl
                    if value.phase == "revise"
                    else False
                )
                result.append(dict(id=value.id, phase=value.phase, actionable=actionable))
        return result

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            Access(self.store).authorize(c, viewer, "strain")
            state = load_state(c, self.store.campaign_id)
            value = self._proof(c, state, identity)
            girl = self._girl(state, value, viewer.user_id)
            controller = self._npc(state, value, viewer.user_id)
            if not (
                (value.phase == "choose" and girl) or (value.girl == girl and girl) or controller
            ):
                raise WorkflowError(
                    "This private contact belongs to its original Girl and actual NPC"
                )
            npc = (
                next((x for x in state.world.npcs if value.npc and x.id == value.npc.entity), None)
                if state.world
                else None
            )
            return dict(
                id=identity,
                revision=state.revision,
                phase=value.phase,
                controller=controller,
                girl=bool(girl and (value.girl is None or value.girl == girl)),
                choices=self._choices(state, value, girl)
                if girl and (value.girl is None or value.girl == girl)
                else [],
                npc=npc.name if npc else None,
                method=value.method,
                response=value.response,
            )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        action: str,
        account: str,
        *,
        npc: str = "",
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe your actual repeatable contact method or NPC response")

        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "strain")
            state = load_state(c, self.store.campaign_id)
            value = self._proof(c, state, identity)
            if not self._girl(state, value, viewer.user_id) and not self._npc(
                state, value, viewer.user_id
            ):
                raise WorkflowError("Only original source participants may respond")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = self._proof(c, state, identity)
            if state.revision != expected or value.phase == "complete":
                raise WorkflowError("STALE_CONTACT: reopen your original contact request")
            girl = self._girl(state, value, viewer.user_id)
            event = str(uuid4())
            if action == "claim":
                if girl is None or (value.phase != "choose" and girl != value.girl):
                    raise WorkflowError(
                        "Only the original Girl can author or revise her actual route"
                    )
                if npc not in {x["id"] for x in self._choices(state, value, girl)}:
                    raise WorkflowError("Choose an actual known ordinary NPC from this source city")
                assert state.world is not None
                body = next(x for x in state.world.npcs if x.id == npc)
                value = value.model_copy(
                    update=dict(
                        phase="confirm",
                        girl=girl,
                        npc=ActorRef(kind="npc", entity=npc),
                        controller=body.controller,
                        method=account.strip(),
                        claim_event=event,
                        response=None,
                        response_event=None,
                    )
                )
                kind = "m3.rebel_contact_claimed"
            elif action == "withdraw":
                if girl is None or girl != value.girl:
                    raise WorkflowError("Only the original Girl withdraws her proposed contact")
                value = value.model_copy(
                    update=dict(
                        phase="choose",
                        girl=None,
                        npc=None,
                        controller=None,
                        method=None,
                        claim_event=None,
                        response=None,
                        response_event=None,
                    )
                )
                kind = "m3.rebel_contact_withdrawn"
            elif action in ("confirm", "revise"):
                if value.phase != "confirm" or not self._npc(state, value, viewer.user_id):
                    raise WorkflowError(
                        "Only the actual NPC controller confirms this established way"
                    )
                if (
                    value.girl is None
                    or self._girl(state, value, int(value.girl.entity)) != value.girl
                ):
                    raise WorkflowError(
                        "Recover the original current Girl before establishing contact"
                    )
                value = value.model_copy(
                    update=dict(
                        phase="complete" if action == "confirm" else "revise",
                        response=account.strip(),
                        response_event=event,
                    )
                )
                kind = "m3.rebel_contact_response"
            else:
                raise WorkflowError("Choose an actual own route, withdrawal or NPC response")
            rules.put(state, rules.Contact.model_validate_json(value.model_dump_json()))
            self.game.event(c, viewer.user_id, key, kind, state, event_id=event, contact=identity)
            if value.phase == "complete":
                work = t.m3["m3_required_work"]
                row = (
                    c.execute(
                        sa.select(work)
                        .where(work.c.campaign_id == self.store.campaign_id, work.c.id == identity)
                        .order_by(work.c.revision.desc())
                        .limit(1)
                    )
                    .mappings()
                    .one()
                )
                if row["state"] != "pending":
                    raise WorkflowError("Recover the original pending contact work")
                c.execute(
                    work.insert().values(
                        **{
                            k: v
                            for k, v in row.items()
                            if k not in ("revision", "state", "event_id")
                        },
                        revision=row["revision"] + 1,
                        state="resolved",
                        event_id=event,
                    )
                )
            return dict(id=identity, phase=value.phase)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.rebel_contact_response",
                dict(id=identity, expected=expected, action=action, account=account, npc=npc),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
