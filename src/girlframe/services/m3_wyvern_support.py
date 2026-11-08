"""Actual physical and resource adapters for the finite Wyvern source workflows."""

import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.engine import m3_wyvern as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import frame_position, resolve
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_leviathan_obsession import require_unlocked
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def context(
    game: "GameService",
    c: Connection,
    state: GameState,
    actor: ActorRef,
    scene: SceneCast,
    play: str,
    target: ActorRef | None = None,
) -> dict[str, Any]:
    bound = profiles(c, game.store.campaign_id)
    own = resolve(state, actor, bound, require_current_profile=False)
    original = rules.frame(state, actor)
    cell = frame_position(state, actor, original)
    if (
        own.offstage_source
        or cell is None
        or own.vessel_id is None
        or not any(x.actor == actor and x.controller == own.controller for x in scene.roles)
    ):
        raise WorkflowError("Establish the actual original Wyvern body, Frame and source scene")
    if play == "wyvern_explore" and own.cell != cell:
        raise WorkflowError("Reach the actual original Frame before entering its interior")
    if play != "wyvern_explore" and (not own.piloting or own.occupied_frame_instance != original):
        raise WorkflowError("Use the actual original Wyvern while truly piloting it")
    other = None
    if target is not None:
        other = resolve(state, target, bound, require_current_profile=False)
        if other.cell != cell or not any(x.actor == target for x in scene.roles):
            raise WorkflowError("Use the actual present original target, not its controller")
    return dict(
        actor=actor.model_dump(mode="json"),
        frame=original,
        cell=list(cell),
        vessel=own.vessel_id,
        position=own.position_sha256,
        piloting=own.piloting,
        target=target.model_dump(mode="json") if target else None,
        target_vessel=other.vessel_id if other else None,
    )


def identity_options(
    game: "GameService", c: Connection, state: GameState, actor: ActorRef, *, mode: str
) -> list[tuple[str, str]]:
    sheet = state.sheets[actor.entity]
    if sheet.character_id != actor.incarnation:
        raise WorkflowError("Preserve the actual original Girl's Identity resources")
    if mode == "unmark":
        from girlframe.engine.m3_clone_am import additional_identities
        from girlframe.engine.m3_oldgen import marked_maxims
        from girlframe.services.m3_clone_am import prove_additional

        extra = additional_identities(state, int(actor.entity))
        if extra:
            prove_additional(game, c, state, int(actor.entity))
        return [
            (x.id, x.name)
            for x in (*sheet.identities, *extra)
            if x.marked and x.id not in sheet.sedation_locked
        ] + list(marked_maxims(state, int(actor.entity)))
    if mode != "erase":
        raise WorkflowError("Choose actual erase or unmark effects")
    result = []
    for item in sheet.identities:
        if item.protected or item.paired or item.am_limiter or item.id in sheet.sedation_locked:
            continue
        try:
            require_unlocked(sheet.identities, (item.id,))
        except ValueError:
            continue
        result.append((item.id, item.name))
    return result


def identity_requirements(
    game: "GameService", c: Connection, state: GameState, actor: ActorRef
) -> dict[str, Any]:
    from girlframe.engine.m3_trainee import RULE
    from girlframe.services.m2_choices import ChoiceEngine
    from girlframe.services.m3_trainee import _relation

    sheet = state.sheets[actor.entity]
    if not has_rule(sheet, RULE, "NEWGIRL"):
        return dict(mentor_tags=[])
    mentor, relation = _relation(game, c, state, actor)
    tags = [x for x in sheet.tags if x.giver_actor == mentor and x.gm_setter_appointment is None]
    for tag in tags:
        ChoiceEngine(game).prove_tag_setter(c, state, int(actor.entity), tag)
    return dict(
        mentor_tags=[dict(id=x.id, label=x.label) for x in tags],
        mentor=mentor.model_dump(mode="json"),
        relation=relation,
    )


