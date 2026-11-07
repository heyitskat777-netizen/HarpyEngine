"""Actual instruction/consultation, participant scene proof and separate execution."""

import json
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_role_punishments as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import depth
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_handler_consequences import active_handler
from girlframe.engine.m3_intracadre_marriage import allocation_fields
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


def available_for_case(
    state: GameState, case: RolePunishment, bindings: tuple[ProfileBinding, ...]
) -> tuple[str, ...]:
    if case.subject == case.executor and case.source_kind == "compliance_virus":
        if case.subject.kind == "pilot":
            from girlframe.engine.m3_punishments import KINDS

            # No invented self-Bond or self-opponent Helpless consequence. The source
            # still has several real bodily/identity/social Punishments to choose.
            return tuple(
                k
                for k, (_, severity) in KINDS.items()
                if severity != "severe"
                and k
                not in ("quality_time", "passing_responsibility", "beating", "revoked_privileges")
            )
        return (
            ("stimulant_injection", "reduced_socialization")
            if any(case.subject in (x.first, x.second) and x.depth > 0 for x in state.actor_bonds)
            else ("stimulant_injection",)
        )
    kinds = rules.available(state, case.subject, case.executor, bindings)
    if (
        case.source_kind in ("compliance_virus", "janus_training")
        and case.subject.kind == "external_pilot"
        and rules.view(state, case.subject, bindings).girl == "harpy"
    ):
        kinds = (*kinds, "stimulant_injection")
    if (
        case.source_kind == "handler_play"
        and case.subject.kind == "pilot"
        and case.executor.kind == "handler"
        and case.chooser == case.executor
        and case.chooser_controller == case.executor_controller
    ):
        return (*kinds, "lobotomization")
    return kinds


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
    chooser: ActorRef | None,
    source_kind: Literal[
        "enforcement_initiative",
        "obedience_volunteer",
        "handler_play",
        "compliance_virus",
        "janus_training",
        "alpha_sex",
        "dose_up",
        "succubus_npc_disobey",
    ],
    action: str | None,
    source_event: str,
    identity: str,
    source_work: str | None = None,
    chooser_controller: int | None = None,
    executor_controller: int | None = None,
) -> tuple[GameState, str]:
    changed = GameState.model_validate_json(state.model_dump_json())
    executor = rules.view(changed, actor, bindings)
    subject = rules.view(changed, target, bindings)
    from girlframe.engine.m3_intracadre_marriage import allocate

    work_id = (
        source_work
        if source_kind == "obedience_volunteer"
        else str(uuid5(NAMESPACE_URL, "girlframe:role-punishment:" + identity))
    )
    allocation = allocate(
        changed, target, source_event=source_event, source_id=identity, work_id=work_id or identity
    )
    if allocation is not None:
        target = allocation.subject
        subject = rules.view(changed, target, bindings)
    if source_kind in ("handler_play", "compliance_virus", "janus_training"):
        if chooser_controller is None or source_work is None:
            raise WorkflowError("Use the actual scoped Handler Play grant and chooser controller.")
    elif chooser is None:
        raise WorkflowError("This source requires the actual original chooser.")
    elif chooser.kind == "handler":
        if chooser != active_handler(changed):
            raise WorkflowError("Use the actual current Handler's original instruction role.")
        chooser_controller = int(chooser.entity)
    else:
        chooser_controller = resolve(
            changed, chooser, bindings, require_current_profile=False
        ).controller
    if not (
        supported(changed, target, actor, bindings)
        or source_kind == "compliance_virus"
        and actor == target
    ) or (actor.kind == "pilot" and not executor.frame_instance):
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
        executor_controller=executor_controller
        if source_kind in ("handler_play", "compliance_virus", "janus_training")
        and executor_controller is not None
        else executor.controller,
        executor_frame=executor.frame_instance,
        subject=rules.bond_ref(changed, target),
        subject_controller=subject.controller,
        pc_work=(
            source_work
            if source_kind == "obedience_volunteer"
            else str(uuid5(NAMESPACE_URL, "girlframe:role-punishment:" + identity))
        )
        if target.kind == "pilot" and actor.kind in ("pilot", "handler")
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
    from girlframe.services.m3_intracadre_marriage import original_offender

    original_offender(game, c, state, case.id, case.source_event, case.subject)
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
        director_instruction = False
        if (
            case.source_kind == "enforcement_initiative"
            and case.action
            and case.chooser is not None
            and case.chooser.kind == "npc"
            and approved_state is not None
            and source_event is not None
            and case.handler_approval_event == case.instruction_event
            and str(case.chooser_controller) == source_event["actor_id"]
        ):
            from girlframe.engine.m3_actor_state import SceneCast

            source_action = game.action(c, case.action)
            context = source_action["data"].get("enforcement", {})
            cast = SceneCast.model_validate_json(json.dumps(context["cast"]))
            raw_judge = (
                c.execute(
                    sa.select(t.events).where(
                        t.events.c.campaign_id == game.store.campaign_id,
                        t.events.c.id == context.get("judge_source"),
                    )
                )
                .mappings()
                .first()
            )
            raw_cast = c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json).where(
                    t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_state_history"].c.event_id == context.get("judge_source"),
                )
            )
            judge_state = GameState.model_validate_json(raw_cast) if raw_cast else None
            saved_cast = (
                next((x for x in judge_state.scene_casts if x.id == cast.id), None)
                if judge_state
                else None
            )
            director_instruction = bool(
                raw_judge is not None
                and raw_judge["kind"] == "m3.scene_cast_changed"
                and raw_judge["actor_id"] == str(case.chooser_controller)
                and json.loads(raw_judge["payload_json"]).get("action") == "adjudicate"
                and json.loads(raw_judge["payload_json"]).get("scene") == cast.id
                and saved_cast is not None
                and saved_cast.adjudicator == case.chooser
                and any(
                    x.actor == case.chooser and x.controller == case.chooser_controller
                    for x in saved_cast.roles
                )
                and context.get("handler") == case.chooser.model_dump(mode="json")
                and context.get("handler_controller") == case.chooser_controller
                and approved_state.world is not None
                and any(
                    x.id == case.chooser.entity and x.alive and "director" in x.jobs
                    for x in approved_state.world.npcs
                )
            )
        if (
            source_event is None
            or approved_state is None
            or approved is None
            or source_event["kind"]
            not in ("m3.role_punishment_instructed", "m3.role_punishment_consulted")
            or (
                case.source_kind not in ("handler_play", "compliance_virus", "janus_training")
                and not director_instruction
                and approved_state.handler != int(source_event["actor_id"])
            )
            or approved.instruction != case.instruction
            or approved.executor != case.executor
            or approved.subject != case.subject
            or approved.handler_approver != case.handler_approver
        ):
            raise WorkflowError(
                "SOURCE_CONSULTATION_MISSING: recover the exact Handler instruction/approval."
            )
    if case.source_kind == "succubus_npc_disobey":
        from girlframe.services.m3_succubus import validate_role_case

        validate_role_case(c, game, state, case)
    if case.source_kind == "dose_up":
        from girlframe.services.m3_dose_up import validate_role_case

        validate_role_case(c, game, state, case)
    if case.source_kind == "alpha_sex":
        from girlframe.services.m3_alpha_sex import validate_role_case

        validate_role_case(c, game, state, case)
    if case.source_kind == "janus_training":
        from girlframe.services.m3_janus_requisitions import validate_role_case

        validate_role_case(c, game, state, case)
    if case.source_kind == "handler_play":
        from girlframe.services.m3_handler_plays import validate_role_case

        validate_role_case(c, game, state, case)
    if case.source_kind == "compliance_virus":
        from girlframe.services.m3_compliance_virus import validate_role_case

        validate_role_case(c, game, state, case)
    if case.source_kind == "enforcement_initiative" and case.executor.kind == "external_pilot":
        assert original is not None
        _harpy_case(c, game, original, case)
    return case


