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
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def project_hardware(state: GameState, body: rules.Body) -> dict[str, Any]:
    """Private effective condition of this same saved vessel's actual components."""
    from girlframe.engine.m3_janus_storage import effective_body_assets

    return body.model_dump(mode="json") | {
        "assets": [
            x.model_dump(mode="json")
            for x in effective_body_assets(state, body.actor, body.vessel, assets=body.assets)
        ]
    }


def _history(game: GameService, c: Connection, event: str) -> GameState:
    from girlframe.services.m3_am_scrutinized import _history as history

    return history(game, c, event)


def _prove_items(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, items: tuple[str, ...]
) -> None:
    from girlframe.services.m3_items import prove_item

    rules.carried_assets(state, actor, items)
    for identity in items:
        prove_item(c, game, state, identity)


def carried_options(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> list[dict[str, str]]:
    items = tuple(x.id for x in state.held_items if x.asset_owner == actor)
    _prove_items(game, c, state, actor, items)
    return [
        dict(id=x.id, label=x.name, asset=str(x.asset_id))
        for x in state.held_items
        if x.id in items
    ]


def prove_conveyance(
    game: GameService, c: Connection, state: GameState, event: str
) -> rules.Conveyance:
    value = next((x for x in rules.conveyances(state) if x.event == event), None)
    if value is None:
        raise WorkflowError("Recover the actual performed physical conveyance")
    born = _history(game, c, event)
    audit = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    before_json = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json)
        .join(
            t.events,
            sa.and_(
                t.events.c.campaign_id == t.m2["m2_state_history"].c.campaign_id,
                t.events.c.id == t.m2["m2_state_history"].c.event_id,
            ),
        )
        .where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.seq < audit["seq"] if audit else sa.false(),
        )
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    if (
        value not in rules.conveyances(born)
        or value.id != event
        or audit is None
        or before_json is None
        or audit["actor_id"] != str(value.controller)
        or not value.items
    ):
        raise WorkflowError("Recover the original human's canonical conveyance source")
    before = GameState.model_validate_json(before_json)
    _prove_items(game, c, before, value.actor, value.items)
    if (
        rules.carried_assets(before, value.actor, value.items) != value.assets
        or any(x not in born.sheets[value.actor.entity].assets for x in value.assets)
        or any(x not in born.held_items for x in before.held_items if x.id in value.items)
        or any(a.id in {x.id for x in value.assets} for b in rules.bodies(born) for a in b.assets)
        or rules._pose(before, value.actor).vessel_id != value.previous
        or rules._pose(born, value.actor).vessel_id != value.vessel
    ):
        raise WorkflowError("Preserve each actual object's sole Asset, custody and condition")
    if value.kind == "code":
        source = rules.swap(born, value.source)
        choice = t.m2["m2_choices"]
        response = t.m2["m2_responses"]
        raw = c.scalar(
            sa.select(response.c.answer_json)
            .join(
                choice,
                sa.and_(
                    choice.c.campaign_id == response.c.campaign_id,
                    choice.c.id == response.c.choice_id,
                ),
            )
            .where(
                response.c.campaign_id == game.store.campaign_id,
                response.c.event_id == event,
                response.c.actor_id == str(value.controller),
                choice.c.kind == "am_code_body",
                choice.c.action_id == source.action,
            )
        )
        answer = ChoiceAnswer.model_validate_json(raw) if raw else None
        if (
            source.event != event
            or audit["kind"] not in ("m2.choice_resolved", "m3.choice_resolved")
            or source.actor != value.actor
            or source.controller != value.controller
            or (source.original_vessel, source.new_vessel) != (value.previous, value.vessel)
            or source.carried_items != value.items
            or answer is None
            or answer.options != (source.preparation,)
            or answer.fields != {"carried_items": json.dumps(list(value.items))}
            or answer.text.strip() != value.account
        ):
            raise WorkflowError("Prove the actual circuit operator's selected physical conveyance")
    elif value.kind == "return":
        source = rules.swap(born, value.source)
        if (
            source.returned_event != event
            or source.actor != value.actor
            or (source.new_vessel, source.original_vessel) != (value.previous, value.vessel)
            or audit["kind"] != "m3.am_body_returned"
            or value.controller != int(value.actor.entity)
        ):
            raise WorkflowError("Prove this original AM's actual return conveyance")
    else:
        from girlframe.engine.m3_am_jailbroken import get

        occupancy = get(born, value.source)
        if (
            occupancy.event != event
            or occupancy.actor != value.actor
            or (occupancy.previous, occupancy.vessel) != (value.previous, value.vessel)
            or occupancy.carried_items != value.items
            or audit["kind"] != "m3.am_jailbroken_occupied"
            or value.controller != int(value.actor.entity)
        ):
            raise WorkflowError("Prove this original AM's actual occupancy conveyance")
    return value