def identity_change(
    game: "GameService",
    c: Connection,
    state: GameState,
    actor: ActorRef,
    ids: tuple[str, ...],
    event: str,
    action: str,
    *,
    mode: str,
    mentor_tags: dict[str, str] | None = None,
) -> tuple[GameState, tuple[str, ...]]:
    from girlframe.engine.m3_identity_slots import bind
    from girlframe.engine.m3_trainee import RULE, erase
    from girlframe.services.m2_choices import ChoiceEngine

    if len(set(ids)) != len(ids) or any(
        x not in dict(identity_options(game, c, state, actor, mode=mode)) for x in ids
    ):
        raise WorkflowError("Choose actual distinct legal Identities from the original source")
    changed = GameState.model_validate_json(state.model_dump_json())
    sheet = changed.sheets[actor.entity]
    if mode == "unmark":
        ChoiceEngine(game).unmark(c, changed, sheet, ids, len(ids))
        sheet.revision += 1
    else:
        assignments = mentor_tags or {}
        if set(assignments) - set(ids):
            raise WorkflowError("Assign Mentor Tags only to actual erased Identities")
        for identity in ids:
            if has_rule(sheet, RULE, "NEWGIRL"):
                options = identity_requirements(game, c, changed, actor)
                available = {x["id"] for x in options["mentor_tags"]}
                selected = assignments.get(identity)
                if (
                    bool(available) != bool(selected)
                    or selected is not None
                    and selected not in available
                ):
                    raise WorkflowError(
                        "Choose a genuine original Mentor Tag for each applicable erasure"
                    )
                real_tags = tuple(x for x in sheet.tags if x.id in available)
                sheet, _, _, _ = erase(sheet, identity, selected, real_tags, event + ":" + identity)
                changed.sheets[actor.entity] = sheet
            else:
                require_unlocked(sheet.identities, (identity,))
                sheet.identities = [x for x in sheet.identities if x.id != identity]
                sheet.revision += 1
        changed.sheets[actor.entity] = bind(sheet)
    changed.facts.append(
        dict(
            kind="wyvern_identity_change",
            event=event,
            action=action,
            body=json.dumps(
                dict(
                    actor=actor.model_dump(mode="json"),
                    ids=ids,
                    mode=mode,
                    mentor_tags=mentor_tags or {},
                )
            ),
        )
    )
    return changed, ()


