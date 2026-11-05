"""Actual instruction/consultation, participant scene proof and separate execution."""

import json
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_role_punishments as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_punishments import Details, validate
from girlframe.engine.m3_role_punishment_state import Instruction, RolePunishment
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def supported(
    state: GameState, target: ActorRef, actor: ActorRef, bindings: tuple[ProfileBinding, ...]
) -> bool:
    return bool(rules.available(state, target, actor, bindings))


def open_case(
    state: GameState,
    bindings: tuple[ProfileBinding, ...],
    *,
    actor: ActorRef,
    target: ActorRef,
    chooser: ActorRef,
    source_kind: Literal["enforcement_initiative", "obedience_volunteer"],
    action: str | None,
    source_event: str,
    identity: str,
    source_work: str | None = None,
) -> tuple[GameState, str]:
    changed = GameState.model_validate_json(state.model_dump_json())
    executor = resolve(changed, actor, bindings, require_current_profile=False)
    subject = resolve(changed, target, bindings, require_current_profile=False)
    if chooser.kind == "handler":
        if chooser != current_ref(changed, int(chooser.entity)):
            raise WorkflowError("Use the actual current Handler's original instruction role.")
        chooser_controller = int(chooser.entity)
    else:
        chooser_controller = resolve(
            changed, chooser, bindings, require_current_profile=False
        ).controller
    if not supported(changed, target, actor, bindings) or not executor.frame_instance:
        raise WorkflowError(
            "UNSUPPORTED_ROLE_PUNISHMENT: this source target has no actual effect port."
        )
    if any(
        x.id == identity or x.action == action and action is not None
        for x in changed.role_punishments
    ):
        raise WorkflowError("This actual mandatory Punishment source already exists.")
    case = RolePunishment(
        id=identity,
        source_kind=source_kind,
        action=action,
        source_work=source_work,
        source_event=source_event,
        chooser=chooser,
        chooser_controller=chooser_controller,
        executor=actor,
        executor_controller=executor.controller,
        executor_frame=executor.frame_instance,
        subject=rules.bond_ref(changed, target),
        subject_controller=subject.controller,
        pc_work=source_work or str(uuid5(NAMESPACE_URL, "girlframe:role-punishment:" + identity))
        if target.kind == "pilot"
        else None,
    )
    changed.role_punishments.append(case)
    return changed, identity


def _replace(state: GameState, case: RolePunishment) -> None:
    state.role_punishments = [case if x.id == case.id else x for x in state.role_punishments]


def case_proof(c: Connection, game: GameService, identity: str) -> RolePunishment:
    state = load_state(c, game.store.campaign_id)
    case = next((x for x in state.role_punishments if x.id == identity), None)
    if case is None:
        raise WorkflowError("This original instruction/execution case is unavailable.")
    body = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == case.source_event,
        )
    )
    original = GameState.model_validate_json(body) if body else None
    first = (
        next((x for x in original.role_punishments if x.id == identity), None) if original else None
    )
    stable = (
        "id",
        "source_kind",
        "action",
        "source_work",
        "source_event",
        "chooser",
        "chooser_controller",
        "executor",
        "executor_controller",
        "executor_frame",
        "subject",
        "subject_controller",
        "pc_work",
    )
    if first is None or any(getattr(first, k) != getattr(case, k) for k in stable):
        raise WorkflowError(
            "SOURCE_ROLE_PUNISHMENT_MISSING: recover the actual original consequence."
        )
    if case.instruction_event:
        event = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == case.instruction_event,
                )
            )
            .mappings()
            .first()
        )
        saved = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == case.instruction_event,
            )
        )
        source = GameState.model_validate_json(saved) if saved else None
        instruction = (
            next((x for x in source.role_punishments if x.id == identity), None) if source else None
        )
        if (
            event is None
            or event["kind"] != "m3.role_punishment_instructed"
            or event["actor_id"] != str(case.chooser_controller)
            or instruction is None
            or instruction.instruction != case.instruction
            or instruction.executor != case.executor
        ):
            raise WorkflowError(
                "SOURCE_INSTRUCTION_MISSING: recover the exact original chooser's instruction."
            )
    if case.handler_approval_event:
        source_event = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == case.handler_approval_event,
                )
            )
            .mappings()
            .first()
        )
        snapshot = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == case.handler_approval_event,
            )
        )
        approved_state = GameState.model_validate_json(snapshot) if snapshot else None
        approved = (
            next((x for x in approved_state.role_punishments if x.id == identity), None)
            if approved_state
            else None
        )
        if (
            source_event is None
            or approved_state is None
            or approved is None
            or source_event["kind"]
            not in ("m3.role_punishment_instructed", "m3.role_punishment_consulted")
            or approved_state.handler != int(source_event["actor_id"])
            or approved.instruction != case.instruction
            or approved.executor != case.executor
            or approved.subject != case.subject
            or approved.handler_approver != case.handler_approver
        ):
            raise WorkflowError(
                "SOURCE_CONSULTATION_MISSING: recover the exact Handler instruction/approval."
            )
    return case


