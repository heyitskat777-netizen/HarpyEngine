"""Actual independent AM branch, prepared hardware and irreversible owned succession."""

import hashlib
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import Field

from girlframe.engine.m2 import AssetState, GameState, IdentityState, PilotSheet, TagState
from girlframe.engine.m3_actor_state import ActorRef, ActorView, Model
from girlframe.engine.m3_am import Limiter
from girlframe.engine.m3_am_backup import Backup, Reversion
from girlframe.engine.m3_am_body import Body, bodies, preparations, put
from girlframe.engine.m3_am_code import Maintenance
from girlframe.engine.m3_am_memory import Erasure
from girlframe.engine.m3_frame_state import FrameRuntime
from girlframe.engine.m3_world_state import Npc


class Assignment(Model):
    owner: ActorRef
    frame: str
    instance: str
    cell: tuple[int, int]
    assets: tuple[AssetState, ...]
    runtime: FrameRuntime | None
    position: int = Field(ge=0)
    event: str
    account: str = Field(min_length=1, max_length=1200)


class Branch(Model):
    id: str
    maintenance: str
    original: ActorRef
    operator: ActorRef
    owner: int
    controller: int
    npc: ActorRef
    preparation: str
    vessel: str
    event: str
    action: str
    captured_revision: int
    identities: tuple[IdentityState, ...]
    limiter_ids: tuple[str, ...]
    original_limiters: tuple[Limiter, ...]
    memory_losses: tuple[Erasure, ...]
    memory_backups: tuple[Backup, ...]
    memory_reversions: tuple[Reversion, ...]
    relationship_memory: tuple[str, ...]
    assignment: Assignment | None = None
    resulting_actor: ActorRef | None = None
    ready_event: str | None = None
    takeover_event: str | None = None
    archive: str | None = None
    npc_history: str | None = None


def branches(state: GameState) -> tuple[Branch, ...]:
    return tuple(
        Branch.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == "am_branch"
    )


