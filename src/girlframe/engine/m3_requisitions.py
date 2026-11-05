"""Paid Asset Installment: actual owned resources, source selection and immutable receipt."""

from girlframe.engine.creation_catalog import CATALOG
from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_state import ActorRef, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_core import install
from girlframe.engine.m3_requisition_state import Installation, Receipt


def asset_name(choice: Installation) -> str:
    if choice.from_frame is None:
        return choice.name.strip()
    frame = "JANUS" if choice.from_frame == "JANUS-B" else choice.from_frame
    book = CATALOG.get(frame)
    if (
        book is None
        or book["family"] != "frame"
        or choice.index is None
        or not 0 <= choice.index < len(book["assets"])
    ):
        raise ValueError("Choose a printed Asset from an official base Frame or write your own")
    return str(book["assets"][choice.index])


def purchase(
    original: GameState,
    actor: ActorRef,
    bindings: tuple[ProfileBinding, ...],
    expected: str,
    choice: Installation,
    identity: str,
    source_event: str,
) -> GameState:
    choice = Installation.model_validate_json(choice.model_dump_json())
    from girlframe.engine.m3_janus_storage import ids as stored_ids

    if choice.replace in stored_ids(original, actor):
        raise ValueError("An actual active stored-Void Asset cannot be replaced at the cap")
    state = GameState.model_validate_json(original.model_dump_json())
    view = resolve(state, actor, bindings)
    if (
        view.rules != "girl_frame"
        or actor.kind != "pilot"
        or view.frame_scrapped
        or view.source_sha256 != expected
    ):
        raise ValueError("STALE_REQUISITION: confirm the actual Girl and current Frame resources")
    if any(x.id == identity or x.source_event == source_event for x in state.requisitions):
        raise ValueError("This actual purchase source has already been applied")
    sheet = state.sheets[actor.entity]
    if sheet.permissions < 1:
        raise ValueError("This Asset Installment costs one available Permission")
    asset = AssetState(
        id="requisition:" + identity,
        family="frame",
        name=asset_name(choice),
        description=choice.description.strip(),
    )
    result = install(
        sheet, asset, replace=choice.replace, effective_void=stored_ids(state, actor), state=state
    )
    result.sheet.permissions -= 1
    state.sheets[actor.entity] = result.sheet
    assert view.frame_instance is not None
    state.requisitions.append(
        Receipt(
            id=identity,
            kind="asset_installment",
            actor=actor,
            frame_instance=view.frame_instance,
            price=1,
            asset_id=asset.id,
            installation=choice,
            source_event=source_event,
        )
    )
    return state
