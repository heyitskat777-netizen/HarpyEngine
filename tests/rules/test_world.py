import pytest
from pydantic import ValidationError

from girlframe.engine import m3_world as rules
from girlframe.engine.m3_world_state import (
    AdversaryPilot,
    Asset,
    Board,
    CorePlan,
    Goal,
    Gorgon,
    Location,
    Npc,
)


def gorgon(kind="benevolent", identity="secret", cell=(0, 0), **updates):
    count = rules.CLASS_ASSETS[kind] + int(updates.get("sprite_group", False))
    assets = tuple(
        Asset(
            id=identity + ":" + str(i),
            name="Asset " + str(i),
            description="A human-authored capability",
            family="gorgon",
        )
        for i in range(count)
    )
    values = {
        "id": identity,
        "name": identity,
        "gorgon_class": kind,
        "types": ("incubus",),
        "cell": cell,
        "assets": assets,
        "core_plan": CorePlan(assets=(assets[0].id,), weakness="A declared tactical opportunity"),
    }
    if kind == "directed":
        values.update(goal=Goal(kind="location", entity_id="city0"), protected_asset=assets[0].id)
    if kind == "sprite":
        values["follows"] = "secret"
    return Gorgon(**(values | updates))


def initial():
    locations = tuple(
        Location(id=kind + str(i), name=kind + str(i), kind=kind, cell=cell)
        for kind, cells in (
            ("base", ((0, 0), (2, 0), (4, 0))),
            ("city", ((0, 4), (2, 4))),
            ("important", ((4, 4), (6, 4), (8, 4))),
        )
        for i, cell in enumerate(cells)
    )
    return rules.create(Board(minimum=(-3, -3), maximum=(10, 10)), locations, gorgon())


def test_starting_map_has_printed_counts_distinct_squares_and_private_class_zero():
    world = initial()
    assert len(world.locations) == 8 and not world.gorgons[0].revealed
    with pytest.raises(ValueError, match="three bases"):
        rules.create(world.board, world.locations[1:], gorgon())
    with pytest.raises(ValueError, match="Class 0"):
        rules.create(world.board, world.locations, gorgon(cell=(1, 1)))
    with pytest.raises(ValidationError, match="own square"):
        rules.update(
            world,
            locations=world.locations
            + (Location(id="another", name="Another city", kind="city", cell=(0, 0)),),
        )
    with pytest.raises(ValidationError, match="map"):
        rules.update(
            world,
            npcs=(
                Npc(
                    id="npc",
                    name="A person",
                    jobs=("civilian",),
                    detail="An identifying detail",
                    controller=1,
                    cell=(99, 99),
                ),
            ),
        )


@pytest.mark.parametrize("kind", rules.CLASS_ASSETS)
def test_gorgon_class_asset_baselines_and_immediate_introduction_work(kind):
    world = initial()
    incoming = gorgon(kind, "new", cell=(1, 1))
    result = rules.introduce_gorgon(world, incoming)
    assert len(result.world.gorgons) == 2 and len(world.gorgons) == 1
    assert bool(result.followups) == (kind == "aggressive")
    assert len(incoming.assets) == rules.CLASS_ASSETS[kind]
    with pytest.raises(ValueError, match="Asset count"):
        wrong = incoming.model_copy(
            update={
                "assets": incoming.assets
                + (
                    Asset(
                        id="extra", name="Extra", description="Extra capability", family="gorgon"
                    ),
                )
            }
        )
        rules.introduce_gorgon(world, wrong)


def test_sprite_group_inherits_real_leader_type_without_self_or_fake_leader():
    world = initial()
    group = gorgon("sprite", "group", cell=(1, 1), sprite_group=True)
    assert len(rules.introduce_gorgon(world, group).world.gorgons[-1].assets) == 2
    with pytest.raises(ValidationError, match="real non-Sprite"):
        rules.introduce_gorgon(world, group.model_copy(update={"follows": "missing"}))
    with pytest.raises(ValidationError, match="Type"):
        rules.introduce_gorgon(world, group.model_copy(update={"types": ("mother",)}))