def _source_handler(game: GameService, c: Connection, value: code.Maintenance) -> ActorRef:
    original = active_handler(_history(game, c, value.proposed_event))
    if original is None:
        raise WorkflowError("Recover this circuit source's actual original Handler")
    return original


def _appointment_at(game: GameService, c: Connection, event: str, author: ActorRef) -> str:
    from girlframe.engine.handler_setup import HandlerSetup

    seq = c.scalar(
        sa.select(t.events.c.seq).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == event,
        )
    )
    if seq is None:
        raise WorkflowError("Recover the actual factual event before its appointment")
    row = (
        c.execute(
            sa.select(t.setup_revisions)
            .join(
                t.events,
                sa.and_(
                    t.events.c.campaign_id == t.setup_revisions.c.campaign_id,
                    t.events.c.id == t.setup_revisions.c.event_id,
                ),
            )
            .where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.kind == "campaign.handler_appointed",
                t.events.c.seq <= seq,
            )
            .order_by(t.setup_revisions.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None or HandlerSetup.model_validate_json(row["body_json"]).handler_id != int(
        author.entity
    ):
        raise WorkflowError("Recover the actual original factual Handler appointment")
    return str(row["event_id"])


def _fact_uid(preparation: rules.Preparation) -> int:
    return (
        int(preparation.fact_author.entity) if preparation.fact_author else preparation.controller
    )


def _can_record_connection(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    preparation: rules.Preparation,
) -> bool:
    if viewer.user_id != _fact_uid(preparation) or state.handler != viewer.user_id:
        return False
    if preparation.fact_author is None:
        return True
    if not same_handler_body(state, preparation.fact_author):
        return False
    from girlframe.services.m3_medical import MedicalService

    return MedicalService(game.store)._handler(c) == (viewer.user_id, preparation.fact_appointment)


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
    maintenance = code.session(original, value.maintenance)
    if (
        value not in rules.preparations(original)
        or event is None
        or (event.kind, event.actor_id) != ("m3.am_body_prepared", str(_fact_uid(value)))
        or original.handler != _fact_uid(value)
        or (maintenance.actor, maintenance.operator, maintenance.controller)
        != (value.actor, value.operator, value.controller)
    ):
        raise WorkflowError("Recover the actual human's original hardware preparation facts")
    if value.fact_author is None:
        if maintenance.operator.kind == "pilot":
            raise WorkflowError("The independent Pilot needs its actual Handler factual source")
    elif (
        value.fact_author != _source_handler(game, c, maintenance)
        or not same_handler_body(original, value.fact_author)
        or _appointment_at(game, c, value.event, value.fact_author) != value.fact_appointment
    ):
        raise WorkflowError("Preserve the original Handler body and actual factual appointment")
    _prove_items(game, c, original, value.actor, value.spec.carried_items)
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
            str(_fact_uid(prep)),
        ):
            raise WorkflowError("Only the actual original factual source establishes hookup")
        if prep.fact_author is not None and (
            not same_handler_body(_history(game, c, link.event), prep.fact_author)
            or _appointment_at(game, c, link.event, prep.fact_author) != prep.fact_appointment
        ):
            raise WorkflowError("Preserve the actual original hookup's Handler source context")
    if value.neural_route is not None:
        from girlframe.services.m3_am_neural_route import prove_route

        route = prove_route(game, c, state, value.neural_route)
        if (
            route.code_maintenance != value.maintenance
            or not any(x.swap == value.id and x.event == value.event for x in route.moves)
            or (
                value.returned_event
                and not any(
                    x.swap == value.id and x.event == value.returned_event for x in route.moves
                )
            )
        ):
            raise WorkflowError("Recover this Code Swap's real continuous route transitions")
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
    if value.carried_items:
        prove_conveyance(game, c, state, value.event)
    if value.returned_event and any(
        x.event == value.returned_event
        for x in rules.conveyances(_history(game, c, value.returned_event))
    ):
        prove_conveyance(game, c, state, value.returned_event)
    return value


def projection(
    game: GameService, c: Connection, state: GameState, value: code.Maintenance
) -> dict[str, Any]:
    from girlframe.engine.m3_am_neural_route import records as route_records
    from girlframe.services.m3_am_neural_route import prove_route

    return dict(
        neural_routes=[
            dict(id=x.id, preparation=x.preparation, label="Actual continuous interface")
            for x in route_records(state)
            if x.code_maintenance == value.id and not x.moves and prove_route(game, c, state, x.id)
        ],
        carried_items=carried_options(game, c, state, value.actor),
        bodies=[
            dict(
                id=x.id,
                label=x.spec.label,
                vessel=x.spec.vessel,
                carried_items=list(x.spec.carried_items),
            )
            for x in rules.preparations(state)
            if x.maintenance == value.id
            and not any(s.preparation == x.id for s in rules.swaps(state))
        ],
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
        or set(answer.fields) - {"carried_items", "neural_route"}
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
    try:
        raw = json.loads(answer.fields["carried_items"]) if "carried_items" in answer.fields else []
        if not isinstance(raw, list) or any(not isinstance(x, str) for x in raw):
            raise ValueError("Select the actual physical object IDs")
        items = tuple(raw)
    except (ValueError, TypeError) as error:
        raise WorkflowError("Select only the actual carried objects") from error
    _prove_items(game, c, state, value.actor, items)
    route_id = answer.fields.get("neural_route")
    if route_id is not None:
        from girlframe.services.m3_am_neural_route import require_code_move

        route = require_code_move(game, c, state, action, route_id)
        if route.preparation != prepared.id:
            raise WorkflowError("Select the exact prepared destination of this Code route")
    changed = rules.transfer(
        state,
        value,
        prepared.id,
        action["data"]["response_event"],
        carried_items=items,
        carry_account=answer.text if items else None,
        neural_route=route_id,
    )
    if route_id is not None:
        from girlframe.engine.m3_am_neural_route import stage_code_move

        stage_code_move(state, route_id, changed.id, action["data"]["response_event"])
    code.put(state, value.model_copy(update=dict(body_swap=changed.id)))


class BodyService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def neural_controls(self, viewer: GuildViewer, actor: ActorRef) -> dict[str, Any]:
        """Original AM's own spinal sources, independently of any Code/body hookup."""
        from girlframe.engine.m3_actor_bonds import current_ref
        from girlframe.engine.m3_actors import resolve
        from girlframe.services.m3_actors import profiles
        from girlframe.services.m3_frame_control import (
            FrameControlService,
            _bodies,
            connection_endpoints,
        )
        from girlframe.services.m3_frame_control import (
            prove as prove_connection,
        )

        with self.store.engine.connect() as c:
            FrameControlService(self.game)._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            if (
                actor.kind != "pilot"
                or actor.entity != str(viewer.user_id)
                or actor != current_ref(state, viewer.user_id)
            ):
                raise WorkflowError("Open the original current AM's own spinal controls")
            self.game.character_binding(c, state, viewer.user_id)
            actual = resolve(state, actor, profiles(c, self.store.campaign_id))
            if actual.controller != viewer.user_id or actual.girl != "AM" or not actual.alive:
                raise WorkflowError("Only the actual living AM owns these spinal controls")
            connections = []
            for value in state.neural_connections:
                if actor not in (value.caster, value.battery):
                    continue
                prove_connection(self.game, c, state, value.id)
                endpoints = connection_endpoints(self.game, c, value)
                error = None
                if value.phase in ("target", "review", "connected"):
                    try:
                        _bodies(self.game, c, state, value)
                    except (WorkflowError, ValueError) as problem:
                        error = str(problem)
                connections.append(
                    dict(
                        id=value.id,
                        phase=value.phase,
                        label="Actual spinal source: " + value.phase,
                        current_endpoints=endpoints,
                        error=error,
                    )
                )
            return dict(
                actor=actor.model_dump(mode="json"),
                revision=state.revision,
                connections=connections,
            )

    def prepare(
        self, viewer: GuildViewer, key: str, maintenance: str, expected: int, spec: rules.BodySpec
    ) -> dict[str, Any]:
        from girlframe.services.m3_am_code import access, actual, source

        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, maintenance)
            actual(self.game, c, state, value)
            author = (
                _source_handler(self.game, c, value) if value.operator.kind == "pilot" else None
            )
            from girlframe.services.m3_medical import MedicalService

            appointment = MedicalService(self.store)._handler(c)[1] if author else None
            if (
                viewer.user_id != (int(author.entity) if author else value.controller)
                or (author is not None and not same_handler_body(state, author))
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
            _prove_items(self.game, c, state, value.actor, spec.carried_items)
            event = str(uuid4())
            body = rules.prepare(
                state, value, spec, event, fact_author=author, fact_appointment=appointment
            )
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
        preparation = prove_preparation(self.game, c, state, value.preparation)
        if viewer.user_id not in (
            int(value.actor.entity),
            value.controller,
            _fact_uid(preparation),
        ):
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
            preparation = prove_preparation(self.game, c, state, value.preparation)
            if (
                viewer.user_id != _fact_uid(preparation)
                or (
                    preparation.fact_author is not None
                    and not same_handler_body(state, preparation.fact_author)
                )
                or state.handler != viewer.user_id
                or state.revision != expected
                or value.returned_event
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "Only the actual original factual source records the real hookup"
                )
            if preparation.fact_author is not None:
                from girlframe.services.m3_medical import MedicalService

                if MedicalService(self.store)._handler(c) != (
                    viewer.user_id,
                    preparation.fact_appointment,
                ):
                    raise WorkflowError("Recover the original factual Handler appointment")
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
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        *,
        carried_items: tuple[str, ...] = (),
        carry_account: str | None = None,
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
            _prove_items(self.game, c, state, value.actor, carried_items)
            changed = rules.return_to_origin(
                state, identity, event, carried_items=carried_items, carry_account=carry_account
            )
            if value.neural_route is not None:
                from girlframe.engine.m3_am_neural_route import stage_code_move

                stage_code_move(state, value.neural_route, value.id, event, returning=True)
            self.game.event(
                c, viewer.user_id, key, "m3.am_body_returned", state, event_id=event, swap=identity
            )
            from girlframe.services.m3_am_body_consequences import synchronize

            synchronize(self.game, c, event)
            return dict(id=identity, vessel=changed.original_vessel)

        return self.store._write(
            viewer,
            key,
            "m3.am_body_return",
            dict(
                id=identity,
                expected=expected,
                **(
                    dict(carried_items=carried_items, carry_account=carry_account)
                    if carried_items or carry_account is not None
                    else {}
                ),
            ),
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
                    project_hardware(state, x)
                    for x in rules.bodies(state)
                    if x.actor == value.actor
                ],
                current=project_hardware(state, occupied) if occupied else None,
                owner=viewer.user_id == int(value.actor.entity),
                controller=viewer.user_id == value.controller,
                can_record_connection=_can_record_connection(
                    self.game,
                    c,
                    state,
                    viewer,
                    prove_preparation(self.game, c, state, value.preparation),
                ),
                carried_items=carried_options(self.game, c, state, value.actor),
                conveyances=[
                    prove_conveyance(self.game, c, state, x.event).model_dump(mode="json")
                    for x in rules.conveyances(state)
                    if x.actor == value.actor
                ],
            )

    def menu(self, viewer: GuildViewer) -> dict[str, Any]:
        from girlframe.services.m3_am_code import access

        with self.store.engine.connect() as c:
            access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            from girlframe.engine.m3_am_neural_route import records as route_records

            return dict(
                revision=state.revision,
                code_continuity=[
                    dict(id=x.id, maintenance=x.maintenance, label=x.spec.label)
                    for x in rules.preparations(state)
                    if int(x.actor.entity) == viewer.user_id
                    and code.session(state, x.maintenance).phase == "proposed"
                    and code.session(state, x.maintenance).root is None
                    and rules.spinal_links(state, x.actor)
                    and not any(
                        r.code_maintenance == x.maintenance and r.preparation == x.id
                        for r in route_records(state)
                    )
                ],
                preparations=[
                    dict(
                        id=x.id,
                        label=x.proposal,
                        mind_assets=[
                            a.model_dump(mode="json")
                            for a in state.sheets[x.actor.entity].assets
                            if a.family == "girl" and a.id not in rules.carried_ids(state, x.actor)
                        ],
                        carried_items=carried_options(self.game, c, state, x.actor),
                    )
                    for x in code.sessions(state)
                    if (
                        int(_source_handler(self.game, c, x).entity)
                        if x.operator.kind == "pilot"
                        else x.controller
                    )
                    == viewer.user_id
                    and x.phase in ("proposed", "ready", "active")
                    and not x.body_swap
                ],
                swaps=[
                    dict(id=x.id, returned=bool(x.returned_event))
                    for x in rules.swaps(state)
                    if viewer.user_id
                    in (
                        int(x.actor.entity),
                        x.controller,
                        _fact_uid(prove_preparation(self.game, c, state, x.preparation)),
                    )
                ],
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        result = []
        for value in code.sessions(state):
            if (
                value.operator.kind == "pilot"
                and bool({"body", "branch"} & set(value.selected_options))
                and value.phase == "active"
                and not value.body_swap
                and _source_handler(self.game, c, value).entity == str(viewer.user_id)
                and not any(x.maintenance == value.id for x in rules.preparations(state))
            ):
                result.append(
                    dict(
                        id=value.id,
                        revision=state.revision,
                        phase="prepare",
                        pending=True,
                        label="Prepare actual Pilot-operated AM hardware",
                        actor=value.actor.model_dump(mode="json"),
                    )
                )
        for swap in rules.swaps(state):
            preparation = prove_preparation(self.game, c, state, swap.preparation)
            if viewer.user_id in (
                int(swap.actor.entity),
                swap.controller,
                _fact_uid(preparation),
            ):
                result.append(
                    dict(
                        id=swap.id,
                        revision=state.revision,
                        phase="returned"
                        if swap.returned_event
                        else "hooked"
                        if rules.connection(state, swap.id).connected
                        else "disconnected",
                        pending=False,
                        label="Actual AM body and hooked return",
                        actor=swap.actor.model_dump(mode="json"),
                    )
                )
        return result
