"""Printed Asset properties follow actual source identity, never a custom label."""

from girlframe.engine.m2 import AssetState, GameState, PilotSheet


def wyvern_intrinsic(sheet: PilotSheet, asset: AssetState) -> bool:
    if (
        asset.family != "frame"
        or sheet.frame != "WYVERN 0.4"
        or not any(x.id == asset.id for x in sheet.assets)
    ):
        return False
    # Old canonical saves have actual generated IDs, but no semantic marker.
    # Prove the actual initial/replacement source instead of trusting a name.
    if sheet.frame_runtime is not None:
        return asset.id == sheet.frame_runtime.id + ":intrinsic"
    return (
        sheet.review.creation.frame_playbook == "WYVERN 0.4"
        and sheet.review.creation.intrinsic_frame_assets == ("Enormous",)
        and asset.id == "frame:intrinsic:0"
    )


def counts_toward_limit(sheet: PilotSheet, asset: AssetState) -> bool:
    return not wyvern_intrinsic(sheet, asset) and asset.battery_asset is None


def can_replace_at_limit(sheet: PilotSheet, asset: AssetState) -> bool:
    return not asset.void and not wyvern_intrinsic(sheet, asset) and asset.battery_asset is None


def frame_capacity(sheet: PilotSheet, state: GameState | None = None) -> int:
    if state is None or sheet.character_id is None:
        return 5
    current = state.sheets.get(str(sheet.owner))
    if (
        current is None
        or current.character_id != sheet.character_id
        or current.frame != sheet.frame
        or (current.frame_runtime.id if current.frame_runtime else None)
        != (sheet.frame_runtime.id if sheet.frame_runtime else None)
    ):
        return 5
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_modular import held

    actor = ActorRef(kind="pilot", entity=str(sheet.owner), incarnation=sheet.character_id)
    return 6 if held(state, actor) is not None else 5
