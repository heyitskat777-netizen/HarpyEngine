"""Source-bound Matrix presence, actual scene damage and one original Frame mark."""

from typing import TYPE_CHECKING, Literal
from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, CastRole, Model, ProfileBinding
from girlframe.engine.m3_class_grafts import eligible
from girlframe.engine.m3_class_grafts import held as class_held
from girlframe.engine.m3_physical_state import Placement
from girlframe.engine.m3_requisition_state import FrameRuleReceipt

RULE = "frame.class.priestess.appearance-matrix"
Mode = Literal["appear", "disappear"]

if TYPE_CHECKING:
    from girlframe.engine.m3_harpy_resources import HarpyResource


class Context(Model):
    id: str
    scene: str
    channel: int
    location: str
    cell: tuple[int, int]
    gm: int
    appointment: str
    event: str


class Mark(Model):
    purchase: str
    actor: ActorRef
    frame: str
    marked: bool = False
    use: str | None = None
    periods: tuple[str, ...] = ()


class Reset(Model):
    purchase: str
    actor: ActorRef
    frame: str
    period: str
    action: str


class Damage(Model):
    id: str
    scene: str
    damager: ActorRef
    target: ActorRef
    asset: str
    frame: str | None = None
    event: str
    action: str | None = None
    work: str | None = None
    revision: int


class Use(Model):
    id: str
    actor: ActorRef
    purchase: str
    frame: str
    context: str
    scene: str
    mode: Mode
    event: str
    revision: int
    origin: Placement
    travels_frame: bool
    witnesses: tuple[ActorRef, ...]
    repaired: tuple[str, ...]
    returned_event: str | None = None


def contexts(state: GameState) -> tuple[Context, ...]:
    return tuple(
        Context.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "matrix_scene"
    )


def damages(state: GameState) -> tuple[Damage, ...]:
    return tuple(
        Damage.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "matrix_damage"
    )


def uses(state: GameState) -> tuple[Use, ...]:
    return tuple(
        Use.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == "matrix_use"
    )


def held(state: GameState, actor: ActorRef) -> FrameRuleReceipt | None:
    return class_held(state, actor, RULE)


def mark(state: GameState, receipt: FrameRuleReceipt) -> Mark:
    return next(
        (
            Mark.model_validate_json(x["body"])
            for x in state.facts
            if x.get("kind") == "matrix_mark" and x.get("id") == receipt.id
        ),
        Mark(purchase=receipt.id, actor=receipt.actor, frame=receipt.frame_instance),
    )


def put(state: GameState, kind: str, identity: str, value: Model) -> None:
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == identity)
    ]
    state.facts.append(dict(kind=kind, id=identity, body=value.model_dump_json()))


def absence(state: GameState, actor: ActorRef) -> Use | None:
    return next(
        (
            x
            for x in reversed(uses(state))
            if x.actor == actor and x.mode == "disappear" and x.returned_event is None
        ),
        None,
    )


def actual_return(state: GameState, actor: ActorRef, event: str) -> None:
    value = absence(state, actor)
    body = next((x for x in state.placements if x.actor == actor), None)
    if value and body and body.girl_cell is not None and body.source_event == event:
        if body.vessel_id != value.origin.vessel_id or body.frame_instance != value.frame:
            raise ValueError("Recover the same original Matrix body and Frame before return")
        put(state, "matrix_use", value.id, value.model_copy(update=dict(returned_event=event)))


def reset_at_start(state: GameState, actor: ActorRef, period: str, action: str) -> bool:
    changed = False
    for receipt in state.requisitions:
        if not (
            isinstance(receipt, FrameRuleReceipt)
            and receipt.rule_id == RULE
            and receipt.actor == actor
            and eligible(state, receipt)
        ):
            continue
        value = mark(state, receipt)
        if period in value.periods:
            continue
        if not period or not action:
            raise ValueError("Matrix reset needs actual original Go-Off-Duty period/action")
        put(
            state,
            "matrix_mark",
            receipt.id,
            value.model_copy(update=dict(marked=False, periods=(*value.periods, period))),
        )
        value_id = str(uuid5(NAMESPACE_URL, "matrix-reset:" + receipt.id + ":" + period))
        put(
            state,
            "matrix_reset",
            value_id,
            Reset(
                purchase=receipt.id,
                actor=actor,
                frame=receipt.frame_instance,
                period=period,
                action=action,
            ),
        )
        changed = True
    return changed


