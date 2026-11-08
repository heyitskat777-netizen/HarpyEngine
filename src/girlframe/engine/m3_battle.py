"""Actual combat resource ports and source-owned damage; never synthetic NPC HP."""

import hashlib
import json

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import depth, make_helpless
from girlframe.engine.m3_actor_state import ActorRef, AssetView, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_battle_state import Category, FrameExposure, Required
from girlframe.engine.m3_items import mechanical_assets
from girlframe.engine.m3_world import damage_gorgon


def category(state: GameState, actor: ActorRef) -> Category:
    if actor.kind == "pilot":
        sheet = state.sheets.get(actor.entity)
        if sheet is None or sheet.character_id != actor.incarnation:
            raise ValueError("Recover the original current Pilot incarnation")
        return "pilot"
    if actor.kind == "handler":
        from girlframe.engine.m3_handler_consequences import same_handler_body

        if not same_handler_body(state, actor):
            raise ValueError("Recover the actual current Handler body")
        return "handler"
    if actor.kind == "gorgon":
        return "gorgon"
    if actor.kind == "external_pilot":
        return (
            "harpy"
            if any(x.id == actor.entity for x in state.harpy_states)
            or (
                state.world is not None
                and any(x.id == actor.entity and x.kind == "harpy" for x in state.world.pilots)
            )
            else "pilot"
        )
    if state.world is not None and any(
        x.id == actor.entity and "director" in x.jobs for x in state.world.npcs
    ):
        return "handler"
    # A captured JANUS Core remains a Harpy, never an ordinary human NPC.
    if any(x.core_id == actor.entity for x in state.parked_frames) or any(
        x.frame_runtime is not None and x.frame_runtime.core_id == actor.entity
        for x in state.sheets.values()
    ):
        return "harpy"
    return "npc"


def assets(
    state: GameState, actor: ActorRef, bindings: tuple[ProfileBinding, ...]
) -> tuple[AssetView, ...]:
    actual = resolve(state, actor, bindings)
    placement = next((x for x in state.placements if x.actor == actor), None)
    own_frame_present = bool(actual.inside_frame) and (
        actual.occupied_frame_instance in (None, actual.frame_instance)
        and (placement is None or placement.occupied_frame_owner is None)
    )
    scene_objects = {x.asset_id for x in state.held_items if x.location_mode == "scene"}
    own = [
        x
        for x in actual.assets
        if x.id not in scene_objects and (x.family != "frame" or own_frame_present)
    ]
    for item in mechanical_assets(state, actor):
        if not any(x.id == item.id for x in own):
            own.append(
                AssetView(
                    id=item.id,
                    name=item.name,
                    family=item.family,
                    damaged=item.damaged,
                    void=item.void,
                )
            )
    return tuple(own)


def intact_assets(
    state: GameState, actor: ActorRef, bindings: tuple[ProfileBinding, ...]
) -> tuple[AssetView, ...]:
    return tuple(x for x in assets(state, actor, bindings) if not x.damaged)


def resource_sha(state: GameState, actor: ActorRef, bindings: tuple[ProfileBinding, ...]) -> str:
    actual = resolve(state, actor, bindings, require_current_profile=False)
    body = actual.model_dump(mode="json") | dict(
        assets=[x.model_dump(mode="json") for x in assets(state, actor, bindings)]
    )
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def end_actor_casts(original: GameState, actor: ActorRef, event: str) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    for index, cast in enumerate(state.scene_casts):
        if any(x.actor == actor for x in cast.roles):
            state.scene_casts[index] = cast.model_copy(
                update=dict(
                    roles=tuple(x for x in cast.roles if x.actor != actor),
                    revision=cast.revision + 1,
                    adjudicator=None if cast.adjudicator == actor else cast.adjudicator,
                )
            )
    state.facts.append(
        dict(kind="battle_actor_cast_ended", actor=actor.model_dump_json(), event=event)
    )
    return state


