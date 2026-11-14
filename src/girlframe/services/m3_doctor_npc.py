"""Finite Doctor effects on the actual NPC, never its controller's Pilot sheet."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.engine import m3_stim_sex as stim
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_mockingbird import actor_tags
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def support_contact(
    game: "GameService", c: Connection, state: GameState, doctor: ActorRef, target: ActorRef
) -> dict[str, Any]:
    """A visible original physical NPC can shelter Doctor without acquiring a sheet."""
    from girlframe.services.m3_actor_history import snapshot_profiles

    bound = snapshot_profiles(c, game.store.campaign_id, state)
    protector = resolve(state, target, bound, require_current_profile=False)
    own = resolve(state, doctor, bound, require_current_profile=False)
    original = (
        next((npc for npc in state.world.npcs if npc.id == target.entity), None)
        if state.world
        else None
    )
    if (
        target.kind != "npc"
        or original is None
        or original.source_kind is not None
        or not original.alive
        or protector.rules != "npc"
        or protector.vessel_id is None
        or protector.cell is None
        or own.cell != protector.cell
        or protector.offstage_source
        or own.offstage_source
        or protector.custody not in (None, "free")
        or own.custody not in (None, "free")
    ):
        raise WorkflowError("Use the actual reachable living NPC protector and original body")
    shared_enclosure = (
        protector.inside_frame is True
        and protector.occupied_frame_instance is not None
        and own.inside_frame is True
        and own.occupied_frame_instance == protector.occupied_frame_instance
    )
    outside = protector.inside_frame is not True and protector.occupied_frame_instance is None
    operating = (
        own.piloting is True
        and own.occupied_frame_instance is not None
        and own.occupied_frame_instance == own.frame_instance
    )
    if not (shared_enclosure or outside and (own.inside_frame is False or operating)):
        raise WorkflowError("Establish actual hiding behind this NPC across the body enclosures")
    return dict(
        target_vessel=protector.vessel_id,
        doctor_vessel=own.vessel_id,
        cell=list(protector.cell),
        enclosure=protector.occupied_frame_instance if shared_enclosure else None,
        operating_frame=own.frame_instance if operating else None,
    )


def contact(
    game: "GameService", c: Connection, state: GameState, doctor: ActorRef, target: ActorRef
) -> dict[str, Any]:
    """Prove a real original body and present physical reach, not an NPC rules label."""
    from girlframe.services.m3_actor_history import snapshot_profiles
    from girlframe.services.m3_changeling_body import _fact

    bound = snapshot_profiles(c, game.store.campaign_id, state)
    patient = resolve(state, target, bound, require_current_profile=False)
    own = resolve(state, doctor, bound, require_current_profile=False)
    # This canonical source proof rejects Frame-created Wraith minds and preserves
    # genuine reset hardware instead of reclassifying it as an ordinary human.
    body = _fact(game, c, state, target)
    if (
        target.kind != "npc"
        or patient.rules != "npc"
        or body.kind not in ("human_npc", "other")
        or patient.vessel_id is None
        or body.vessel != patient.vessel_id
        or patient.cell is None
        or own.cell != patient.cell
        or patient.offstage_source
        or own.offstage_source
        or patient.custody not in (None, "free")
        or own.custody not in (None, "free")
    ):
        raise WorkflowError("Recover the actual physical NPC body and current Nanobot reach")
    shared_enclosure = (
        patient.inside_frame is True
        and patient.occupied_frame_instance is not None
        and own.inside_frame is True
        and own.occupied_frame_instance == patient.occupied_frame_instance
    )
    outside_patient = patient.inside_frame is not True and patient.occupied_frame_instance is None
    operating_frame = (
        own.piloting is True
        and own.occupied_frame_instance is not None
        and own.occupied_frame_instance == own.frame_instance
    )
    if not (shared_enclosure or outside_patient and (own.inside_frame is False or operating_frame)):
        raise WorkflowError("Establish real Nanobot reach across the actual body enclosures")
    return dict(
        body_fact=body.id,
        body_event=body.event,
        target_vessel=patient.vessel_id,
        doctor_vessel=own.vessel_id,
        cell=list(patient.cell),
        enclosure=patient.occupied_frame_instance if shared_enclosure else None,
        operating_frame=own.frame_instance if operating_frame else None,
    )


def effects(state: GameState, target: ActorRef) -> list[dict[str, str]]:
    """Current Tags, explicit Helplessness and individually source-bound Stim physiology."""
    return (
        [
            dict(id="tag:" + tag.id, label="Remove Tag: " + tag.label, source=fingerprint(tag))
            for tag in actor_tags(state, target)
            if not tag.rejection_pending
        ]
        + [
            dict(
                id="helpless:" + condition.id,
                label="Remove actual source Helplessness",
                source=fingerprint(condition),
            )
            for condition in state.helpless_conditions
            if condition.active and condition.subject == target
        ]
        + [
            dict(
                id="stim_helpless:" + effect.id,
                label="Remove Stim physiological Helplessness",
                source=fingerprint(effect),
            )
            for effect in stim.helpless_effects(state, target)
        ]
    )


def select(
    game: "GameService", c: Connection, state: GameState, target: ActorRef, effect: str
) -> dict[str, str]:
    selected = next((x for x in effects(state, target) if x["id"] == effect), None)
    if selected is None:
        raise WorkflowError("Select an actual current NPC Tag or supported Helpless source")
    if effect.startswith("stim_helpless:"):
        from girlframe.services.m3_stim_sex import prove_effect

        actual = prove_effect(game, c, state, effect.removeprefix("stim_helpless:"))
        if (
            target.kind != "npc"
            or actual.kind != "helpless"
            or actual.target != target
            or fingerprint(actual) != selected["source"]
            or actual not in stim.helpless_effects(state, target)
        ):
            raise WorkflowError("Recover this original NPC's actual active Stim Helpless source")
    return selected


def remove(
    game: "GameService",
    c: Connection,
    state: GameState,
    target: ActorRef,
    selected: dict[str, Any],
    event: str,
    action: str,
) -> None:
    current = select(game, c, state, target, selected["id"])
    if current != selected:
        raise WorkflowError("Refresh the changed original NPC effect before confirming care")
    effect = selected["id"]
    if effect.startswith("tag:"):
        assert state.world is not None
        identity = effect.removeprefix("tag:")
        state.world = state.world.model_copy(
            update={
                "npcs": tuple(
                    npc.model_copy(update={"tags": tuple(t for t in npc.tags if t.id != identity)})
                    if npc.id == target.entity
                    else npc
                    for npc in state.world.npcs
                )
            }
        )
    elif effect.startswith("stim_helpless:"):
        original = next(
            x
            for x in stim.helpless_effects(state, target)
            if x.id == effect.removeprefix("stim_helpless:")
        )
        stim.put(
            state,
            stim.HelplessRecovery(
                id="nanobot:" + action + ":" + original.id,
                effect=original.id,
                effect_event=original.event,
                target=target,
                drug=original.drug,
                doctor_action=action,
                event=event,
            ),
        )
    else:
        identity = effect.removeprefix("helpless:")
        state.helpless_conditions = [
            condition.model_copy(update=dict(active=False, recovery_event=event))
            if condition.id == identity and condition.subject == target
            else condition
            for condition in state.helpless_conditions
        ]
    state.facts.append(
        dict(
            kind="doctor_npc_effect_removed",
            patient=target.model_dump_json(),
            effect=effect,
            source=selected["source"],
            event=event,
            action=action,
        )
    )


def award_heat(
    game: "GameService",
    c: Connection,
    state: GameState,
    target: ActorRef,
    amount: int,
    action: str,
    event: str,
) -> dict[str, Any]:
    """Compatibility entry for existing Nanobot callers and receipt metadata."""
    from girlframe.services.m3_npc_resources import award_heat as award_npc_heat

    return award_npc_heat(game, c, state, target, amount, action, event)


def _assets(
    game: "GameService", c: Connection, state: GameState, target: ActorRef
) -> list[dict[str, Any]]:
    from girlframe.engine.m3_items import actual_asset
    from girlframe.services.m3_items import prove_item

    result = []
    for item in state.held_items:
        if item.holder != target or item.location_mode != "carried":
            continue
        asset = actual_asset(state, item)
        if asset is None:
            continue
        prove_item(c, game, state, item.id)
        result.append(
            dict(
                id=item.id,
                asset_id=asset.id,
                name=asset.name,
                damaged=asset.damaged,
                void=asset.void,
            )
        )
    return result


def patient_options(
    game: "GameService",
    c: Connection,
    state: GameState,
    target: ActorRef,
) -> dict[str, Any]:
    from girlframe.services.m3_npc_resources import prove

    value = prove(game, c, state, target)
    return dict(
        resource=value.id,
        heat=value.heat,
        assets=_assets(game, c, state, target),
        identities=[x.model_dump(mode="json") for x in value.identities],
        effects=effects(state, target),
    )


def apply_patient(
    game: "GameService",
    c: Connection,
    state: GameState,
    target: ActorRef,
    *,
    assets: tuple[str, ...],
    repair: int,
    identity: str | None,
    effect: dict[str, Any] | None,
    event: str,
    action: str,
) -> dict[str, Any]:
    """Validate all real patient choices before repairing/unmarking/removing anything."""
    from girlframe.engine import m3_npc_resources as resources
    from girlframe.engine.m2 import AssetState
    from girlframe.services.m3_npc_resources import prove

    value = prove(game, c, state, target, in_flight=event)
    actual = _assets(game, c, state, target)
    damaged = {row["id"] for row in actual if row["damaged"]}
    if (
        repair not in (0, 1, 2)
        or len(assets) != min(repair, len(damaged))
        or len(set(assets)) != len(assets)
        or not set(assets) <= damaged
    ):
        raise WorkflowError("Choose the actual number of existing damaged NPC Assets to repair")
    try:
        changed = resources.unmark(value, identity, event)
    except ValueError as exc:
        raise WorkflowError(str(exc)) from None
    if effect is not None and select(game, c, state, target, effect["id"]) != effect:
        raise WorkflowError("Refresh the original selected NPC effect")
    if effect is not None:
        remove(game, c, state, target, effect, event, action)
    repaired = []
    for item in state.held_items:
        if item.id not in assets:
            repaired.append(item)
            continue
        asset = AssetState.model_validate_json(item.asset_json or "{}")
        asset.damaged = False
        repaired.append(
            item.model_copy(update=dict(asset_json=asset.model_dump_json(), state_event=event))
        )
    state.held_items = repaired
    resources.put(state, changed)
    return dict(
        resource=value.id,
        assets=list(assets),
        identity=identity,
        effect=effect["id"] if effect else None,
    )
