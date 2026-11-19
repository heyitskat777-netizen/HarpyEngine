"""An original Scientist's private laboratory exchange of an actual Void Asset."""

from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_core import install
from girlframe.engine.m3_handler_private_scene import LabExchange
from girlframe.engine.m3_janus_storage import ids as stored_void
from girlframe.engine.m3_promotional_opportunity import in_responsibility
from girlframe.engine.m3_void import FINAL
from girlframe.services.onboarding import WorkflowError


def lab_at(state: GameState, cell: tuple[int, int] | None) -> str | None:
    return (
        next(
            (
                x.id
                for x in state.world.locations
                if x.cell == cell
                and x.kind == "base"
                and x.foundation_operational
                and in_responsibility(state, x.cell)
            ),
            None,
        )
        if state.world is not None
        else None
    )


def eligible(state: GameState, girl: ActorRef) -> tuple[tuple[str, str], ...]:
    sheet = state.sheets.get(girl.entity)
    if sheet is None or sheet.character_id != girl.incarnation:
        return ()
    bound = stored_void(state, girl)
    return tuple(
        (x.id, x.name)
        for x in sheet.assets
        if x.family == "girl" and x.void and x.intrinsic is None and x.id not in bound
    )


def excise(
    state: GameState,
    girl: ActorRef,
    picked: str,
    proposal: LabExchange,
    event: str,
) -> str:
    if picked not in dict(eligible(state, girl)) or any(
        x.actor == girl and x.stage not in FINAL for x in state.void_thresholds
    ):
        raise WorkflowError(
            "Choose an actual ordinary Void-touched Girl Asset with no active threshold"
        )
    original = state.sheets[girl.entity]
    remaining = original.model_copy(
        update=dict(assets=[x for x in original.assets if x.id != picked])
    )
    replacement = AssetState(
        id=event + ":scientist-exchange",
        family="girl",
        name=proposal.name.strip(),
        description=proposal.description.strip(),
    )
    result = install(remaining, replacement, state=state)
    state.sheets[girl.entity] = result.sheet
    return replacement.id