def asset(state: GameState, actor: ActorRef, identity: str) -> "HarpyResource | None":
    from girlframe.engine.m3_mockingbird_sex import assets

    return next((x for x in assets(state, actor) if x.id == identity), None)


def record_damage(
    before: GameState,
    after: GameState,
    *,
    damager: ActorRef | None,
    target: ActorRef,
    identity: str | None,
    scene: str | None,
    event: str,
    action: str | None,
    work: str | None,
    occurrence: str,
) -> None:
    if damager is None or not identity or not scene:
        return
    try:
        old, new = asset(before, target, identity), asset(after, target, identity)
    except ValueError:
        return
    if old is None or new is None or old.damaged or not new.damaged:
        return
    frame = None
    if old.family == "frame" and target.kind == "pilot":
        from girlframe.engine.m3_nightmare import current

        _, frame = current(before, target)
    value = Damage(
        id=str(
            uuid5(NAMESPACE_URL, "matrix-damage:" + event + ":" + target.token + ":" + occurrence)
        ),
        scene=scene,
        damager=damager,
        target=target,
        asset=identity,
        frame=frame,
        event=event,
        action=action,
        work=work,
        revision=before.revision,
    )
    put(after, "matrix_damage", value.id, value)


def eligible_damage(state: GameState, actor: ActorRef, scene: str) -> tuple[Damage, ...]:
    latest = {(x.target, x.asset): x for x in damages(state)}
    repaired = {identity for use in uses(state) for identity in use.repaired}
    result = []
    for value in latest.values():
        if (
            value.id in repaired
            or value.scene != scene
            or not (value.damager == actor or value.target == actor)
        ):
            continue
        current = asset(state, value.target, value.asset)
        if current is None:
            raise ValueError("SOURCE_PORT_REQUIRED: recover the original damaged physical Asset")
        if value.frame and value.target.kind == "pilot":
            from girlframe.engine.m3_nightmare import current as current_frame

            if current_frame(state, value.target)[1] != value.frame:
                raise ValueError("SOURCE_PORT_REQUIRED: do not heal a replacement Frame")
        if current.damaged:
            result.append(value)
    return tuple(result)


def _undamage(state: GameState, value: Damage, event: str) -> None:
    target = value.target
    if target.kind == "pilot":
        sheet = state.sheets.get(target.entity)
        if sheet is None or sheet.character_id != target.incarnation:
            raise ValueError("Recover the same actual damaged original character")
        selected = next((x for x in sheet.assets if x.id == value.asset), None)
        if selected is None:
            raise ValueError("SOURCE_PORT_REQUIRED: recover this Asset's sole current origin")
        selected.damaged = False
        sheet.revision += 1
        return
    if target.kind == "gorgon" and state.world:
        state.world = state.world.model_copy(
            update=dict(
                gorgons=tuple(
                    x.model_copy(
                        update=dict(
                            assets=tuple(
                                a.model_copy(update=dict(damaged=False))
                                if a.id == value.asset
                                else a
                                for a in x.assets
                            )
                        )
                    )
                    if x.id == target.entity
                    else x
                    for x in state.world.gorgons
                )
            )
        )
        return
    if target.kind == "external_pilot":
        from girlframe.engine.m3_harpy_resources import assets, set_assets

        changed = set_assets(
            state,
            target,
            tuple(
                x.model_copy(update=dict(damaged=False)) if x.id == value.asset else x
                for x in assets(state, target)
            ),
            event=event,
        )
        for field in GameState.model_fields:
            setattr(state, field, getattr(changed, field))
        return
    from girlframe.engine.m3_items import actual_asset, same_holder

    matching = [
        (x, a)
        for x in state.held_items
        if same_holder(state, x.holder, target)
        and (a := actual_asset(state, x)) is not None
        and a.id == value.asset
    ]
    if len(matching) != 1:
        raise ValueError("SOURCE_PORT_REQUIRED: recover this Asset's sole actual object origin")
    item, actual = matching[0]
    changed_asset = actual.model_copy(update=dict(damaged=False))
    state.held_items = [
        x.model_copy(update=dict(asset_json=changed_asset.model_dump_json(), state_event=event))
        if x.id == item.id
        else x
        for x in state.held_items
    ]


