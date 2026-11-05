"""Personal Firearm grants an actual Girl Asset and source-bound future lost-item returns."""

from typing import Literal

from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_acquisition_state import FirearmIssue, PersonalFirearmGrant
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_core import install
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.engine.playbooks import canonical_frame
from girlframe.engine.rules_registry import Registry

RULE = "frame.enforcer.personal-firearm"
Kind = Literal["ability_unlock", "frame_grafting"]
REPLACEMENT_NOTICE = (
    "The Foundation issues a distinct physical replacement pistol. "
    "A stolen original keeps its recorded custody. Real retrieval uses a separate actual transfer. "
    "The replacement uses the normal Girl Asset capacity."
)


def held(state: GameState, actor: ActorRef, frame: str) -> list[PersonalFirearmGrant]:
    return [
        x
        for x in state.personal_firearms
        if x.actor == actor
        and x.frame_instance == frame
        and (x.purchase is None or not suspended(state, x.purchase))
    ]


def grant(
    original: GameState,
    actor: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    frame: str,
    identity: str,
    event: str,
    *,
    purchase: str | None = None,
    replace: str | None = None,
    source_work: str | None = None,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    current = resolve(state, actor, bindings, require_current_profile=False)
    if (
        current.ref.kind != "pilot"
        or current.rules != "girl_frame"
        or current.frame_instance != frame
        or current.frame_scrapped
        or not event
        or not identity
    ):
        raise ValueError("Grant the actual original Girl's current usable Frame entitlement")
    if any(x.id == identity for x in state.personal_firearms) or any(
        x.actor == actor and x.frame_instance == frame for x in state.personal_firearms
    ):
        raise ValueError("This actual Frame already holds Personal Firearm")
    asset = AssetState(
        id="firearm:" + identity + ":0",
        family="girl",
        name="Personal Firearm",
        description="A pistol and access to ammunition.",
    )
    state.sheets[actor.entity] = install(state.sheets[actor.entity], asset, replace=replace).sheet
    state.personal_firearms.append(
        PersonalFirearmGrant(
            id=identity,
            actor=actor,
            frame_instance=frame,
            source_event=event,
            purchase=purchase,
            source_work=source_work,
            issues=(
                FirearmIssue(
                    asset=asset.id,
                    source_event=event,
                    recipient=actor,
                    controller=current.controller,
                    replaces_asset=replace,
                ),
            ),
        )
    )
    return state


def purchase(
    original: GameState,
    actor: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    expected: str,
    registry: Registry,
    kind: Kind,
    account: str,
    identity: str,
    grant_id: str,
    source: str,
    *,
    replace: str | None = None,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    current = resolve(state, actor, bindings)
    entry = registry.require_available(RULE)
    if (
        entry.scope != "frame"
        or entry.frame_rule != "requisition"
        or entry.frame_playbook != "THE ENFORCER"
    ):
        raise ValueError("Use the actual source Enforcer Requisition, not a Class/playbook heading")
    if (
        current.source_sha256 != expected
        or current.ref.kind != "pilot"
        or current.frame_instance is None
    ):
        raise ValueError("STALE_ACQUISITION: review the original Girl and current Frame")
    if kind not in ("ability_unlock", "frame_grafting"):
        raise ValueError("Choose actual Ability Unlock or Frame Grafting")
    own = canonical_frame(state.sheets[actor.entity].frame) == "THE ENFORCER"
    if (kind == "ability_unlock") != own:
        raise ValueError(
            "Unlock comes from your actual Frame; Grafting uses another Frame playbook"
        )
    if any(x.id == identity or x.source_event == source for x in state.requisitions):
        raise ValueError("This actual acquisition purchase source is already recorded")
    price: Literal[2, 3] = 2 if kind == "ability_unlock" else 3
    sheet = state.sheets[actor.entity]
    if sheet.permissions < price:
        raise ValueError("This acquisition needs its actual available Permissions")
    sheet.permissions -= price
    sheet.revision += 1
    state = grant(
        state,
        actor,
        bindings,
        current.frame_instance,
        grant_id,
        source,
        purchase=identity,
        replace=replace,
    )
    state.requisitions.append(
        FrameRuleReceipt(
            id=identity,
            kind=kind,
            actor=actor,
            frame_instance=current.frame_instance,
            frame=sheet.frame,
            donor_frame="THE ENFORCER",
            rule_id=RULE,
            grant=grant_id,
            price=price,
            account=account,
            source_event=source,
        )
    )
    return state


def reissue(
    original: GameState,
    actor: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    grant_id: str,
    lost: str,
    frame: str,
    event: str,
    action: str,
    *,
    replace: str | None = None,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    current = resolve(state, actor, bindings, require_current_profile=False)
    entitlement = next((x for x in held(state, actor, frame) if x.id == grant_id), None)
    if (
        entitlement is None
        or current.frame_instance != frame
        or current.frame_scrapped
        or entitlement.issues[-1].asset != lost
        or any(x.id == lost for x in state.sheets[actor.entity].assets)
        or any(x.action == action for x in entitlement.issues)
        or not action
        or not event
    ):
        raise ValueError(
            "Use the original still-lost issued pistol and actual qualified current Frame"
        )
    asset = AssetState(
        id="firearm:" + entitlement.id + ":" + str(len(entitlement.issues)),
        family="girl",
        name="Personal Firearm",
        description="A Foundation-issued replacement service pistol and access to ammunition.",
    )
    state.sheets[actor.entity] = install(state.sheets[actor.entity], asset, replace=replace).sheet
    updated = entitlement.model_copy(
        update={
            "issues": (
                *entitlement.issues,
                FirearmIssue(
                    asset=asset.id,
                    source_event=event,
                    action=action,
                    kind="foundation_replacement",
                    recipient=actor,
                    controller=current.controller,
                    replaces_asset=lost,
                ),
            )
        }
    )
    state.personal_firearms = [
        updated if x.id == updated.id else x for x in state.personal_firearms
    ]
    return state


def retain(
    original: GameState,
    actor: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    grant_id: str,
    frame: str,
    event: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    current = resolve(state, actor, bindings, require_current_profile=False)
    sheet = state.sheets[actor.entity]
    existing = next(
        (x for x in state.personal_firearms if x.id == grant_id and x.actor == actor), None
    )
    if (
        existing is None
        or current.frame_instance != frame
        or not event
        or sheet.frame_runtime is None
        or RULE not in sheet.frame_runtime.acquired_rules
        or any(x.id != grant_id for x in held(state, actor, frame))
    ):
        raise ValueError("Retain only the actual selected Personal Firearm rule in its new Frame")
    state.personal_firearms = [
        x.model_copy(update={"frame_instance": frame}) if x.id == grant_id else x
        for x in state.personal_firearms
    ]
    state.facts.append(
        dict(
            kind="personal_firearm_retained",
            grant=grant_id,
            actor=actor.model_dump_json(),
            frame=frame,
            source_event=event,
        )
    )
    return state
