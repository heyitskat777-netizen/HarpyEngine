"""The original Girl decides whether to add an actual private find as an Asset."""

from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_state import ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_contraband_state import ContrabandFind
from girlframe.engine.m3_core import install
from girlframe.engine.m3_requisition_state import GirlAsset


def claim(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    find: ContrabandFind,
    expected: str,
    taken: bool,
    choice: GirlAsset | None,
    account: str,
    response_event: str,
) -> GameState:
    if choice is not None:
        choice = GirlAsset.model_validate_json(choice.model_dump_json())
    state = GameState.model_validate_json(original.model_dump_json())
    if type(taken) is not bool or find.taken is not None or find not in state.contraband_finds:
        raise ValueError("Choose only your original unused actual contraband find")
    actor = resolve(state, find.actor, bindings, require_current_profile=False)
    if actor.rules != "girl_frame" or actor.source_sha256 != expected:
        raise ValueError("STALE_CONTRABAND: confirm your actual original Girl's current resources")
    asset_id = "contraband:" + find.id if taken else None
    if taken:
        if (
            choice is None
            or not choice.name.strip()
            or not choice.description.strip()
            or not account.strip()
        ):
            raise ValueError("Confirm the actual find and name/describe your chosen Girl Asset")
        assert asset_id is not None
        from girlframe.engine.m3_janus_storage import ids as stored_ids

        result = install(
            state.sheets[find.actor.entity],
            AssetState(
                id=asset_id,
                family="girl",
                name=choice.name.strip(),
                description=choice.description.strip(),
                concealed=True,
            ),
            replace=choice.replace,
            effective_void=stored_ids(state, find.actor),
        )
        state.sheets[find.actor.entity] = result.sheet
    elif choice is not None:
        raise ValueError("Declining the optional Asset cannot supply acquisition choices")
    updated = ContrabandFind.model_validate_json(
        find.model_copy(
            update={
                "taken": taken,
                "choice": choice,
                "asset_id": asset_id,
                "response_event": response_event,
                "account": account.strip(),
            }
        ).model_dump_json()
    )
    state.contraband_finds = [updated if x.id == find.id else x for x in state.contraband_finds]
    return state


def share(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    find: ContrabandFind,
    expected: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    actor = resolve(state, find.actor, bindings, require_current_profile=False)
    if (
        find not in state.contraband_finds
        or actor.source_sha256 != expected
        or find.taken is not True
    ):
        raise ValueError("STALE_CONTRABAND: reopen the actual claimed Asset")
    sheet = state.sheets[find.actor.entity]
    asset = next((x for x in sheet.assets if x.id == find.asset_id and x.concealed), None)
    if asset is None or "assets" not in sheet.public_fields:
        raise ValueError("This actual Asset is not concealed in a sheet that publishes Assets")
    asset.concealed = False
    sheet.revision += 1
    return state
