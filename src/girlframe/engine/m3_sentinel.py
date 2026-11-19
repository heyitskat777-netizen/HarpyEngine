"""Corrupted terrain is a lasting map effect from an actual Sentinel."""

from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Cell, CorruptedCell, Gorgon, World

RULE = "gorgon-type.sentinel.sentinel-type"


def already_corrupted(world: World, cell: Cell | None) -> bool:
    return cell is not None and any(x.cell == cell for x in world.corrupted_cells)


def corrupt(
    world: World, actual: Gorgon, cell: Cell | None, action: str, scene: str, event: str
) -> World:
    if (
        cell is None
        or not world.board.contains(cell)
        or not actual.alive
        or "sentinel" not in actual.types
    ):
        raise ValueError("Use the actual living Sentinel's occupied map square")
    if already_corrupted(world, cell):
        raise ValueError("This actual square is already Corrupted")
    value = CorruptedCell(cell=cell, sentinel=actual.id, action=action, scene=scene, event=event)
    return update(world, corrupted_cells=(*world.corrupted_cells, value))