def current(c: Connection, game: GameService, state: GameState, case: RolePunishment) -> None:
    bound = profiles(c, game.store.campaign_id)
    executor = resolve(state, case.executor, bound, require_current_profile=False)
    target = rules.view(state, case.subject, bound)
    if (
        executor.controller != case.executor_controller
        or executor.frame_instance != case.executor_frame
        or target.controller != case.subject_controller
    ):
        raise WorkflowError("Recover the actual original executor, Frame and affected person.")
    if case.chooser.kind == "handler":
        if (
            current_ref(state, int(case.chooser.entity)) != case.chooser
            or HandlerService(game.store).current(c)[1].handler_id != case.chooser_controller
        ):
            raise WorkflowError("Recover the original Handler's actual instruction authority.")
    else:
        resolve(state, case.chooser, bound, require_current_profile=False)


def pc_execution(
    c: Connection,
    game: GameService,
    row: dict[str, Any],
    viewer: GuildViewer,
    details: Details | None = None,
) -> RolePunishment | None:
    identity = json.loads(row["body_json"]).get("role_case")
    if identity is None:
        return None
    case = case_proof(c, game, identity)
    current(c, game, load_state(c, game.store.campaign_id), case)
    if (
        case.pc_work != row["id"]
        or viewer.user_id != case.executor_controller
        or case.instruction is None
        or case.effect_event is not None
        or set(case.attendance) != {case.executor_controller, case.subject_controller}
    ):
        raise WorkflowError(
            "The original executor must carry out the exact instructed on-screen Punishment."
        )
    if details is not None and details != Details.model_validate_json(
        case.instruction.details_json
    ):
        raise WorkflowError(
            "Carry out the actual chosen instruction; only its original chooser may change it."
        )
    severity = validate(Details.model_validate_json(case.instruction.details_json))
    if (
        severity == "moderate"
        and case.chooser.kind != "handler"
        and not case.handler_approval_event
    ):
        raise WorkflowError(
            "Consult the actual Handler about this exact executor and proposal first."
        )
    return case


def mark_pc_effect(state: GameState, case: RolePunishment, event: str, account: str) -> None:
    _replace(state, case.model_copy(update=dict(effect_event=event, execution_account=account)))


def _latest_work(c: Connection, game: GameService) -> dict[str, dict[str, Any]]:
    work = t.m3["m3_required_work"]
    return {
        x["id"]: dict(x)
        for x in c.execute(
            sa.select(work)
            .where(work.c.campaign_id == game.store.campaign_id)
            .order_by(work.c.revision)
        ).mappings()
    }