def excursion(
    game: "GameService",
    c: Connection,
    state: GameState,
    session: rules.Session,
    event: str,
    *,
    operation: str,
    actors: tuple[ActorRef, ...],
    elapsed_fact: str | None = None,
    child_action: str | None = None,
) -> tuple[GameState, tuple[str, ...]]:
    from girlframe.engine.m3_physical_state import Placement

    changed = GameState.model_validate_json(state.model_dump_json())
    cell = frame_position(changed, session.actor, session.frame)
    if cell is None or operation not in ("enter", "return"):
        raise WorkflowError("Use the actual original Frame interior and return source")
    party = next((x for x in rules.records(changed, rules.Party) if x.id == session.party), None)
    if party is None or party.bound_action != session.id:
        raise WorkflowError("Recover actual source companions and performed exploration")
    bound = profiles(c, game.store.campaign_id)
    for actor in actors:
        identity = rules.identity("interior", session.id, actor.token)
        guest = next(
            (x for x in rules.records(changed, rules.InteriorGuest) if x.id == identity), None
        )
        if operation == "enter":
            if guest is not None:
                continue
            actual = resolve(changed, actor, bound, require_current_profile=False)
            accepted = party.attendance_events.get(actor.token)
            if actor != session.actor and (actor not in party.present or not accepted):
                raise WorkflowError(
                    "Only genuinely consenting actual companions enter this excursion"
                )
            if actual.cell != cell or actual.offstage_source:
                raise WorkflowError(
                    "The actual companion must physically reach this original Frame"
                )
            pose = next((x for x in changed.placements if x.actor == actor), None)
            origin = pose.model_dump_json() if pose else actual.model_dump_json()
            rules.put(
                changed,
                rules.InteriorGuest(
                    id=identity,
                    session=session.id,
                    actor=actor,
                    carrier=session.actor,
                    frame=session.frame,
                    controller=actual.controller,
                    accepted_event=accepted or party.event,
                    entered_event=event,
                    original_pose=origin,
                ),
            )
            if pose is not None:
                if (
                    pose.custody is not None
                    or pose.incapacitated
                    or pose.subsumed
                    or not pose.vitals_active
                ):
                    raise WorkflowError(
                        "Retain actual custody and body conditions before exploring"
                    )
                other = actor != session.actor
                moved = pose.model_copy(
                    update=dict(
                        girl_cell=cell,
                        mode="inside_frame",
                        occupied_frame_owner=session.actor if other else None,
                        occupied_frame_instance=session.frame if other else None,
                        source_event=event,
                        account="Actual source-owned exploration of the original Frame",
                    )
                )
                moved = Placement.model_validate_json(moved.model_dump_json())
                changed.placements = [moved if x.actor == actor else x for x in changed.placements]
        else:
            if guest is None or guest.ended_event:
                continue
            if elapsed_fact is None and child_action is None:
                danger = next(
                    (x for x in rules.records(changed, rules.Danger) if x.session == session.id),
                    None,
                )
                if danger is not None:
                    raise WorkflowError(
                        "Resolve actual elapsed time or genuine escape before returning"
                    )
            pose = next((x for x in changed.placements if x.actor == actor), None)
            if pose is not None:
                origin_pose = Placement.model_validate_json(guest.original_pose)
                # Preserve parked hardware; returning from an interior is not a Frame teleport.
                assigned_cell = frame_position(changed, actor, pose.frame_instance)
                occupied_owner = origin_pose.occupied_frame_owner or actor
                occupied_instance = (
                    origin_pose.occupied_frame_instance or origin_pose.frame_instance
                )
                old_cockpit_here = (
                    frame_position(changed, occupied_owner, occupied_instance) == cell
                )
                restore_inside = origin_pose.mode != "outside_frame" and old_cockpit_here
                destination = pose.model_copy(
                    update=dict(
                        girl_cell=cell,
                        frame_cell=assigned_cell or pose.frame_cell,
                        mode=origin_pose.mode if restore_inside else "outside_frame",
                        occupied_frame_owner=origin_pose.occupied_frame_owner
                        if restore_inside
                        else None,
                        occupied_frame_instance=origin_pose.occupied_frame_instance
                        if restore_inside
                        else None,
                        source_event=event,
                        account="Actual source return from Frame exploration",
                    )
                )
                destination = Placement.model_validate_json(destination.model_dump_json())
                changed.placements = [
                    destination if x.actor == actor else x for x in changed.placements
                ]
            elif actor.kind == "npc" and changed.world is not None:
                changed.world = changed.world.model_copy(
                    update=dict(
                        npcs=tuple(
                            x.model_copy(update=dict(cell=cell)) if x.id == actor.entity else x
                            for x in changed.world.npcs
                        )
                    )
                )
            elif actor.kind == "handler":
                changed.facts.append(
                    dict(
                        kind="wyvern_explorer_return",
                        actor=actor.model_dump_json(),
                        cell=json.dumps(cell),
                        event=event,
                        account="Actual source return from Frame interior",
                    )
                )
            elif actor.kind == "external_pilot":
                actual_pose = next((x for x in changed.external_poses if x.actor == actor), None)
                if actual_pose is None:
                    raise WorkflowError(
                        "Recover the real external body before ending its interior occupancy"
                    )
                frame_here = frame_position(changed, actor, actual_pose.frame) == cell
                update = dict(
                    girl_cell=cell,
                    position_event=event,
                    mode=actual_pose.mode if frame_here else "outside_frame",
                    account="Actual source return from Frame interior",
                )
                if frame_here and actual_pose.mode != "outside_frame":
                    update["frame_cell"] = cell
                changed.external_poses = [
                    actual_pose.model_copy(update=update) if x.actor == actor else x
                    for x in changed.external_poses
                ]
            else:
                raise WorkflowError(
                    "This actual body needs its source-specific interior return adapter"
                )
            rules.put(changed, guest.model_copy(update=dict(ended_event=event)))
    changed.facts.append(
        dict(
            kind="wyvern_excursion_transition",
            session=session.id,
            event=event,
            body=json.dumps(
                dict(
                    operation=operation,
                    actors=[x.model_dump(mode="json") for x in actors],
                    elapsed=elapsed_fact,
                    child=child_action,
                )
            ),
        )
    )
    return changed, ()


