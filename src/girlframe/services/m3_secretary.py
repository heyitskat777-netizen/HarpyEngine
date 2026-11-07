"""Actual personal Secretary source, delegated authority and owned gunpoint coordination."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_handler_advancements as advancement
from girlframe.engine import m3_secretary as rules
from girlframe.engine.m2 import ChoiceAnswer, GameState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, CastRole
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.engine.m3_missions import Mission
from girlframe.engine.m3_npc_orders import Order
from girlframe.engine.m3_world import introduce_npc, update
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_battle import _cast
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.m3_items import prove_item
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_npc_orders import NpcOrderService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def paid(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Acquisition:
    value = next((x for x in rules.acquisitions(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual original Secretary acquisition")
    gate = Access(game.store)
    assert gate.registry is not None
    gate.registry.require_available(rules.RULE)
    born = next(
        (x for x in rules.acquisitions(_history(c, game, value.event)) if x.id == identity), None
    )
    _, _, handler, appointment, award = HandlerAdvancementService(game.store)._proof(c, value.award)
    if (
        born != value
        or award is None
        or award.acquired_rule != rules.RULE
        or award.acquisition != value.id
        or award.spend_event != value.event
        or (handler, appointment) != (value.handler, value.appointment)
    ):
        raise WorkflowError("Recover the genuine original held award and exact Secretary spend")
    return value


def appointed(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Secretary:
    value = next((x for x in rules.secretaries(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover this exact actual personal Secretary appointment")
    receipt = paid(game, c, state, value.acquisition)
    source = _history(c, game, value.event)
    born = next((x for x in rules.secretaries(source) if x.id == identity), None)
    original = Npc.model_validate_json(value.original_npc_json)
    npc = (
        next((x for x in state.world.npcs if x.id == value.actor.entity), None)
        if state.world
        else None
    )
    event = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
        )
    ).first()
    birth_npc = (
        next((x for x in source.world.npcs if x.id == value.actor.entity), None)
        if source.world
        else None
    )
    if (
        born != value
        or value.actor.kind != "npc"
        or npc is None
        or birth_npc is None
        or birth_npc.controller != original.controller
        or npc.id != original.id
        or receipt.handler != value.handler
        or receipt.appointment != value.appointment
        or event != ("m3.secretary_appointed", receipt.handler.entity)
    ):
        raise WorkflowError("Preserve the actual Secretary person/controller and original Handler")
    return value


def current(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Secretary:
    value = appointed(game, c, state, identity)
    from girlframe.services.m3_handler_creation import HandlerCreationService

    if (
        not same_handler_body(state, value.handler)
        or HandlerCreationService(game.store)._appointment_source(c, int(value.handler.entity))
        != value.appointment
    ):
        raise WorkflowError("This Secretary belongs to its original Handler and appointment")
    actual = resolve(
        state, value.actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    npc = next(x for x in state.world.npcs if x.id == value.actor.entity) if state.world else None
    if (
        not actual.alive
        or actual.custody not in (None, "free")
        or actual.offstage_source
        or npc is None
        or npc.employment != "foundation"
    ):
        raise WorkflowError("Use the actual free living Secretary in the current world")
    return value


def order_authority(
    game: GameService,
    c: Connection,
    state: GameState,
    issuer: ActorRef,
    target: ActorRef,
    controller: int,
) -> rules.Secretary:
    value = rules.held(state, issuer)
    if value is None:
        raise WorkflowError("Only this exact actual Secretary speaks with delegated authority")
    value = current(game, c, state, value.id)
    if (
        value.handler.entity != str(controller)
        or target.kind != "pilot"
        or current_ref(state, int(target.entity)) != target
    ):
        raise WorkflowError(
            "The original Handler delegates only to its real Secretary and recipient"
        )
    return value


def prove_order(game: GameService, c: Connection, state: GameState, order: Order) -> None:
    value = current(game, c, state, order.condition)
    if (
        value.actor != order.issuer
        or value.handler != order.principal
        or int(value.handler.entity) != order.controller
    ):
        raise WorkflowError("Recover the exact personal Secretary and original Handler principal")


def record_authority(state: GameState, order: Order) -> None:
    if order.origin_kind != "secretary" or order.principal is None:
        raise ValueError("Record only the actual delegated Secretary Order")
    rules.put(
        state,
        rules.Performed(
            id="secretary-authority:" + order.id,
            secretary=order.condition,
            actor=order.issuer,
            principal=order.principal,
            play="authority",
            event=order.event,
            account=order.instruction,
            scene=order.cast.id,
            order=order.id,
            recipients=(order.target,),
        ),
    )


def prove_performed(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Performed:
    value = next((x for x in rules.performances(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual performed Secretary work")
    appointment = appointed(game, c, state, value.secretary)
    born = next(
        (x for x in rules.performances(_history(c, game, value.event)) if x.id == identity), None
    )
    if born != value or (value.actor, value.principal) != (appointment.actor, appointment.handler):
        raise WorkflowError("Preserve the original actual Secretary's source-owned work")
    if value.recipient_roles:
        original = _history(c, game, value.event)
        cast = next((x for x in original.scene_casts if x.id == value.scene), None)
        event = c.execute(
            sa.select(t.events.c.kind, t.events.c.actor_id).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == value.event
            )
        ).first()
        if (
            value.play != "authority"
            or value.order is not None
            or cast is None
            or not cast.open
            or cast.channel != value.statement_channel
            or cast.revision != value.statement_cast_revision
            or value.recipients != tuple(x.actor for x in value.recipient_roles)
            or len(set(value.recipients)) != len(value.recipients)
            or not any(x.actor == value.actor for x in cast.roles)
            or any(
                role not in cast.roles or role.actor == value.actor
                for role in value.recipient_roles
            )
            or event is None
            or (event.kind, event.actor_id) != ("m3.secretary_spoke", value.principal.entity)
        ):
            raise WorkflowError(
                "Recover the original spoken scene and exact addressed cast/controllers"
            )
        for role in value.recipient_roles:
            if role.actor.kind == "pilot":
                sheet = original.sheets.get(role.actor.entity)
                if (
                    sheet is None
                    or sheet.character_id != role.actor.incarnation
                    or sheet.owner != role.controller
                    or sheet.owner not in original.order
                ):
                    raise WorkflowError(
                        "Recover the original addressed Pilot incarnation/controller"
                    )
                label = sheet.callsign
            else:
                actual_recipient = resolve(original, role.actor, (), require_current_profile=False)
                if actual_recipient.controller != role.controller:
                    raise WorkflowError("Recover the actual original recipient controller")
                label = actual_recipient.label
            if value.recipient_labels.get(role.actor.token) != label:
                raise WorkflowError("Recover the actual original recipient role label")
    elif (
        value.statement_channel is not None
        or value.statement_cast_revision is not None
        or value.recipient_labels
    ):
        raise WorkflowError("An addressed statement requires its exact original recipients")
    if value.mission:
        raw = c.scalar(
            sa.select(t.m3["m3_mission_history"].c.body_json).where(
                t.m3["m3_mission_history"].c.campaign_id == game.store.campaign_id,
                t.m3["m3_mission_history"].c.id == value.mission,
                t.m3["m3_mission_history"].c.event_id == value.mission_event,
            )
        )
        if raw != value.mission_json:
            raise WorkflowError("The briefing must retain its genuine existing mission facts")
    return value


def _hostile(action: dict[str, Any]) -> tuple[ActorRef, ActorRef] | None:
    meta = action["data"].get("engage") or action["data"].get("battle")
    if not meta or action["data"].get("receipt") is not None:
        return None
    return ActorRef.model_validate(meta["actor"]), ActorRef.model_validate(meta["target"])


def opportunity(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> dict[str, Any] | None:
    hostile = _hostile(action)
    if hostile is None or rules.pending(state, action["id"]):
        return None
    attacker, target = hostile
    if attacker.kind != "pilot":
        return None
    for saved in rules.secretaries(state):
        if not same_handler_body(state, saved.handler) or not same_handler_body(state, target):
            continue
        try:
            value = current(game, c, state, saved.id)
            cast = _cast(game, c, state, int(action["channel_id"]))
            actual, enemy = (
                resolve(
                    state, ref, profiles(c, game.store.campaign_id), require_current_profile=False
                )
                for ref in (value.actor, attacker)
            )
            if (
                actual.cell is None
                or actual.cell != enemy.cell
                or enemy.inside_frame is not False
                or not any(x.actor == value.actor for x in cast.roles)
                or not any(x.actor == attacker for x in cast.roles)
            ):
                continue
            weapons = []
            for item in state.held_items:
                if (
                    item.holder == value.actor
                    and item.weapon
                    and item.condition == "intact"
                    and item.location_mode == "carried"
                ):
                    prove_item(c, game, state, item.id)
                    weapons.append(dict(id=item.id, label=item.name))
            if weapons:
                return dict(
                    secretary=value.id,
                    actor=value.actor.model_dump(mode="json"),
                    handler=value.handler.model_dump(mode="json"),
                    weapons=weapons,
                )
        except (ValueError, WorkflowError):
            continue
    return None


def intervene(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    weapon: str,
    event: str,
    account: str,
    *,
    firearm: bool,
) -> rules.Gunpoint:
    available = opportunity(game, c, state, action)
    hostile = _hostile(action)
    if (
        available is None
        or hostile is None
        or not firearm
        or not account.strip()
        or weapon not in {x["id"] for x in available["weapons"]}
    ):
        raise WorkflowError("Use the actual carried firearm and real original go-after action")
    value = current(game, c, state, available["secretary"])
    held = rules.Gunpoint(
        id=str(uuid4()),
        secretary=value.id,
        actor=value.actor,
        principal=value.handler,
        attacker=hostile[0],
        action=action["id"],
        cast=_cast(game, c, state, int(action["channel_id"])),
        weapon=weapon,
        event=event,
        account=account.strip(),
    )
    rules.put(state, held)
    action["data"]["secretary_gunpoint"] = held.id
    game.request(c, action, int(held.attacker.entity), "secretary_gunpoint", dict(gunpoint=held.id))
    return held


def gunpoint(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Gunpoint:
    value = next((x for x in rules.gunpoints(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual original gunpoint source")
    secretary = appointed(game, c, state, value.secretary)
    birth = _history(c, game, value.event)
    original = next((x for x in rules.gunpoints(birth) if x.id == identity), None)
    action = game.action(c, value.action)
    if (
        original is None
        or value.actor != secretary.actor
        or value.principal != secretary.handler
        or action["data"].get("secretary_gunpoint") != value.id
        or any(
            getattr(original, k) != getattr(value, k)
            for k in (
                "id",
                "secretary",
                "actor",
                "principal",
                "attacker",
                "action",
                "cast",
                "weapon",
                "event",
                "account",
            )
        )
    ):
        raise WorkflowError("Preserve the real Secretary, firearm and same original hostile action")
    return value


def require_clear(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    pending = rules.pending(state, action["id"])
    if pending:
        gunpoint(game, c, state, pending.id)
        raise WorkflowError("GUNPOINT: resolve the actual source-owned tactical response first")


def prepare_response(
    game: GameService,
    c: Connection,
    state: GameState,
    viewer: GuildViewer,
    channel: int,
    prepared: PlayInput,
) -> dict[str, Any] | None:
    if prepared.parent is None:
        return None
    parent = game.action(c, prepared.parent)
    identity = parent["data"].get("secretary_gunpoint")
    if not identity:
        return None
    SecretaryService(game.store)._access(c, viewer)
    value = gunpoint(game, c, state, identity)
    if (
        value.phase != "responding"
        or viewer.user_id != int(value.attacker.entity)
        or current_ref(state, viewer.user_id) != value.attacker
        or value.response_action is not None
        or channel != value.cast.channel
    ):
        raise WorkflowError("Only the real held attacker starts its actual source response")
    return dict(
        gunpoint=value.id, source_action=value.action, cast=value.cast.model_dump(mode="json")
    )


def link_response(state: GameState, identity: str, child: str, event: str) -> None:
    value = next(x for x in rules.gunpoints(state) if x.id == identity)
    if value.phase != "responding" or value.response_action:
        raise ValueError("Bind one actual response Play to this held original action")
    rules.put(state, value.model_copy(update=dict(response_action=child, response_started=event)))


def finish_response(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    meta = action["data"].get("secretary_response")
    if not meta:
        return
    value = gunpoint(game, c, state, meta["gunpoint"])
    if value.response_action != action["id"] or action["parent_id"] != value.action:
        raise WorkflowError("Complete only the genuine original held attacker's actual response")
    rules.put(state, value.model_copy(update=dict(phase="awaiting_resolution")))
    choices = t.m2["m2_choices"]
    c.execute(
        choices.update()
        .where(
            choices.c.campaign_id == game.store.campaign_id,
            choices.c.action_id == value.action,
            choices.c.kind == "secretary_response_play",
            choices.c.state == "pending",
            choices.c.actor_id == value.attacker.entity,
        )
        .values(state="completed_by_child", revision=choices.c.revision + 1)
    )
    parent = game.action(c, value.action)
    game.request(
        c,
        parent,
        int(value.principal.entity),
        "secretary_gunpoint_resolution",
        dict(gunpoint=value.id, response=action["id"]),
    )


def response_projection(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    identity = json.loads(request["body_json"])["gunpoint"]
    value = gunpoint(game, c, state, identity)
    return value.model_dump(mode="json")


def apply_response(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
) -> str:
    value = gunpoint(game, c, state, json.loads(request["body_json"])["gunpoint"])
    event = action["data"]["response_event"]
    if not answer.text.strip() or len(answer.options) != 1:
        raise WorkflowError("Describe the actual tactical response or Secretary action")
    choice = answer.options[0]
    if request["kind"] == "secretary_gunpoint":
        if (
            request["actor_id"] != value.attacker.entity
            or value.phase != "awaiting_attacker"
            or current_ref(state, int(value.attacker.entity)) != value.attacker
        ):
            raise WorkflowError("Only the original attacker owns this actual tactical response")
        if choice not in ("withdraw", "respond"):
            raise WorkflowError("Withdraw the actual go-after action or play a real response")
        phase = "withdrawn" if choice == "withdraw" else "responding"
        rules.put(
            state,
            value.model_copy(
                update=dict(phase=phase, response_event=event, response_account=answer.text.strip())
            ),
        )
        if phase == "responding":
            game.request(
                c,
                action,
                int(value.attacker.entity),
                "secretary_response_play",
                dict(gunpoint=value.id),
            )
        return phase
    if (
        request["kind"] != "secretary_gunpoint_resolution"
        or request["actor_id"] != value.principal.entity
    ):
        raise WorkflowError("The actual original Handler resolves only this Secretary source")
    if choice == "proceed":
        if value.phase != "awaiting_resolution" or not value.response_action:
            raise WorkflowError(
                "A real completed response is required before original continuation"
            )
        child = game.action(c, value.response_action)
        if (
            child["state"] != "complete"
            or child["parent_id"] != value.action
            or child["data"].get("secretary_response", {}).get("gunpoint") != value.id
        ):
            raise WorkflowError("Resolve the actual original attacker's source response first")
        phase = "proceeded"
    elif choice == "release":
        phase = "released"
    else:
        raise WorkflowError("Record actual tactical continuation or the Secretary lowering its gun")
    rules.put(
        state,
        value.model_copy(
            update=dict(phase=phase, resolution_event=event, resolution_account=answer.text.strip())
        ),
    )
    return phase


class SecretaryService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        gate = Access(self.store)
        gate.authorize(c, viewer, "economy", director_response=True)
        gate.authorize(c, viewer, "playbooks", director_response=True)
        assert gate.registry is not None
        gate.registry.require_available(rules.RULE)

    def _write(
        self, viewer: GuildViewer, key: str, kind: str, payload: dict[str, Any], operation: Any
    ) -> dict[str, Any]:
        try:
            return self.store._write(
                viewer,
                key,
                kind,
                payload,
                operation,
                auto_audit=False,
                authorize=lambda c: self._access(c, viewer),
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def _own(
        self, c: Connection, state: GameState, viewer: GuildViewer, identity: str, revision: int
    ) -> rules.Secretary:
        value = current(self.game, c, state, identity)
        if value.handler.entity != str(viewer.user_id) or state.revision != revision:
            raise WorkflowError("Only the original purchasing Handler makes these exact four Plays")
        return value

    def buy(
        self, viewer: GuildViewer, key: str, award_id: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _, state, handler, appointment, award = HandlerAdvancementService(self.store)._source(
                c, viewer, award_id
            )
            HandlerAdvancementService(self.store)._current(c, state, handler, appointment)
            if (
                state.revision != revision
                or award is None
                or award.phase != "held"
                or not account.strip()
                or any(same_handler_body(state, x.handler) for x in rules.acquisitions(state))
            ):
                raise WorkflowError(
                    "Spend one actual held award on this original Handler's Secretary"
                )
            event = str(uuid4())
            value = rules.Acquisition(
                id="secretary:" + award_id,
                award=award_id,
                handler=handler,
                appointment=appointment,
                event=event,
                account=account.strip(),
            )
            rules.put(state, value)
            advancement.put(
                state,
                advancement.Award.model_validate_json(
                    award.model_copy(
                        update=dict(
                            phase="spent",
                            acquired_rule=rules.RULE,
                            acquisition=value.id,
                            spend_event=event,
                            spend_account=account.strip(),
                        )
                    ).model_dump_json()
                ),
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.handler_advancement_spent",
                state,
                event_id=event,
                award_id=award_id,
                rule_id=rules.RULE,
            )
            return dict(id=value.id, phase="acquired")

        return self._write(
            viewer,
            key,
            "m3.secretary_acquired",
            dict(award=award_id, revision=revision, account=account),
            operation,
        )

    def appoint(
        self,
        viewer: GuildViewer,
        key: str,
        acquisition: str,
        revision: int,
        style: Literal["am", "military", "clone", "competent"],
        *,
        existing: str | None = None,
        name: str = "",
        detail: str = "",
        cell: tuple[int, int] | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            receipt = paid(self.game, c, state, acquisition)
            HandlerAdvancementService(self.store)._current(
                c, state, receipt.handler, receipt.appointment
            )
            if (
                state.revision != revision
                or receipt.handler.entity != str(viewer.user_id)
                or state.world is None
                or any(x.acquisition == acquisition for x in rules.secretaries(state))
            ):
                raise WorkflowError("Appoint one real Secretary for this original paid source")
            event, identity = str(uuid4()), str(uuid4())
            branch: Literal["promoted", "created"]
            if existing is not None:
                npc = next((x for x in state.world.npcs if x.id == existing and x.alive), None)
                if npc is None or rules.held(state, ActorRef(kind="npc", entity=npc.id)):
                    raise WorkflowError("Promote an actual living unappointed NPC")
                original = npc
                state.world = update(
                    state.world,
                    npcs=tuple(
                        x.model_copy(update=dict(employment="foundation")) if x.id == npc.id else x
                        for x in state.world.npcs
                    ),
                )
                branch = "promoted"
            else:
                if cell is None or not name.strip() or not detail.strip():
                    raise WorkflowError("Name the actual new person and known initial location")
                npc = Npc(
                    id="secretary-person:" + identity,
                    name=name.strip(),
                    detail=detail.strip(),
                    controller=viewer.user_id,
                    cell=cell,
                    jobs=("base_personnel",),
                    employment="foundation",
                    revealed=True,
                )
                original = npc
                state.world = introduce_npc(state.world, npc)
                branch = "created"
            value = rules.Secretary(
                id=identity,
                acquisition=acquisition,
                actor=ActorRef(kind="npc", entity=npc.id),
                handler=receipt.handler,
                appointment=receipt.appointment,
                event=event,
                branch=branch,
                original_npc_json=original.model_dump_json(),
                style=style,
            )
            rules.put(state, value)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.secretary_appointed",
                state,
                event_id=event,
                secretary=identity,
                npc_id=npc.id,
                branch=branch,
            )
            return dict(id=identity, branch=branch, actor=value.actor.model_dump(mode="json"))

        return self._write(
            viewer,
            key,
            "m3.secretary_appointed",
            dict(
                acquisition=acquisition,
                revision=revision,
                style=style,
                existing=existing,
                name=name,
                detail=detail,
                cell=cell,
            ),
            operation,
        )

    def appear(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        channel: int,
        destination: tuple[int, int],
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_scene_requisitions import guard

            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = self._own(c, state, viewer, identity, revision)
            scene = self.game.scene(c, channel)
            cast = _cast(self.game, c, state, channel)
            guard(c, self.store, cast.id, value.actor)
            if self.game.pending_actions(c) or not account.strip() or state.world is None:
                raise WorkflowError("Name the actual needed place before an active Play begins")
            lock = self.game.lock(c, channel)
            if lock and lock["state"] != "released":
                raise WorkflowError("Restore actual chat permissions before this appearance")
            if not state.world.board.contains(destination):
                raise WorkflowError("Choose an actual place on the known world map")
            npc = next(x for x in state.world.npcs if x.id == value.actor.entity)
            event = str(uuid4())
            state.world = update(
                state.world,
                npcs=tuple(
                    x.model_copy(update=dict(cell=destination)) if x.id == npc.id else x
                    for x in state.world.npcs
                ),
            )
            roles = (
                cast.roles
                if any(x.actor == value.actor for x in cast.roles)
                else cast.roles
                + (CastRole(actor=value.actor, controller=npc.controller, source_event=event),)
            )
            changed = cast.model_copy(update=dict(roles=roles, revision=cast.revision + 1))
            state.scene_casts = [x for x in state.scene_casts if x.id != cast.id] + [changed]
            c.execute(
                t.m2["m2_scenes"]
                .update()
                .where(
                    t.m2["m2_scenes"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_scenes"].c.channel_id == str(channel),
                )
                .values(
                    revision=scene["revision"] + 1,
                    participants_json=json.dumps(
                        sorted(set(scene["participants"]) | {npc.controller})
                    ),
                )
            )
            performed = rules.Performed(
                id=str(uuid4()),
                secretary=value.id,
                actor=value.actor,
                principal=value.handler,
                play="appear",
                event=event,
                account=account.strip(),
                scene=cast.id,
                destination=destination,
            )
            rules.put(state, performed)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.secretary_appeared",
                state,
                event_id=event,
                secretary=identity,
                performed=performed.id,
            )
            return dict(id=performed.id, actor=value.actor.model_dump(mode="json"), scene=cast.id)

        return self._write(
            viewer,
            key,
            "m3.secretary_appeared",
            dict(
                id=identity,
                revision=revision,
                channel=channel,
                destination=destination,
                account=account,
            ),
            operation,
        )

    def speak(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        channel: int,
        text: str,
        target: int | None = None,
        *,
        recipients: tuple[ActorRef, ...] = (),
    ) -> dict[str, Any]:
        if target is not None and recipients:
            raise WorkflowError("Choose a direct Order or addressed statement, not both")
        if target is not None:
            with self.store.engine.connect() as c:
                state = load_state(c, self.store.campaign_id)
                value = self._own(c, state, viewer, identity, revision)
            return NpcOrderService(self.game).issue(
                viewer, key, channel, value.actor, target, revision, text, origin_kind="secretary"
            )

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = self._own(c, state, viewer, identity, revision)
            cast = _cast(self.game, c, state, channel)
            if not any(x.actor == value.actor for x in cast.roles) or not text.strip():
                raise WorkflowError("The actual Secretary speaks to this real source scene")
            addressed = tuple(
                next((x for x in cast.roles if x.actor == ref), None) for ref in recipients
            )
            if (
                len(set(recipients)) != len(recipients)
                or any(x is None for x in addressed)
                or value.actor in recipients
            ):
                raise WorkflowError("Choose distinct actual addressed roles from this source scene")
            roles = tuple(x for x in addressed if x is not None)
            for role in roles:
                if (
                    resolve(
                        state,
                        role.actor,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    ).controller
                    != role.controller
                ):
                    raise WorkflowError(
                        "Refresh this actual scene's original recipient controllers"
                    )
            event = str(uuid4())
            played = rules.Performed(
                id=str(uuid4()),
                secretary=value.id,
                actor=value.actor,
                principal=value.handler,
                play="authority",
                event=event,
                account=text.strip(),
                scene=cast.id,
                recipients=recipients,
                recipient_roles=roles,
                recipient_labels={
                    role.actor.token: resolve(
                        state,
                        role.actor,
                        profiles(c, self.store.campaign_id),
                        require_current_profile=False,
                    ).label
                    for role in roles
                },
                statement_channel=cast.channel if roles else None,
                statement_cast_revision=cast.revision if roles else None,
            )
            rules.put(state, played)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.secretary_spoke",
                state,
                event_id=event,
                secretary=identity,
                performed=played.id,
            )
            return dict(id=played.id)

        return self._write(
            viewer,
            key,
            "m3.secretary_spoke",
            dict(id=identity, revision=revision, channel=channel, text=text, target=target)
            | (
                dict(recipients=[x.model_dump(mode="json") for x in recipients])
                if recipients
                else {}
            ),
            operation,
        )

    def competence(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        mission_id: str,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = self._own(c, state, viewer, identity, revision)
            missions = MissionService(self.store)
            mission = missions._mission(c, mission_id)
            if mission.handler != int(value.handler.entity) or not account.strip():
                raise WorkflowError("Prepare actual work from this original Handler's real mission")
            offered = not bool(mission.participants)
            people = mission.offered_to if offered else mission.participants
            ids = missions._source_characters(c, mission, offered=offered)
            recipients = tuple(
                ActorRef(kind="pilot", entity=str(uid), incarnation=ids[str(uid)])
                for uid in people
                if str(uid) in state.sheets and state.sheets[str(uid)].character_id == ids[str(uid)]
            )
            if not recipients:
                raise WorkflowError("Deliver the substantive work to actual original recipients")
            history = (
                c.execute(
                    sa.select(t.m3["m3_mission_history"]).where(
                        t.m3["m3_mission_history"].c.campaign_id == self.store.campaign_id,
                        t.m3["m3_mission_history"].c.id == mission.id,
                        t.m3["m3_mission_history"].c.revision == mission.revision,
                    )
                )
                .mappings()
                .one()
            )
            event = str(uuid4())
            played = rules.Performed(
                id=str(uuid4()),
                secretary=value.id,
                actor=value.actor,
                principal=value.handler,
                play="competence",
                event=event,
                account=account.strip(),
                mission=mission.id,
                mission_event=history["event_id"],
                mission_json=mission.model_dump_json(),
                recipients=recipients,
            )
            rules.put(state, played)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.secretary_competence_delivered",
                state,
                event_id=event,
                secretary=identity,
                performed=played.id,
                mission_id=mission.id,
            )
            return dict(id=played.id, recipients=len(recipients))

        return self._write(
            viewer,
            key,
            "m3.secretary_competence_delivered",
            dict(id=identity, revision=revision, mission=mission_id, account=account),
            operation,
        )

    def hold(
        self,
        viewer: GuildViewer,
        key: str,
        action_id: str,
        revision: int,
        weapon: str,
        account: str,
        *,
        firearm: bool = True,
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            action = self.game.action(c, action_id)
            available = opportunity(self.game, c, state, action)
            if available is None or state.revision != revision:
                raise WorkflowError("Reopen the actual unrolled go-after action and Secretary")
            value = self._own(c, state, viewer, available["secretary"], revision)
            event = str(uuid4())
            held = intervene(self.game, c, state, action, weapon, event, account, firearm=firearm)
            self.game.save_action(c, action, state="awaiting_choices")
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.secretary_gunpoint_held",
                state,
                event_id=event,
                action_id=action_id,
                secretary=value.id,
                gunpoint=held.id,
            )
            return dict(id=held.id, action=action_id, phase=held.phase)

        return self._write(
            viewer,
            key,
            "m3.secretary_gunpoint_held",
            dict(
                action=action_id, revision=revision, weapon=weapon, account=account, firearm=firearm
            ),
            operation,
        )

    def menu(self, viewer: GuildViewer, identity: str | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            performed = next((x for x in rules.performances(state) if x.id == identity), None)
            if performed:
                performed = prove_performed(self.game, c, state, performed.id)
                if not rules.reads_performance(performed, viewer.user_id):
                    raise WorkflowError(
                        "This substantive Secretary work belongs to original recipients"
                    )
                author = performed.principal.entity == str(viewer.user_id)
                visible = tuple(
                    x for x in performed.recipient_roles if author or x.controller == viewer.user_id
                )
                body = performed.model_dump(
                    mode="json",
                    exclude={
                        "recipient_roles",
                        "recipient_labels",
                        "statement_channel",
                        "statement_cast_revision",
                    },
                )
                body.update(
                    addressed_notice=bool(performed.recipient_roles),
                    addressed_to=[performed.recipient_labels[x.actor.token] for x in visible],
                    recipient_roles=[x.model_dump(mode="json") for x in visible],
                )
                if performed.recipient_roles:
                    body["recipients"] = [x.actor.model_dump(mode="json") for x in visible]
                return dict(kind="performed", revision=state.revision, body=body)
            receipts = [
                paid(self.game, c, state, x.id)
                for x in rules.acquisitions(state)
                if x.handler.entity == str(viewer.user_id)
            ]
            values = [
                appointed(self.game, c, state, x.id)
                for x in rules.secretaries(state)
                if x.handler.entity == str(viewer.user_id)
            ]
            if identity and identity not in ({x.id for x in receipts} | {x.id for x in values}):
                raise WorkflowError(
                    "This personal Secretary source belongs to another original Handler"
                )
            value = values[0] if values else None
            scenes = []
            for row in c.execute(
                sa.select(t.m2["m2_scenes"]).where(
                    t.m2["m2_scenes"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_scenes"].c.open.is_(True),
                )
            ).mappings():
                cast = _cast(self.game, c, state, int(row["channel_id"]))
                if viewer.user_id not in json.loads(row["participants_json"]) and not (
                    value and any(x.actor == value.actor for x in cast.roles)
                ):
                    continue
                scenes.append(
                    dict(
                        id=row["id"],
                        channel=int(row["channel_id"]),
                        audience=[
                            dict(
                                ref=role.actor.model_dump(mode="json"),
                                token=role.actor.token,
                                label=resolve(
                                    state,
                                    role.actor,
                                    profiles(c, self.store.campaign_id),
                                    require_current_profile=False,
                                ).label,
                            )
                            for role in cast.roles
                            if value is not None and role.actor != value.actor
                        ],
                        girls=[
                            dict(
                                ref=x.actor.model_dump(mode="json"),
                                token=x.actor.token,
                                label=resolve(
                                    state,
                                    x.actor,
                                    profiles(c, self.store.campaign_id),
                                    require_current_profile=False,
                                ).label,
                            )
                            for x in cast.roles
                            if x.actor.kind == "pilot"
                        ],
                    )
                )
            opportunities = []
            if value:
                for action_row in c.execute(
                    sa.select(t.m2["m2_actions"].c.id).where(
                        t.m2["m2_actions"].c.campaign_id == self.store.campaign_id,
                        t.m2["m2_actions"].c.state.not_in(("complete", "aborted")),
                    )
                ):
                    action = self.game.action(c, action_row.id)
                    available = opportunity(self.game, c, state, action)
                    if available and available["secretary"] == value.id:
                        opportunities.append(dict(action=action["id"], **available))
            missions = []
            if value:
                for raw in c.scalars(
                    sa.select(t.m3["m3_missions"].c.body_json).where(
                        t.m3["m3_missions"].c.campaign_id == self.store.campaign_id,
                        t.m3["m3_missions"].c.handler_id == str(viewer.user_id),
                    )
                ):
                    mission = Mission.model_validate_json(raw)
                    missions.append(dict(id=mission.id, label=mission.objective))
            return dict(
                kind="secretary",
                revision=state.revision,
                acquisition=receipts[0].id if receipts else None,
                secretary=value.model_dump(mode="json") if value else None,
                awards=[
                    dict(id=x.id, label=x.account)
                    for x in advancement.awards(state)
                    if x.phase == "held" and x.handler.entity == str(viewer.user_id)
                ],
                npcs=[dict(id=x.id, name=x.name) for x in state.world.npcs if x.alive]
                if state.world
                else [],
                places=[
                    dict(id=x.id, name=x.name, cell=x.cell)
                    for x in state.world.locations
                    if x.condition != "destroyed"
                ]
                if state.world
                else [],
                scenes=scenes,
                missions=missions,
                opportunities=opportunities,
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        result = [
            dict(
                id=x.id,
                revision=state.revision,
                label="Personal Secretary",
                phase="acquired",
                pending=False,
            )
            for x in rules.acquisitions(state)
            if x.handler.entity == str(viewer.user_id)
        ]
        for value in rules.performances(state):
            if rules.reads_performance(value, viewer.user_id):
                result.append(
                    dict(
                        id=value.id,
                        revision=state.revision,
                        label="Addressed Secretary statement"
                        if value.recipient_roles
                        else "Secretary work — " + value.play,
                        phase="performed",
                        pending=False,
                    )
                )
        # Gunpoint replies are actual canonical choices, exposed by ordinary shared-Play Inbox.
        return result


def refresh_after_response(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    """Rebase the same unrolled Engage on the real completed response costs."""
    identity = action["data"].get("secretary_gunpoint")
    value = gunpoint(game, c, state, identity) if identity else None
    if value is None or value.phase not in ("proceeded", "released"):
        raise WorkflowError("Resolve the actual held source before original continuation")
    if action["data"].get("receipt") is not None:
        raise WorkflowError("Never replace an already known roll")
    if value.response_action:
        child = game.action(c, value.response_action)
        if child["state"] != "complete" or child["parent_id"] != action["id"]:
            raise WorkflowError("Preserve the actual completed original response")
    meta = action["data"].get("engage")
    if meta is None:
        raise WorkflowError("This unrolled source needs its exact combat continuation adapter")
    bound = profiles(c, game.store.campaign_id)
    cast = _cast(game, c, state, int(action["channel_id"]))
    from girlframe.engine.m3_actors import fingerprint

    if fingerprint(cast) != meta["cast_sha256"]:
        raise WorkflowError("Recover changed actual cast before this original continuation")
    acting = resolve(state, value.attacker, bound)
    target = resolve(state, ActorRef.model_validate(meta["target"]), bound)
    if not any(not x.damaged for x in acting.assets):
        raise WorkflowError("No actual undamaged Asset remains for this original Engage")
    if acting.offstage_source or target.offstage_source:
        raise WorkflowError("An actual offstage original cannot resume this battlefield action")
    meta["actor_sha256"] = acting.source_sha256
    meta["target_sha256"] = target.source_sha256
    action["data"]["sheet_revision"] = state.sheets[value.attacker.entity].revision
