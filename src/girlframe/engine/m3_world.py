"""Source-based world operations; fiction/choices remain explicit human inputs."""

from pydantic import Field

from girlframe.engine.m3_world_state import (
    AdversaryPilot,
    Board,
    Cell,
    Gorgon,
    GorgonClass,
    Location,
    Model,
    Npc,
    World,
)

CLASS_ASSETS: dict[GorgonClass, int] = {
    "aggressive": 6,
    "dormant": 3,
    "erratic": 4,
    "directed": 5,
    "sprite": 1,
    "benevolent": 2,
}


class Followup(Model):
    kind: str
    entity: str
    source_pdf: int


class Result(Model):
    world: World
    followups: tuple[Followup, ...] = ()


def update(world: World, **values: object) -> World:
    return World.model_validate_json(world.model_copy(update=values).model_dump_json())


def create(board: Board, locations: tuple[Location, ...], secret: Gorgon) -> World:
    if (
        sum(x.kind == "base" for x in locations) != 3
        or sum(x.kind == "city" for x in locations) < 2
        or sum(x.kind == "important" for x in locations) != 3
        or any(x.condition != "intact" for x in locations)
        or any(x.allegiance != "foundation" for x in locations)
    ):
        raise ValueError(
            "Start with three bases, at least two cities and three important locations"
        )
    if (
        secret.gorgon_class != "benevolent"
        or secret.revealed
        or not any(x.kind == "base" and x.cell == secret.cell for x in locations)
    ):
        raise ValueError("Place the unrevealed Class 0 at a real starting base")
    validate_initial_gorgon(secret)
    return World(board=board, locations=locations, gorgons=(secret,))


def validate_initial_gorgon(gorgon: Gorgon) -> None:
    if gorgon.destroyed_assets:
        raise ValueError("A newly introduced Gorgon cannot import destroyed Asset history")
    if len(gorgon.assets) != CLASS_ASSETS[gorgon.gorgon_class] + int(gorgon.sprite_group):
        raise ValueError("Use the printed Class Asset count, with two for a Sprite group")
    if not gorgon.alive or gorgon.exposed or any(x.damaged for x in gorgon.assets):
        raise ValueError(
            "A newly introduced Gorgon starts alive with an unexposed Core and intact Assets"
        )
    if (
        gorgon.core_strike_failed
        or gorgon.collateral_city is not None
        or gorgon.collateral_successes
        or gorgon.collateral_resolved
    ):
        raise ValueError("New Gorgons cannot import old combat conditions or triggered counters")


def introduce_gorgon(world: World, gorgon: Gorgon) -> Result:
    validate_initial_gorgon(gorgon)
    updated = update(world, gorgons=world.gorgons + (gorgon,))
    followups = (
        (Followup(kind="aggressive_introduction_npc_death", entity=gorgon.id, source_pdf=165),)
        if gorgon.gorgon_class == "aggressive"
        else ()
    )
    return Result(world=updated, followups=followups)


def introduce_npc(world: World, npc: Npc) -> World:
    if not npc.alive or npc.tags:
        raise ValueError(
            "Introduce a living NPC; source-specific initial Tags need their own event"
        )
    cities = {x.id for x in world.locations if x.kind == "city" and x.cell == npc.cell}
    applied = [x for x in world.npc_recruitment if x.city in cities]
    if applied:
        npc = npc.model_copy(
            update={
                "secret_factions": tuple(
                    sorted(set(npc.secret_factions) | {x.faction for x in applied})
                )
            }
        )
    return update(
        world,
        npcs=world.npcs + (npc,),
        npc_recruitment=tuple(x for x in world.npc_recruitment if x not in applied),
    )


def goal_cell(world: World, gorgon: Gorgon) -> Cell:
    goal = gorgon.goal
    if goal is None:
        raise ValueError("A Directed Gorgon needs its actual goal")
    if goal.kind == "cell":
        assert goal.cell is not None
        return goal.cell
    for entity in world.locations if goal.kind == "location" else world.npcs:
        if entity.id == goal.entity_id:
            return entity.cell
    raise ValueError("Resolve the missing goal before world advancement")


def distance(first: Cell, second: Cell) -> int:
    return max(abs(first[0] - second[0]), abs(first[1] - second[1]))


