"""The printed Aggressive introduction casualty shared by Strain arrivals."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Gorgon, Npc


def aggressive_casualty(
    state: GameState, incoming: Gorgon, victim: Npc, work: str, event: str, account: str
) -> GameState:
    from girlframe.engine.m3_battle import category, end_actor_casts
    from girlframe.engine.m3_enforcer import end_grasps
    from girlframe.engine.m3_physical import interrupt_journeys

    ref = ActorRef(kind="npc", entity=victim.id)
    if category(state, ref) == "harpy":
        raise ValueError("A captured Harpy Core is not an ordinary NPC introduction victim")
    if "director" in victim.jobs:
        from girlframe.engine.m3_battle_director import die

        state = die(state, ref, event, account)
    else:
        state = end_actor_casts(
            end_grasps(interrupt_journeys(state, ref, event, account), ref, event), ref, event
        )
        assert state.world is not None
        state.world = update(
            state.world,
            npcs=tuple(
                x.model_copy(update={"alive": False}) if x.id == victim.id else x
                for x in state.world.npcs
            ),
        )
    state.facts.append(
        dict(
            kind="aggressive_introduction_consumed",
            source_work=work,
            source_event=event,
            gorgon=incoming.id,
            followup="aggressive_introduction_npc_death",
            source_pdf="165",
            victim=ref.model_dump_json(),
            original_body=victim.model_dump_json(),
            account=account,
        )
    )
    return state