def get(state: GameState, identity: str) -> Branch:
    value = next((x for x in branches(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the actual branch birth and original-person source")
    return value


def branch(state: GameState, ref: ActorRef) -> Branch | None:
    return next((x for x in branches(state) if ref in (x.npc, x.resulting_actor)), None)


def is_branch(state: GameState, ref: ActorRef) -> bool:
    return branch(state, ref) is not None


def uses_vessel(state: GameState, vessel: str) -> bool:
    return any(x.vessel == vessel for x in branches(state))


def _id(identity: str, source: str) -> str:
    return str(uuid5(NAMESPACE_URL, "girlframe:am-branch:" + identity + ":" + source))


def branch_limiters(state: GameState, ref: ActorRef) -> tuple[Limiter, ...] | None:
    if not is_branch(state, ref):
        return None
    return tuple(
        Limiter.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "am_limiter" and Limiter.model_validate_json(x["body"]).actor == ref
    )


def remembered_before_birth(
    state: GameState, ref: ActorRef, memory: str, learned_revision: int
) -> bool | None:
    value = branch(state, ref)
    if value is None or learned_revision > value.captured_revision:
        return None
    from girlframe.engine.m3_am_memory import can_recall

    memory_state = GameState(
        revision=state.revision,
        facts=[
            dict(kind=kind, body=x.model_dump_json())
            for kind, values in (
                ("am_memory_erasure", value.memory_losses),
                ("am_backup", value.memory_backups),
                ("am_backup_reversion", value.memory_reversions),
            )
            for x in values
        ],
    )
    return can_recall(memory_state, value.original, memory, learned_revision=learned_revision)


def current_body(state: GameState, ref: ActorRef) -> Body:
    value = branch(state, ref)
    if value is None:
        raise ValueError("Use the actual branch person")
    body = next((x for x in bodies(state) if x.vessel == value.vessel), None)
    if body is None or body.occupant != ref or body.actor != ref:
        raise ValueError("Recover the same branch's actual occupied hardware")
    if ref.kind == "pilot":
        sheet = state.sheets.get(ref.entity)
        pose = next((x for x in state.placements if x.actor == ref), None)
        if (
            sheet is None
            or sheet.character_id != ref.incarnation
            or pose is None
            or pose.vessel_id != body.vessel
            or pose.girl_cell is None
        ):
            raise ValueError("Recover the source-activated branch's live physical state")
        return body.model_copy(
            update=dict(
                assets=tuple(x for x in sheet.assets if x.family == "girl"),
                cell=pose.girl_cell,
                medical=sheet.medical_state,
            )
        )
    npc = next((x for x in state.world.npcs if x.id == ref.entity), None) if state.world else None
    if value.takeover_event or npc is None or not npc.alive or npc.controller != value.controller:
        raise ValueError("The former NPC representation cannot act as the current Girl")
    return body.model_copy(update=dict(cell=npc.cell))


def npc_view(state: GameState, base: ActorView) -> ActorView:
    value = branch(state, base.ref)
    if value is None:
        return base
    from girlframe.engine.m3_actors import assets, fingerprint, identities

    body = current_body(state, base.ref)
    return base.model_copy(
        update=dict(
            girl="AM",
            assets=assets(body.assets),
            identities=identities(value.identities),
            vessel_id=body.vessel,
            inside_frame=False,
            piloting=False,
            vitals_active=True,
            custody=base.custody if body.medical == "fit" else "medical_incapacity",
            source_sha256=hashlib.sha256(
                (base.source_sha256 + fingerprint(value) + fingerprint(body)).encode()
            ).hexdigest(),
        )
    )


def frame_owner_alias(state: GameState, old_owner: ActorRef, instance: str) -> ActorRef | None:
    for value in branches(state):
        assigned = value.assignment
        result = value.resulting_actor
        if (
            value.takeover_event
            and assigned
            and result
            and assigned.owner == old_owner
            and assigned.instance == instance
            and value.archive
            and any(
                x.id == value.archive
                and x.actor == value.original
                and x.ending == "am_branch_terminated"
                for x in state.career_archives
            )
            and result.entity in state.sheets
            and state.sheets[result.entity].character_id == result.incarnation
        ):
            return result
    return None


def create(state: GameState, value: Maintenance, preparation: str, event: str) -> Branch:
    from girlframe.engine import m3_am as am
    from girlframe.engine import m3_am_backup as backup
    from girlframe.engine import m3_am_body as hardware
    from girlframe.engine.m3_am_memory import losses

    source = next((x for x in preparations(state) if x.id == preparation), None)
    sheet = state.sheets[value.actor.entity]
    if (
        source is None
        or source.maintenance != value.id
        or source.actor != value.actor
        or not event
        or not value.action
        or "branch" not in value.selected_options
        or value.branch
        or any(x.maintenance == value.id for x in branches(state))
        or uses_vessel(state, source.spec.vessel)
        or any(x.vessel == source.spec.vessel for x in bodies(state))
        or source.spec.mind_assets
        or any(x.paired or x.slot is None for x in sheet.identities)
        or state.world is None
    ):
        raise ValueError(
            "Use one actual empty vessel; coupled/mental-resource sources require their own ports"
        )
    hardware._ordinary(state, value.actor, source.spec.assets)
    identity = str(uuid4())
    npc_ref = ActorRef(kind="npc", entity="am-branch:" + identity)
    original_limiters = am.limiters(state, value.actor)
    limiter_map = {x.id: _id(identity, "limiter:" + x.id) for x in original_limiters}
    mapping = {x.id: _id(identity, "identity:" + x.id) for x in sheet.identities}
    copied = tuple(
        x.model_copy(
            update=dict(
                id=mapping[x.id], am_limiter=limiter_map.get(x.am_limiter) if x.am_limiter else None
            )
        )
        for x in sheet.identities
    )
    result = Branch(
        id=identity,
        maintenance=value.id,
        original=value.actor,
        operator=value.operator,
        owner=value.owner,
        controller=value.controller,
        npc=npc_ref,
        preparation=source.id,
        vessel=source.spec.vessel,
        event=event,
        action=value.action,
        captured_revision=state.revision,
        identities=copied,
        limiter_ids=tuple(limiter_map.values()),
        original_limiters=original_limiters,
        memory_losses=losses(state, value.actor),
        memory_backups=backup.backups(state, value.actor),
        memory_reversions=backup.reversions(state, value.actor),
        relationship_memory=tuple(
            x.model_dump_json() for x in state.actor_bonds if value.actor in (x.first, x.second)
        ),
    )
    for old in original_limiters:
        limited = old.model_copy(
            update=dict(
                id=limiter_map[old.id],
                actor=npc_ref,
                identity=mapping[old.identity],
                source_event=event,
            )
        )
        put(state, "am_limiter", limited.id, limited)
    introduced = Npc(
        id=npc_ref.entity,
        name=source.spec.label,
        cell=source.cell,
        jobs=("guard",),
        detail="Actual prepared AM branch, classified as an unarmed Guard by its original Handler",
        controller=value.controller,
        revealed=True,
    )
    state.world = state.world.model_copy(update=dict(npcs=state.world.npcs + (introduced,)))
    body = Body(
        vessel=source.spec.vessel,
        actor=npc_ref,
        label=source.spec.label,
        cell=source.cell,
        assets=source.spec.assets,
        medical=source.spec.medical,
        occupant=npc_ref,
        origin_event=source.event,
        event=event,
    )
    put(state, "am_body_hardware", body.vessel, body)
    put(state, "am_branch", identity, result)
    return result


def assign(state: GameState, identity: str, position: int, event: str, account: str) -> Branch:
    from girlframe.engine.m3_am_body import swaps as body_swaps

    value = get(state, identity)
    original = state.sheets.get(value.original.entity)
    pose = next((x for x in state.placements if x.actor == value.original), None)
    body = current_body(state, value.npc)
    if (
        value.takeover_event
        or original is None
        or original.character_id != value.original.incarnation
        or original.frame != "THE ENFORCER"
        or original.frame_scrapped
        or pose is None
        or pose.mode != "outside_frame"
        or pose.custody
        or pose.subsumed
        or pose.girl_cell != body.cell
        or pose.frame_cell != body.cell
        or not event
        or not account.strip()
        or len(account) > 1200
        or not 0 <= position < len(state.order)
        or any(x.occupied_frame_owner == value.original for x in state.placements)
        or any(x.actor == value.original and not x.returned_event for x in body_swaps(state))
    ):
        raise ValueError(
            "Review the actual available Enforcer and resulting Status; "
            "other packages need source adapters"
        )
    frame = (
        original.frame_runtime.id
        if original.frame_runtime
        else "initial:" + str(value.original.incarnation)
    )
    runtime = (
        original.frame_runtime.model_copy(update=dict(acquired_rules=()))
        if original.frame_runtime
        else None
    )
    package = Assignment(
        owner=value.original,
        frame=original.frame,
        instance=frame,
        cell=body.cell,
        assets=tuple(x for x in original.assets if x.family == "frame"),
        runtime=runtime,
        position=position,
        event=event,
        account=account,
    )
    result = value.resulting_actor or ActorRef(
        kind="pilot", entity=str(value.owner), incarnation=str(uuid4())
    )
    changed = value.model_copy(
        update=dict(assignment=package, resulting_actor=result, ready_event=event)
    )
    put(state, "am_branch", identity, changed)
    return changed


def build_sheet(state: GameState, value: Branch, profile_revision: int) -> PilotSheet:
    from girlframe.engine.creation import CreationDraft
    from girlframe.engine.creation_review import ReviewSheet
    from girlframe.engine.m3_careers import original_sheet

    if value.assignment is None or value.resulting_actor is None:
        raise ValueError("Prepare the actual branch's resulting Girl and existing Frame")
    source = original_sheet(state, value.original)
    body = current_body(state, value.npc)
    assert state.world is not None
    npc = next(x for x in state.world.npcs if x.id == value.npc.entity)
    tags = []
    for tag in npc.tags:
        giver: ActorRef | None
        try:
            giver = ActorRef.model_validate_json(tag.giver_entity)
        except ValueError:
            giver = value.npc if tag.giver_entity == value.npc.entity else None
        if giver is None:
            raise ValueError(
                "SOURCE_BRANCH_TAG_SETTER_REQUIRED: preserve the actual postbirth setter"
            )
        from girlframe.engine.m3_actors import resolve

        controller = resolve(state, giver, (), require_current_profile=False).controller
        tags.append(
            TagState(
                id=tag.id,
                label=tag.label,
                giver=controller,
                giver_actor=giver,
                marked=tag.marked,
                scene_used=tag.trigger_scene,
                rejection_pending=tag.rejection_pending,
            )
        )
    creation = CreationDraft(
        girl_playbook="AM",
        frame_playbook=value.assignment.frame,
        # Birth/activation is not a new starting-Asset selection. The actual supplied
        # hardware is carried in the authoritative live Assets below.
        girl_assets=(),
        girl_appearance=body.label,
    )
    review = ReviewSheet(
        owner=value.owner,
        callsign=npc.name,
        activation_callsign=npc.name,
        character_revision=profile_revision,
        creation_revision=0,
        setup_revision=0,
        creation=creation,
        initial_conditions=source.review.initial_conditions,
        rulings=source.review.rulings,
        access=(),
    )
    runtime = value.assignment.runtime or FrameRuntime(
        id=value.assignment.instance,
        generation=1,
        source_work=value.id,
        frame_name="Actual reassigned existing Frame",
    )
    return PilotSheet(
        owner=value.owner,
        character_id=value.resulting_actor.incarnation,
        callsign=npc.name,
        girl="AM",
        frame=value.assignment.frame,
        source_fingerprint="am-branch:" + value.id,
        source_profile_revision=profile_revision,
        review=review,
        identities=[x.model_copy(deep=True) for x in value.identities],
        assets=list(body.assets) + list(value.assignment.assets),
        tags=tags,
        heat=0,
        permissions=0,
        frame_runtime=runtime,
        medical_state=body.medical,
    )


def materialize_relationships(state: GameState, value: Branch, event: str) -> GameState:
    """Freeze genuine postbirth NPC Bonds before numeric owners can change incarnation."""
    from girlframe.engine.m3_actor_bonds import current_ref, migrate_actor, set_depth
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_handler_consequences import active_handler

    if state.world is None:
        raise ValueError("Recover the actual branch NPC relationships")
    npc = next(x for x in state.world.npcs if x.id == value.npc.entity)
    changed = migrate_actor(state, value.npc, event)
    for key, depth in npc.bonds.items():
        kind, entity = key.split(":", 1)
        if kind == "pilot":
            other = current_ref(state, int(entity))
            if other.kind != "pilot":
                raise ValueError("Recover the actual original Pilot Bond endpoint")
        elif kind == "handler":
            handler = active_handler(state)
            if handler is None or handler.entity != entity:
                raise ValueError("Recover the actual original Handler Bond endpoint")
            other = handler
        else:
            other = ActorRef.model_validate(dict(kind=kind, entity=entity))
        resolve(state, other, (), require_current_profile=False)
        changed = set_depth(changed, value.npc, other, depth, event)
    return changed