def _harpy_case(c: Connection, game: GameService, state: GameState, case: RolePunishment) -> None:
    from girlframe.services.m3_enforcement_initiative import _prove_harpy, _refs

    if case.action is None:
        raise WorkflowError("Recover this actual Harpy's original Initiative action.")
    actual = game.action(c, case.action)
    meta = actual["data"].get("enforcement", {})
    from girlframe.services.m3_intracadre_marriage import original_offender

    offender = original_offender(game, c, state, case.id, case.source_event, case.subject)
    if (
        (_refs(actual)[0], rules.bond_ref(state, _refs(actual)[1])) != (case.executor, offender)
        or meta.get("punishment") != case.id
        or rules.view(state, case.executor, profiles(c, game.store.campaign_id)).frame_instance
        != case.executor_frame
    ):
        raise WorkflowError("SOURCE_HARPY_EXECUTION_MISSING: recover the original Frame and case.")
    _prove_harpy(c, game, state, case.executor)


def current(c: Connection, game: GameService, state: GameState, case: RolePunishment) -> None:
    bound = profiles(c, game.store.campaign_id)
    executor = rules.view(state, case.executor, bound)
    target = rules.view(state, case.subject, bound)
    if (
        executor.controller != case.executor_controller
        or executor.frame_instance != case.executor_frame
        or target.controller != case.subject_controller
    ):
        raise WorkflowError("Recover the actual original executor, Frame and affected person.")
    if case.source_kind == "succubus_npc_disobey":
        from girlframe.services.m3_succubus import validate_role_case

        validate_role_case(c, game, state, case)
        return
    if case.source_kind == "dose_up":
        from girlframe.services.m3_dose_up import validate_role_case

        validate_role_case(c, game, state, case)
        return
    if case.source_kind == "alpha_sex":
        from girlframe.services.m3_alpha_sex import validate_role_case

        validate_role_case(c, game, state, case)
        return
    if case.source_kind == "janus_training":
        from girlframe.services.m3_janus_requisitions import validate_role_case

        validate_role_case(c, game, state, case)
        return
    if case.source_kind == "handler_play":
        from girlframe.services.m3_handler_plays import validate_role_case

        validate_role_case(c, game, state, case)
        return
    if case.source_kind == "compliance_virus":
        from girlframe.services.m3_compliance_virus import validate_role_case

        validate_role_case(c, game, state, case)
        return
    if case.executor.kind == "external_pilot":
        _harpy_case(c, game, state, case)
    if case.chooser is None:
        raise WorkflowError("Recover the actual original instruction owner.")
    if case.chooser.kind == "handler":
        if (
            active_handler(state) != case.chooser
            or HandlerService(game.store).current(c)[1].handler_id != case.chooser_controller
        ):
            raise WorkflowError("Recover the original Handler's actual instruction authority.")
    else:
        resolve(state, case.chooser, bound, require_current_profile=False)
        if case.source_kind == "enforcement_initiative" and case.action:
            from girlframe.services.m3_enforcement_initiative import instruction_authority

            actual, controller = instruction_authority(game, c, state, game.action(c, case.action))
            if actual != case.chooser or controller != case.chooser_controller:
                raise WorkflowError("Recover the actual source Director's original instruction.")


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
        or case.ended_event is not None
        or set(case.attendance) != {case.executor_controller, case.subject_controller}
    ):
        raise WorkflowError(
            "The original executor must carry out the exact instructed on-screen Punishment."
        )
    instructed = Details.model_validate_json(case.instruction.details_json)
    compared = details
    if details is not None and details.kind == "lobotomization" and details.surgery is not None:
        surgery = next(
            (
                x
                for x in load_state(c, game.store.campaign_id).lobotomies
                if x.id == details.surgery
            ),
            None,
        )
        if (
            surgery is None
            or case.pc_work not in surgery.work_ids
            or surgery.inflictor != case.executor
        ):
            raise WorkflowError("Recover the exact instructed surgery and actual inflictor.")
        compared = details.model_copy(update={"surgery": None})
    if compared is not None and compared != instructed:
        raise WorkflowError(
            "Carry out the actual chosen instruction; only its original chooser may change it."
        )
    severity = validate(Details.model_validate_json(case.instruction.details_json))
    if (
        severity == "moderate"
        and (case.chooser is None or case.chooser.kind != "handler")
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
        if case.ended_event is not None:
            continue
        if case.pc_work and case.pc_work in existing and case.source_kind == "obedience_volunteer":
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
            if case.action:
                source = game.action(c, case.action)
                scope: dict[str, Any] = dict(
                    campaign_id=game.store.campaign_id, scene_id=source["scene_id"]
                )
            elif case.source_kind == "handler_play":
                from girlframe.services.m3_handler_plays import role_scope

                scope = role_scope(c, game, case).model_dump() | dict(
                    campaign_id=game.store.campaign_id
                )
            elif case.source_kind == "compliance_virus":
                from girlframe.services.m3_compliance_virus import role_scope

                scope = role_scope(c, game, case).model_dump() | dict(
                    campaign_id=game.store.campaign_id
                )
            else:
                raise WorkflowError("Recover this original Punishment's actual source work.")
            related(
                c,
                game.store,
                scope,
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
                    **allocation_fields(state, case.id),
                ),
                case.source_event,
            )
    state = load_state(c, game.store.campaign_id)
    changed = False
    completion_id = str(uuid4())
    completed_cases: list[str] = []
    finished_actions: set[str] = set()
    for case in tuple(state.role_punishments):
        if not case.effect_event or case.completion_event or case.ended_event:
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
        _replace(state, case.model_copy(update={"completion_event": completion_id}))
        completed_cases.append(case.id)
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
            event_id=completion_id,
        )
        for identity in completed_cases:
            completed = next(x for x in state.role_punishments if x.id == identity)
            if completed.source_kind == "handler_play":
                from girlframe.services.m3_handler_plays import complete_role_case

                complete_role_case(c, game, completed, completion_id)
            elif completed.source_kind == "succubus_npc_disobey":
                from girlframe.services.m3_succubus import complete_role_case

                complete_role_case(c, game, completed, completion_id)
            elif completed.source_kind == "dose_up":
                from girlframe.services.m3_dose_up import complete_role_case

                complete_role_case(c, game, completed, completion_id)
            elif completed.source_kind == "alpha_sex":
                from girlframe.services.m3_alpha_sex import complete_role_case

                complete_role_case(c, game, completed, completion_id)
            elif completed.source_kind == "compliance_virus":
                from girlframe.services.m3_compliance_virus import (
                    complete_role_case as complete_virus,
                )

                complete_virus(c, game, completed, completion_id)
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
            if case.effect_event or case.completion_event or case.ended_event:
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
                    state="resolved" if case.completion_event or case.ended_event else "pending",
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
            actual_handler = active_handler(state)
            if actual_handler is not None:
                refs.append(actual_handler)
            if state.world:
                refs.extend(ActorRef(kind="npc", entity=x.id) for x in state.world.npcs if x.alive)
                refs.extend(
                    ActorRef(kind="gorgon", entity=x.id) for x in state.world.gorgons if x.alive
                )
                refs.extend(
                    ActorRef(kind="external_pilot", entity=x.id)
                    for x in state.world.pilots
                    if x.alive
                )
            refs.extend(
                ActorRef(kind="external_pilot", entity=x.id) for x in state.harpy_states if x.alive
            )
            for peer in refs if viewer.user_id == case.chooser_controller else []:
                try:
                    if depth(
                        state, rules.bond_ref(state, case.subject), rules.bond_ref(state, peer)
                    ):
                        peers.append(
                            dict(
                                ref=peer.model_dump(mode="json"),
                                token=peer.token,
                                label=rules.view(state, peer, bound).label,
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
            if (
                case.pc_work
                and viewer.user_id == case.chooser_controller
                and not case.effect_event
                and not case.ended_event
            ):
                from girlframe.services.m3_punishments import PunishmentService

                pc_choices = PunishmentService(self.store).get(viewer, case.pc_work).get("choices")
            return dict(
                id=identity,
                revision=state.revision,
                stale=stale,
                case=projection,
                kinds=list(available_for_case(state, case, bound)) if not stale else [],
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
                applied = PunishmentService(self.store).apply(
                    viewer,
                    key,
                    pc_call[0],
                    pc_call[1],
                    revision,
                    pc_call[2],
                    execution_account=account,
                )
                return applied | dict(id=identity, pc_work=pc_call[0])

        def access(c: Connection) -> None:
            original = case_proof(c, self.game, identity)
            source_instruction = bool(
                instruction is not None
                and original.source_kind
                in ("enforcement_initiative", "obedience_volunteer", "compliance_virus")
                and viewer.user_id == original.chooser_controller
            )
            Access(self.store).authorize(
                c, viewer, "discipline", director_response=attest or source_instruction
            )
            self._visible(c, viewer, original)

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            case = case_proof(c, self.game, identity)
            state = load_state(c, self.store.campaign_id)
            current(c, self.game, state, case)
            if (
                state.revision != revision
                or case.effect_event
                or case.ended_event
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
                if instruction.kind != details.kind or instruction.kind not in available_for_case(
                    state, case, profiles(c, self.store.campaign_id)
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
                        source_kind=case.source_kind,
                    )
                source_approval = bool(
                    viewer.user_id == case.chooser_controller
                    and (
                        case.source_kind in ("enforcement_initiative", "compliance_virus")
                        or case.source_kind == "handler_play"
                        and viewer.user_id == state.handler
                        or case.chooser is not None
                        and case.chooser.kind == "handler"
                        and viewer.user_id == state.handler
                    )
                )
                case = case.model_copy(
                    update=dict(
                        instruction=instruction,
                        instruction_event=event,
                        handler_approval_event=event if source_approval else None,
                        handler_approver=case.chooser if source_approval else None,
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
                        "handler_approver": active_handler(state),
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
                    source_kind=case.source_kind,
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