def original_ended(state: GameState, actor: ActorRef) -> bool:
    if any(x.actor == actor for x in state.career_archives) or any(
        x.actor == actor for x in state.handler_archives
    ):
        return True
    if actor.kind == "external_pilot":
        harpy = next((x for x in state.harpy_states if x.id == actor.entity), None)
        if harpy is not None:
            return not harpy.alive
    if state.world is not None:
        rows = {
            "npc": state.world.npcs,
            "gorgon": state.world.gorgons,
            "external_pilot": state.world.pilots,
        }.get(actor.kind, ())
        return any(x.id == actor.entity and not getattr(x, "alive", True) for x in rows)
    return False


def owned_asset(
    state: GameState,
    actor: ActorRef,
    identity: str,
    bindings: tuple[ProfileBinding, ...],
    *,
    attacking: bool = False,
    allow_damaged: bool = False,
) -> AssetView:
    actual = resolve(state, actor, bindings)
    if attacking and actor.kind == "pilot":
        if actual.inside_frame is None:
            raise ValueError("Record the actual original body's cockpit state before combat")
        if not actual.piloting and any(
            x.id == identity and x.family == "frame" for x in actual.assets
        ):
            raise ValueError("Outside her Frame the Girl fights with actual Girl Assets")
    asset = next(
        (
            x
            for x in assets(state, actor, bindings)
            if x.id == identity and (allow_damaged or not x.damaged)
        ),
        None,
    )
    if asset is None:
        raise ValueError("Choose an actual undamaged owned Asset")
    if attacking and actor.kind == "pilot":
        if actual.inside_frame is None:
            raise ValueError("Record the actual original body's cockpit state before combat")
        if not actual.piloting and asset.family != "girl":
            raise ValueError("Outside her Frame the Girl fights with actual Girl Assets")
    return asset


def core_available(
    state: GameState,
    target: ActorRef,
    attacker: ActorRef,
    bindings: tuple[ProfileBinding, ...],
) -> str:
    actual = resolve(state, target, bindings)
    if target.kind == "gorgon":
        from girlframe.engine.m3_leviathan import require_layers_clear

        assert state.world is not None
        require_layers_clear(next(x for x in state.world.gorgons if x.id == target.entity))
        if not actual.core_exposed:
            raise ValueError("Expose this actual Gorgon's Core before a decisive strike")
        return "gorgon:" + target.entity
    if actual.inside_frame is None and target.kind in ("pilot", "external_pilot"):
        raise ValueError("Establish actual cockpit context before striking the Core")
    if actual.inside_frame:
        placement = next((x for x in state.placements if x.actor == target), None)
        carrier = placement.occupied_frame_owner or target if placement else target
        frame = actual.occupied_frame_instance or actual.frame_instance
        exposures = [
            x
            for x in state.facts
            if x.get("kind") == "battle_frame_exposure"
            and x.get("target") == carrier.model_dump_json()
            and x.get("frame") == frame
        ]
        if not exposures and not actual.core_exposed:
            raise ValueError(
                "Expose the original occupied Frame's Core through actual source facts"
            )
        return exposures[-1]["event"] if exposures else "actual-exposed:" + target.token
    return "unarmored:" + target.token


