"""Actual Rebel Group merger preserves people, physical assets and source history."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_world import update

RULE = "strain.rebellion.endgame.2"


def merge(
    original: GameState, source: str, receiving: str, work: str, event: str, account: str
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    world = state.world
    if world is None or source == receiving or not account.strip():
        raise ValueError("Choose two distinct actual active Rebel Groups and describe their merger")
    groups = {x.id: x for x in world.factions if x.kind == "rebel" and x.active}
    if source not in groups or receiving not in groups:
        raise ValueError("The selected original and receiving Rebel Groups must still be active")
    if any(x.get("kind") == "rebel_merger" and x.get("work") == work for x in state.facts):
        raise ValueError("This actual group merger is already saved")

    def affiliation(value: str | None) -> str | None:
        return receiving if value == source else value

    state.world = update(
        world,
        factions=tuple(
            x.model_copy(update=dict(active=False, underfunded=True))
            if x.id == source
            else x.model_copy(
                update=dict(cells=tuple(sorted(set(x.cells) | set(groups[source].cells))))
            )
            if x.id == receiving
            else x
            for x in world.factions
        ),
        npcs=tuple(
            x.model_copy(
                update=dict(
                    faction=affiliation(x.faction),
                    secret_factions=tuple(
                        dict.fromkeys(receiving if v == source else v for v in x.secret_factions)
                    ),
                )
            )
            for x in world.npcs
        ),
        pilots=tuple(
            x.model_copy(update=dict(faction=affiliation(x.faction))) for x in world.pilots
        ),
        npc_recruitment=tuple(
            x.model_copy(update=dict(faction=receiving)) if x.faction == source else x
            for x in world.npc_recruitment
        ),
    )
    state.facts.append(
        dict(
            kind="rebel_merger",
            source=source,
            receiving=receiving,
            work=work,
            event=event,
            account=account,
        )
    )
    return state
