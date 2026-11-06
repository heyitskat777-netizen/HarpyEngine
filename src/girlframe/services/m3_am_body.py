"""Actual body preparation, operator transfer proof and original-AM-owned return."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_am_body as rules
from girlframe.engine import m3_am_code as code
from girlframe.engine.m2 import ChoiceAnswer, GameState
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _history(game: GameService, c: Connection, event: str) -> GameState:
    from girlframe.services.m3_am_scrutinized import _history as history

    return history(game, c, event)


def prove_preparation(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Preparation:
    value = next((x for x in rules.preparations(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual prepared empty hardware")
    original = _history(game, c, value.event)
    event = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
        )
    ).first()
    if (
        value not in rules.preparations(original)
        or event is None
        or (event.kind, event.actor_id) != ("m3.am_body_prepared", str(value.controller))
        or original.handler != value.controller
    ):
        raise WorkflowError("Recover the actual human's original hardware preparation facts")
    return value


def prove(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Swap:
    value = rules.swap(state, identity)
    original = _history(game, c, value.event)
    saved = rules.swap(original, identity)
    maintenance = code.session(state, value.maintenance)
    created = code.session(original, value.maintenance)
    prep = prove_preparation(game, c, state, value.preparation)
    choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
    response = c.scalar(
        sa.select(responses.c.answer_json)
        .join(
            choices,
            sa.and_(
                choices.c.campaign_id == responses.c.campaign_id,
                choices.c.id == responses.c.choice_id,
            ),
        )
        .where(
            responses.c.campaign_id == game.store.campaign_id,
            responses.c.event_id == value.event,
            responses.c.actor_id == str(value.controller),
            choices.c.kind == "am_code_body",
            choices.c.action_id == value.action,
        )
    )
    if (
        saved != value.model_copy(update=dict(returned_event=None))
        or maintenance.body_swap != value.id
        or created.body_swap != value.id
        or (maintenance.actor, maintenance.operator, maintenance.action)
        != (value.actor, value.operator, value.action)
        or "body" not in created.selected_options
        or prep.maintenance != value.maintenance
        or response is None
        or json.loads(response).get("options") != [prep.id]
        or game.action(c, value.action)["data"]["result"]["tier"] not in ("mid", "high")
    ):
        raise WorkflowError("Recover the actual performed circuits/body choice and same AM")
    for body in rules.bodies(state):
        if body.actor == value.actor and body not in rules.bodies(_history(game, c, body.event)):
            raise WorkflowError("Recover the actual latest body hardware condition")
    link = rules.connection(state, value.id)
    linked = rules.connection(_history(game, c, link.event), value.id)
    if (
        link != linked
        or link.actor != value.actor
        or link.vessels != (value.original_vessel, value.new_vessel)
    ):
        raise WorkflowError("Recover the original pair's actual physical hookup")
    if link.event != value.event:
        event = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == link.event
            )
        ).first()
        if event is None or (event.kind, event.actor_id) != (
            "m3.am_body_connection",
            str(value.controller),
        ):
            raise WorkflowError("Only the actual original factual source establishes hookup")
    if value.returned_event:
        event = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == value.returned_event,
            )
        ).first()
        if (
            rules.swap(_history(game, c, value.returned_event), identity) != value
            or event is None
            or (event.kind, event.actor_id) != ("m3.am_body_returned", value.actor.entity)
        ):
            raise WorkflowError("Recover the original AM's actual hooked return")
    return value


def projection(
    game: GameService, c: Connection, state: GameState, value: code.Maintenance
) -> dict[str, Any]:
    return dict(
        bodies=[
            dict(id=x.id, label=x.spec.label, vessel=x.spec.vessel)
            for x in rules.preparations(state)
            if x.maintenance == value.id
            and not any(s.preparation == x.id for s in rules.swaps(state))
        ]
    )


def apply(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], answer: ChoiceAnswer
) -> None:
    value = code.session(state, action["data"]["am_code"]["maintenance"])
    if game.immediate_work(c, value.owner):
        raise WorkflowError("Resolve the actual immediate body/resource work before transfer")
    if (
        len(answer.options) != 1
        or answer.denied
        or answer.fields
        or answer.flag is not None
        or answer.number is not None
        or answer.member is not None
        or not answer.text.strip()
        or len(answer.text) > 1200
    ):
        raise WorkflowError(
            "The actual circuit operator selects and performs this prepared body swap"
        )
    prepared = prove_preparation(game, c, state, answer.options[0])
    if (
        prepared.maintenance != value.id
        or prepared.operator != value.operator
        or prepared.controller != value.controller
    ):
        raise WorkflowError("Use this actual original operator's prepared hardware")
    changed = rules.transfer(state, value, prepared.id, action["data"]["response_event"])
    code.put(state, value.model_copy(update=dict(body_swap=changed.id)))


class BodyService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def prepare(
        self, viewer: GuildViewer, key: str, maintenance: str, expected: int, spec: rules.BodySpec
    ) -> dict[str, Any]:
        from girlframe.services.m3_am_code import access, actual, source

        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, maintenance)
            actual(self.game, c, state, value)
            if (
                viewer.user_id != value.controller
                or state.handler != viewer.user_id
                or state.revision != expected
                or value.phase not in ("proposed", "ready", "active")
                or self.game.immediate_work(c, value.owner)
                or c.scalar(
                    sa.select(t.m2["m2_actions"].c.id).where(
                        t.m2["m2_actions"].c.campaign_id == self.store.campaign_id,
                        t.m2["m2_actions"].c.state.not_in(("complete", "aborted")),
                        t.m2["m2_actions"].c.id.not_in(
                            tuple(x for x in (value.root, value.action) if x)
                        ),
                    )
                )
                is not None
            ):
                raise WorkflowError(
                    "Only the actual original Handler records these local empty-body facts"
                )
            event = str(uuid4())
            body = rules.prepare(state, value, spec, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.am_body_prepared",
                state,
                event_id=event,
                maintenance=value.id,
                preparation=body.id,
            )
            return dict(id=body.id)

        return self.store._write(
            viewer,
            key,
            "m3.am_body_prepare",
            dict(maintenance=maintenance, expected=expected, spec=spec.model_dump(mode="json")),
            change,
            auto_audit=False,
            authorize=lambda c: access(self.game, c, viewer),
        )

    def _own(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[GameState, rules.Swap]:
        from girlframe.services.m3_am_code import access

        access(self.game, c, viewer)
        state = load_state(c, self.store.campaign_id)
        value = prove(self.game, c, state, identity)
        if viewer.user_id not in (int(value.actor.entity), value.controller):
            raise WorkflowError("These hardware/body records belong to their original humans")
        return state, value

    def connection(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        connected: bool,
        account: str,
    ) -> dict[str, Any]:
        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, value = self._own(c, viewer, identity)
            if (
                viewer.user_id != value.controller
                or state.handler != viewer.user_id
                or state.revision != expected
                or value.returned_event
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "Only the actual original factual source records the real hookup"
                )
            event = str(uuid4())
            link = rules.connection(state, identity).model_copy(
                update=dict(connected=connected, event=event)
            )
            rules.put(state, "am_body_connection", identity, link)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.am_body_connection",
                state,
                event_id=event,
                swap=identity,
            )
            return dict(id=identity, connected=connected)

        return self.store._write(
            viewer,
            key,
            "m3.am_body_hookup",
            dict(id=identity, expected=expected, connected=connected, account=account),
            change,
            auto_audit=False,
        )

    def return_body(
        self, viewer: GuildViewer, key: str, identity: str, expected: int
    ) -> dict[str, Any]:
        from girlframe.services.m3_requisitions import RequisitionService

        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state, value = self._own(c, viewer, identity)
            self.game.character_binding(c, state, viewer.user_id)
            if viewer.user_id != int(value.actor.entity) or state.revision != expected:
                raise WorkflowError("Only the original AM chooses her hooked return")
            RequisitionService(self.game)._safe(c, state, viewer.user_id)
            if code.session(state, value.maintenance).phase != "complete":
                raise WorkflowError(
                    "Finish the actual maintenance effects before the hooked return"
                )
            event = str(uuid4())
            changed = rules.return_to_origin(state, identity, event)
            self.game.event(
                c, viewer.user_id, key, "m3.am_body_returned", state, event_id=event, swap=identity
            )
            return dict(id=identity, vessel=changed.original_vessel)

        return self.store._write(
            viewer,
            key,
            "m3.am_body_return",
            dict(id=identity, expected=expected),
            change,
            auto_audit=False,
        )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state, value = self._own(c, viewer, identity)
            occupied = rules.current(state, value.actor)
            return dict(
                revision=state.revision,
                swap=value.model_dump(mode="json"),
                connection=rules.connection(state, identity).model_dump(mode="json"),
                bodies=[
                    x.model_dump(mode="json") for x in rules.bodies(state) if x.actor == value.actor
                ],
                current=occupied.model_dump(mode="json") if occupied else None,
                owner=viewer.user_id == int(value.actor.entity),
                controller=viewer.user_id == value.controller,
            )

    def menu(self, viewer: GuildViewer) -> dict[str, Any]:
        from girlframe.services.m3_am_code import access

        with self.store.engine.connect() as c:
            access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            return dict(
                revision=state.revision,
                preparations=[
                    dict(
                        id=x.id,
                        label=x.proposal,
                        mind_assets=[
                            a.model_dump(mode="json")
                            for a in state.sheets[x.actor.entity].assets
                            if a.family == "girl"
                        ],
                    )
                    for x in code.sessions(state)
                    if x.controller == viewer.user_id
                    and x.phase in ("proposed", "ready", "active")
                    and not x.body_swap
                ],
                swaps=[
                    dict(id=x.id, returned=bool(x.returned_event))
                    for x in rules.swaps(state)
                    if viewer.user_id in (int(x.actor.entity), x.controller)
                ],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                revision=state.revision,
                phase="returned"
                if x.returned_event
                else "hooked"
                if rules.connection(state, x.id).connected
                else "disconnected",
                pending=False,
                label="Actual AM body and hooked return",
                actor=x.actor.model_dump(mode="json"),
            )
            for x in rules.swaps(state)
            if viewer.user_id in (int(x.actor.entity), x.controller)
        ]