def expose_frame(
    original: GameState,
    target: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    event: str,
    account: str,
    *,
    opponent: ActorRef | None = None,
    willing: bool = False,
    tag: str | None = None,
    scene: str | None = None,
) -> GameState:
    """Trusted source adjudication validates every mechanical exposure condition itself."""
    state = GameState.model_validate_json(original.model_dump_json())
    actual = resolve(state, target, bindings)
    if target.kind != "pilot" or not actual.inside_frame or actual.frame_instance is None:
        raise ValueError(
            "Expose the actual occupied canonical Frame, not a parked or invented body"
        )
    placement = next((x for x in state.placements if x.actor == target), None)
    if placement is None or placement.occupied_frame_owner is not None:
        raise ValueError("The actual carrier's Pilot owns this Frame exposure")
    sheet = state.sheets[target.entity]
    enemy = resolve(state, opponent, bindings) if opponent is not None else None
    known_tag = next((x for x in sheet.tags if x.id == tag), None) if tag else None
    source_cast = next((x for x in state.scene_casts if x.id == scene and x.open), None)
    if tag is not None and (
        known_tag is None
        or enemy is None
        or enemy.controller not in known_tag.observers
        or known_tag.rejection_pending
        or enemy.controller == actual.controller
        or known_tag.scene_used == scene
        or source_cast is None
        or not any(
            x.actor == target and x.controller == actual.controller for x in source_cast.roles
        )
        or not any(
            x.actor == opponent and x.controller == enemy.controller for x in source_cast.roles
        )
    ):
        raise ValueError(
            "Another actual scene human must be able to mark this unused observed Girl Tag"
        )
    girls = [x for x in sheet.assets if x.family == "girl"]
    identities = list(sheet.identities)
    record = FrameExposure(
        owner=target,
        frame_instance=actual.frame_instance,
        opponent=opponent,
        source_event=event,
        willing=willing,
        tag=tag,
        scene=scene if tag else None,
        intense=opponent is not None and depth(state, target, opponent) == 2,
        girl_assets=bool(girls) and all(x.damaged for x in girls),
        identities=bool(identities) and all(x.marked for x in identities),
        account=account,
    )
    state.facts.append(
        dict(
            kind="battle_frame_exposure",
            target=target.model_dump_json(),
            frame=actual.frame_instance,
            opponent=opponent.model_dump_json() if opponent else "",
            event=event,
            body=record.model_dump_json(),
        )
    )
    return state


