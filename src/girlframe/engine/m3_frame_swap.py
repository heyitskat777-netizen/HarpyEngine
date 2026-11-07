"""Optional paid Frame exchange; unsupported base rules remain unavailable."""

from girlframe.engine.creation import official_frame
from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.frame_setup import HarpyCore
from girlframe.engine.m2 import AssetState, GameState, IdentityState, pair_key
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_frame_state import FrameRuntime
from girlframe.engine.m3_frame_swap_state import Selection, SwapReceipt
from girlframe.engine.m3_intracadre_marriage import available, debit, payment_for
from girlframe.engine.m3_personal_firearm import RULE, held, retain
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.playbooks import FRAME_TYPES, canonical_frame
from girlframe.engine.rules_registry import Registry
from girlframe.engine.shared_setup import AM_ROLES


def destination(registry: Registry, selected: str) -> tuple[str, tuple[str, ...]]:
    frame = canonical_frame(selected)
    frame = "JANUS-B" if frame == "JANUS" else frame
    if frame not in FRAME_TYPES:
        raise ValueError("Choose an official core Frame; ancillary modules remain disabled")
    native = [
        x
        for x in registry.entries
        if x.scope == "frame"
        and x.frame_playbook == official_frame(frame)
        and x.frame_rule == "base"
    ]
    if not native:
        raise ValueError("SOURCE_BASELINE_MISSING: recover the destination Frame base inventory")
    # No test fixture or alias may turn an unsupported base into a free acquired ability.
    for entry in native:
        registry.require_available(entry.id)
    return frame, tuple(x.id for x in native)


def retained_rules(
    state: GameState,
    actor: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    registry: Registry,
) -> tuple[str, ...]:
    actual = resolve(state, actor, bindings, require_current_profile=False)
    if actual.frame_instance is None:
        return ()
    from girlframe.engine import m3_enforcer_requisitions as enforcer

    result = []
    from girlframe.engine.m3_class_grafts import held as class_held
    from girlframe.engine.m3_class_retention import RULES

    for rule in RULES:
        if class_held(state, actor, rule):
            registry.require_available(rule)
            registry.require_available("core.core.frame-requisitions")
            result.append(rule)
    if held(state, actor, actual.frame_instance):
        registry.require_available(RULE)
        result.append(RULE)
    for rule in (*enforcer.RULES, *enforcer.BASE):
        if (
            enforcer.held(state, actor, rule)
            or actual.frame == "THE ENFORCER"
            and rule in enforcer.BASE
        ):
            try:
                registry.require_available(rule)
            except ValueError:
                continue
            result.append(rule)
    return tuple(result)


def bonded_refs(state: GameState, actor: ActorRef) -> tuple[ActorRef, ...]:
    expected = {
        ActorRef(kind="pilot", entity=str(uid), incarnation=state.sheets[str(uid)].character_id)
        for uid in state.order
        if str(uid) in state.sheets
        and uid != int(actor.entity)
        and state.bonds.get(pair_key(int(actor.entity), uid))
    }
    for edge in state.actor_bonds:
        if edge.depth and actor in (edge.first, edge.second):
            expected.add(edge.second if edge.first == actor else edge.first)
    return tuple(sorted(expected, key=lambda x: x.token))