def test_directed_guard_and_core_require_actual_owned_damage_and_weakness_review():
    world = rules.introduce_gorgon(initial(), gorgon("directed", "directed", cell=(1, 1))).world
    target = world.gorgons[-1]
    for asset in target.assets[:2]:
        with pytest.raises(ValueError, match="protective"):
            rules.damage_gorgon(world, target.id, asset.id, indirect=False)
    with pytest.raises(ValueError, match="designated"):
        rules.expose_gorgon(world, target.id, "We created the declared opportunity")
    damaged = rules.damage_gorgon(world, target.id, target.protected_asset, indirect=True)
    with pytest.raises(ValueError, match="exposed Core"):
        rules.kill_gorgon(damaged, target.id)
    exposed = rules.expose_gorgon(damaged, target.id, "The actual weakness is now present")
    defeated = rules.kill_gorgon(exposed, target.id)
    assert not defeated.gorgons[-1].alive and world.gorgons[-1].alive
    assert sum(a.damaged for a in defeated.gorgons[-1].assets) == 1


def test_period_end_moves_one_square_destroys_locations_and_cannot_repeat():
    world = rules.introduce_gorgon(initial(), gorgon("directed", "directed", cell=(1, 1))).world
    world = rules.introduce_gorgon(world, gorgon("aggressive", "attack", cell=(2, 0))).world
    with pytest.raises(ValueError, match="every Directed"):
        rules.end_off_duty(world, "period", (), ())
    with pytest.raises(ValueError, match="one adjacent"):
        rules.end_off_duty(
            world, "period", (rules.Movement(gorgon="directed", destination=(0, 4)),), ()
        )
    result = rules.end_off_duty(
        world, "period", (rules.Movement(gorgon="directed", destination=(0, 2)),), ()
    )
    assert next(x for x in result.world.locations if x.id == "base1").condition == "destroyed"
    assert result.world.gorgons[1].cell == (0, 2) and len(result.world.territory) == 9
    assert [x.kind for x in result.followups] == ["budget_structure_destroyed"]
    with pytest.raises(ValueError, match="once"):
        rules.end_off_duty(result.world, "period", (), ())


def test_aggressive_outside_location_requires_chosen_class_without_resource_reset_or_reveal():
    world = rules.introduce_gorgon(initial(), gorgon("aggressive", "attack", cell=(1, 1))).world
    old = world.gorgons[-1]
    with pytest.raises(ValueError, match="Class change"):
        rules.end_off_duty(world, "period", (), ())
    replacement = old.model_copy(update={"gorgon_class": "dormant"})
    change = rules.ClassChange(
        gorgon=old.id, replacement=replacement, account="It settles into dormancy"
    )
    changed = rules.end_off_duty(world, "period", (), (change,)).world.gorgons[-1]
    assert changed.gorgon_class == "dormant" and len(changed.assets) == 6
    with pytest.raises(ValueError, match="preserves"):
        rules.end_off_duty(
            world,
            "period",
            (),
            (
                change.model_copy(
                    update={"replacement": replacement.model_copy(update={"revealed": True})}
                ),
            ),
        )


def test_destroyed_base_creates_territory_only_for_gorgon_cause_and_keeps_career_outcome_owned():
    world = initial()
    first = rules.destroy(world, "base0", gorgon_cause=False)
    assert not first.world.territory
    second = rules.destroy(first.world, "base1", gorgon_cause=True)
    final = rules.destroy(second.world, "base2", gorgon_cause=True)
    assert [x.kind for x in final.followups] == [
        "budget_structure_destroyed",
        "quadrant_lost_handler_outcome",
    ]
    assert all(x.condition == "destroyed" for x in final.world.locations if x.kind == "base")


def test_transport_requires_actual_existing_custody_and_does_not_imply_conversion():
    world = initial()
    harpy = AdversaryPilot(
        id="harpy",
        name="Harpy",
        kind="harpy",
        cell=(1, 1),
        girl="MOCKINGBIRD",
        frame="JANUS-B",
        assets=(),
        controller=1,
    )
    world = rules.update(world, pilots=(harpy,))
    with pytest.raises(ValueError, match="existing actual custody"):
        rules.move_prisoner(world, "harpy", (0, 0), "transport", 1)
    captured = harpy.model_copy(
        update={"custody": "captured", "custodian": 1, "custody_event": "capture"}
    )
    world = rules.update(world, pilots=(captured,))
    moved = rules.move_prisoner(world, "harpy", (0, 0), "transport", 1).pilots[0]
    assert moved.custody == "transported" and moved.kind == "harpy"
    assert moved.custody_event == "transport"