def synchronize(
    game: GameService, c: Connection, action: dict[str, Any] | None, event: str
) -> None:
    """Create actual PC work after its source exists, finish only real effects/followups."""
    state = load_state(c, game.store.campaign_id)
    existing = _latest_work(c, game)
    for case in state.role_punishments:
        if case.pc_work and case.pc_work in existing and case.source_work:
            row = existing[case.pc_work]
            body = json.loads(row["body_json"])
            if not body.get("role_case"):
                if (
                    row["state"] == "resolved"
                    or row["owner_id"] != str(case.chooser_controller)
                    or row["subject_id"] != str(case.subject_controller)
                ):
                    raise WorkflowError(
                        "Recover the actual unchanged original chooser's pending Punishment."
                    )
                c.execute(
                    t.m3["m3_required_work"]
                    .insert()
                    .values(
                        **{
                            k: v
                            for k, v in row.items()
                            if k not in ("revision", "body_json", "event_id")
                        },
                        revision=row["revision"] + 1,
                        event_id=case.source_event,
                        body_json=json.dumps(body | dict(role_case=case.id)),
                    )
                )
            elif body["role_case"] != case.id:
                raise WorkflowError(
                    "This actual Punishment already has a different executor appointment."
                )
        if case.pc_work and case.pc_work not in existing:
            if not case.action:
                raise WorkflowError("Recover this original Punishment's actual source work.")
            source = game.action(c, case.action)
            related(
                c,
                game.store,
                dict(campaign_id=game.store.campaign_id, scene_id=source["scene_id"]),
                case.pc_work,
                case.chooser_controller,
                case.subject_controller,
                "punishment",
                dict(
                    reason="role_punishment",
                    role_case=case.id,
                    character=case.subject.incarnation,
                    source_action=case.action,
                    immediate=True,
                ),
                case.source_event,
            )
    state = load_state(c, game.store.campaign_id)
    changed = False
    finished_actions: set[str] = set()
    for case in tuple(state.role_punishments):
        if not case.effect_event or case.completion_event:
            continue
        pending = False
        if case.pc_work:
            work = _latest_work(c, game)
            chain = {case.pc_work}
            while True:
                children = {
                    x["id"]
                    for x in work.values()
                    if json.loads(x["body_json"]).get("source_work") in chain
                }
                if children <= chain:
                    break
                chain |= children
            pending = any(
                x["id"] in chain
                and x["state"] != "resolved"
                and (x["id"] == case.pc_work or json.loads(x["body_json"]).get("immediate"))
                for x in work.values()
            )
        if pending:
            continue
        _replace(state, case.model_copy(update={"completion_event": event}))
        changed = True
        if case.action:
            finished_actions.add(case.action)
    if changed:
        game.event(
            c,
            state.handler or "system",
            str(uuid4()),
            "m3.role_punishment_completed",
            state,
            source_event=event,
        )
    # Initiative owns its source lock/choice continuation. The callback checks exact case
    # completion and never lets a generic acknowledgment resolve this consequence.
    if action is not None:
        finished_actions.add(action["id"])
    for identity in finished_actions:
        actual = game.action(c, identity)
        if actual["data"].get("enforcement"):
            from girlframe.services.m3_enforcement_initiative import continue_punishment

            continue_punishment(game, c, actual, event)