def directed_steps(world: World, gorgon: Gorgon) -> tuple[Cell, ...]:
    if gorgon.cell is None:
        raise ValueError("UNKNOWN_POSITION: record the actual Gorgon position before movement")
    target = goal_cell(world, gorgon)
    current = distance(gorgon.cell, target)
    if current == 0:
        return (gorgon.cell,)
    return tuple(
        cell
        for dx in (-1, 0, 1)
        for dy in (-1, 0, 1)
        if (dx, dy) != (0, 0)
        and world.board.contains(cell := (gorgon.cell[0] + dx, gorgon.cell[1] + dy))
        and distance(cell, target) < current
    )


def locate_gorgon(world: World, identity: str, cell: Cell, source_event: str) -> World:
    actual = next((x for x in world.gorgons if x.id == identity), None)
    if actual is None or actual.cell is not None:
        raise ValueError("Record only the actual missing initial Gorgon position")
    if not source_event or not world.board.contains(cell):
        raise ValueError("Record the actual source and a square on the current map")
    return update(
        world,
        gorgons=tuple(
            x.model_copy(update={"cell": cell, "position_event": source_event})
            if x.id == identity
            else x
            for x in world.gorgons
        ),
    )


def destroy(world: World, identity: str, *, gorgon_cause: bool) -> Result:
    target = next((x for x in world.locations if x.id == identity), None)
    if target is None or target.condition == "destroyed":
        raise ValueError(
            "Destroy a current location once; repeated destruction creates no new event"
        )
    territory = world.territory
    if gorgon_cause:
        territory |= frozenset(
            (target.cell[0] + dx, target.cell[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
        )
    updated = update(
        world,
        territory=territory,
        locations=tuple(
            x.model_copy(update={"condition": "destroyed"}) if x.id == identity else x
            for x in world.locations
        ),
    )
    followups = [Followup(kind="budget_structure_destroyed", entity=identity, source_pdf=150)]
    if any(
        x.kind == "base" and x.allegiance == "foundation" and x.condition != "destroyed"
        for x in world.locations
    ) and not any(
        x.kind == "base" and x.allegiance == "foundation" and x.condition != "destroyed"
        for x in updated.locations
    ):
        followups.append(
            Followup(kind="quadrant_lost_handler_outcome", entity=identity, source_pdf=122)
        )
    return Result(world=updated, followups=tuple(followups))


class Movement(Model):
    gorgon: str
    destination: Cell


class ClassChange(Model):
    gorgon: str
    replacement: Gorgon
    account: str = Field(min_length=1, max_length=1200)


def end_off_duty(
    world: World,
    period_id: str,
    movements: tuple[Movement, ...],
    changes: tuple[ClassChange, ...],
    *,
    present_gorgons: frozenset[str] | None = None,
) -> Result:
    if period_id in world.completed_off_duty or not period_id.strip():
        raise ValueError("World effects apply once at an explicit Off-Duty end")
    present = {x.id for x in world.gorgons} if present_gorgons is None else present_gorgons
    directed = {
        x.id: x
        for x in world.gorgons
        if x.alive and x.gorgon_class == "directed" and x.id in present
    }
    if len(movements) != len(directed) or {x.gorgon for x in movements} != set(directed):
        raise ValueError(
            "The Handler must choose a legal one-square step for every Directed Gorgon"
        )
    unplaced = {
        x.id: x
        for x in world.gorgons
        if x.alive
        and x.id in present
        and x.gorgon_class == "aggressive"
        and not any(loc.cell == x.cell and loc.operational for loc in world.locations)
    }
    if len(changes) != len(unplaced) or {x.gorgon for x in changes} != set(unplaced):
        raise ValueError(
            "Choose a Class change for every Aggressive Gorgon outside a surviving location"
        )
    updated = world
    followups: list[Followup] = []
    for movement in movements:
        original = directed[movement.gorgon]
        if movement.destination not in directed_steps(updated, original):
            raise ValueError(
                "Directed movement must advance one adjacent square toward its actual goal"
            )
        updated = update(
            updated,
            gorgons=tuple(
                x.model_copy(update={"cell": movement.destination}) if x.id == original.id else x
                for x in updated.gorgons
            ),
        )
    for change in changes:
        old, replacement = unplaced[change.gorgon], change.replacement
        class_setup = {"gorgon_class", "goal", "protected_asset", "follows", "sprite_group"}
        if (
            not change.account.strip()
            or replacement.gorgon_class == "aggressive"
            or (replacement.model_dump(exclude=class_setup) != old.model_dump(exclude=class_setup))
        ):
            raise ValueError(
                "A Class change preserves the existing entity, Type, Assets, Core and location"
            )
        updated = update(
            updated, gorgons=tuple(replacement if x.id == old.id else x for x in updated.gorgons)
        )
    # Simultaneous attackers destroy one location once.
    destroyed = set()
    for gorgon in world.gorgons:
        if (
            gorgon.alive
            and gorgon.id in present
            and gorgon.gorgon_class == "aggressive"
            and gorgon.id not in unplaced
        ):
            target = next(x for x in world.locations if x.cell == gorgon.cell and x.operational)
            if target.id not in destroyed:
                outcome = destroy(updated, target.id, gorgon_cause=True)
                updated = outcome.world
                followups.extend(outcome.followups)
                destroyed.add(target.id)
    updated = update(updated, completed_off_duty=world.completed_off_duty + (period_id,))
    return Result(world=updated, followups=tuple(followups))


def damage_gorgon(world: World, identity: str, asset_id: str, *, indirect: bool) -> World:
    target = next((x for x in world.gorgons if x.id == identity and x.alive), None)
    if target is None:
        raise ValueError("Choose a living Gorgon")
    asset = next((x for x in target.assets if x.id == asset_id and not x.damaged), None)
    if asset is None:
        raise ValueError("Damage one current intact owned Asset")
    if (
        not indirect
        and target.protected_asset is not None
        and any(x.id == target.protected_asset and not x.damaged for x in target.assets)
    ):
        raise ValueError("The protective Directed Asset cannot be overcome by a direct attack")
    changed = target.model_copy(
        update={
            "assets": tuple(
                x.model_copy(update={"damaged": True}) if x.id == asset_id else x
                for x in target.assets
            )
        }
    )
    return update(world, gorgons=tuple(changed if x.id == identity else x for x in world.gorgons))


def expose_gorgon(world: World, identity: str, account: str) -> World:
    from girlframe.engine.m3_leviathan import require_layers_clear

    target = next((x for x in world.gorgons if x.id == identity and x.alive), None)
    if target is None or target.exposed or not account.strip():
        raise ValueError("Review an actual living Gorgon's Core weakness")
    dealt_with = {x.id for x in target.assets if x.damaged} | {
        x.id for x in target.destroyed_assets
    }
    if not set(target.core_plan.assets) <= dealt_with:
        raise ValueError("Damage all designated Core-protecting Assets first")
    require_layers_clear(target)
    return update(
        world,
        gorgons=tuple(
            x.model_copy(update={"exposed": True}) if x.id == identity else x for x in world.gorgons
        ),
    )


def collateral_city(world: World, identity: str, *, intercepted: bool) -> Result:
    """Called only after a Gorgon Play resolves; no second count for either option."""
    gorgon = next((x for x in world.gorgons if x.id == identity and x.alive), None)
    if gorgon is None or gorgon.collateral_city is None or gorgon.collateral_resolved:
        return Result(world=world)
    city = next(x for x in world.locations if x.id == gorgon.collateral_city)
    if intercepted or city.condition == "destroyed" or city.cell != gorgon.cell:
        return Result(world=world)
    count = min(2, gorgon.collateral_successes + 1)
    changed = update(
        world,
        gorgons=tuple(
            x.model_copy(update={"collateral_successes": count, "collateral_resolved": count == 2})
            if x.id == identity
            else x
            for x in world.gorgons
        ),
    )
    return destroy(changed, city.id, gorgon_cause=True) if count == 2 else Result(world=changed)


def kill_gorgon(world: World, identity: str) -> World:
    target = next((x for x in world.gorgons if x.id == identity and x.alive), None)
    if target is None or not target.exposed:
        raise ValueError("A Gorgon is defeated only by destroying its exposed Core")
    return update(
        world,
        gorgons=tuple(
            x.model_copy(update={"alive": False}) if x.id == identity else x for x in world.gorgons
        ),
    )


def move_prisoner(
    world: World, identity: str, destination: Cell, event: str, custodian: int
) -> World:
    target = next((x for x in world.pilots if x.id == identity and x.alive), None)
    if (
        target is None
        or target.custody not in ("captured", "transported")
        or target.custodian != custodian
    ):
        raise ValueError("Transport requires existing actual custody by the current custodian")
    changed = AdversaryPilot.model_validate_json(
        target.model_copy(
            update={
                "cell": destination,
                "custody": "transported",
                "custody_event": event,
            }
        ).model_dump_json()
    )
    return update(world, pilots=tuple(changed if x.id == identity else x for x in world.pilots))