def validate(
    state: GameState,
    actor: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    registry: Registry,
    selection: Selection,
) -> str:
    actual = resolve(state, actor, bindings, require_current_profile=False)
    if actor.kind != "pilot" or actual.rules != "girl_frame" or actual.frame_scrapped:
        raise ValueError("Optional exchange requires your actual usable original Frame")
    if any(x.held and actor in (x.actor, x.target) for x in state.enforcer_grasps):
        raise ValueError("End the actual grasp before exchanging Frames")
    frame, _ = destination(registry, selection.frame)
    if canonical_frame(frame) == canonical_frame(actual.frame or ""):
        raise ValueError("Choose a different Frame playbook for this optional exchange")
    sheet = state.sheets[actor.entity]
    if selection.retained_rule not in retained_rules(state, actor, bindings, registry):
        raise ValueError("Select an actually held supported rule from your current Frame")
    from girlframe.engine.m3_class_grafts import held as class_held
    from girlframe.engine.m3_class_retention import RULES

    if selection.retained_rule in RULES:
        paid = class_held(state, actor, selection.retained_rule)
        if paid is None or selection.retained_receipt != paid.id:
            raise ValueError("Select this exact original retained Class purchase")
    elif selection.retained_receipt is not None:
        raise ValueError("This rule has no adapted paid Class retention source")
    if any(suspended(state, x.id) for x in state.requisitions if x.actor == actor):
        raise ValueError("Restore your original suspended Requisitions before exchanging Frames")
    retained = next(
        (x for x in sheet.assets if x.id == selection.retained_asset and x.family == "frame"), None
    )
    if retained is None:
        raise ValueError("Choose one actual owned current Frame Asset to retain")
    names = [x.name for x in selection.assets]
    if (
        len(set(names)) != 2
        or not set(names) <= set(CATALOG[official_frame(frame)]["assets"])
        or any(not x.description.strip() for x in selection.assets)
    ):
        raise ValueError(
            "Choose and describe two distinct printed starting Assets for the new Frame"
        )
    if (selection.fanbase is not None) != (frame == "THE PRINCE"):
        raise ValueError(
            "The Prince requires its complete new Fanbase; other Frames cannot buy one"
        )
    if selection.fanbase is not None and selection.fanbase.missing():
        raise ValueError("Complete every actual Fanbase choice")
    if frame == "THE RED QUEEN":
        if (
            selection.court_role not in AM_ROLES
            or selection.court_target is None
            or selection.court_target.kind != "pilot"
            or selection.court_target == actor
        ):
            raise ValueError("Assign the actual fifth Court role to another current Girl")
        resolve(state, selection.court_target, bindings, require_current_profile=False)
    elif selection.court_role is not None or selection.court_target is not None:
        raise ValueError("Court setup belongs only to the new Red Queen")
    if frame == "CHANGELING":
        if set(selection.psych_strings) != set(bonded_refs(state, actor)):
            raise ValueError("Initial Psych Strings must match all actual current Bonds")
    elif selection.psych_strings:
        raise ValueError("Initial Psych Strings belong only to CHANGELING")
    return frame


