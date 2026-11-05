"""Creature Comforts needs its paid source, future qualifying roll and actual owned scene."""

from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_core import install
from girlframe.engine.m3_requisition_state import (
    ComfortBenefit,
    ComfortReceipt,
    ComfortScene,
    GirlAsset,
)


def purchase(
    original: GameState,
    actor: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    expected: str,
    identity: str,
    event: str,
    account: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    actual = resolve(state, actor, bindings)
    if actual.rules != "girl_frame" or actor.kind != "pilot" or actual.source_sha256 != expected:
        raise ValueError("STALE_REQUISITION: confirm your actual Girl's resources")
    if not account.strip() or any(
        x.id == identity or x.source_event == event for x in state.requisitions
    ):
        raise ValueError("Record one new paid Creature Comforts source and its owned request")
    sheet = state.sheets[actor.entity]
    if sheet.permissions < 1:
        raise ValueError("Creature Comforts costs one available Permission")
    sheet.permissions -= 1
    sheet.revision += 1
    state.requisitions.append(
        ComfortReceipt(id=identity, actor=actor, source_event=event, account=account.strip())
    )
    return state


def qualify(
    purchase: ComfortReceipt,
    actor: ActorRef,
    period: str,
    action: str,
    play: str,
    total: int,
    raw_event: str,
    event: str,
) -> ComfortBenefit | None:
    if actor != purchase.actor or play != "go_off_duty" or total < 8:
        return None
    return ComfortBenefit(
        purchase=purchase.id,
        actor=actor,
        period=period,
        action=action,
        raw_event=raw_event,
        qualification_event=event,
        total=total,
    )


def record_scene(
    state: GameState,
    bindings: tuple[ProfileBinding, ...],
    benefit: ComfortBenefit,
    cast: SceneCast,
    participants: tuple[ActorRef, ...],
    owner: int,
    summary: str,
    identity: str,
    location: str,
) -> ComfortBenefit:
    if benefit.taken is not None or benefit.scene is not None or not cast.open or not participants:
        raise ValueError("Record one actual scene for this offered Creature Comforts benefit")
    roles = tuple(x for x in cast.roles if x.actor in participants)
    if (
        len(set(participants)) != len(participants)
        or {x.actor for x in roles} != set(participants)
        or not any(x.actor == benefit.actor and x.controller == owner for x in roles)
    ):
        raise ValueError("Choose actual cast roles including your original purchasing Girl")
    place = (
        next(
            (x for x in state.world.locations if x.id == location and x.operational),
            None,
        )
        if state.world
        else None
    )
    if place is None:
        raise ValueError("Record this Off-Duty improvement at an actual surviving location")
    for role in roles:
        actual = resolve(state, role.actor, bindings, require_current_profile=False)
        if actual.controller != role.controller or (
            actual.cell is not None and actual.cell != place.cell
        ):
            raise ValueError(
                "Use actual current roles already at the scene's location; "
                "casting does not move them"
            )
    return benefit.model_copy(
        update={
            "scene": ComfortScene(
                id=identity,
                cast_id=cast.id,
                cast_revision=cast.revision,
                location=place.id,
                roles=roles,
                summary=summary,
                acknowledgements=(owner,),
            )
        }
    )


def attest(benefit: ComfortBenefit, human: int) -> ComfortBenefit:
    scene = benefit.scene
    if (
        benefit.taken is not None
        or scene is None
        or human not in {x.controller for x in scene.roles}
        or human in scene.acknowledgements
    ):
        raise ValueError("Record only your own actual attendance once")
    return benefit.model_copy(
        update={
            "scene": scene.model_copy(update={"acknowledgements": (*scene.acknowledgements, human)})
        }
    )


def ready(benefit: ComfortBenefit) -> bool:
    scene = benefit.scene
    return bool(
        scene is not None and set(scene.acknowledgements) == {x.controller for x in scene.roles}
    )


def decline(benefit: ComfortBenefit, human: int, account: str) -> ComfortBenefit:
    if (
        benefit.taken is not None
        or benefit.scene is not None
        or human != int(benefit.actor.entity)
        or not account.strip()
    ):
        raise ValueError("Only the purchasing Girl may decline this unused optional scene")
    return benefit.model_copy(update={"taken": False, "account": account.strip()})


def grant(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    expected: str,
    benefit: ComfortBenefit,
    chosen: GirlAsset,
    identity: str,
) -> tuple[GameState, ComfortBenefit]:
    from girlframe.engine.m3_privileges import suspended

    if suspended(original, benefit.purchase):
        raise ValueError("Restore the temporarily revoked Requisition before using it")
    chosen = GirlAsset.model_validate_json(chosen.model_dump_json())
    state = GameState.model_validate_json(original.model_dump_json())
    actor = resolve(state, benefit.actor, bindings)
    if (
        actor.rules != "girl_frame"
        or actor.source_sha256 != expected
        or benefit.taken is not None
        or any(
            x.get("kind") == "creature_comforts_asset" and x.get("purchase") == benefit.purchase
            for x in state.facts
        )
        or not ready(benefit)
        or not any(
            x.id == benefit.purchase and x.actor == benefit.actor and x.kind == "creature_comforts"
            for x in state.requisitions
        )
        or not chosen.name.strip()
        or not chosen.description.strip()
    ):
        raise ValueError(
            "Use the actual purchased opportunity, complete owned scene and current Asset choices"
        )
    asset = AssetState(
        id=identity, family="girl", name=chosen.name.strip(), description=chosen.description.strip()
    )
    from girlframe.engine.m3_janus_storage import ids as stored_ids

    result = install(
        state.sheets[benefit.actor.entity],
        asset,
        replace=chosen.replace,
        effective_void=stored_ids(state, benefit.actor),
    )
    state.sheets[benefit.actor.entity] = result.sheet
    state.facts.append(
        {
            "kind": "creature_comforts_asset",
            "purchase": benefit.purchase,
            "asset": asset.id,
            "period": benefit.period,
            "action": benefit.action,
            "actor": benefit.actor.model_dump_json(),
        }
    )
    return state, benefit.model_copy(
        update={
            "taken": True,
            "asset_id": asset.id,
            "asset_name": asset.name,
            "asset_description": asset.description,
        }
    )