def damage(
    original: GameState,
    target: ActorRef,
    identity: str | None,
    bindings: tuple[ProfileBinding, ...],
    event: str,
    *,
    opponent: ActorRef | None = None,
    indirect: bool = False,
    inside_frame: bool | None = None,
) -> tuple[GameState, tuple[Required, ...]]:
    """Apply actual damage, or return the exact printed owner's replacement obligation.

    This trusted reducer deliberately does not append SQL work before its real event exists.
    The service commits returned obligations with the original source event afterward.
    """
    state = GameState.model_validate_json(original.model_dump_json())
    from girlframe.engine.m3_doctor import require_harm_allowed

    protection = require_harm_allowed(state, target, opponent)
    if protection is not None:
        state.facts.append(
            dict(
                kind="doctor_protector_harm",
                patient=target.model_dump_json(),
                protector=protection.protector.model_dump_json(),
                event=event,
            )
        )
    actual = resolve(state, target, bindings)
    kind = category(state, target)
    if not event.strip():
        raise ValueError("Combat effects require their actual immutable source event")
    if kind == "handler" and actual.rules == "handler_girl":
        from girlframe.engine.m3_items import damage_mechanical_asset

        if identity is None or opponent is None:
            raise ValueError("Actual HandlerGirl damage needs its real owned Asset and opponent")
        return damage_mechanical_asset(
            state, target, identity, event, opponent=opponent, inside_frame=inside_frame
        ), ()
    if kind == "handler":
        if identity is not None:
            owned_asset(state, target, identity, bindings)
        return state, (
            Required(
                kind="director_damage" if target.kind == "npc" else "handler_damage",
                target=target,
                opponent=opponent,
                asset=identity,
                source_pdf=15,
            ),
        )
    if kind == "npc":
        if identity is not None:
            owned_asset(state, target, identity, bindings)
        return state, (
            Required(
                kind="npc_damage", target=target, opponent=opponent, asset=identity, source_pdf=15
            ),
        )
    if identity is None:
        raise ValueError("Damage an actual chosen owned Asset")
    asset = owned_asset(state, target, identity, bindings)
    if target.kind == "gorgon":
        assert state.world is not None
        state.world = damage_gorgon(state.world, target.entity, identity, indirect=indirect)
        return state, ()
    if target.kind == "pilot":
        if actual.inside_frame is None:
            raise ValueError("Record real cockpit occupancy before damage can exhaust a family")
        sheet = state.sheets[target.entity]
        if asset.family == "girl" and not actual.inside_frame and opponent is None:
            if not any(
                x.family == "girl" and not x.damaged and x.id != identity for x in sheet.assets
            ):
                raise ValueError("Last Girl Asset requires the actual opponent for Helpless")
        for item in sheet.assets:
            if item.id == identity:
                item.damaged = True
        sheet.revision += 1
        if (
            asset.family == "girl"
            and not actual.inside_frame
            and not any(x.family == "girl" and not x.damaged for x in sheet.assets)
        ):
            assert opponent is not None
            state = make_helpless(state, target, opponent, event)
        if asset.family == "frame" and not any(
            x.family == "frame" and not x.damaged for x in sheet.assets
        ):
            return state, (
                Required(kind="defeat", target=target, opponent=opponent, source_pdf=15),
            )
        return state, ()
    if kind == "harpy" and target.kind == "external_pilot":
        from girlframe.engine.m3_harpy_resources import assets as harpy_assets
        from girlframe.engine.m3_harpy_resources import set_assets

        original_assets = harpy_assets(state, target)
        last_girl = asset.family == "girl" and not any(
            x.family == "girl" and not x.damaged and x.id != identity for x in original_assets
        )
        if last_girl and actual.inside_frame is None:
            raise ValueError(
                "Record the actual Harpy body/link position before its last Girl Asset"
            )
        if last_girl and not actual.inside_frame and opponent is None:
            raise ValueError("Last Harpy Girl Asset needs its actual opponent for Helpless")
        changed_assets = tuple(
            x.model_copy(update={"damaged": True}) if x.id == identity else x
            for x in original_assets
        )
        state = set_assets(state, target, changed_assets, event=event)
        if last_girl and not actual.inside_frame:
            assert opponent is not None
            state = make_helpless(state, target, opponent, event)
        if asset.family == "frame" and not any(
            x.family == "frame" and not x.damaged for x in changed_assets
        ):
            return state, (
                Required(kind="harpy_defeat", target=target, opponent=opponent, source_pdf=182),
            )
        return state, ()
    if state.world is None:
        raise ValueError("Recover the actual external Pilot resource record")
    external = next(x for x in state.world.pilots if x.id == target.entity)
    if not any(x.id == identity for x in external.assets):
        raise ValueError("Use the external Pilot's original actual Asset")
    last_external_girl = asset.family == "girl" and not any(
        x.family == "girl" and not x.damaged and x.id != identity for x in external.assets
    )
    if last_external_girl and (
        actual.inside_frame is None or actual.inside_frame is False and opponent is None
    ):
        raise ValueError("The original external Girl's actual occupancy and opponent are required")
    changed_external = external.model_copy(
        update={
            "assets": tuple(
                x.model_copy(update={"damaged": True}) if x.id == identity else x
                for x in external.assets
            )
        }
    )
    state.world = state.world.model_copy(
        update={
            "pilots": tuple(
                changed_external if x.id == external.id else x for x in state.world.pilots
            )
        }
    )
    if asset.family == "frame" and not any(
        x.family == "frame" and not x.damaged for x in changed_external.assets
    ):
        return state, (
            Required(
                kind="harpy_defeat" if external.kind == "harpy" else "defeat",
                target=target,
                opponent=opponent,
                source_pdf=182 if external.kind == "harpy" else 15,
            ),
        )
    if last_external_girl and not actual.inside_frame:
        assert opponent is not None
        state = make_helpless(state, target, opponent, event)
    return state, ()