def carry(
    game: "GameService",
    c: Connection,
    state: GameState,
    cargo: rules.Cargo,
    event: str,
    *,
    unload: bool = False,
) -> tuple[GameState, tuple[str, ...]]:
    changed = GameState.model_validate_json(state.model_dump_json())
    cell = frame_position(changed, cargo.actor, cargo.frame)
    if cell is None or cargo.actor == cargo.owner or cargo.accepted_event is None:
        raise WorkflowError("Use the actual original consenting Frame cargo and carrier")
    own = resolve(
        changed, cargo.owner, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if own.frame_instance != cargo.guest_frame:
        raise WorkflowError("Preserve the actual guest Frame rather than a replacement")
    if not unload:
        if frame_position(changed, cargo.owner, cargo.guest_frame) != cell:
            raise WorkflowError("Bring the actual guest Frame to the carrier before loading")
        if rules.cargo(changed, cargo.owner, cargo.guest_frame):
            raise WorkflowError("This actual Frame is already carried")
        container = (cargo.actor, cargo.frame)
        seen = {(cargo.owner, cargo.guest_frame)}
        while container not in seen:
            seen.add(container)
            parent = rules.cargo(changed, *container)
            if parent is None:
                break
            container = (parent.actor, parent.frame)
        else:
            raise WorkflowError("Actual Frame containment cannot form a cycle")
        rules.put(changed, cargo.model_copy(update=dict(boarded_event=event)))
    else:
        existing = rules.cargo(changed, cargo.owner, cargo.guest_frame)
        if existing is None or existing.id != cargo.id:
            raise WorkflowError("Unload only this actual still-carried Frame")
        pose = next((x for x in changed.placements if x.actor == cargo.owner), None)
        if pose is None:
            raise WorkflowError("Recover the real original guest Frame placement before unloading")
        update = dict(
            frame_cell=cell, source_event=event, account="Actual Wyvern Frame cargo unloaded"
        )
        if pose.mode != "outside_frame" and pose.occupied_frame_owner is None:
            update["girl_cell"] = cell
        changed.placements = [
            pose.model_copy(update=update) if x.actor == cargo.owner else x
            for x in changed.placements
        ]
        rules.put(changed, existing.model_copy(update=dict(ended_event=event)))
    return changed, ()


def spawn_wraith(
    game: "GameService", c: Connection, state: GameState, wraith: rules.Wraith, event: str
) -> tuple[GameState, ActorRef]:
    from girlframe.engine.m3_world_state import Npc

    changed = GameState.model_validate_json(state.model_dump_json())
    cell = frame_position(changed, wraith.actor, wraith.frame)
    if (
        changed.world is None
        or cell is None
        or wraith.profile != "frame_bound_npc"
        or not wraith.rules_answer
    ):
        raise WorkflowError(
            "Record actual Handler rules and original Frame before unleashing its mind"
        )
    controller = wraith.controller or wraith.handler_controller
    if controller not in wraith.table:
        raise WorkflowError("Only actual source-table humans may play this mind")
    identity = rules.identity("mind", wraith.frame, wraith.slot)
    actual = ActorRef(kind="npc", entity=identity)
    previous = next((x for x in changed.world.npcs if x.id == identity), None)
    if previous is not None and (
        previous.source_kind != "wyvern_wraith" or previous.name != wraith.name
    ):
        raise WorkflowError(
            "Preserve this original named mind rather than replacing another person"
        )
    npc = Npc(
        id=identity,
        name=wraith.name,
        cell=cell,
        jobs=(),
        source_kind="wyvern_wraith",
        detail=wraith.rules_answer,
        controller=controller,
        revealed=True,
    )
    changed.world = changed.world.model_copy(
        update=dict(npcs=tuple(x for x in changed.world.npcs if x.id != identity) + (npc,))
    )
    return changed, actual


def voice_control(
    game: "GameService",
    c: Connection,
    state: GameState,
    wraith: rules.Wraith,
    controller: int,
    event: str,
) -> tuple[GameState, ActorRef]:
    from girlframe.engine.m3_actor_state import CastRole

    if wraith.persona is None or controller not in wraith.table or not wraith.active:
        raise WorkflowError("Use only this actual unleashed mind and original table human")
    changed = GameState.model_validate_json(state.model_dump_json())
    if changed.world is None:
        raise WorkflowError("Recover the actual source mind roster")
    source = rules.session(changed, wraith.session)
    lock = game.lock(c, source.cast.channel)
    if lock and lock["state"] != "released":
        raise WorkflowError("Finish and restore the actual scene Play before changing its voice")
    changed.world = changed.world.model_copy(
        update=dict(
            npcs=tuple(
                x.model_copy(update=dict(controller=controller))
                if x.id == wraith.persona.entity
                else x
                for x in changed.world.npcs
            )
        )
    )
    cast = next((x for x in changed.scene_casts if x.id == source.cast.id and x.open), None)
    if cast is not None:
        role = CastRole(actor=wraith.persona, controller=controller, source_event=event)
        updated = cast.model_copy(
            update=dict(
                roles=tuple(x for x in cast.roles if x.actor != wraith.persona) + (role,),
                revision=cast.revision + 1,
            )
        )
        changed.scene_casts = [updated if x.id == cast.id else x for x in changed.scene_casts]
    return changed, wraith.persona


def end_wraith(
    game: "GameService", c: Connection, state: GameState, wraith: rules.Wraith, event: str
) -> tuple[GameState, tuple[str, ...]]:
    changed = GameState.model_validate_json(state.model_dump_json())
    if wraith.persona is not None:
        changed.scene_casts = [
            x.model_copy(
                update=dict(
                    roles=tuple(r for r in x.roles if r.actor != wraith.persona),
                    revision=x.revision + 1,
                )
            )
            if any(r.actor == wraith.persona for r in x.roles)
            else x
            for x in changed.scene_casts
        ]
    return changed, ()


def exploration_party(
    game: "GameService",
    c: Connection,
    state: GameState,
    actor: ActorRef,
    scene: SceneCast,
    companions: tuple[ActorRef, ...],
) -> dict[str, Any]:
    """Validate real bodies before the original exploration consumes dice or Heat."""
    own = context(game, c, state, actor, scene, "wyvern_explore")
    bound = profiles(c, game.store.campaign_id)
    if len(set(companions)) != len(companions) or actor in companions:
        raise WorkflowError("Choose distinct actual companions, not the explorer again")
    result = {}
    for other in companions:
        body = resolve(state, other, bound, require_current_profile=False)
        pose = next((x for x in state.placements if x.actor == other), None)
        if (
            body.cell is None
            or list(body.cell) != own["cell"]
            or not body.alive
            or body.offstage_source
            or body.vessel_id is None
            or not any(x.actor == other and x.controller == body.controller for x in scene.roles)
            or pose is not None
            and (
                pose.custody is not None
                or pose.incapacitated
                or pose.subsumed
                or not pose.vitals_active
            )
        ):
            raise WorkflowError("Actual consenting companions must be present and able to enter")
        result[other.token] = dict(vessel=body.vessel_id, position=body.position_sha256)
    return result


def renovate(
    game: "GameService",
    c: Connection,
    state: GameState,
    value: rules.Renovation,
    event: str,
) -> tuple[GameState, tuple[str, ...]]:
    from girlframe.engine.m2 import AssetState
    from girlframe.engine.m3_core import install
    from girlframe.engine.m3_janus_storage import effective_assets
    from girlframe.services.m3_items import new_void_families

    if value.asset or value.completed_event or value.kind == "past" and not value.answered_event:
        raise WorkflowError("Finish the real Handler answer before installing this found object")
    changed = GameState.model_validate_json(state.model_dump_json())
    sheet = changed.sheets[value.actor.entity]
    if sheet.character_id != value.actor.incarnation:
        raise WorkflowError("Preserve the original Girl receiving this found Asset")
    asset = AssetState(
        id=rules.identity("renovated-asset", value.id),
        family="girl",
        name=value.name,
        description=value.description,
        void=value.kind == "void",
        classification_event=event,
    )
    effective = frozenset(x.id for x in effective_assets(state, value.actor) if x.void)
    installed = install(sheet, asset, replace=value.replace, effective_void=effective, state=state)
    changed.sheets[value.actor.entity] = installed.sheet
    work = (
        (rules.identity("renovation-void", value.id),)
        if value.actor in new_void_families(state, changed)
        else ()
    )
    rules.put(changed, value.model_copy(update=dict(asset=asset.id, work=work)))
    changed.facts.append(
        dict(
            kind="wyvern_renovation",
            id=value.id,
            event=event,
            actor=value.actor.model_dump_json(),
            asset=asset.id,
        )
    )
    return changed, work


def prove_renovation_void(
    game: "GameService",
    c: Connection,
    first: dict[str, Any],
    body: dict[str, Any],
    actor: ActorRef,
) -> None:
    from girlframe.engine.m3_requisition_state import FrameRuleReceipt
    from girlframe.services.m3_handler_advancements import _history
    from girlframe.services.m3_wyvern import prove_acquisition

    saved = _history(c, game, first["event_id"])
    value = next(
        (x for x in rules.records(saved, rules.Renovation) if x.id == body.get("renovation")), None
    )
    if (
        value is None
        or value.actor != actor
        or value.kind != "void"
        or not value.asset
        or first["id"] not in value.work
        or value.event != first["event_id"]
        or body.get("source_action") is not None
        or body.get("details") != dict(family="girl")
    ):
        raise WorkflowError("Recover the genuine paid Renovation Void source")
    receipt = next(
        (
            x
            for x in saved.requisitions
            if isinstance(x, FrameRuleReceipt) and x.id == value.receipt
        ),
        None,
    )
    if receipt is None or receipt.rule_id != rules.RENOVATE:
        raise WorkflowError("Recover the actual Renovation acquisition")
    prove_acquisition(game, c, saved, receipt)
    asset = next((x for x in saved.sheets[actor.entity].assets if x.id == value.asset), None)
    if asset is None or not asset.void or asset.classification_event != first["event_id"]:
        raise WorkflowError("Preserve the actual installed Void Girl Asset")


def synchronize(game: "GameService", c: Connection, event: str) -> None:
    from uuid import uuid4

    import sqlalchemy as sa

    from girlframe.database import tables as t
    from girlframe.services.m2_state import load_state
    from girlframe.services.m3_handler_advancements import _history
    from girlframe.services.m3_void import complete, prepare_threshold
    from girlframe.services.m3_work import related

    saved = _history(c, game, event)
    table = t.m3["m3_required_work"]
    from girlframe.services.m3_handler_plays import request_from_play

    for source in rules.records(saved, rules.Session):
        if source.play != "wyvern_protector" or source.total >= 8 or source.handler_play:
            continue
        action = game.action(c, source.id)
        row = next((x for x in game.pending(c, source.id) if x["kind"] == "wyvern_handler"), None)
        if row is None or json.loads(row["body_json"]).get("handler_grant"):
            continue
        state = load_state(c, game.store.campaign_id)
        grant_event = str(uuid4())
        assert source.target is not None
        changed_state, grant = request_from_play(
            game,
            c,
            state,
            action,
            row["id"],
            "wyvern.protector.low",
            grant_event,
            targets=(source.target,),
        )
        rules.put(
            changed_state,
            rules.session(changed_state, source.id).model_copy(update=dict(handler_play=grant)),
        )
        game.event(
            c,
            int(source.actor.entity),
            str(uuid4()),
            "m3.wyvern_handler_required",
            changed_state,
            event_id=grant_event,
            action_id=source.id,
        )
    for value in rules.records(saved, rules.Renovation):
        if value.event != event or not value.work:
            continue
        identity = value.work[0]
        if c.scalar(
            sa.select(table.c.id)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == identity)
            .limit(1)
        ):
            continue
        related(
            c,
            game.store,
            dict(campaign_id=game.store.campaign_id, campaign_context=True),
            identity,
            int(value.actor.entity),
            int(value.actor.entity),
            "void_threshold",
            dict(
                reason="wyvern_renovation",
                renovation=value.id,
                owner=value.actor.model_dump(mode="json"),
                character=value.actor.incarnation,
                source_action=None,
                source_pdf=19,
                immediate=True,
                details=dict(family="girl"),
            ),
            event,
        )
        changed, threshold = prepare_threshold(c, game, identity)
        opened = game.event(
            c,
            int(value.actor.entity),
            str(uuid4()),
            "m3.wyvern_renovation_void_opened",
            changed,
            work_id=identity,
            source_event=event,
        )
        if threshold.stage in ("prevented", "converted", "escaped"):
            complete(c, game, threshold, opened, None, "wyvern-renovation:" + identity)
    state = load_state(c, game.store.campaign_id)
    any_completed = False
    for value in rules.records(state, rules.Renovation):
        if not value.work or value.completed_event:
            continue
        pending = []
        for identity in value.work:
            status = c.scalar(
                sa.select(table.c.state)
                .where(table.c.campaign_id == game.store.campaign_id, table.c.id == identity)
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            pending.append(status != "resolved")
        if not any(pending):
            rules.put(state, value.model_copy(update=dict(completed_event=event)))
            any_completed = True
    if any_completed:
        human = c.scalar(
            sa.select(t.events.c.actor_id).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        if human is None:
            raise WorkflowError("Preserve the real source human completing Renovation")
        game.event(
            c, int(human), str(uuid4()), "m3.wyvern_renovation_completed", state, source_event=event
        )


def handler_play(
    game: "GameService",
    c: Connection,
    state: GameState,
    source: rules.Session,
    event: str,
) -> tuple[GameState, tuple[str, ...]]:
    action = game.action(c, source.id)
    if source.play != "wyvern_protector" or source.target is None:
        raise WorkflowError("Use only the original failed Protector's actual target")
    if not any(x["kind"] == "wyvern_handler" for x in game.pending(c, source.id)):
        game.request(c, action, source.handler_controller, "wyvern_handler")
    return state, ()


def prove_handler_grant(game: "GameService", c: Connection, state: GameState, grant: Any) -> None:
    from girlframe.services.m3_wyvern import prove_source

    if grant.source_action is None or grant.source_choice is None:
        raise WorkflowError("Recover the actual original Protector source")
    source = prove_source(game, c, state, grant.source_action)
    if (
        source.play != "wyvern_protector"
        or source.total >= 8
        or source.target is None
        or grant.targets != (source.target,)
        or source.handler_controller != grant.chooser_controller
        or source.handler_play != grant.id
    ):
        raise WorkflowError("Preserve the failed Protector's actual Handler and target")


def complete_handler_grant(game: "GameService", c: Connection, grant: Any, event: str) -> None:
    import sqlalchemy as sa

    from girlframe.database import tables as t
    from girlframe.services.m2_state import load_state
    from girlframe.services.m3_wyvern import synchronize as sync_source

    state = load_state(c, game.store.campaign_id)
    prove_handler_grant(game, c, state, grant)
    choices = t.m2["m2_choices"]
    row = (
        c.execute(
            sa.select(choices).where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.id == grant.source_choice,
                choices.c.action_id == grant.source_action,
                choices.c.kind == "wyvern_handler",
                choices.c.actor_id == str(grant.chooser_controller),
            )
        )
        .mappings()
        .first()
    )
    if row is None or json.loads(row["body_json"]).get("handler_grant") != grant.id:
        raise WorkflowError("Recover the actual original required Handler choice")
    if row["state"] not in ("pending", "submitted"):
        return
    c.execute(
        choices.update()
        .where(choices.c.campaign_id == game.store.campaign_id, choices.c.id == row["id"])
        .values(
            state="completed_by_work",
            revision=row["revision"] + 1,
            body_json=json.dumps(
                json.loads(row["body_json"]) | dict(handler_play_event=grant.completed_event)
            ),
        )
    )
    sync_source(game, c, game.action(c, grant.source_action), event)


def roused_effect(
    game: "GameService", c: Connection, state: GameState, use: rules.RousedUse, event: str
) -> tuple[GameState, tuple[str, ...]]:
    from girlframe.services.m3_wyvern_combat import roused_effect as apply_effect

    return apply_effect(game, c, state, use, event)


def shield(
    game: "GameService", c: Connection, state: GameState, value: rules.Shield, event: str
) -> tuple[GameState, tuple[str, ...]]:
    from girlframe.services.m3_wyvern_combat import shield as apply_shield

    return apply_shield(game, c, state, value, event)


def wraith_modifiers(
    game: "GameService", c: Connection, state: GameState, actor: ActorRef, play: str
) -> list[dict[str, Any]]:
    from girlframe.services.m3_wyvern import prove_source, require_rule

    if not rules.wraith_bonus(state, actor, play):
        return []
    require_rule(game, c, state, actor, rules.WRAITH)
    body = resolve(state, actor, profiles(c, game.store.campaign_id), require_current_profile=False)
    original = rules.frame(state, actor)
    if not body.piloting or body.occupied_frame_instance != original:
        return []
    for source in rules.records(state, rules.Wraith):
        if (
            source.actor == actor
            and source.frame == original
            and source.active
            and source.persona is not None
            and source.profile == "frame_bound_npc"
            and play in rules.BONUSES[source.slot]
        ):
            prove_source(game, c, state, source.session)
            if source.rules_event is None or not source.rules_answer:
                raise WorkflowError("Recover the Handler's actual Frame-bound mind profile")
            return [dict(source="wyvern_wraith_am", amount=1)]
    return []


def require_play_target(
    game: "GameService", c: Connection, state: GameState, prepared: Any
) -> None:
    """Known Plays against a target, distinct from actual mutually owned support/intimacy."""
    from girlframe.engine.m3_actor_bonds import current_ref
    from girlframe.services.m3_wyvern_combat import require_targetable

    if prepared.play not in (
        "engage",
        "all_out_assault",
        "go_for_the_core",
        "put_someone_beneath_you",
        "brutalize",
        "enforcement_initiative",
        "snoop",
        "consume_eat",
    ):
        return
    target = prepared.target_actor
    if target is None and prepared.target is not None and str(prepared.target) in state.sheets:
        target = current_ref(state, prepared.target)
    if target is not None:
        require_targetable(game, c, state, target)


def guard_damage_changes(
    game: "GameService", c: Connection, before: GameState, after: GameState
) -> None:
    """Protect actual saved Assets also in older punishment and source-specific reducers."""
    from girlframe.services.m3_wyvern_combat import require_damage_allowed

    bound = profiles(c, game.store.campaign_id)
    for source in rules.records(before, rules.Shield):
        if not rules.shield_active(before, source):
            continue
        actor = source.target
        if actor.kind == "pilot":
            old = before.sheets.get(actor.entity)
            new = after.sheets.get(actor.entity)
            if (
                old is None
                or new is None
                or old.character_id != actor.incarnation
                or new.character_id != actor.incarnation
            ):
                continue
            previously = {x.id for x in old.assets if not x.damaged}
            damaged_now = {x.id for x in new.assets if x.damaged}
        else:
            try:
                previously = {
                    x.id
                    for x in resolve(before, actor, bound, require_current_profile=False).assets
                    if not x.damaged
                }
                damaged_now = {
                    x.id
                    for x in resolve(
                        after, actor, bound, require_alive=False, require_current_profile=False
                    ).assets
                    if x.damaged
                }
            except ValueError:
                continue
        if previously & damaged_now:
            require_damage_allowed(game, c, before, actor)
