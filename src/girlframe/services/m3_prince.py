"""The Prince's actual performances, fans, purchases and source-owned consequences."""

import json
from typing import Any, Literal, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_prince as rules
from girlframe.engine.m2 import AssetState, ChoiceAnswer, GameState, PlayInput, shift_status
from girlframe.engine.m3_actor_bonds import change, current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_core import install
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_intracadre_marriage import available, debit
from girlframe.engine.m3_mockingbird import give_tag
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.engine.m3_work_scope import WorkScope
from girlframe.engine.m3_world_state import Npc
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access, digest
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _audit, _cast, _response, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_intracadre_marriage import prepare_payment
from girlframe.services.m3_privileges import purchase_proof
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def _copy(state: GameState, other: GameState) -> None:
    for name in GameState.model_fields:
        setattr(state, name, getattr(other, name))


def _get(state: GameState, model: Any, identity: str) -> Any:
    value = next((x for x in rules.records(state, model) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Open the actual original Prince source")
    return value


def _access(game: GameService, c: Connection, viewer: GuildViewer, rule: str) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(rule)


def _actor(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> Any:
    actual = resolve(state, actor, profiles(c, game.store.campaign_id))
    rules.current_frame(state, actor)
    if not actual.alive or actual.rules != "girl_frame":
        raise WorkflowError("Use the actual current original Girl and existing usable Frame")
    return actual


def prove_grant(game: GameService, c: Connection, state: GameState, grant: rules.Grant) -> None:
    born = _get(_history(c, game, grant.event), rules.Grant, grant.id)
    receipt = next((x for x in state.requisitions if x.id == grant.purchase), None)
    if (
        born != grant
        or not isinstance(receipt, FrameRuleReceipt)
        or (
            receipt.rule_id != grant.rule
            or receipt.actor != grant.actor
            or receipt.frame_instance != grant.frame
            or receipt.source_event != grant.event
            or receipt.grant != grant.id
            or receipt.donor_frame != "THE PRINCE"
        )
    ):
        raise WorkflowError("Recover the actual original paid Prince source and receipt")
    purchase_proof(c, game.store, receipt)


def held(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, rule: str
) -> rules.Grant | None:
    if not any(x.actor == actor and x.rule == rule for x in rules.records(state, rules.Grant)):
        return None
    try:
        frame = rules.current_frame(state, actor)
    except ValueError:
        return None
    for value in reversed(rules.records(state, rules.Grant)):
        if (
            value.actor == actor
            and value.rule == rule
            and value.frame == frame
            and not suspended(state, value.purchase)
        ):
            prove_grant(game, c, state, value)
            return value
    return None


def _released(game: GameService, rule: str) -> bool:
    approval = game.store.policy.m3_approval
    if (
        approval is None
        or "plays" not in approval.subsystems
        or game.store.policy.owner_m3_rulings is None
    ):
        return False
    try:
        registry = Access(game.store).registry
        if (
            registry is None
            or digest(registry) != approval.registry_sha256
            or approval.scope == "core_complete"
            and registry.coverage != "RULES_COMPLETE"
        ):
            return False
        registry.require_available(rule)
    except (ValueError, WorkflowError):
        return False
    return True


def _disobediences(game: GameService, c: Connection, grant: rules.Grant) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    table = t.m2["m2_actions"]
    for identity in c.scalars(
        sa.select(table.c.id).where(
            table.c.campaign_id == game.store.campaign_id,
            table.c.actor_id == grant.actor.entity,
            table.c.state == "complete",
        )
    ):
        action = game.action(c, identity)
        if (
            action["data"].get("play") == "disobey_orders"
            and action["data"].get("result", {}).get("can_disobey")
            and action["data"].get("character_ids", {}).get(grant.actor.entity)
            == grant.actor.incarnation
        ):
            _roll_source(game, c, action)
            result.append(
                dict(id=identity, label="Actual completed disobedience " + str(len(result) + 1))
            )
    return result


def _fanbase(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, event: str | None = None
) -> rules.FanbaseState:
    value = rules.current_fanbase(state, actor)
    if value:
        original = rules.current_fanbase(_history(c, game, value.event), actor)
        if original != value:
            raise WorkflowError("Preserve the actual source of current demographics and demands")
        return value
    sheet = state.sheets[actor.entity]
    if sheet.frame != "THE PRINCE":
        raise WorkflowError("SOURCE_FANBASE_REQUIRED: recover this actual retained Fanbase source")
    source = sheet.frame_runtime.fanbase if sheet.frame_runtime else sheet.review.creation.fanbase
    if source is None or source.missing():
        raise WorkflowError("Recover the genuine original Prince creation or Frame setup")
    frame = rules.current_frame(state, actor)
    entries = []
    for index, name in enumerate(source.additional_identities):
        key = frame + ":fan:" + str(index) if sheet.frame_runtime else "fan:" + str(index)
        actual = next(
            (x for x in sheet.identities if x.id == key and x.name == name and x.protected), None
        )
        if actual is None:
            raise WorkflowError("Preserve the original real protected demographic Identity")
        entries.append(
            rules.Demographic(
                id=rules.identity(actor.token, frame, key),
                name=name,
                identity=key,
                event=event or "",
            )
        )
    value = rules.FanbaseState(
        actor=actor,
        frame=frame,
        origin=sheet.source_fingerprint,
        demographics=tuple(entries),
        demanded=tuple(source.label(x) for x in source.demanded),
        rejected=tuple(source.label(x) for x in source.rejected),
        event=event or "",
    )
    if event:
        rules.put(state, value)
    return value


def current_fanbase(
    game: GameService, c: Connection, state: GameState, actor: ActorRef
) -> dict[str, Any] | None:
    try:
        return _fanbase(game, c, state, actor).model_dump(mode="json")
    except (ValueError, WorkflowError):
        return None


def _parties(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    target: ActorRef,
    channel: int,
) -> tuple[Any, Any, SceneCast]:
    first = _actor(game, c, state, actor)
    other = resolve(state, target, profiles(c, game.store.campaign_id))
    scene = _cast(game, c, state, channel)
    if (
        target == actor
        or not other.alive
        or target.kind not in ("pilot", "handler", "npc")
        or not all(
            any(x.actor == person and x.controller == controller for x in scene.roles)
            for person, controller in ((actor, first.controller), (target, other.controller))
        )
    ):
        raise WorkflowError("Use the actual original on-scene people and their own controllers")
    return first, other, scene


def _proof(game: GameService, c: Connection, state: GameState, model: Any, identity: str) -> Any:
    value = _get(state, model, identity)
    born = _get(_history(c, game, value.event), model, identity)
    immutable = {
        rules.Performance: (
            "actor",
            "target",
            "caster",
            "counterpart",
            "cast",
            "frame",
            "fanbase_event",
            "part",
            "following",
            "account",
            "event",
        ),
        rules.Recognition: (
            "actor",
            "target",
            "caster",
            "counterpart",
            "handler",
            "handler_controller",
            "cast",
            "frame",
            "grant",
            "event",
            "account",
        ),
        rules.PlanGrant: (
            "actor",
            "handler",
            "controller",
            "cast",
            "action",
            "override",
            "grant",
            "event",
        ),
        rules.OffDutyTask: (
            "actor",
            "frame",
            "period",
            "action",
            "receipt",
            "rule",
            "grant",
            "event",
        ),
        rules.Violation: (
            "actor",
            "handler",
            "controller",
            "cast",
            "event",
            "account",
            "disclosed",
        ),
        rules.DemandAttempt: ("actor", "frame", "cast", "event", "account"),
        rules.DemandException: ("actor", "fanbase_event", "action", "receipt", "event", "account"),
    }.get(model)
    if immutable is None:
        if born != value:
            raise WorkflowError("Preserve the immutable actual Prince source")
    elif any(getattr(born, k) != getattr(value, k) for k in immutable):
        raise WorkflowError("Preserve the actual original people, source and choices")
    updates = {
        rules.Recognition: (
            ("selected_event", ("branch",)),
            ("question_event", ("question",)),
            ("completed_event", ("answer", "tag")),
        ),
        rules.PlanGrant: (("used_event", ("account", "recipients", "reveal_cast")),),
        rules.OffDutyTask: (("completed_event", ("option", "account")),),
        rules.Violation: (("decided_event", ("case",)),),
        rules.DemandException: (("used_event", ("used_by",)),),
    }.get(model, ())
    for pointer, fields in updates:
        actual_event = getattr(value, pointer)
        if actual_event:
            saved = _get(_history(c, game, actual_event), model, identity)
            if getattr(saved, pointer) != actual_event or any(
                getattr(saved, field) != getattr(value, field) for field in fields
            ):
                raise WorkflowError("Recover the original canonical performed source result")
    return value


class PrinceService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _write(
        self,
        viewer: GuildViewer,
        key: str,
        kind: str,
        revision: int,
        payload: dict[str, Any],
        operation: Any,
        rule: str = rules.FANBASE,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            _access(self.game, c, viewer, rule)

        def execute(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            if state.revision != revision:
                raise WorkflowError("STALE_PRINCE: reopen the actual current source")
            event = str(uuid4())
            result: dict[str, Any] = operation(c, state, event)
            canonical_kind = kind
            metadata = {k: v for k, v in result.items() if k in ("id", "rule", "source")}
            if kind == "m3.prince_acquired":
                receipt = next(
                    (
                        x
                        for x in state.requisitions
                        if x.id == result["purchase"] and isinstance(x, FrameRuleReceipt)
                    ),
                    None,
                )
                if not isinstance(receipt, FrameRuleReceipt) or receipt.source_event != event:
                    raise WorkflowError("Publish only the actual source-priced paid receipt")
                canonical_kind = "m3." + receipt.kind + "_purchased"
                metadata.update(
                    requisition_id=receipt.id, cost=receipt.price, rule_id=receipt.rule_id
                )
            self.game.event(
                c,
                viewer.user_id,
                key,
                canonical_kind,
                state,
                event_id=event,
                **metadata,
            )
            return result

        try:
            return self.store._write(
                viewer,
                key,
                kind,
                dict(revision=revision) | payload,
                execute,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def menu(self, viewer: GuildViewer, channel: int | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            if state.handler == viewer.user_id and str(viewer.user_id) not in state.sheets:
                handler = active_handler(state)
                return dict(
                    revision=state.revision,
                    actor=handler.model_dump(mode="json") if handler else None,
                    frame=None,
                    fanbase=None,
                    targets=[],
                    heat=0,
                    permissions=0,
                    purchases=[],
                    tasks=self._tasks(c, viewer),
                )
            actor = current_ref(state, viewer.user_id)
            actual = _actor(self.game, c, state, actor)
            fanbase = current_fanbase(self.game, c, state, actor)
            targets = []
            if channel is not None:
                scene = _cast(self.game, c, state, channel)
                for role in scene.roles:
                    if role.actor != actor and role.actor.kind in ("pilot", "handler", "npc"):
                        target = resolve(state, role.actor, profiles(c, self.store.campaign_id))
                        if target.alive:
                            targets.append(
                                dict(
                                    id=role.actor.token,
                                    ref=role.actor.model_dump(mode="json"),
                                    label=target.label,
                                )
                            )
            return dict(
                revision=state.revision,
                actor=actor.model_dump(mode="json"),
                frame=rules.current_frame(state, actor),
                fanbase=fanbase,
                targets=targets,
                heat=actual.heat,
                permissions=available(state, actor),
                purchases=[
                    dict(
                        id=x,
                        title=rules.TITLES[x],
                        price=2 if state.sheets[actor.entity].frame == "THE PRINCE" else 3,
                        held=bool(held(self.game, c, state, actor, x)),
                    )
                    for x in rules.RULES
                ],
                tasks=self._tasks(c, viewer),
            )

    def demand_menu(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            if not _released(self.game, rules.FANBASE) or str(viewer.user_id) not in state.sheets:
                return dict(available=False)
            actor = current_ref(state, viewer.user_id)
            if (
                state.sheets[actor.entity].frame != "THE PRINCE"
                and rules.current_fanbase(state, actor) is None
            ):
                return dict(available=False)
            value = _fanbase(self.game, c, state, actor)
            return dict(
                available=True,
                fanbase=value.model_dump(mode="json"),
                exceptions=[
                    dict(id=x.id, label=x.account)
                    for x in rules.records(state, rules.DemandException)
                    if x.actor == actor and x.used_by is None
                ],
            )

    def member_menu(
        self, viewer: GuildViewer, prince: ActorRef, member: ActorRef
    ) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer, rules.FANBASE)
            state = load_state(c, self.store.campaign_id)
            actual = resolve(state, member, profiles(c, self.store.campaign_id))
            if not actual.alive or actual.controller != viewer.user_id:
                raise WorkflowError("Use only your actual controlled person's factual membership")
            value = _fanbase(self.game, c, state, prince)
            return dict(
                revision=state.revision,
                demographics=[dict(id=x.id, label=x.name) for x in value.demographics],
            )

    def buy(
        self, viewer: GuildViewer, key: str, revision: int, rule: str, account: str
    ) -> dict[str, Any]:
        if rule not in rules.RULES or not account.strip():
            raise WorkflowError("Choose the actual printed Prince Requisition and acquisition")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            from girlframe.services.m3_requisitions import RequisitionService

            actor = current_ref(state, viewer.user_id)
            _actor(self.game, c, state, actor)
            RequisitionService(self.game)._safe(c, state, viewer.user_id)
            sheet = state.sheets[actor.entity]
            if rule == rules.BAD and active_handler(state) is None:
                raise WorkflowError("Recover the actual Handler who gains the printed Play")
            if any(
                x.actor == actor and x.frame == rules.current_frame(state, actor) and x.rule == rule
                for x in rules.records(state, rules.Grant)
            ) and rule not in (rules.HERO, rules.GROWING):
                raise WorkflowError(
                    "Restore the original paid source rather than purchasing it twice"
                )
            price = 2 if sheet.frame == "THE PRINCE" else 3
            if rule in (rules.TV, rules.BAD, rules.GROWING):
                _fanbase(self.game, c, state, actor, event)
            purchase, grant_id = str(uuid4()), str(uuid4())
            payment = prepare_payment(self.game, c, state, viewer, actor, rule, price, "THE PRINCE")
            debit(state, actor, price, event=event, source=purchase, payment=payment)
            receipt = FrameRuleReceipt(
                id=purchase,
                kind="ability_unlock" if price == 2 else "frame_grafting",
                actor=actor,
                frame_instance=rules.current_frame(state, actor),
                frame=sheet.frame,
                donor_frame="THE PRINCE",
                rule_id=rule,
                grant=grant_id,
                price=cast(Literal[2, 3], price),
                account=account.strip(),
                source_event=event,
            )
            state.requisitions.append(receipt)
            grant = rules.Grant(
                id=grant_id,
                actor=actor,
                frame=receipt.frame_instance,
                rule=rule,
                purchase=purchase,
                event=event,
                handler=active_handler(state) if rule == rules.BAD else None,
            )
            rules.put(state, grant)
            if rule == rules.HERO:
                first = not any(x.actor == actor for x in rules.records(state, rules.Hero))
                rules.promote(state, actor, first=first)
                rules.put(
                    state,
                    rules.Hero(
                        id=grant.id,
                        actor=actor,
                        frame=grant.frame,
                        grant=grant.id,
                        first=first,
                        event=event,
                    ),
                )
            sheet.revision += 1
            return dict(
                id=grant.id, rule=rule, purchase=purchase, cost=price, requisition_id=purchase
            )

        return self._write(
            viewer,
            key,
            "m3.prince_acquired",
            revision,
            dict(rule=rule, account=account),
            operation,
            rule,
        )

    def request_payment(
        self, viewer: GuildViewer, key: str, revision: int, rule: str, account: str
    ) -> dict[str, Any]:
        from girlframe.engine.m3_intracadre_marriage import marriage_for
        from girlframe.services.m3_intracadre_marriage import MarriageService

        if rule not in rules.RULES:
            raise WorkflowError("Choose the actual source-priced Prince Requisition")
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer, rule)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            source = marriage_for(state, actor)
            if source is None or source.financial == actor:
                raise WorkflowError("Your actual purchase already decides your own wallet")
        return MarriageService(self.store, self.game).request_payment(
            viewer, key, source.id, revision, rule, "THE PRINCE", account
        )

    def perform(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        channel: int,
        target: ActorRef,
        part: str,
        following: bool,
        account: str,
    ) -> dict[str, Any]:
        if not part.strip() or not account.strip() or type(following) is not bool:
            raise WorkflowError("Author the actual part, audience and relation to your demands")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            actor = current_ref(state, viewer.user_id)
            first, other, scene = _parties(self.game, c, state, actor, target, channel)
            fanbase = _fanbase(self.game, c, state, actor, event)
            identity = str(uuid4())
            rules.put(
                state,
                rules.Performance(
                    id=identity,
                    actor=actor,
                    target=target,
                    caster=first.controller,
                    counterpart=other.controller,
                    cast=scene,
                    frame=rules.current_frame(state, actor),
                    fanbase_event=fanbase.event,
                    part=part.strip(),
                    following=following,
                    account=account.strip(),
                    event=event,
                ),
            )
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.prince_part_declared",
            revision,
            dict(
                channel=channel,
                target=target.model_dump(mode="json"),
                part=part,
                following=following,
                account=account,
            ),
            operation,
            rules.PERFORMER,
        )

    def exception_attempt(
        self, viewer: GuildViewer, key: str, revision: int, channel: int, account: str
    ) -> dict[str, Any]:
        if not account.strip():
            raise WorkflowError("Name the actual contrary act that requires Keep or Disobey")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            actor = current_ref(state, viewer.user_id)
            _actor(self.game, c, state, actor)
            _fanbase(self.game, c, state, actor, event)
            scene = _cast(self.game, c, state, channel)
            if not any(x.actor == actor and x.controller == viewer.user_id for x in scene.roles):
                raise WorkflowError(
                    "Use the original person's actual scene and Fanbase expectation"
                )
            identity = str(uuid4())
            rules.put(
                state,
                rules.DemandAttempt(
                    id=identity,
                    actor=actor,
                    frame=rules.current_frame(state, actor),
                    cast=scene,
                    event=event,
                    account=account.strip(),
                ),
            )
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.prince_contrary_attempt",
            revision,
            dict(channel=channel, account=account),
            operation,
        )

    def break_character(
        self, viewer: GuildViewer, key: str, revision: int, performance: str, account: str
    ) -> dict[str, Any]:
        if not account.strip():
            raise WorkflowError("Describe the actual break from the performed part")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = prove_performance(self.game, c, state, performance)
            if viewer.user_id != value.caster or not value.completed_event or value.broken_event:
                raise WorkflowError("Only the original performer records this actual active break")
            allowances = sum(
                x.performance == value.id and x.option == "dismiss"
                for x in rules.records(state, rules.Selection)
            )
            used = sum(
                x.performance == value.id and x.dismissed for x in rules.records(state, rules.Break)
            )
            dismissed = bool(allowances and used == 0)
            rules.put(
                state,
                rules.Break(
                    id=str(uuid4()),
                    performance=value.id,
                    actor=value.actor,
                    event=event,
                    dismissed=dismissed,
                    account=account.strip(),
                ),
            )
            if not dismissed:
                rules.put(state, value.model_copy(update=dict(broken_event=event)))
            return dict(id=value.id)

        return self._write(
            viewer,
            key,
            "m3.prince_character_broken",
            revision,
            dict(performance=performance, account=account),
            operation,
            rules.PERFORMER,
        )

    def member(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        prince: ActorRef,
        member: ActorRef,
        demographic: str,
        account: str,
    ) -> dict[str, Any]:
        if not account.strip():
            raise WorkflowError("Record the actual person's factual fan membership")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = _fanbase(self.game, c, state, prince, event)
            target = resolve(state, member, profiles(c, self.store.campaign_id))
            if (
                target.controller != viewer.user_id
                or not target.alive
                or not any(x.id == demographic for x in value.demographics)
            ):
                raise WorkflowError(
                    "The actual person/controller authors their real demographic membership"
                )
            identity = str(uuid4())
            rules.put(
                state,
                rules.Membership(
                    id=identity,
                    prince=prince,
                    member=member,
                    controller=target.controller,
                    demographic=demographic,
                    event=event,
                    account=account.strip(),
                ),
            )
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.prince_member_recorded",
            revision,
            dict(
                prince=prince.model_dump(mode="json"),
                member=member.model_dump(mode="json"),
                demographic=demographic,
                account=account,
            ),
            operation,
        )

    def recognize(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        channel: int,
        target: ActorRef,
        account: str,
    ) -> dict[str, Any]:
        if not account.strip():
            raise WorkflowError(
                "Describe the actual indication that this person knows your Frame legacy"
            )

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            actor = current_ref(state, viewer.user_id)
            first, other, scene = _parties(self.game, c, state, actor, target, channel)
            grant = held(self.game, c, state, actor, rules.IMMORTAL)
            handler = active_handler(state)
            if grant is None or handler is None:
                raise WorkflowError("Acquire the actual current Immortal Hero source")
            identity = str(uuid4())
            rules.put(
                state,
                rules.Recognition(
                    id=identity,
                    actor=actor,
                    target=target,
                    caster=first.controller,
                    counterpart=other.controller,
                    handler=handler,
                    handler_controller=int(handler.entity),
                    cast=scene,
                    frame=grant.frame,
                    grant=grant.id,
                    event=event,
                    account=account.strip(),
                ),
            )
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.prince_legacy_recognized",
            revision,
            dict(channel=channel, target=target.model_dump(mode="json"), account=account),
            operation,
            rules.IMMORTAL,
        )

    def legacy(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        identity: str,
        option: str,
        account: str,
        text: str = "",
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = _proof(self.game, c, state, rules.Recognition, identity)
            if value.completed_event or not account.strip():
                raise WorkflowError("Resume the actual unresolved original legacy response")
            first, other, _ = _parties(
                self.game, c, state, value.actor, value.target, value.cast.channel
            )
            if first.controller != value.caster or other.controller != value.counterpart:
                raise WorkflowError("Preserve both actual original source controllers")
            if value.branch is None:
                if viewer.user_id != value.counterpart or option not in (
                    "predecessor",
                    "mission",
                    "secret",
                ):
                    raise WorkflowError("The actual counterpart owns the printed legacy choice")
                value = value.model_copy(update=dict(branch=option, selected_event=event))
                if option == "mission":
                    if depth(state, value.actor, value.target) == 0:
                        _copy(state, change(state, value.actor, value.target, 1, event))
                    value = value.model_copy(
                        update=dict(answer=account.strip(), completed_event=event)
                    )
            elif value.branch == "predecessor" and not value.question_event:
                if (
                    viewer.user_id != value.caster
                    or option not in ("ask", "pass")
                    or (option == "ask" and not text.strip())
                ):
                    raise WorkflowError(
                        "The original Prince owns the optional real predecessor question"
                    )
                value = value.model_copy(
                    update=dict(
                        question=text.strip() if option == "ask" else "", question_event=event
                    )
                )
            elif value.branch == "predecessor":
                if viewer.user_id != value.counterpart or not text.strip():
                    raise WorkflowError(
                        "The actual witness gives the real comparing Tag and answer"
                    )
                tag = rules.identity("legacy-tag", value.id)
                _copy(
                    state,
                    give_tag(
                        state,
                        profiles(c, self.store.campaign_id),
                        value.actor,
                        value.target,
                        text.strip(),
                        tag,
                        event,
                        (value.caster, value.counterpart),
                    ),
                )
                value = value.model_copy(
                    update=dict(tag=tag, answer=account.strip(), completed_event=event)
                )
            elif value.branch == "secret":
                handler = active_handler(state)
                if handler != value.handler or viewer.user_id != value.handler_controller:
                    raise WorkflowError(
                        "The actual Handler authors the expression that flashes on their face"
                    )
                value = value.model_copy(update=dict(answer=account.strip(), completed_event=event))
            else:
                raise WorkflowError("Use the actual pending owned legacy response")
            rules.put(state, value)
            return dict(id=value.id)

        return self._write(
            viewer,
            key,
            "m3.prince_legacy_answered",
            revision,
            dict(id=identity, option=option, account=account, text=text),
            operation,
            rules.IMMORTAL,
        )

    def off_duty(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        identity: str,
        option: str,
        account: str,
        *,
        demanded: tuple[str, ...] = (),
        rejected: tuple[str, ...] = (),
        demographic: str = "",
        lose: str = "",
        name: str = "",
        cell: tuple[int, int] | None = None,
        asset_name: str = "",
        asset_description: str = "",
        replace: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            task = _proof(self.game, c, state, rules.OffDutyTask, identity)
            if (
                task.completed_event
                or task.actor != current_ref(state, viewer.user_id)
                or task.frame != rules.current_frame(state, task.actor)
                or not account.strip()
            ):
                raise WorkflowError("Use your actual original pending Off-Duty opportunity")
            value = _fanbase(self.game, c, state, task.actor, event)
            if task.rule == rules.TV:
                if option in ("adjust", "replace"):
                    updated = value.model_copy(
                        update=dict(demanded=demanded, rejected=rejected, event=event)
                    )
                    updated = rules.FanbaseState.model_validate_json(updated.model_dump_json())
                    if option == "replace":
                        old = next((x for x in updated.demographics if x.id == lose), None)
                        if (
                            old is None
                            or not demographic.strip()
                            or demographic.strip().casefold()
                            in {x.name.casefold() for x in value.demographics}
                        ):
                            raise WorkflowError(
                                "Choose one actual old demographic and name the new one"
                            )
                        state.sheets[task.actor.entity].identities = [
                            x
                            for x in state.sheets[task.actor.entity].identities
                            if x.id != old.identity
                        ]
                        updated = updated.model_copy(
                            update=dict(
                                demographics=tuple(x for x in updated.demographics if x != old)
                            )
                        )
                        updated = rules.add_demographic(state, updated, demographic, event)
                    rules.put(state, updated)
                elif option == "fan":
                    handler = active_handler(state)
                    if (
                        not state.world
                        or handler is None
                        or cell is None
                        or not state.world.board.contains(cell)
                        or not name.strip()
                        or not any(x.id == demographic for x in value.demographics)
                    ):
                        raise WorkflowError(
                            "Introduce an actual named demographic fan at a known factual location"
                        )
                    faction = next(
                        (x for x in state.world.factions if x.kind == "foundation"), None
                    )
                    npc_id = rules.identity("recruit", task.id)
                    if any(
                        x.id == npc_id or x.name.casefold() == name.strip().casefold()
                        for x in state.world.npcs
                    ):
                        raise WorkflowError(
                            "Introduce a genuinely new real recruit, not a duplicate person"
                        )
                    fan = Npc(
                        id=npc_id,
                        name=name.strip(),
                        jobs=("fan", "base_personnel"),
                        detail=account.strip(),
                        controller=int(handler.entity),
                        cell=cell,
                        faction=faction.id if faction else None,
                        employment="foundation",
                        revealed=True,
                    )
                    state.world = state.world.model_copy(update=dict(npcs=(*state.world.npcs, fan)))
                    target = ActorRef(kind="npc", entity=npc_id)
                    _copy(state, change(state, task.actor, target, 1, event))
                    rules.put(
                        state,
                        rules.Membership(
                            id=rules.identity("member", task.id),
                            prince=task.actor,
                            member=target,
                            controller=int(handler.entity),
                            demographic=demographic,
                            event=event,
                            account=account.strip(),
                        ),
                    )
                else:
                    raise WorkflowError("Choose one real printed TV Interviews effect")
            elif task.rule == rules.GROWING:
                if option == "perform":
                    if (
                        not demographic.strip()
                        or not asset_name.strip()
                        or not asset_description.strip()
                    ):
                        raise WorkflowError(
                            "Describe the actual concert, new audience and real fame Asset"
                        )
                    from girlframe.engine.m3_janus_storage import effective_assets

                    asset = AssetState(
                        id=rules.identity("fame", task.id),
                        name=asset_name.strip(),
                        description=asset_description.strip(),
                        family="girl",
                    )
                    result = install(
                        state.sheets[task.actor.entity],
                        asset,
                        replace=replace,
                        effective_void=frozenset(
                            x.id for x in effective_assets(state, task.actor) if x.void
                        ),
                        state=state,
                    )
                    state.sheets[task.actor.entity] = result.sheet
                    rules.add_demographic(state, value, demographic, event)
                elif option != "decline":
                    raise WorkflowError(
                        "Perform the actual funded concert or decline this opportunity"
                    )
            else:
                raise WorkflowError("Use the actual printed source task")
            rules.put(
                state,
                task.model_copy(
                    update=dict(option=option, account=account.strip(), completed_event=event)
                ),
            )
            return dict(id=task.id)

        return self._write(
            viewer,
            key,
            "m3.prince_off_duty_effect",
            revision,
            dict(
                id=identity,
                option=option,
                account=account,
                demanded=list(demanded),
                rejected=list(rejected),
                demographic=demographic,
                lose=lose,
                name=name,
                cell=cell,
                asset_name=asset_name,
                asset_description=asset_description,
                replace=replace,
            ),
            operation,
            rules.TV if option in ("adjust", "replace", "fan") else rules.GROWING,
        )

    def reveal_plan(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        identity: str,
        account: str,
        *,
        channel: int | None = None,
        action: str | None = None,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            purchase = next(
                (
                    x
                    for x in rules.records(state, rules.Grant)
                    if x.id == identity and x.rule == rules.BAD
                ),
                None,
            )
            if purchase:
                prove_grant(self.game, c, state, purchase)
                if (
                    purchase.handler is None
                    or action is None
                    or action not in {x["id"] for x in _disobediences(self.game, c, purchase)}
                ):
                    raise WorkflowError(
                        "Choose actual completed disobedience under the acquired Handler Play"
                    )
                value = next(
                    (
                        x
                        for x in rules.records(state, rules.PlanGrant)
                        if x.grant == purchase.id and x.action == action
                    ),
                    None,
                )
                if value is None:
                    original = self.game.action(c, action)
                    original_cast = original["data"].get("tag_context", {}).get("cast")
                    scene = (
                        SceneCast.model_validate(original_cast)
                        if original_cast
                        else _cast(
                            self.game,
                            c,
                            state,
                            channel if channel is not None else int(original["channel_id"]),
                        )
                    )
                    value = rules.PlanGrant(
                        id=rules.identity("plan-grant-action", purchase.id, action),
                        actor=purchase.actor,
                        handler=purchase.handler,
                        controller=int(purchase.handler.entity),
                        cast=scene,
                        action=action,
                        grant=purchase.id,
                        event=event,
                    )
                    rules.put(state, value)
            else:
                value = _proof(self.game, c, state, rules.PlanGrant, identity)
            value = cast(rules.PlanGrant, value)
            if (
                value.controller != viewer.user_id
                or active_handler(state) != value.handler
                or not account.strip()
            ):
                raise WorkflowError(
                    "Only the original actual Handler uses this real reveal-plan Play"
                )
            actual_action = self.game.action(c, value.action)
            if (
                actual_action["state"] != "complete"
                or not actual_action["data"].get("result", {}).get("can_disobey")
                or actual_action["data"].get("play") != "disobey_orders"
                or actual_action["actor_id"] != value.actor.entity
            ):
                raise WorkflowError("Reveal only a genuine completed original disobedience")
            _roll_source(self.game, c, actual_action)
            paid = _get(state, rules.Grant, value.grant)
            prove_grant(self.game, c, state, paid)
            active = held(self.game, c, state, value.actor, rules.BAD)
            if active is None or active.id != paid.id:
                raise WorkflowError(
                    "Restore the actual current acquired source before using its Handler Play"
                )
            if value.override:
                prove_override(self.game, c, state, actual_action)
            current = _cast(
                self.game, c, state, channel if channel is not None else value.cast.channel
            )
            recipients = tuple(sorted({x.controller for x in current.roles} | {viewer.user_id}))
            use = rules.PlanUse(
                id=str(uuid4()),
                plan=value.id,
                actor=value.actor,
                handler=value.handler,
                controller=value.controller,
                cast=current,
                action=value.action,
                event=event,
                account=account.strip(),
                recipients=recipients,
            )
            rules.put(state, use)
            rules.put(
                state,
                value.model_copy(
                    update=dict(
                        used_event=event,
                        account=account.strip(),
                        recipients=recipients,
                        reveal_cast=current,
                    )
                ),
            )
            return dict(id=use.id, source=value.id)

        return self._write(
            viewer,
            key,
            "m3.prince_plan_revealed",
            revision,
            dict(id=identity, account=account)
            | (dict(channel=channel) if channel is not None else {})
            | (dict(action=action) if action is not None else {}),
            operation,
            rules.BAD,
        )

    def report_violation(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        channel: int,
        account: str,
        disclosed: bool,
    ) -> dict[str, Any]:
        if not account.strip() or type(disclosed) is not bool:
            raise WorkflowError("Author the actual demand breach and whether you disclose it")

        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            actor = current_ref(state, viewer.user_id)
            _fanbase(self.game, c, state, actor, event)
            scene = _cast(self.game, c, state, channel)
            handler = active_handler(state)
            if handler is None or not any(
                x.actor == actor and x.controller == viewer.user_id for x in scene.roles
            ):
                raise WorkflowError("Use the actual original person's source scene and Handler")
            identity = str(uuid4())
            rules.put(
                state,
                rules.Violation(
                    id=identity,
                    actor=actor,
                    handler=handler,
                    controller=int(handler.entity),
                    cast=scene,
                    event=event,
                    account=account.strip(),
                    disclosed=disclosed,
                ),
            )
            return dict(id=identity)

        return self._write(
            viewer,
            key,
            "m3.prince_violation_recorded",
            revision,
            dict(channel=channel, account=account, disclosed=disclosed),
            operation,
        )

    def decide_violation(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        identity: str,
        punish: bool,
        account: str,
    ) -> dict[str, Any]:
        def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
            value = _proof(self.game, c, state, rules.Violation, identity)
            if (
                not value.disclosed
                or value.decided_event
                or active_handler(state) != value.handler
                or viewer.user_id != value.controller
                or type(punish) is not bool
                or not account.strip()
            ):
                raise WorkflowError(
                    "The actual informed original Handler owns this optional discipline"
                )
            case = None
            if punish:
                case = _open_discipline(
                    self.game,
                    c,
                    state,
                    actor=value.actor,
                    executor=value.handler,
                    controller=value.controller,
                    scene=value.cast,
                    source=value.id,
                    action=None,
                    event=event,
                )
            rules.put(state, value.model_copy(update=dict(case=case, decided_event=event)))
            return dict(id=value.id)

        return self._write(
            viewer,
            key,
            "m3.prince_violation_judged",
            revision,
            dict(id=identity, punish=punish, account=account),
            operation,
        )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        for model in (
            rules.Performance,
            rules.Recognition,
            rules.PlanGrant,
            rules.PlanUse,
            rules.Grant,
            rules.OffDutyTask,
            rules.Violation,
            rules.DemandAttempt,
        ):
            for value in rules.records(state, model):
                owners: set[int]
                if isinstance(value, rules.Performance):
                    owners, active = {value.caster, value.counterpart}, not value.completed_event
                elif isinstance(value, rules.Recognition):
                    owners = {value.caster, value.counterpart}
                    if value.branch == "secret":
                        owners.add(value.handler_controller)
                    active = not value.completed_event
                elif isinstance(value, rules.PlanGrant):
                    owners, active = (
                        {value.controller, int(value.actor.entity)},
                        False,
                    )
                elif isinstance(value, rules.PlanUse):
                    owners, active = {value.controller, *value.recipients}, False
                elif isinstance(value, rules.Grant):
                    if value.rule != rules.BAD or value.handler is None:
                        continue
                    owners, active = {int(value.actor.entity), int(value.handler.entity)}, False
                elif isinstance(value, rules.Violation):
                    owners = {int(value.actor.entity)} | (
                        {value.controller} if value.disclosed else set()
                    )
                    active = value.disclosed and not value.decided_event
                elif isinstance(value, rules.DemandAttempt):
                    owners, active = {int(value.actor.entity)}, value.action is None
                else:
                    task = cast(rules.OffDutyTask, value)
                    owners, active = {int(task.actor.entity)}, not task.completed_event
                if viewer.user_id in owners:
                    if isinstance(value, rules.Performance):
                        incoming = active and (
                            viewer.user_id == value.caster
                            if not value.action
                            else any(
                                x["actor_id"] == str(viewer.user_id)
                                for x in self.game.pending(c, value.action)
                            )
                        )
                    elif isinstance(value, rules.Recognition):
                        chooser = (
                            value.counterpart
                            if value.branch is None
                            else value.caster
                            if value.branch == "predecessor" and not value.question_event
                            else value.handler_controller
                            if value.branch == "secret"
                            else value.counterpart
                        )
                        incoming = active and viewer.user_id == chooser
                    elif isinstance(value, rules.Violation):
                        incoming = active and viewer.user_id == value.controller
                    else:
                        incoming = active
                    result.append(
                        dict(
                            id=value.model_dump()["id"],
                            revision=state.revision,
                            label={
                                rules.Performance: "Performer: actual part",
                                rules.Recognition: "Immortal Hero: actual legacy",
                                rules.PlanGrant: "Bad Girl: reveal a real plan",
                                rules.PlanUse: "Saved addressed plan reveal",
                                rules.Grant: "Bad Girl: acquired Handler Play",
                                rules.OffDutyTask: "Prince: interview or funded concert",
                                rules.Violation: "Fanbase: actual breach report",
                                rules.DemandAttempt: "Fanbase: actual Keep/Disobey",
                            }[model],
                            phase="pending" if active else "complete",
                            pending=incoming,
                        )
                    )
        return result

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            if not any(x["id"] == identity for x in self._tasks(c, viewer)):
                raise WorkflowError(
                    "Only the actual original source parties read this private record"
                )
            state = load_state(c, self.store.campaign_id)
            for model in (
                rules.Performance,
                rules.Recognition,
                rules.PlanGrant,
                rules.PlanUse,
                rules.Grant,
                rules.OffDutyTask,
                rules.Violation,
                rules.DemandAttempt,
            ):
                if any(x.model_dump()["id"] == identity for x in rules.records(state, model)):
                    value = _proof(self.game, c, state, model, identity)
                    detail = value.model_dump(mode="json")
                    if (
                        isinstance(value, rules.PlanGrant)
                        and viewer.user_id != value.controller
                        and viewer.user_id not in value.recipients
                    ):
                        detail.update(account="", recipients=(), reveal_cast=None)
                    if isinstance(value, rules.PlanUse):
                        detail = dict(id=value.id, account=value.account, used_event=value.event)
                    if isinstance(value, rules.Performance) and viewer.user_id != value.caster:
                        detail.pop("following", None)
                        detail.pop("account", None)
                    result = dict(
                        id=identity, revision=state.revision, kind=model.__name__, record=detail
                    )
                    if isinstance(value, rules.OffDutyTask):
                        fans = _fanbase(self.game, c, state, value.actor)
                        result["fanbase"] = fans.model_dump(mode="json")
                        from girlframe.engine.m3_assets import can_replace_at_limit

                        result["replace"] = [
                            dict(id=x.id, label=x.name)
                            for x in state.sheets[value.actor.entity].assets
                            if x.family == "girl"
                            and not x.void
                            and can_replace_at_limit(state.sheets[value.actor.entity], x)
                        ]
                    if isinstance(value, rules.Performance) and value.action:
                        result["choices"] = [
                            dict(x)
                            for x in self.game.pending(c, value.action)
                            if x["actor_id"] == str(viewer.user_id)
                        ]
                    if isinstance(value, rules.Grant):
                        prove_grant(self.game, c, state, value)
                        result["disobediences"] = _disobediences(self.game, c, value)
                    if isinstance(value, rules.Performance) and viewer.user_id == value.caster:
                        result["exceptions"] = [
                            dict(id=x.id, label=x.account)
                            for x in rules.records(state, rules.DemandException)
                            if x.actor == value.actor and not x.used_by
                        ]
                    return result
            raise WorkflowError("Open the genuine saved Prince source")


def prove_performance(
    game: GameService, c: Connection, state: GameState, identity: str
) -> rules.Performance:
    value = cast(rules.Performance, _proof(game, c, state, rules.Performance, identity))
    _audit(game, c, value.event, ("m3.prince_part_declared",), value.caster)
    if value.action:
        if not value.bound_event:
            raise WorkflowError("Recover the actual original bound performance")
        bound = _get(_history(c, game, value.bound_event), rules.Performance, value.id)
        action = game.action(c, value.action)
        if (
            bound.action != value.action
            or action["actor_id"] != value.actor.entity
            or action["data"].get("prince", {}).get("performance") != value.id
        ):
            raise WorkflowError("Preserve the actual original performance Play binding")
        if value.result_event:
            _roll_source(game, c, action)
            result = _get(_history(c, game, value.result_event), rules.Performance, value.id)
            if result.tier != value.tier or result.action != value.action:
                raise WorkflowError("Recover the actual original performed roll and result birth")
    for selected in rules.records(state, rules.Selection):
        if selected.performance != value.id:
            continue
        born = _get(_history(c, game, selected.event), rules.Selection, selected.id)
        row = (
            c.execute(
                sa.select(t.m2["m2_choices"]).where(
                    t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_choices"].c.id == selected.choice,
                )
            )
            .mappings()
            .first()
        )
        if selected != born or row is None:
            raise WorkflowError("Recover the genuine independently owned performer choice")
        _response(
            game,
            c,
            selected.action,
            selected.choice,
            selected.event,
            selected.controller,
            row["kind"],
        )
    if value.conformed_event:
        conformed = _get(_history(c, game, value.conformed_event), rules.Performance, value.id)
        if conformed.conformed_part != value.conformed_part:
            raise WorkflowError("Preserve the original high-result demand-following rendition")
    return value


def prepare(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any]:
    _access(game, c, viewer, rules.PERFORMER)
    value = prove_performance(game, c, state, prepared.source_work or "")
    _, _, scene = _parties(game, c, state, value.actor, value.target, channel)
    if (
        value.actor != current_ref(state, viewer.user_id)
        or value.action
        or rules.current_frame(state, value.actor) != value.frame
        or scene != value.cast
    ):
        raise WorkflowError("Use the actual unchanged original declared part and audience")
    handler = active_handler(state)
    if handler is None:
        raise WorkflowError("Recover the actual original Handler source")
    return dict(
        performance=value.id,
        actor=value.actor.model_dump(mode="json"),
        target=value.target.model_dump(mode="json"),
        caster=value.caster,
        counterpart=value.counterpart,
        cast=scene.model_dump(mode="json"),
        cast_sha256=fingerprint(scene),
        handler=handler.model_dump(mode="json"),
        handler_controller=int(handler.entity),
        table=sorted({x.controller for x in scene.roles} | {scene.facilitator}),
    )


def bind(state: GameState, action: dict[str, Any], event: str) -> None:
    value = _get(state, rules.Performance, action["data"]["prince"]["performance"])
    if value.action:
        raise WorkflowError("Never bind a second Play to the original actual part")
    rules.put(state, value.model_copy(update=dict(action=action["id"], bound_event=event)))


def authorize(
    game: GameService, c: Connection, viewer: GuildViewer, action: dict[str, Any]
) -> None:
    _access(game, c, viewer, rules.PERFORMER)
    if viewer.user_id not in action["data"]["prince"]["table"]:
        raise WorkflowError("Only the actual original on-scene people own these responses")


def pre_roll(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    value = prove_performance(game, c, state, action["data"]["prince"]["performance"])
    if value.caster != viewer.user_id or value.action != action["id"]:
        raise WorkflowError("Use the actual original performer's single confirmed roll")
    _parties(game, c, state, value.actor, value.target, value.cast.channel)


def parties(state: GameState, action: dict[str, Any]) -> tuple[ActorRef, ActorRef]:
    value = _get(state, rules.Performance, action["data"]["prince"]["performance"])
    return value.actor, value.target


def results(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    value = _get(state, rules.Performance, action["data"]["prince"]["performance"])
    if value.result_event:
        raise WorkflowError("Resume the actual original result rather than rolling again")
    tier = action["data"]["result"]["tier"]
    rules.put(
        state,
        value.model_copy(update=dict(tier=tier, result_event=action["data"]["response_event"])),
    )
    if tier == "low":
        game.request(c, action, value.counterpart, "prince_falter")
    elif tier == "high" and not value.following:
        game.request(c, action, value.caster, "prince_conform")
    else:
        game.request(c, action, value.caster, "prince_choose_actor")
        game.request(c, action, value.counterpart, "prince_choose_target")


def _discipline(
    game: GameService, c: Connection, state: GameState, value: rules.Performance, event: str
) -> str:
    return _open_discipline(
        game,
        c,
        state,
        actor=value.actor,
        executor=value.target,
        controller=value.counterpart,
        scene=value.cast,
        source=value.id,
        action=value.action,
        event=event,
    )


def _open_discipline(
    game: GameService,
    c: Connection,
    state: GameState,
    *,
    actor: ActorRef,
    executor: ActorRef,
    controller: int,
    scene: SceneCast,
    source: str,
    action: str | None,
    event: str,
) -> str:
    from girlframe.services.m3_role_punishments import open_case

    actual = resolve(state, executor, profiles(c, game.store.campaign_id))
    identity = rules.identity("discipline", source)
    source_id = rules.identity("role", identity)
    changed, _ = open_case(
        state,
        profiles(c, game.store.campaign_id),
        actor=executor,
        target=actor,
        chooser=executor,
        source_kind="prince",
        action=action,
        source_event=event,
        identity=source_id,
        source_work=identity,
    )
    _copy(state, changed)
    rules.put(
        state,
        rules.Discipline(
            id=identity,
            actor=actor,
            executor=executor,
            controller=controller,
            frame=actual.frame_instance,
            cast=scene,
            source=source,
            action=action,
            event=event,
            case=source_id,
        ),
    )
    return source_id


def _finish(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    if game.pending(c, action["id"]):
        return
    value = _get(state, rules.Performance, action["data"]["prince"]["performance"])
    if value.completed_event:
        return
    cases = [x.case for x in rules.records(state, rules.Discipline) if x.source == value.id]
    if any(
        not any(x.id == identity and x.completion_event for x in state.role_punishments)
        for identity in cases
    ):
        return
    from girlframe.services.m2_choices import ChoiceEngine

    rules.put(state, value.model_copy(update=dict(completed_event=event)))
    ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)


def apply_choice(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    answer: ChoiceAnswer,
) -> bool:
    kind, event = row["kind"], action["data"]["response_event"]
    if kind == "prince_bad_girl":
        if (
            answer.options not in (("use",), ("pass",))
            or answer.fields
            or answer.denied
            or answer.number is not None
            or answer.flag is not None
        ):
            raise WorkflowError("Choose the actual source-owned optional Bad Girl conversion")
        if answer.options == ("use",):
            actor = current_ref(state, int(action["actor_id"]))
            grant = held(game, c, state, actor, rules.BAD)
            if grant is None or row["actor_id"] != actor.entity or not answer.text.strip():
                raise WorkflowError(
                    "The original owner states how the actual disobedience follows demands"
                )
            source = action["data"].get("prince_demands")
            if action["data"].get("prince_demand_attempt") or source and not source["following"]:
                raise WorkflowError(
                    "This actual contrary-to-fans source is not a demand-following refusal"
                )
            roll_event, _ = _roll_source(game, c, action)
            rolled = _history(c, game, roll_event)
            if grant not in rules.records(rolled, rules.Grant):
                raise WorkflowError("Bad Girl must be genuinely acquired before this actual roll")
            fanbase = _fanbase(game, c, rolled, actor)
            override = rules.BadGirlOverride(
                id=str(uuid4()),
                actor=actor,
                action=action["id"],
                choice=row["id"],
                receipt=action["data"]["receipt"]["id"],
                grant=grant.id,
                fanbase_event=fanbase.event,
                before=action["data"]["result"]["total"],
                event=event,
                account=answer.text.strip(),
            )
            if override.before > 7:
                raise WorkflowError("Bad Girl changes only this actual low Disobey result")
            rules.put(state, override)
            action["data"]["prince_override"] = override.model_dump(mode="json")
            scene = _cast(game, c, state, int(action["channel_id"]))
            handler = grant.handler
            if handler is None:
                raise WorkflowError("Preserve the actual Handler who gains the reveal-plan Play")
            rules.put(
                state,
                rules.PlanGrant(
                    id=rules.identity("plan", override.id),
                    actor=actor,
                    handler=handler,
                    controller=int(handler.entity),
                    cast=scene,
                    action=action["id"],
                    override=override.id,
                    grant=grant.id,
                    event=event,
                ),
            )
        from girlframe.services.m2_choices import ChoiceEngine

        action["data"]["prince_bad_pending"] = False
        ChoiceEngine(game).results(c, state, action)
        return True
    if not kind.startswith("prince_"):
        return False
    value = prove_performance(game, c, state, action["data"]["prince"]["performance"])
    first, other, _ = _parties(game, c, state, value.actor, value.target, value.cast.channel)
    if first.controller != value.caster or other.controller != value.counterpart:
        raise WorkflowError(
            "Use the actual original response controllers, never a replacement account"
        )
    owner = int(row["actor_id"])
    if (
        answer.flag is not None
        or answer.member is not None
        or answer.fields
        or answer.number is not None
    ):
        raise WorkflowError("Use only this genuine owned printed Performer choice")
    if kind == "prince_conform":
        if owner != value.caster or answer.options or answer.denied or not answer.text.strip():
            raise WorkflowError(
                "Author the actual high-result part that follows your Fanbase demands"
            )
        value = value.model_copy(
            update=dict(conformed_event=event, conformed_part=answer.text.strip())
        )
        rules.put(state, value)
        game.request(c, action, value.caster, "prince_choose_actor")
        game.request(c, action, value.counterpart, "prince_choose_target")
        option, case = "conform", None
    elif kind == "prince_falter":
        if (
            owner != value.counterpart
            or answer.denied
            or answer.options not in (("tag",), ("punish",), ("pass",))
        ):
            raise WorkflowError(
                "The actual counterpart sees through the act and chooses its consequence"
            )
        option, case = answer.options[0], None
        if option == "tag":
            if not answer.text.strip():
                raise WorkflowError("The actual counterpart authors their real inflicted Tag")
            _copy(
                state,
                give_tag(
                    state,
                    profiles(c, game.store.campaign_id),
                    value.actor,
                    value.target,
                    answer.text.strip(),
                    rules.identity("falter-tag", value.id),
                    event,
                    (value.caster, value.counterpart),
                ),
            )
        elif option == "punish":
            case = _discipline(game, c, state, value, event)
        elif answer.text:
            raise WorkflowError("Declining the optional consequence invents no Tag or Punishment")
    elif kind == "prince_erase_tags":
        if owner != value.caster or answer.options or not answer.text.strip():
            raise WorkflowError("The actual performer selects their own conflicting Tags privately")
        sheet = state.sheets[value.actor.entity]
        selected = [x for x in sheet.tags if x.id in answer.denied]
        if len(selected) != len(answer.denied) or any(x.rejection_pending for x in selected):
            raise WorkflowError("Select only real conflicting Tags with completed source work")
        sheet.tags = [x for x in sheet.tags if x.id not in answer.denied]
        sheet.revision += 1
        option, case = "erase_tags", None
    else:
        expected = (
            value.caster
            if kind == "prince_choose_actor"
            else value.counterpart
            if kind == "prince_choose_target"
            else None
        )
        if owner != expected or len(answer.options) != 1 or answer.options[0] not in rules.OPTIONS:
            raise WorkflowError(
                "Each actual original chooser independently chooses one printed benefit"
            )
        option, case = answer.options[0], None
        if option == "bond":
            if answer.denied:
                raise WorkflowError("Choose the actual Bond without unrelated Tag erasure")
            _copy(state, change(state, value.actor, value.target, 1, event))
        elif option == "status":
            if answer.denied:
                raise WorkflowError("Raise actual Status without unrelated Tag erasure")
            shift_status(state, value.caster, 1)
        elif option == "erase":
            if owner != value.caster:
                if answer.denied:
                    raise WorkflowError("The original performer privately selects the actual Tags")
                game.request(c, action, value.caster, "prince_erase_tags", dict(origin=row["id"]))
                rules.put(
                    state,
                    rules.Selection(
                        id=row["id"],
                        performance=value.id,
                        action=action["id"],
                        choice=row["id"],
                        controller=owner,
                        option=option,
                        event=event,
                        account=answer.text,
                    ),
                )
                return True
            sheet = state.sheets[value.actor.entity]
            selected = [x for x in sheet.tags if x.id in answer.denied]
            if len(selected) != len(answer.denied) or not answer.text.strip():
                raise WorkflowError(
                    "Select actual conflicting Tags and explain their conflict with the part"
                )
            if any(x.rejection_pending for x in selected):
                raise WorkflowError("Finish actual pending Tag source work before erasing its Tag")
            sheet.tags = [x for x in sheet.tags if x.id not in answer.denied]
            sheet.revision += 1
        elif answer.denied:
            raise WorkflowError("A dismissed break does not erase unrelated Tags")
    rules.put(
        state,
        rules.Selection(
            id=row["id"],
            performance=value.id,
            action=action["id"],
            choice=row["id"],
            controller=owner,
            option=option,
            event=event,
            tags=answer.denied,
            account=answer.text,
            case=case,
        ),
    )
    _finish(game, c, state, action, event)
    return True


def projection(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], row: dict[str, Any]
) -> dict[str, Any]:
    if row["kind"] == "prince_bad_girl":
        actor = current_ref(state, int(action["actor_id"]))
        return dict(
            options=[
                ("pass", "Keep the actual low result"),
                ("use", "Following demands: treat as11+"),
            ],
            tags=[],
            fanbase=_fanbase(game, c, state, actor).model_dump(mode="json"),
        )
    value = _get(state, rules.Performance, action["data"]["prince"]["performance"])
    options = [
        (
            x,
            {
                "bond": "Deepen my actual Bond",
                "status": "Raise the performer's Status",
                "erase": "Erase actual Tags conflicting with the part",
                "dismiss": "One temporary break is dismissed",
            }[x],
        )
        for x in rules.OPTIONS
    ]
    if row["kind"] == "prince_falter":
        from girlframe.services.m3_role_punishments import supported

        options = [
            ("pass", "Choose no optional consequence"),
            ("tag", "Give the actual performer a Tag"),
        ]
        if supported(state, value.actor, value.target, profiles(c, game.store.campaign_id)):
            options.append(("punish", "Actually Punish the original performer"))
    if row["kind"] in ("prince_conform", "prince_erase_tags"):
        options = []
    return dict(
        options=options,
        part=value.part,
        tags=[dict(id=x.id, label=x.label) for x in state.sheets[value.actor.entity].tags]
        if int(row["actor_id"]) == value.caster
        else [],
    )


def intercept_bad_girl(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    if action["data"].get("prince_bad_offered"):
        return bool(action["data"].get("prince_bad_pending"))
    if action["data"].get("play") != "disobey_orders" or action["data"]["result"]["total"] > 7:
        return False
    source = action["data"].get("prince_demands")
    if action["data"].get("prince_demand_attempt") or source and not source["following"]:
        return False
    actor = current_ref(state, int(action["actor_id"]))
    if not _released(game, rules.BAD):
        return False
    if held(game, c, state, actor, rules.BAD) is None:
        return False
    _fanbase(game, c, state, actor, action["data"]["response_event"])
    action["data"].update(prince_bad_offered=True, prince_bad_pending=True)
    game.request(c, action, int(actor.entity), "prince_bad_girl")
    return True


def prove_override(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> int | None:
    raw = action["data"].get("prince_override")
    if raw is None:
        return None
    value = rules.BadGirlOverride.model_validate(raw)
    born = _get(_history(c, game, value.event), rules.BadGirlOverride, value.id)
    answer = _response(
        game, c, value.action, value.choice, value.event, int(value.actor.entity), "prince_bad_girl"
    )
    if (
        value != born
        or value not in rules.records(state, rules.BadGirlOverride)
        or value.action != action["id"]
        or value.receipt != action["data"]["receipt"]["id"]
        or action["data"]["play"] != "disobey_orders"
        or action["actor_id"] != value.actor.entity
        or action["data"]["character_ids"].get(value.actor.entity) != value.actor.incarnation
        or value.before > 7
        or answer.options != ("use",)
        or answer.text.strip() != value.account
    ):
        raise WorkflowError(
            "Recover the genuine original low Disobey and owned demand-following conversion"
        )
    grant = _get(_history(c, game, value.event), rules.Grant, value.grant)
    prove_grant(game, c, state, grant)
    return 11


def prepare_mark(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, prepared: PlayInput
) -> dict[str, Any] | None:
    if not prepared.identity:
        return None
    actor = current_ref(state, viewer.user_id)
    sheet = state.sheets[actor.entity]
    entry = next((x for x in sheet.identities if x.id == prepared.identity), None)
    if (
        entry is None
        or not entry.protected
        or ":fan:" not in entry.id
        and not entry.id.startswith("fan:")
    ):
        return None
    _access(game, c, viewer, rules.FANBASE)
    value = _fanbase(game, c, state, actor)
    if (
        not any(x.identity == entry.id for x in value.demographics)
        or getattr(prepared, "prince_demands", None) != "following"
        or not getattr(prepared, "prince_demand_account", "").strip()
    ):
        raise WorkflowError("Mark a real demographic only while actually following its demands")
    return dict(
        actor=actor.model_dump(mode="json"),
        identity=entry.id,
        fanbase=value.model_dump(mode="json"),
        account=getattr(prepared, "prince_demand_account", ""),
    )


def prepare_demands(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, prepared: PlayInput
) -> dict[str, Any] | None:
    relation = getattr(prepared, "prince_demands", None)
    if relation is None:
        return None
    actor = current_ref(state, viewer.user_id)
    _access(game, c, viewer, rules.FANBASE)
    fanbase = _fanbase(game, c, state, actor)
    account = getattr(prepared, "prince_demand_account", "")
    if not account.strip():
        raise WorkflowError(
            "Author the real demand relationship, not an inferred private intention"
        )
    exception = None
    if relation == "against" and prepared.play not in ("keep_your_head", "disobey_orders"):
        value = _get(state, rules.DemandException, getattr(prepared, "prince_exception", "") or "")
        action = game.action(c, value.action)
        _proof(game, c, state, rules.DemandException, value.id)
        _roll_source(game, c, action)
        previous = rules.current_fanbase(_history(c, game, value.fanbase_event), actor)
        if (
            value.actor != actor
            or action["state"] != "complete"
            or value.account != account.strip()
            or value.used_by is not None
            or previous is None
            or previous.demanded != fanbase.demanded
            or previous.rejected != fanbase.rejected
        ):
            raise WorkflowError("Complete the actual named Keep/Disobey before this contrary act")
        exception = value.id
    return dict(
        actor=actor.model_dump(mode="json"),
        following=relation == "following",
        account=account.strip(),
        fanbase=fanbase.model_dump(mode="json"),
        exception=exception,
    )


def record_mark(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    if action["data"].get("prince_mark") or action["data"].get("prince_demands"):
        actor = current_ref(state, int(action["actor_id"]))
        _fanbase(game, c, state, actor, event)
        mark = action["data"].get("prince_mark")
        if mark:
            rules.put(
                state,
                rules.DemographicMark(
                    id=action["data"]["receipt"]["id"],
                    actor=actor,
                    action=action["id"],
                    receipt=action["data"]["receipt"]["id"],
                    identity=mark["identity"],
                    event=event,
                    account=mark["account"],
                ),
            )
        source = action["data"].get("prince_demands", {})
        if source.get("exception"):
            value = _get(state, rules.DemandException, source["exception"])
            if value.used_by is not None:
                raise WorkflowError("This actual contrary-act exception was already consumed")
            rules.put(state, value.model_copy(update=dict(used_by=action["id"], used_event=event)))


def prove_mark(game: GameService, c: Connection, state: GameState, action: dict[str, Any]) -> None:
    """Prove the real demographic mark without recursive roll-source proof."""
    meta = action["data"].get("prince_mark")
    canonical = game.action(c, action["id"])["data"].get("prince_mark")
    selected = action["data"].get("prepared", {}).get("identity")
    if (
        meta is None
        and canonical is None
        and (not selected or not (selected.startswith("fan:") or ":fan:" in selected))
    ):
        return
    receipt = (
        c.execute(
            sa.select(t.m2["m2_receipts"]).where(
                t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_receipts"].c.action_id == action["id"],
            )
        )
        .mappings()
        .first()
    )
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.kind.in_(("m2.rolled", "m3.rolled")),
                sa.func.json_extract(t.events.c.payload_json, "$.action_id") == action["id"],
            )
        )
        .mappings()
        .first()
    )
    if (
        receipt is None
        or event is None
        or json.loads(receipt["body_json"]) != action["data"].get("receipt")
    ):
        raise WorkflowError("Preserve the actual demographic mark receipt and following source")
    original = _history(c, game, event["id"])
    mark = next(
        (x for x in rules.records(original, rules.DemographicMark) if x.action == action["id"]),
        None,
    )
    if mark is None and canonical is None and meta is None:
        return
    if (
        mark is None
        or meta is None
        or canonical != meta
        or mark not in rules.records(state, rules.DemographicMark)
        or mark.receipt != receipt["id"]
        or mark.identity != selected
        or mark.account != meta.get("account")
    ):
        raise WorkflowError(
            "Recover the immutable born mark, not a missing or substituted following source"
        )
    actor = ActorRef.model_validate(meta["actor"])
    fans = _fanbase(game, c, original, actor)
    sheet = original.sheets.get(actor.entity)
    entry = next((x for x in sheet.identities if x.id == selected), None) if sheet else None
    prepared = action["data"]["prepared"]
    if (
        actor.entity != action["actor_id"]
        or actor.incarnation != action["data"]["character_ids"].get(actor.entity)
        or event["actor_id"] != actor.entity
        or meta["identity"] != selected
        or not any(x.identity == selected for x in fans.demographics)
        or entry is None
        or not entry.protected
        or not entry.marked
        or prepared.get("prince_demands") != "following"
        or not meta.get("account")
        or meta["account"] != prepared.get("prince_demand_account")
    ):
        raise WorkflowError("Recover the real protected demographic and explicit following mark")


def prepare_exception(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    if not prepared.source_work or not any(
        x.id == prepared.source_work for x in rules.records(state, rules.DemandAttempt)
    ):
        return None
    _access(game, c, viewer, rules.FANBASE)
    value = _proof(game, c, state, rules.DemandAttempt, prepared.source_work)
    if (
        value.actor != current_ref(state, viewer.user_id)
        or value.action
        or value.frame != rules.current_frame(state, value.actor)
        or prepared.play not in ("keep_your_head", "disobey_orders")
        or prepared.order_id
        or prepared.parent
        or prepared.off_duty_id
        or _cast(game, c, state, channel) != value.cast
    ):
        raise WorkflowError(
            "Use the actual Fanbase expectation source, not a person-issued Order alias"
        )
    return dict(
        attempt=value.id,
        actor=value.actor.model_dump(mode="json"),
        controller=viewer.user_id,
        account=value.account,
        cast=value.cast.model_dump(mode="json"),
        table=sorted({x.controller for x in value.cast.roles} | {value.cast.facilitator}),
        source_work=value.id,
    )


def bind_exception(state: GameState, action: dict[str, Any], event: str) -> None:
    value = _get(state, rules.DemandAttempt, action["data"]["prince_demand_attempt"]["attempt"])
    if value.action:
        raise WorkflowError("Bind only one real Play to this actual contrary-act attempt")
    rules.put(state, value.model_copy(update=dict(action=action["id"], bound_event=event)))


def pre_roll_exception(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    value = _proof(
        game, c, state, rules.DemandAttempt, action["data"]["prince_demand_attempt"]["attempt"]
    )
    if (
        value.actor != current_ref(state, viewer.user_id)
        or value.action != action["id"]
        or not value.bound_event
        or _get(_history(c, game, value.bound_event), rules.DemandAttempt, value.id).action
        != action["id"]
        or value.frame != rules.current_frame(state, value.actor)
    ):
        raise WorkflowError("Recover the actual original bound demand exception Play")


def complete_exception(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    meta = action["data"].get("prince_demand_attempt")
    if not meta or action["state"] != "complete":
        return
    value = _proof(game, c, state, rules.DemandAttempt, meta["attempt"])
    if (
        value.action != action["id"]
        or action["actor_id"] != value.actor.entity
        or action["data"]["play"] not in ("keep_your_head", "disobey_orders")
    ):
        raise WorkflowError("Complete the actual Fanbase source Play and its real consequences")
    _roll_source(game, c, action)
    allowed = action["data"]["play"] == "keep_your_head" or action["data"]["result"].get(
        "can_disobey"
    )
    if allowed:
        fans = _fanbase(game, c, state, value.actor, event)
        key = rules.identity("exception", action["id"])
        if not any(x.id == key for x in rules.records(state, rules.DemandException)):
            rules.put(
                state,
                rules.DemandException(
                    id=key,
                    actor=value.actor,
                    fanbase_event=fans.event,
                    action=action["id"],
                    receipt=action["data"]["receipt"]["id"],
                    event=event,
                    account=value.account,
                ),
            )


def _plan_after_disobedience(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    if (
        action["data"].get("play") != "disobey_orders"
        or action["state"] != "complete"
        or not action["data"].get("result", {}).get("can_disobey")
        or not _released(game, rules.BAD)
    ):
        return
    if any(x.action == action["id"] for x in rules.records(state, rules.PlanGrant)):
        return
    rolled_event, _ = _roll_source(game, c, action)
    rolled = _history(c, game, rolled_event)
    actor = ActorRef(
        kind="pilot",
        entity=str(action["actor_id"]),
        incarnation=action["data"]["character_ids"][str(action["actor_id"])],
    )
    frame = rules.current_frame(rolled, actor)
    grant = next(
        (
            x
            for x in reversed(rules.records(rolled, rules.Grant))
            if x.actor == actor
            and x.frame == frame
            and x.rule == rules.BAD
            and not suspended(rolled, x.purchase)
        ),
        None,
    )
    if grant is None:
        return
    prove_grant(game, c, state, grant)
    if grant.handler is None:
        raise WorkflowError("Recover the original Handler's acquired Bad Girl Play source")
    context = action["data"].get("tag_context", {}).get("cast")
    scene = (
        SceneCast.model_validate(context)
        if context
        else _cast(game, c, state, int(action["channel_id"]))
    )
    rules.put(
        state,
        rules.PlanGrant(
            id=rules.identity("plan-action", action["id"]),
            actor=actor,
            handler=grant.handler,
            controller=int(grant.handler.entity),
            cast=scene,
            action=action["id"],
            grant=grant.id,
            event=event,
        ),
    )


def sync_finished(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    _plan_after_disobedience(game, c, state, action, event)
    if action["data"].get("prince_demand_attempt"):
        complete_exception(game, c, state, action, event)
        return
    source = action["data"].get("prince_demands")
    if (
        source
        and not source["following"]
        and action["state"] == "complete"
        and action["data"]["play"] in ("keep_your_head", "disobey_orders")
    ):
        _roll_source(game, c, action)
        allowed = action["data"]["play"] == "keep_your_head" or action["data"]["result"].get(
            "can_disobey"
        )
        if allowed:
            actor = ActorRef.model_validate(source["actor"])
            fanbase = _fanbase(game, c, state, actor, event)
            if any(
                x.id == rules.identity("exception", action["id"])
                for x in rules.records(state, rules.DemandException)
            ):
                return
            rules.put(
                state,
                rules.DemandException(
                    id=rules.identity("exception", action["id"]),
                    actor=actor,
                    fanbase_event=fanbase.event,
                    action=action["id"],
                    receipt=action["data"]["receipt"]["id"],
                    event=event,
                    account=source["account"],
                ),
            )


def flirt_modifier(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    if prepared.play != "flirt" or not _released(game, rules.POWER):
        return None
    from girlframe.services.m3_princess_performer import acting_owner

    actor = current_ref(state, acting_owner(game, c, viewer, prepared, state))
    grant = held(game, c, state, actor, rules.POWER)
    if grant is None:
        return None
    _access(game, c, viewer, rules.POWER)
    target = prepared.target_actor or (
        current_ref(state, prepared.target) if prepared.target else None
    )
    if target is None:
        return None
    _parties(game, c, state, actor, target, channel)
    from girlframe.engine.m2 import higher

    lower = target.kind == "pilot" and higher(state, int(actor.entity), int(target.entity))
    fan = next(
        (
            x
            for x in reversed(rules.records(state, rules.Membership))
            if x.prince == actor and x.member == target
        ),
        None,
    )
    if fan:
        _proof(game, c, state, rules.Membership, fan.id)
    if not lower and fan is None:
        return None
    return dict(
        source=rules.POWER,
        amount=2,
        actor=int(actor.entity),
        grant=grant.id,
        target=target.model_dump(mode="json"),
        membership=fan.id if fan else None,
    )


def sync_off_duty(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    prepared = action["data"].get("prepared", {})
    if (
        action["data"].get("play") != "go_off_duty"
        or not prepared.get("off_duty_id")
        or not action["data"].get("receipt")
    ):
        return
    roll_event, _ = _roll_source(game, c, action)
    rolled = _history(c, game, roll_event)
    actor = current_ref(state, int(action["actor_id"]))
    event = action["data"]["response_event"]
    frame = rules.current_frame(state, actor)
    for rule in (rules.TV, rules.GROWING):
        if not _released(game, rule):
            continue
        grants = [
            x
            for x in rules.records(state, rules.Grant)
            if x.actor == actor
            and x.rule == rule
            and x.frame == frame
            and not suspended(state, x.purchase)
        ]
        if rule == rules.TV:
            grants = grants[-1:]
        for grant in grants:
            if grant not in rules.records(rolled, rules.Grant):
                continue
            prove_grant(game, c, state, grant)
            if rule == rules.GROWING and any(
                x.grant == grant.id for x in rules.records(state, rules.OffDutyTask)
            ):
                continue
            identity = rules.identity("off-duty", prepared["off_duty_id"], grant.id)
            if any(x.id == identity for x in rules.records(state, rules.OffDutyTask)):
                continue
            rules.put(
                state,
                rules.OffDutyTask(
                    id=identity,
                    actor=actor,
                    frame=frame,
                    period=prepared["off_duty_id"],
                    action=action["id"],
                    receipt=action["data"]["receipt"]["id"],
                    rule=rule,
                    grant=grant.id,
                    event=event,
                ),
            )


def require_off_duty_complete(
    game: GameService, c: Connection, state: GameState, period: str, actor: ActorRef
) -> None:
    if any(
        x.period == period and x.actor == actor and not x.completed_event
        for x in rules.records(state, rules.OffDutyTask)
    ):
        raise WorkflowError("Finish the actual Prince interview or owned concert response first")


def validate_role_case(c: Connection, game: GameService, state: GameState, case: Any) -> None:
    from girlframe.services.m3_intracadre_marriage import original_offender

    source = _get(state, rules.Discipline, case.source_work or "")
    born = _get(_history(c, game, source.event), rules.Discipline, source.id)
    offender = original_offender(game, c, state, case.id, case.source_event, case.subject)
    if (
        any(
            getattr(source, x) != getattr(born, x)
            for x in (
                "actor",
                "executor",
                "controller",
                "frame",
                "cast",
                "source",
                "action",
                "event",
                "case",
            )
        )
        or source.case != case.id
        or source.actor != offender
        or source.executor != case.executor
        or source.controller != case.executor_controller
        or source.event != case.source_event
        or source.action != case.action
    ):
        raise WorkflowError("Preserve the real Prince cause, original offender and actual executor")
    if source.action:
        prove_performance(game, c, state, source.source)
    else:
        value = _proof(game, c, state, rules.Violation, source.source)
        if not value.disclosed or value.actor != source.actor or value.handler != source.executor:
            raise WorkflowError("Recover the actual disclosed breach and original informed Handler")


def role_scope(c: Connection, game: GameService, case: Any) -> WorkScope:
    state = load_state(c, game.store.campaign_id)
    validate_role_case(c, game, state, case)
    source = _get(state, rules.Discipline, case.source_work)
    return WorkScope(scene_id=source.cast.id)


def complete_role_case(c: Connection, game: GameService, case: Any, event: str) -> None:
    state = load_state(c, game.store.campaign_id)
    validate_role_case(c, game, state, case)
    if not case.effect_event or case.completion_event != event:
        raise WorkflowError("Complete the actual Punishment effect and mandatory followups")
    source = _get(state, rules.Discipline, case.source_work)
    if source.completed_event:
        return
    actual = str(uuid4())
    rules.put(state, source.model_copy(update=dict(completed_event=actual)))
    if source.action:
        action = game.action(c, source.action)
        _finish(game, c, state, action, actual)
    game.event(
        c,
        source.controller,
        "prince-punished:" + case.id,
        "m3.prince_punished",
        state,
        event_id=actual,
        source=source.id,
    )


def synchronize(game: GameService, c: Connection, action: dict[str, Any], event: str) -> None:
    if not action["data"].get("prince"):
        return
    state = load_state(c, game.store.campaign_id)
    if any(value.action == action["id"] for value in rules.records(state, rules.Discipline)):
        # Choice application creates the source-bound case in the saved state.
        # Materialize its owned work only after that event exists, before offering
        # the counterpart controls or considering the original Play complete.
        from girlframe.services.m3_role_punishments import synchronize as sync_role

        sync_role(game, c, None, event)
        state = load_state(c, game.store.campaign_id)
        action = game.action(c, action["id"])
    _finish(game, c, state, action, event)
