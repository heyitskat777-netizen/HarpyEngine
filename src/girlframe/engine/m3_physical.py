"""Original physical facts need actual ownership and a distinct review source."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorView, ProfileBinding
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_physical_state import InitialPlacement, Placement


def validate(
    state: GameState,
    bindings: tuple[ProfileBinding, ...],
    proposal: InitialPlacement,
) -> ActorView:
    proposal = InitialPlacement.model_validate_json(proposal.model_dump_json())
    actor = resolve(state, proposal.actor, bindings, require_current_profile=False)
    if actor.rules != "girl_frame" or actor.frame_instance != proposal.frame_instance:
        raise ValueError("STALE_PLACEMENT: recover the actual original character and Frame")
    if any(x.actor == proposal.actor for x in state.placements):
        raise ValueError("Initial placement cannot reset or move an already placed body")
    if state.world is None or any(
        not state.world.board.contains(cell) for cell in (proposal.girl_cell, proposal.frame_cell)
    ):
        raise ValueError("Record both actual positions on the current canonical map")
    if proposal.mode == "piloting" and actor.frame_scrapped:
        raise ValueError(
            "A scrapped Frame cannot be piloted; occupancy is a separate physical fact"
        )
    return actor


def initial(
    original: GameState,
    bindings: tuple[ProfileBinding, ...],
    proposal: InitialPlacement,
    vessel: str,
    proposed_event: str,
    source_event: str,
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    proposal = InitialPlacement.model_validate_json(proposal.model_dump_json())
    validate(state, bindings, proposal)
    if any(x.vessel_id == vessel for x in state.placements):
        raise ValueError("An initial vessel cannot be assigned to a different actual character")
    state.placements.append(
        Placement(
            actor=proposal.actor,
            vessel_id=vessel,
            frame_instance=proposal.frame_instance,
            girl_cell=proposal.girl_cell,
            frame_cell=proposal.frame_cell,
            mode=proposal.mode,
            proposed_event=proposed_event,
            source_event=source_event,
            account=proposal.account,
        )
    )
    return state
