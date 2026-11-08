"""Owned higher-up demands, actual responses and independent visit ending."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_budget_visitor as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class VisitorService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _proof(self, c: Connection, state: GameState, identity: str) -> rules.Visit:
        value = rules.get(state, identity)
        source = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == value.source_event,
                )
            )
            .mappings()
            .first()
        )
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == value.source_event,
            )
        )
        original = rules.get(GameState.model_validate_json(raw), identity) if raw else None
        immutable = (
            "id",
            "source_work",
            "source_event",
            "period",
            "handler",
            "visitor",
            "controller",
            "cell",
            "people",
            "account",
        )
        if (
            source is None
            or original is None
            or source["kind"] != "m3.strain_effect_applied"
            or source["actor_id"] != value.handler.entity
            or json.loads(source["payload_json"]).get("rule_id") != rules.RULE
            or json.loads(source["payload_json"]).get("work_id") != value.source_work
            or any(getattr(original, x) != getattr(value, x) for x in immutable)
        ):
            raise WorkflowError("Recover the original higher-up, source visit and original Cadre")
        return value

    def _person(self, state: GameState, value: rules.Visit, user: int) -> ActorRef | None:
        person = next((x for x in value.people if x.entity == str(user)), None)
        sheet = state.sheets.get(str(user))
        return (
            person
            if (
                person
                and sheet
                and sheet.character_id == person.incarnation
                and user in state.order
            )
            else None
        )

    def _controller(self, state: GameState, value: rules.Visit, user: int) -> bool:
        npc = (
            next((x for x in state.world.npcs if x.id == value.visitor.entity), None)
            if state.world
            else None
        )
        return bool(npc and npc.alive and npc.controller == value.controller == user)

    def available(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        for value in rules.visits(state):
            controller = self._controller(state, value, viewer.user_id)
            person = self._person(state, value, viewer.user_id)
            needs = controller and (
                value.phase == "active"
                or any(x.response and not x.settlement for x in value.demands)
            )
            needs = needs or bool(
                person and any(x.girl == person and not x.settlement for x in value.demands)
            )
            if needs:
                result.append(dict(id=value.id, phase=value.phase))
        return result

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            Access(self.store).authorize(c, viewer, "strain")
            state = load_state(c, self.store.campaign_id)
            value = self._proof(c, state, identity)
            person = self._person(state, value, viewer.user_id)
            controller = self._controller(state, value, viewer.user_id)
            if not controller and not person:
                raise WorkflowError(
                    "Only the original visitor controller or original Girl may open this visit"
                )
            return dict(
                id=identity,
                revision=state.revision,
                phase=value.phase,
                controller=controller,
                visitor=resolve(state, value.visitor, ()).label,
                people=[
                    dict(id=x.entity, name=state.sheets[x.entity].callsign)
                    for x in value.people
                    if x.entity in state.sheets
                    and state.sheets[x.entity].character_id == x.incarnation
                ],
                demands=[
                    x.model_dump(mode="json")
                    for x in value.demands
                    if controller or x.girl == person
                ],
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
        target: str = "",
        demand: str = "",
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200 or len(demand) > 1200:
            raise WorkflowError(
                "Describe the actual observed offense, response, settlement or ending"
            )

        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "strain")
            state = load_state(c, self.store.campaign_id)
            value = self._proof(c, state, identity)
            if not (
                self._controller(state, value, viewer.user_id)
                or self._person(state, value, viewer.user_id)
            ):
                raise WorkflowError("Only an original participant may respond")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = self._proof(c, state, identity)
            if state.revision != expected or not same_handler_body(state, value.handler):
                raise WorkflowError("STALE_VISIT: reopen the original source visit")
            controller = self._controller(state, value, viewer.user_id)
            person = self._person(state, value, viewer.user_id)
            event = str(uuid4())
            if action == "demand":
                if not controller or value.phase != "active" or not demand.strip():
                    raise WorkflowError(
                        "The actual visiting NPC's controller authors the offense and demand"
                    )
                girl = next((x for x in value.people if x.entity == target), None)
                if girl is None or self._person(state, value, int(girl.entity)) != girl:
                    raise WorkflowError(
                        "Choose the original current Girl who actually offended this visitor"
                    )
                actual_profiles = profiles(c, self.store.campaign_id)
                if (
                    resolve(state, girl, actual_profiles).cell != value.cell
                    or resolve(state, value.visitor, actual_profiles).cell != value.cell
                ):
                    raise WorkflowError(
                        "The actual offense needs known co-present bodies at the visit location"
                    )
                value = value.model_copy(
                    update=dict(
                        demands=(
                            *value.demands,
                            rules.Demand(
                                id=event,
                                girl=girl,
                                offense=account.strip(),
                                demand=demand.strip(),
                                event=event,
                            ),
                        )
                    )
                )
            elif action in ("respond", "settle"):
                actual = next((x for x in value.demands if x.id == target), None)
                if actual is None or actual.settlement:
                    raise WorkflowError("Open an actual unsettled reparation demand")
                if action == "respond":
                    if person != actual.girl:
                        raise WorkflowError(
                            "Only the original affected Girl records her actual response"
                        )
                    revised = actual.model_copy(
                        update=dict(response=account.strip(), response_event=event)
                    )
                else:
                    if not controller or not actual.response:
                        raise WorkflowError(
                            "The actual NPC controller confirms only a real reported response"
                        )
                    revised = actual.model_copy(
                        update=dict(settlement=account.strip(), settlement_event=event)
                    )
                value = value.model_copy(
                    update=dict(
                        demands=tuple(revised if x.id == target else x for x in value.demands)
                    )
                )
            elif action == "end":
                if not controller or value.phase != "active":
                    raise WorkflowError("The actual NPC controller ends this real visit")
                value = value.model_copy(update=dict(phase="complete", ended_event=event))
            else:
                raise WorkflowError("Choose an actual demand, response, settlement or visit ending")
            rules.put(state, rules.Visit.model_validate_json(value.model_dump_json()))
            state.facts.append(
                dict(
                    kind="budget_visitor_action",
                    visit=identity,
                    event=event,
                    action=action,
                    actor=str(viewer.user_id),
                    target=target,
                    account=account,
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.budget_visitor_action",
                state,
                event_id=event,
                visit=identity,
                action=action,
                target=target,
            )
            if action == "end":
                work = t.m3["m3_required_work"]
                row = (
                    c.execute(
                        sa.select(work)
                        .where(
                            work.c.campaign_id == self.store.campaign_id,
                            work.c.id == identity,
                        )
                        .order_by(work.c.revision.desc())
                        .limit(1)
                    )
                    .mappings()
                    .one()
                )
                if row["state"] != "pending":
                    raise WorkflowError("Recover the original pending visit work")
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
            return dict(id=identity, phase=value.phase, event=event)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.budget_visitor_action",
                dict(
                    id=identity,
                    expected=expected,
                    action=action,
                    account=account,
                    target=target,
                    demand=demand,
                ),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