class RolePunishmentService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _visible(self, c: Connection, viewer: GuildViewer, case: RolePunishment) -> None:
        self.game.authorize(c, viewer, game=False)
        if viewer.user_id not in {
            case.chooser_controller,
            case.executor_controller,
            case.subject_controller,
            load_state(c, self.store.campaign_id).handler,
        }:
            raise WorkflowError("This actual instruction and scene belong to other participants.")

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        result = []
        for case in state.role_punishments:
            needs_approval = bool(
                case.instruction
                and validate(Details.model_validate_json(case.instruction.details_json))
                == "moderate"
                and not case.handler_approval_event
            )
            if viewer.user_id not in {
                case.chooser_controller,
                case.executor_controller,
                case.subject_controller,
            } and not (needs_approval and viewer.user_id == state.handler):
                continue
            if case.effect_event or case.completion_event:
                actionable = False
            elif case.instruction is None:
                actionable = viewer.user_id == case.chooser_controller
            elif needs_approval:
                actionable = viewer.user_id == state.handler
            elif not case.scene_account:
                actionable = viewer.user_id == case.executor_controller
            elif set(case.attendance) != {case.executor_controller, case.subject_controller}:
                actionable = (
                    viewer.user_id in {case.executor_controller, case.subject_controller}
                    and viewer.user_id not in case.attendance
                )
            else:
                actionable = viewer.user_id == case.executor_controller
            result.append(
                dict(
                    id=case.id,
                    state="resolved" if case.completion_event else "pending",
                    chooser=viewer.user_id == case.chooser_controller,
                    executor=viewer.user_id == case.executor_controller,
                    actionable=actionable,
                )
            )
        return result

    def tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            return self._tasks(c, viewer)

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            case = case_proof(c, self.game, identity)
            self._visible(c, viewer, case)
            state = load_state(c, self.store.campaign_id)
            stale = False
            try:
                current(c, self.game, state, case)
            except (ValueError, WorkflowError):
                stale = True
            peers: list[dict[str, Any]] = []
            bound = profiles(c, self.store.campaign_id)
            refs = [
                ActorRef(kind="pilot", entity=str(x.owner), incarnation=x.character_id)
                for x in bound
            ]
            if state.handler:
                refs.append(current_ref(state, state.handler))
            if state.world:
                refs.extend(ActorRef(kind="npc", entity=x.id) for x in state.world.npcs if x.alive)
            for peer in refs if viewer.user_id == case.chooser_controller else []:
                try:
                    if depth(
                        state, rules.bond_ref(state, case.subject), rules.bond_ref(state, peer)
                    ):
                        peers.append(
                            dict(
                                ref=peer.model_dump(mode="json"),
                                token=peer.token,
                                label=resolve(
                                    state, peer, bound, require_current_profile=False
                                ).label,
                            )
                        )
                except ValueError:
                    continue
            projection = case.model_dump(mode="json")
            if viewer.user_id not in {case.executor_controller, case.subject_controller}:
                if case.scene_account:
                    projection["scene_account"] = (
                        "The actual scene participants recorded their attendance."
                    )
                if case.execution_account:
                    projection["execution_account"] = (
                        "The named executor supplied actual completion evidence."
                    )
            if case.instruction and viewer.user_id not in {
                case.chooser_controller,
                case.executor_controller,
                state.handler,
            }:
                selected = Details.model_validate_json(case.instruction.details_json)
                if selected.kind == "strict_regulations" and not selected.disclosed:
                    projection["instruction"]["details_json"] = selected.model_copy(
                        update={"regulation": "Concealed behavioural rule"}
                    ).model_dump_json()
            pc_choices: dict[str, Any] | None = None
            if case.pc_work and viewer.user_id == case.chooser_controller and not case.effect_event:
                from girlframe.services.m3_punishments import PunishmentService

                pc_choices = PunishmentService(self.store).get(viewer, case.pc_work).get("choices")
            return dict(
                id=identity,
                revision=state.revision,
                stale=stale,
                case=projection,
                kinds=list(rules.available(state, case.subject, case.executor, bound))
                if not stale
                else [],
                peers=peers,
                pc_choices=pc_choices,
                chooser=viewer.user_id == case.chooser_controller,
                executor=viewer.user_id == case.executor_controller,
                can_attest=viewer.user_id in {case.executor_controller, case.subject_controller}
                and viewer.user_id not in case.attendance,
                can_approve=viewer.user_id == state.handler
                and case.instruction is not None
                and validate(Details.model_validate_json(case.instruction.details_json))
                == "moderate"
                and case.handler_approval_event is None,
            )

    def change(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        *,
        instruction: Instruction | None = None,
        scene: str | None = None,
        attest: bool = False,
        approve: bool = False,
        execute: bool = False,
        account: str = "",
    ) -> dict[str, Any]:
        pc_call: tuple[str, int, Details] | None = None
        if execute:
            with self.store.engine.connect() as c:
                case = case_proof(c, self.game, identity)
                if case.pc_work:
                    from girlframe.services.m3_punishments import PunishmentService

                    row = PunishmentService(self.store)._row(c, case.pc_work)
                    if case.instruction is None:
                        raise WorkflowError(
                            "The actual chooser must instruct the Punishment first."
                        )
                    pc_call = (
                        case.pc_work,
                        row["revision"],
                        Details.model_validate_json(case.instruction.details_json),
                    )
            if pc_call:
                return PunishmentService(self.store).apply(
                    viewer,
                    key,
                    pc_call[0],
                    pc_call[1],
                    revision,
                    pc_call[2],
                    execution_account=account,
                )

        def access(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "discipline", director_response=attest)
            self._visible(c, viewer, case_proof(c, self.game, identity))

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            case = case_proof(c, self.game, identity)
            state = load_state(c, self.store.campaign_id)
            current(c, self.game, state, case)
            if (
                state.revision != revision
                or case.effect_event
                or sum((instruction is not None, scene is not None, attest, approve, execute)) != 1
            ):
                raise WorkflowError(
                    "STALE_ROLE_PUNISHMENT: reopen the original current instruction/scene."
                )
            event = str(uuid4())
            if instruction is not None:
                if viewer.user_id != case.chooser_controller or case.attendance:
                    raise WorkflowError(
                        "Only the original chooser instructs before the actual scene begins."
                    )
                details = Details.model_validate_json(instruction.details_json)
                if instruction.kind != details.kind or instruction.kind not in rules.available(
                    state, case.subject, case.executor, profiles(c, self.store.campaign_id)
                ):
                    raise WorkflowError(
                        "Choose an actual supported and applicable Punishment type."
                    )
                validate(details)
                if case.subject.kind != "pilot":
                    rules.social(
                        state,
                        case.subject,
                        case.executor,
                        instruction,
                        profiles(c, self.store.campaign_id),
                        event,
                        "preview-validation",
                    )
                case = case.model_copy(
                    update=dict(
                        instruction=instruction,
                        instruction_event=event,
                        handler_approval_event=event if case.chooser.kind == "handler" else None,
                        handler_approver=case.chooser if case.chooser.kind == "handler" else None,
                    )
                )
                kind = "instructed"
            elif scene is not None:
                if (
                    viewer.user_id != case.executor_controller
                    or not scene.strip()
                    or case.scene_account
                    or case.instruction is None
                ):
                    raise WorkflowError("The actual executor records one concrete on-screen scene.")
                case = case.model_copy(
                    update=dict(scene_account=scene.strip(), attendance=(viewer.user_id,))
                )
                kind = "scene_set"
            elif attest:
                if (
                    viewer.user_id not in {case.executor_controller, case.subject_controller}
                    or viewer.user_id in case.attendance
                    or not case.scene_account
                ):
                    raise WorkflowError(
                        "Each actual participant records only their own played attendance."
                    )
                case = case.model_copy(update={"attendance": (*case.attendance, viewer.user_id)})
                kind = "scene_attested"
            elif approve:
                HandlerService(self.store).authorize(c, viewer)
                if case.instruction is None:
                    raise WorkflowError("Review the exact original proposal and executor first.")
                case = case.model_copy(
                    update={
                        "handler_approval_event": event,
                        "handler_approver": current_ref(state, viewer.user_id),
                    }
                )
                kind = "consulted"
            else:
                if (
                    viewer.user_id != case.executor_controller
                    or case.instruction is None
                    or set(case.attendance) != {case.executor_controller, case.subject_controller}
                    or not account.strip()
                ):
                    raise WorkflowError(
                        "Carry out the exact actual instruction after the on-screen scene."
                    )
                state = rules.social(
                    state,
                    case.subject,
                    case.executor,
                    case.instruction,
                    profiles(c, self.store.campaign_id),
                    event,
                    str(uuid4()),
                )
                case = case.model_copy(update=dict(effect_event=event, execution_account=account))
                kind = "executed"
            _replace(state, case)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.role_punishment_" + kind,
                state,
                event_id=event,
                case_id=identity,
            )
            source_action = self.game.action(c, case.action) if case.action else None
            synchronize(self.game, c, source_action, event)
            return dict(id=identity, effect_applied=execute)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.role_punishment_change",
                dict(
                    id=identity,
                    revision=revision,
                    instruction=instruction.model_dump(mode="json") if instruction else None,
                    scene=scene,
                    attest=attest,
                    approve=approve,
                    execute=execute,
                    account=account,
                ),
                operation,
                authorize=access,
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