def apply(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    actor: ActorRef,
    context: Context,
    mode: Mode,
    event: str,
) -> tuple[GameState, Use]:
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_nightmare import current
    from girlframe.engine.m3_physical import _save

    state = GameState.model_validate_json(original.model_dump_json())
    receipt = held(state, actor)
    if receipt is None or mark(state, receipt).marked or not event:
        raise ValueError("Use this original Frame's genuine unmarked Appearance Matrix")
    _, frame = current(state, actor)
    body = next((x for x in state.placements if x.actor == actor), None)
    view = resolve(state, actor, bindings)
    cast = next((x for x in state.scene_casts if x.id == context.scene and x.open), None)
    if (
        body is None
        or body.frame_instance != frame
        or not view.alive
        or body.custody
        or body.occupied_frame_owner
        or body.subsumed
        or not body.vitals_active
        or body.incapacitated
        or view.offstage_source
        or body.girl_cell is None
        or body.frame_cell is None
        or cast is None
        or any(x.state == "boarded" and x.carrier == actor for x in state.passengers)
    ):
        raise ValueError("SOURCE_PORT_REQUIRED: use this free known original Matrix body/Frame")
    present = any(x.actor == actor for x in cast.roles) and view.cell == context.cell
    if mode == "disappear" and not present:
        raise ValueError("Disappear only from this actual original scene and location")
    if mode == "appear" and present:
        raise ValueError("The original body is already actually present here")
    witnesses = []
    for role in cast.roles:
        actual = resolve(state, role.actor, bindings, require_current_profile=False)
        if actual.cell == context.cell and actual.offstage_source is None:
            witnesses.append(role.actor)
    if actor not in witnesses:
        witnesses.append(actor)
    repair = eligible_damage(state, actor, context.scene)
    for damage in repair:
        _undamage(state, damage, event)
    # These are new OOC cast projections for the actual ability, never edits to old answers.
    changed_casts = []
    for current_cast in state.scene_casts:
        roles = (
            tuple(x for x in current_cast.roles if x.actor != actor)
            if current_cast.open
            else current_cast.roles
        )
        if current_cast.id == context.scene and mode == "appear":
            roles += (CastRole(actor=actor, controller=int(actor.entity), source_event=event),)
        changed_casts.append(
            current_cast.model_copy(update=dict(roles=roles, revision=current_cast.revision + 1))
            if roles != current_cast.roles
            else current_cast
        )
    state.scene_casts = changed_casts
    whole = body.mode != "outside_frame"
    destination = context.cell if mode == "appear" else None
    _save(
        state,
        body.model_copy(
            update=dict(
                girl_cell=destination,
                frame_cell=destination if whole else body.frame_cell,
                source_event=event,
                account="Actual Appearance Matrix " + mode,
            )
        ),
    )
    value = Use(
        id=str(uuid5(NAMESPACE_URL, "matrix-use:" + event)),
        actor=actor,
        purchase=receipt.id,
        frame=frame,
        context=context.id,
        scene=context.scene,
        mode=mode,
        event=event,
        revision=state.revision,
        origin=body,
        travels_frame=whole,
        witnesses=tuple(witnesses),
        repaired=tuple(x.id for x in repair),
    )
    put(state, "matrix_use", value.id, value)
    put(
        state,
        "matrix_mark",
        receipt.id,
        mark(state, receipt).model_copy(update=dict(marked=True, use=value.id)),
    )
    return GameState.model_validate_json(state.model_dump_json()), value
