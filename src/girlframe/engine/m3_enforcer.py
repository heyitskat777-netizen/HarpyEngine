"""Obedience Conditioning's real trust, volunteer eligibility and Foundation custody."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_enforcer_state import Accusation, Grasp, RankFact

OBEDIENCE = "frame.enforcer.obedience-conditioning"
INITIATIVE = "frame.enforcer.enforcement-initiative"


def initiative(state: GameState, actor: ActorRef) -> bool:
    if actor.kind == "external_pilot":
        from girlframe.engine.m3_harpy_defeat import harpy

        body = harpy(state, actor)
        return bool(
            getattr(body, "alive", True)
            and not body.frame_shutdown
            and INITIATIVE in getattr(body, "plays", ())
        )
    sheet = state.sheets.get(actor.entity)
    from girlframe.engine.m3_enforcer_requisitions import held

    return bool(
        actor.kind == "pilot"
        and sheet
        and sheet.character_id == actor.incarnation
        and int(actor.entity) in state.order
        and not sheet.frame_scrapped
        and (
            sheet.frame == "THE ENFORCER"
            or held(state, actor, INITIATIVE) is not None
            or sheet.frame_runtime is not None
            and INITIATIVE in sheet.frame_runtime.acquired_rules
        )
    )


def grasp(
    original: GameState,
    actor: ActorRef,
    target: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    action: str,
    event: str,
    *,
    piloting: bool = False,
) -> GameState:
    from girlframe.engine.m3_actor_bonds import make_helpless

    state = GameState.model_validate_json(original.model_dump_json())
    holder = resolve(state, actor, bindings, require_current_profile=False)
    from girlframe.engine.m3_role_punishments import view

    target_view = view(state, target, bindings)
    if not initiative(state, actor) or not holder.frame_instance or actor == target:
        raise ValueError("Use an actual current Enforcer taking hold of another actual role")
    if any(x.action == action or x.id == event for x in state.enforcer_grasps):
        raise ValueError("This actual known grasp result was already applied")
    if any(x.held and x.target == target for x in state.enforcer_grasps):
        raise ValueError("Resolve the existing actual grip on that role first")
    state.enforcer_grasps.append(
        Grasp(
            id=event,
            actor=actor,
            target=target,
            frame_instance=holder.frame_instance,
            action=action,
            source_event=event,
            contact="frame" if piloting else "body",
        )
    )
    girl = target.kind == "pilot"
    if target.kind == "external_pilot" and state.world:
        girl = any(x.id == target.entity and x.kind != "harpy" for x in state.world.pilots)
    if (
        girl
        or target.kind == "npc"
        and target_view.rules != "director"
        or target.kind == "handler"
        and target_view.rules == "handler_girl"
    ):
        from girlframe.engine.m3_items import body_ref

        state = make_helpless(state, body_ref(state, target), actor, event)
    # Harpies/Gorgons remain unable to escape this actual grip, without being silently
    # reclassified as Girls or receiving the source's different Helplessness benefit.
    return state


def release_grasp(
    original: GameState, identity: str, actor: ActorRef, event: str, account: str
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    saved = next((x for x in state.enforcer_grasps if x.id == identity), None)
    if saved is None or not saved.held or saved.actor != actor or not event or not account.strip():
        raise ValueError("Only the original holder may voluntarily release her actual grip")
    ended = Grasp.model_validate_json(
        saved.model_copy(
            update=dict(held=False, release_event=event, release_account=account)
        ).model_dump_json()
    )
    state.enforcer_grasps = [ended if x.id == identity else x for x in state.enforcer_grasps]
    # Releasing a grip does not manufacture the separate moment alone/help that removes
    # sourceful Helplessness. Actual recovery uses the existing original-role port.
    return state


def end_grasps(original: GameState, actor: ActorRef, event: str) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    for saved in tuple(state.enforcer_grasps):
        if saved.held and actor in (saved.actor, saved.target):
            updated = saved.model_copy(
                update=dict(
                    held=False,
                    release_event=event,
                    release_account="The original career ended; nobody moved or supplied consent.",
                )
            )
            state.enforcer_grasps = [
                updated if x.id == saved.id else x for x in state.enforcer_grasps
            ]
    return state


def conditioning(state: GameState, actor: ActorRef) -> bool:
    sheet = state.sheets.get(actor.entity)
    from girlframe.engine.m3_enforcer_requisitions import held

    return bool(
        actor.kind == "pilot"
        and sheet
        and sheet.character_id == actor.incarnation
        and int(actor.entity) in state.order
        and not sheet.frame_scrapped
        and (
            sheet.frame == "THE ENFORCER"
            or held(state, actor, OBEDIENCE) is not None
            or sheet.frame_runtime is not None
            and OBEDIENCE in sheet.frame_runtime.acquired_rules
        )
        and (len(state.order) < 2 or state.order[-1] != int(actor.entity))
    )


def detention(state: GameState, subject: ActorRef) -> Accusation | None:
    found = [x for x in state.enforcer_accusations if x.subject == subject and x.detained]
    if len(found) > 1:
        raise ValueError("Recover the actual NPC's inconsistent Foundation custody sources")
    return found[0] if found else None


def record_rank(
    original: GameState,
    subject: ActorRef,
    relative_to: ActorRef,
    superior_officer: bool,
    handler: ActorRef,
    identity: str,
    event: str,
    account: str,
    bindings: tuple[ProfileBinding, ...],
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    if handler.kind != "handler" or str(state.handler) != handler.entity:
        raise ValueError(
            "Only the actual current Handler adjudicates the factual superior-officer rank"
        )
    resolve(state, subject, bindings, require_current_profile=False)
    resolve(state, relative_to, bindings, require_current_profile=False)
    if any(x.id == identity or x.source_event == event for x in state.enforcer_ranks):
        raise ValueError("Use one new actual rank declaration source")
    state.enforcer_ranks.append(
        RankFact(
            id=identity,
            subject=subject,
            relative_to=relative_to,
            superior_officer=superior_officer,
            handler=handler,
            source_event=event,
            account=account,
        )
    )
    return state


def accuse(
    original: GameState,
    actor: ActorRef,
    subject: ActorRef,
    expected: str,
    bindings: tuple[ProfileBinding, ...],
    rank_id: str,
    identity: str,
    event: str,
    account: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    actual = resolve(state, actor, bindings, require_current_profile=False)
    target = resolve(state, subject, bindings, require_current_profile=False)
    if not conditioning(state, actor) or actual.source_sha256 != expected:
        raise ValueError(
            "Only the actual non-Dog Enforcer's current conditioning authorizes this accusation"
        )
    ranks = [x for x in state.enforcer_ranks if x.subject == subject and x.relative_to == actor]
    rank = ranks[-1] if ranks else None
    if rank is None or rank.id != rank_id or rank.superior_officer:
        raise ValueError(
            "An actual current factual rank declaration must establish this NPC is not superior"
        )
    if subject.kind != "npc" or target.custody or detention(state, subject):
        raise ValueError("Use an actual free NPC, not an invented prisoner extraction")
    if any(x.id == identity or x.source_event == event for x in state.enforcer_accusations):
        raise ValueError("This actual accusation has already been recorded")
    if state.world is None or actual.frame_instance is None:
        raise ValueError("Recover the actual original Frame and NPC source")
    npc = next(x for x in state.world.npcs if x.id == subject.entity)
    state.enforcer_accusations.append(
        Accusation(
            id=identity,
            actor=actor,
            frame_instance=actual.frame_instance,
            subject=subject,
            rank_fact=rank.id,
            source_event=event,
            account=account,
            original_cell=npc.cell,
        )
    )
    return state


def release(
    original: GameState, identity: str, handler: ActorRef, event: str, evidence: str
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    if handler.kind != "handler" or handler.entity != str(state.handler):
        raise ValueError("The current Handler must record actual innocence evidence")
    case = next((x for x in state.enforcer_accusations if x.id == identity), None)
    if case is None or not case.detained or not event or not evidence.strip():
        raise ValueError("Prove this actual detained NPC innocent before release")
    updated = Accusation.model_validate_json(
        case.model_copy(
            update=dict(
                detained=False,
                release_event=event,
                released_by=handler,
                innocence_evidence=evidence,
            )
        ).model_dump_json()
    )
    state.enforcer_accusations = [
        updated if x.id == identity else x for x in state.enforcer_accusations
    ]
    # The past map position is historical. Release does not teleport the NPC back there.
    state.facts.append(
        dict(
            kind="enforcer_release_position_unknown",
            actor=case.subject.model_dump_json(),
            accusation=case.id,
            source_event=event,
        )
    )
    return state


def record_released_position(
    original: GameState,
    identity: str,
    cell: tuple[int, int],
    handler: ActorRef,
    event: str,
    account: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    case = next((x for x in state.enforcer_accusations if x.id == identity), None)
    if (
        case is None
        or case.detained
        or case.position_event is not None
        or not event
        or not account.strip()
        or state.world is None
        or not state.world.board.contains(cell)
        or handler.kind != "handler"
        or handler.entity != str(state.handler)
    ):
        raise ValueError(
            "Record one actual source-proved released NPC location on the canonical map"
        )
    if (
        detention(state, case.subject) is not None
        or next(x for x in reversed(state.enforcer_accusations) if x.subject == case.subject).id
        != identity
    ):
        raise ValueError("Use the latest actual release, never an earlier detention episode")
    npc = next((x for x in state.world.npcs if x.id == case.subject.entity and x.alive), None)
    if npc is None or npc.captive_of is not None:
        raise ValueError(
            "Recover the actual original released NPC body without inventing extraction"
        )
    updated = case.model_copy(
        update=dict(release_cell=cell, position_event=event, position_account=account)
    )
    state.enforcer_accusations = [
        updated if x.id == identity else x for x in state.enforcer_accusations
    ]
    state.world = state.world.model_copy(
        update={
            "npcs": tuple(
                x.model_copy(update={"cell": cell}) if x.id == npc.id else x
                for x in state.world.npcs
            )
        }
    )
    state.facts.append(
        dict(
            kind="enforcer_release_position_recorded",
            actor=case.subject.model_dump_json(),
            accusation=case.id,
            source_event=event,
        )
    )
    return state


def end_lost_frame_grasps(original: GameState, event: str) -> GameState:
    """Only actual Frame-contact grips end on sourceful loss of their original vessel."""
    state = GameState.model_validate_json(original.model_dump_json())
    for grip in tuple(state.enforcer_grasps):
        if not grip.held or grip.contact != "frame":
            continue
        if grip.actor.kind == "external_pilot":
            from girlframe.engine.m3_harpy_defeat import harpy

            body = harpy(state, grip.actor)
            lost = (
                body.frame_shutdown
                or not getattr(body, "alive", True)
                or body.frame_instance != grip.frame_instance
            )
        else:
            sheet = state.sheets.get(grip.actor.entity)
            if sheet is None or sheet.character_id != grip.actor.incarnation:
                continue
            current = sheet.frame_runtime.id if sheet.frame_runtime else None
            lost = sheet.frame_scrapped or current is not None and current != grip.frame_instance
        if lost:
            state.enforcer_grasps = [
                x.model_copy(
                    update=dict(
                        held=False,
                        release_event=event,
                        release_account=(
                            "The actual original Frame holding this grip was lost; "
                            "nobody moved or recovered Helplessness."
                        ),
                    )
                )
                if x.id == grip.id
                else x
                for x in state.enforcer_grasps
            ]
    return state