def purchase(
    original: GameState,
    actor: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    expected: str,
    registry: Registry,
    selection: Selection,
    identity: str,
    event: str,
    plan: str,
    *,
    court_accepted: bool = False,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    actual = resolve(state, actor, bindings, require_current_profile=False)
    if actual.source_sha256 != expected or not all((identity, event, plan)):
        raise ValueError("STALE_FRAME_SWAP: reopen your actual current Frame and resources")
    frame = validate(state, actor, bindings, registry, selection)
    if frame == "THE RED QUEEN" and not court_accepted:
        raise ValueError("The original external Court recipient must accept this exact assignment")
    if any(x.id == identity or x.source_event == event for x in state.requisitions):
        raise ValueError("Use one new actual paid Frame Swap source")
    sheet = state.sheets[actor.entity]
    if available(state, actor) < 4:
        raise ValueError("Frame Swap costs four available Permissions")
    debit(
        state,
        actor,
        4,
        event=event,
        source=identity,
        payment=payment_for(state, actor, "frame_swap", 4, plan),
    )
    old_frame = actual.frame_instance
    assert old_frame is not None
    kept = next(x for x in sheet.assets if x.id == selection.retained_asset)
    from girlframe.engine import m3_enforcer_requisitions as enforcer
    from girlframe.engine.m3_class_grafts import held as class_held
    from girlframe.engine.m3_class_retention import RULES
    from girlframe.engine.m3_class_retention import retain as retain_class

    class_receipt = (
        class_held(state, actor, selection.retained_rule)
        if selection.retained_rule in RULES
        else None
    )

    grant = held(state, actor, old_frame)[0] if selection.retained_rule == RULE else None
    retained_grant = (
        enforcer.held(state, actor, selection.retained_rule)
        if selection.retained_rule != RULE
        else None
    )
    runtime = FrameRuntime(
        id="swap:" + identity,
        generation=sheet.frame_runtime.generation + 1 if sheet.frame_runtime else 1,
        source_work=plan,
        frame_name=selection.name,
        frame_appearance=selection.appearance,
        core_id="swap:" + identity + ":core" if frame == "JANUS-B" else None,
        harpy_core=HarpyCore() if frame == "JANUS-B" else None,
        fanbase=selection.fanbase,
        court={
            role: int(selection.court_target.entity)
            if role == selection.court_role and selection.court_target
            else int(actor.entity)
            for role in AM_ROLES
        }
        if frame == "THE RED QUEEN"
        else {},
        consume_hunger="Quiet" if frame == "CONSUME" else None,
        psych_strings=tuple(int(x.entity) for x in selection.psych_strings if x.kind == "pilot"),
        psych_string_refs=selection.psych_strings,
        acquired_rules=(selection.retained_rule,),
    )
    sheet.assets = [x for x in sheet.assets if x.family == "girl"]
    sheet.assets.extend(
        AssetState(
            id=runtime.id + ":asset:" + str(i),
            family="frame",
            name=x.name,
            description=x.description,
        )
        for i, x in enumerate(selection.assets)
    )
    # The actual retained item keeps damage/Void/source identity. Extra cap treatment is a
    # native Wyvern rule; borrowing the item alone cannot silently borrow that second rule.
    sheet.assets.append(kept.model_copy(update={"intrinsic": None}))
    if frame == "WYVERN 0.4":
        sheet.assets.append(
            AssetState(
                id=runtime.id + ":intrinsic",
                family="frame",
                name="Enormous",
                intrinsic="wyvern_enormous",
            )
        )
    if selection.fanbase:
        sheet.identities.extend(
            IdentityState(id=runtime.id + ":fan:" + str(i), name=name, protected=True)
            for i, name in enumerate(selection.fanbase.additional_identities)
        )
    sheet.frame, sheet.frame_runtime, sheet.obsolescence_marked = frame, runtime, 0
    sheet.revision += 1
    if grant is not None:
        state = retain(state, actor, bindings, grant.id, runtime.id, event)
    elif retained_grant is not None:
        state.facts.append(
            dict(
                kind="enforcer_rule_retained",
                grant=retained_grant.id,
                actor=actor.model_dump_json(),
                old_frame=old_frame,
                frame=runtime.id,
                source_event=event,
                requisition=identity,
            )
        )
    elif class_receipt is not None:
        pass  # The immutable paid Class source is linked after its SwapReceipt exists.
    elif selection.retained_rule in enforcer.BASE:
        retained = enforcer.Grant(
            id="swap-rule:" + identity,
            actor=actor,
            frame=runtime.id,
            rule=selection.retained_rule,
            purchase=identity,
            source_event=event,
            source_kind="frame_swap",
            source_work=plan,
        )
        state.facts.append(dict(kind="enforcer_rule_acquired", body=retained.model_dump_json()))
    else:
        raise ValueError("Keep the original actually owned selected Frame rule source")
    state.requisitions.append(
        SwapReceipt(
            id=identity,
            actor=actor,
            old_frame=old_frame,
            new_frame=runtime.id,
            selection=selection,
            source_event=event,
            plan=plan,
        )
    )
    if class_receipt is not None:
        swap = next(
            x for x in state.requisitions if isinstance(x, SwapReceipt) and x.id == identity
        )
        retain_class(state, class_receipt, swap)
    return GameState.model_validate_json(state.model_dump_json())
