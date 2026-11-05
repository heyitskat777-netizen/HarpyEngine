"""Source-priced JANUS acquisitions and actual Core Tag treatment."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_janus as cores
from girlframe.engine import m3_janus_requisitions as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.engine.playbooks import canonical_frame
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_janus import prove_core
from girlframe.services.m3_privileges import purchase_proof
from girlframe.services.m3_requisitions import RequisitionService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

# Listed only after the named consumer exists. Registry review remains independent.
IMPLEMENTED: tuple[str, ...] = (rules.TRAINING, rules.UNIVERSAL, rules.PANDORA, rules.PET)


def available(c: Connection, game: GameService, rule: str) -> bool:
    try:
        registry = Access(game.store).registry
        assert registry is not None
        registry.require_available(rule)
        return True
    except (ValueError, WorkflowError):
        return False


def owned(
    c: Connection, game: GameService, state: GameState, actor: ActorRef, rule: str
) -> FrameRuleReceipt | None:
    if not available(c, game, rule):
        return None
    receipt = rules.held(state, actor, rule)
    if receipt is not None:
        purchase_proof(c, game.store, receipt)
    return receipt


class JanusRequisitionService(RequisitionService):
    def __init__(self, game: GameService):
        super().__init__(game)
        self.game = game

    def menu(self, viewer: GuildViewer) -> dict[str, Any]:
        data = self.view(viewer)
        with self.store.engine.connect() as c:
            state = load_state(c, self.store.campaign_id)
            actor = ActorRef.model_validate(data["actor"])
            access = Access(self.store)
            choices = []
            for rule in IMPLEMENTED:
                if (
                    state.sheets[actor.entity].frame not in ("JANUS", "JANUS-B")
                    and rule != rules.PANDORA
                ):
                    continue  # Other grafts require their actual base-Core runtime first.
                try:
                    assert access.registry is not None
                    access.registry.require_available(rule)
                except (ValueError, WorkflowError):
                    continue
                if rules.held(state, actor, rule) is None:
                    choices.append(dict(id=rule, label=rules.TITLES[rule]))
            return data | dict(
                rules=choices,
                kind="ability_unlock"
                if canonical_frame(state.sheets[actor.entity].frame) in ("JANUS", "JANUS-B")
                else "frame_grafting",
                held=[
                    dict(id=r, label=rules.TITLES[r])
                    for r in cores.RULES
                    if rules.held(state, actor, r) is not None
                ],
            )

    def buy_rule(
        self, viewer: GuildViewer, key: str, expected: str, rule: str, account: str
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            access = Access(self.store)
            access.authorize(c, viewer, "economy")
            assert access.registry is not None
            entry = access.registry.require_available(rule)
            if (
                rule not in IMPLEMENTED
                or entry.frame_playbook != "JANUS"
                or entry.frame_rule != "requisition"
            ):
                raise WorkflowError("Choose a reviewed JANUS Requisition with its actual consumer")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            self._safe(c, state, viewer.user_id)
            actor = current_ref(state, viewer.user_id)
            view = resolve(state, actor, profiles(c, self.store.campaign_id))
            if view.frame not in ("JANUS", "JANUS-B") and rule != rules.PANDORA:
                raise WorkflowError(
                    "This graft needs an implemented original Core/base ability source"
                )
            if view.source_sha256 != expected or view.frame_instance is None or not account.strip():
                raise WorkflowError("Refresh the original owned Frame and actual acquisition")
            if any(
                isinstance(x, FrameRuleReceipt)
                and x.actor == actor
                and x.frame_instance == view.frame_instance
                and x.rule_id == rule
                for x in state.requisitions
            ):
                raise WorkflowError(
                    "Restore your existing original entitlement instead of buying it twice"
                )
            kind: Literal["ability_unlock", "frame_grafting"] = (
                "ability_unlock"
                if canonical_frame(view.frame or "") in ("JANUS", "JANUS-B")
                else "frame_grafting"
            )
            price: Literal[2, 3] = 2 if kind == "ability_unlock" else 3
            sheet = state.sheets[actor.entity]
            if sheet.permissions < price:
                raise WorkflowError("This actual acquisition needs its available Permissions")
            identity, event = str(uuid4()), str(uuid4())
            sheet.permissions -= price
            sheet.revision += 1
            state.requisitions.append(
                FrameRuleReceipt(
                    id=identity,
                    kind=kind,
                    actor=actor,
                    frame_instance=view.frame_instance,
                    frame=sheet.frame,
                    donor_frame="JANUS",
                    rule_id=rule,
                    grant="janus:" + identity,
                    price=price,
                    account=account,
                    source_event=event,
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3." + kind + "_purchased",
                state,
                event_id=event,
                requisition_id=identity,
                rule_id=rule,
                cost=price,
            )
            return dict(id=identity, rule=rule, cost=price)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.janus_rule_purchased",
                dict(expected=expected, rule=rule, account=account),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def tags(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            view = resolve(state, actor, profiles(c, self.store.campaign_id))
            value = cores.bound(state, actor, str(view.frame_instance))
            if value is None or not value.alive or not value.attached:
                raise WorkflowError("Use the actual still-attached original Core")
            prove_core(c, self.game, state, cores.ref(value))
            return dict(
                actor=actor.model_dump(mode="json"),
                core=cores.ref(value).model_dump(mode="json"),
                revision=state.revision,
                tags=[dict(id=x.id, label=x.label) for x in value.tags],
                trained=available(c, self.game, rules.TRAINING)
                and rules.held(state, actor, rules.TRAINING) is not None,
            )

    def start_training(
        self, viewer: GuildViewer, key: str, revision: int, account: str
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "playbooks")

        def operation(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_role_punishments import open_case, synchronize

            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            self._safe(c, state, viewer.user_id)
            if state.revision != revision or not account.strip():
                raise WorkflowError("Refresh the actual owned Core Training")
            actor = current_ref(state, viewer.user_id)
            receipt = owned(c, self.game, state, actor, rules.TRAINING)
            if receipt is None:
                raise WorkflowError("Acquire actual Obedience Training before this authority")
            core = cores.bound(state, actor, receipt.frame_instance)
            if core is None or not core.alive or not core.attached:
                raise WorkflowError("Use the actual attached original Core")
            prove_core(c, self.game, state, cores.ref(core))
            event, identity = str(uuid4()), str(uuid4())
            state, case = open_case(
                state,
                profiles(c, self.store.campaign_id),
                actor=actor,
                target=cores.ref(core),
                chooser=actor,
                source_kind="janus_training",
                action=None,
                source_event=event,
                identity=identity,
                source_work=receipt.id,
                chooser_controller=viewer.user_id,
                executor_controller=viewer.user_id,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.janus_training_started",
                state,
                event_id=event,
                case_id=case,
                purchase=receipt.id,
                account=account,
            )
            synchronize(self.game, c, None, event)
            return dict(id=case)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.janus_training_started",
                dict(account=account),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def remove_tag(
        self, viewer: GuildViewer, key: str, revision: int, identity: str, account: str
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "playbooks")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            self._safe(c, state, viewer.user_id)
            if state.revision != revision or not account.strip():
                raise WorkflowError("Refresh the actual original Core Tag removal")
            actor = current_ref(state, viewer.user_id)
            view = resolve(state, actor, profiles(c, self.store.campaign_id))
            value = cores.bound(state, actor, str(view.frame_instance))
            if (
                value is None
                or not value.alive
                or not value.attached
                or not any(x.id == identity for x in value.tags)
            ):
                raise WorkflowError("Remove one actual existing original Core Tag")
            prove_core(c, self.game, state, cores.ref(value))
            trained = owned(c, self.game, state, actor, rules.TRAINING)
            other = resolve(state, cores.ref(value), profiles(c, self.store.campaign_id))
            if view.cell is not None and other.cell is not None and view.cell != other.cell:
                raise WorkflowError("Actual separated bodies do not prove Core treatment reach")
            event = str(uuid4())
            changed = cores.update(
                state,
                cores.ref(value),
                tags=tuple(x for x in value.tags if x.id != identity),
                state_event=event,
            )
            if not cores.core(changed, cores.ref(value)).tags:
                changed = cores.free_core(changed, cores.ref(value), event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.janus_core_tag_removed",
                changed,
                event_id=event,
                core=cores.ref(value).model_dump(mode="json"),
                tag=identity,
                trained=trained is not None,
                account=account,
            )
            work = None
            if trained is None or not cores.core(changed, cores.ref(value)).tags:
                if state.handler is None:
                    raise WorkflowError("Recover the actual current source Handler")
                work = str(uuid4())
                related(
                    c,
                    self.store,
                    dict(campaign_id=self.store.campaign_id, campaign_context=True),
                    work,
                    state.handler,
                    viewer.user_id,
                    "punishment",
                    dict(
                        reason="janus_core_tag_removal",
                        owner=actor.model_dump(mode="json"),
                        character=actor.incarnation,
                        core=cores.ref(value).model_dump(mode="json"),
                        removed_tag=identity,
                        source_event=event,
                        source_pdf=68,
                        immediate=True,
                    ),
                    event,
                )
            void_work = open_freed_core_void(c, self.game, changed, cores.ref(value), event)
            return dict(core=value.id, removed=identity, punishment=work, void_work=void_work)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.janus_core_tag_removed",
                dict(tag=identity, account=account),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None


def prove_tag_removal(c: Connection, game: GameService, row: dict[str, Any]) -> None:
    body = json.loads(row["body_json"])
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == body["source_event"],
            )
        )
        .mappings()
        .first()
    )
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == body["source_event"],
        )
    )
    if event is None or raw is None:
        raise WorkflowError("Recover the actual source Core treatment event")
    state = GameState.model_validate_json(raw)
    actor = ActorRef.model_validate(body["owner"])
    core = ActorRef.model_validate(body["core"])
    value = prove_core(c, game, state, core)
    data = json.loads(event["payload_json"])
    if (
        event["kind"] != "m3.janus_core_tag_removed"
        or event["actor_id"] != actor.entity
        or actor.incarnation != body["character"]
        or row["subject_id"] != actor.entity
        or value.frame_owner != actor
        or data.get("tag") != body["removed_tag"]
        or data.get("core") != core.model_dump(mode="json")
        or data.get("trained") is not False
        and value.tags
        or any(x.id == body["removed_tag"] for x in value.tags)
    ):
        raise WorkflowError("Prove the actual unauthorized or freeing Core Tag removal")


def validate_role_case(c: Connection, game: GameService, state: GameState, case: Any) -> None:
    if case.source_kind != "janus_training" or case.action is not None or case.source_work is None:
        raise WorkflowError("Use the actual owned Obedience Training consequence source")
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == case.source_event
            )
        )
        .mappings()
        .first()
    )
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == case.source_event,
        )
    )
    source = GameState.model_validate_json(raw) if raw else None
    receipt = owned(c, game, source, case.executor, rules.TRAINING) if source else None
    body = json.loads(event["payload_json"]) if event else {}
    if (
        receipt is None
        or receipt.id != case.source_work
        or event is None
        or event["kind"] != "m3.janus_training_started"
        or event["actor_id"] != str(case.executor_controller)
        or body.get("case_id") != case.id
        or body.get("purchase") != receipt.id
        or case.chooser != case.executor
        or case.chooser_controller != case.executor_controller
    ):
        raise WorkflowError("Prove this actual original Pilot's paid Core Training authority")
    core = prove_core(c, game, state, case.subject)
    if (
        core.frame_owner != case.executor
        or core.frame_instance != case.executor_frame
        or not core.alive
    ):
        raise WorkflowError("Punish only this actual current original Core without killing her")


def open_freed_core_void(
    c: Connection, game: GameService, state: GameState, actor: ActorRef, event: str
) -> str | None:
    from girlframe.services.m3_void import _append, prepare_threshold

    value = cores.core(state, actor)
    fact = next(
        (
            x
            for x in state.facts
            if x.get("kind") == "janus_core_freed"
            and x.get("core") == actor.model_dump_json()
            and x.get("event") == event
        ),
        None,
    )
    if fact is None or not json.loads(fact["newly_void"]):
        return None
    owner = value.frame_owner
    sheet = state.sheets.get(owner.entity)
    if sheet is None or sheet.character_id != owner.incarnation:
        return None
    identity = str(uuid4())
    related(
        c,
        game.store,
        dict(campaign_id=game.store.campaign_id, campaign_context=True),
        identity,
        int(owner.entity),
        int(owner.entity),
        "void_threshold",
        dict(
            reason="janus_core_freed",
            owner=owner.model_dump(mode="json"),
            character=owner.incarnation,
            source_action=None,
            source_event=event,
            core=actor.model_dump(mode="json"),
            frame=value.frame_instance,
            source_pdf=19,
            janus_source_pdf=68,
            immediate=True,
            details=dict(family="frame"),
        ),
        event,
    )
    updated, threshold = prepare_threshold(c, game, identity)
    opened = game.event(
        c,
        int(owner.entity),
        str(uuid4()),
        "m3.janus_core_freedom_void_opened",
        updated,
        work_id=identity,
        source_event=event,
    )
    if threshold.stage == "prevented":
        row = (
            c.execute(
                sa.select(t.m3["m3_required_work"]).where(
                    t.m3["m3_required_work"].c.campaign_id == game.store.campaign_id,
                    t.m3["m3_required_work"].c.id == identity,
                )
            )
            .mappings()
            .one()
        )
        _append(
            c,
            dict(row),
            opened,
            json.loads(row["body_json"])
            | dict(threshold=threshold.id, resolution=threshold.stage, actual_actor=None),
            resolved=True,
        )
    return identity


def prove_freed_core_void(
    c: Connection, game: GameService, first: dict[str, Any], body: dict[str, Any], actor: ActorRef
) -> None:
    history = t.m2["m2_state_history"]
    raw = c.scalar(
        sa.select(history.c.body_json).where(
            history.c.campaign_id == game.store.campaign_id, history.c.event_id == first["event_id"]
        )
    )
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == first["event_id"]
            )
        )
        .mappings()
        .one()
    )
    before_raw = c.scalar(
        sa.select(history.c.body_json)
        .join(t.events, history.c.event_id == t.events.c.id)
        .where(history.c.campaign_id == game.store.campaign_id, t.events.c.seq < event["seq"])
        .order_by(t.events.c.seq.desc())
        .limit(1)
    )
    source = GameState.model_validate_json(raw) if raw else None
    before = GameState.model_validate_json(before_raw) if before_raw else None
    core = ActorRef.model_validate(body["core"])
    value = prove_core(c, game, source, core) if source else None
    prior = cores.find(before, core) if before else None
    data = json.loads(event["payload_json"])
    fact = (
        next(
            (
                x
                for x in source.facts
                if x.get("kind") == "janus_core_freed"
                and x.get("core") == core.model_dump_json()
                and x.get("event") == first["event_id"]
            ),
            None,
        )
        if source
        else None
    )
    if (
        value is None
        or prior is None
        or len(prior.tags) != 1
        or value.tags
        or prior.tags[0].id != data.get("tag")
        or value.takeover_event != first["event_id"]
        or value.frame_owner != actor
        or value.frame_instance != body["frame"]
        or fact is None
        or not json.loads(fact["newly_void"])
        or event["kind"] != "m3.janus_core_tag_removed"
        or event["actor_id"] != actor.entity
    ):
        raise WorkflowError(
            "Prove the actual voluntary final Core Tag removal and Frame corruption"
        )
