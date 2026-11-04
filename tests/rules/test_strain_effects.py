import pytest
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_service import service
from test_world import gorgon, initial

from girlframe.engine import m3_strain_effects as rules
from girlframe.engine import m3_world as world_rules
from girlframe.engine.m3_world_state import Asset, CorePlan, Faction, Location, Npc

ledger = ledger_fixture


@pytest.fixture
def canon(ledger):
    _, game = service(ledger)
    value = state(game)
    value.world = initial()
    return value


def choice(rule, **values):
    return rules.Choice(
        rule_id="strain." + rule, account="An actual human-described source event", **values
    )


@pytest.mark.parametrize(
    "kind,cell,rule",
    [
        ("directed", (10, 0), "void.low.1.1"),
        ("dormant", (1, 1), "void.low.2.1"),
        ("erratic", (1, 0), "void.low.2.1"),
        ("aggressive", (0, 4), "void.low.4.1"),
        ("sprite", (0, 0), "void.low.5.1"),
    ],
)
def test_source_gorgon_placement_and_immediate_npc_consequences_are_applied(
    canon, kind, cell, rule
):
    canon.world = world_rules.introduce_npc(
        canon.world,
        Npc(
            id="npc",
            name="A person",
            jobs=("civilian",),
            detail="A named local",
            controller=1,
            cell=cell,
        ),
    )
    extra = {"victim": "npc"} if kind in ("aggressive", "sprite") else {}
    result = rules.apply(canon, choice(rule, gorgon=gorgon(kind, "new", cell), **extra), "work")
    assert len(result.world.gorgons) == 2 and len(canon.world.gorgons) == 1
    if kind == "aggressive":
        assert not result.world.npcs[0].alive
    if kind == "sprite":
        assert result.world.npcs[0].captive_of == "new"


def test_invalid_source_location_unrelated_choices_and_invented_npc_fail(canon):
    with pytest.raises(ValueError, match="map edge"):
        rules.apply(canon, choice("void.low.1.1", gorgon=gorgon("directed", "new", (1, 1))), "work")
    with pytest.raises(ValueError, match="living NPC"):
        rules.apply(
            canon,
            choice("void.low.4.1", gorgon=gorgon("aggressive", "new", (0, 4)), victim="fake"),
            "work",
        )


def test_city_threat_counts_only_successful_resolved_collateral_and_destroys_on_second(canon):
    canon.world = world_rules.introduce_npc(
        canon.world,
        Npc(
            id="victim",
            name="Local NPC",
            jobs=("civilian",),
            detail="A named local",
            controller=1,
            cell=(0, 4),
        ),
    )
    applied = rules.apply(
        canon,
        choice("void.low.4.1", gorgon=gorgon("aggressive", "attack", (0, 4)), victim="victim"),
        "work",
    )
    stopped = world_rules.collateral_city(applied.world, "attack", intercepted=True)
    assert stopped.world.gorgons[-1].collateral_successes == 0
    first = world_rules.collateral_city(stopped.world, "attack", intercepted=False)
    assert first.world.locations[3].condition == "intact"
    second = world_rules.collateral_city(first.world, "attack", intercepted=False)
    assert second.world.locations[3].condition == "destroyed" and len(second.world.territory) == 9
    assert second.world.gorgons[-1].collateral_successes == 2
    assert second.world.gorgons[-1].collateral_resolved
    rebuilt = world_rules.update(
        second.world,
        locations=tuple(
            x.model_copy(update={"condition": "intact"}) if x.id == "city0" else x
            for x in second.world.locations
        ),
    )
    assert (
        world_rules.collateral_city(rebuilt, "attack", intercepted=False)
        .world.locations[3]
        .condition
        == "intact"
    )
    with pytest.raises(ValueError, match="unrelated"):
        rules.apply(
            canon,
            choice("void.low.2.1", gorgon=gorgon("dormant", "new", (1, 1)), rooms=((2, 3),)),
            "work",
        )


def test_rebel_city_effect_binds_only_next_npc_to_real_group_and_consumes_once(canon):
    faction = Faction(id="rebels", name="A Rebel Group", kind="rebel", cells=((0, 4),))
    result = rules.apply(
        canon, choice("rebellion.low.1.1", target="city0", faction=faction), "work"
    )
    outsider = Npc(
        id="outside",
        name="An outsider",
        jobs=("civilian",),
        controller=1,
        cell=(1, 1),
        detail="Not from that city",
    )
    first = world_rules.introduce_npc(result.world, outsider)
    assert first.npc_recruitment
    city_npc = outsider.model_copy(update={"id": "insider", "cell": (0, 4)})
    consumed = world_rules.introduce_npc(first, city_npc)
    assert consumed.npcs[-1].secret_factions == ("rebels",) and not consumed.npc_recruitment
    again = world_rules.introduce_npc(consumed, city_npc.model_copy(update={"id": "later"}))
    assert again.npcs[-1].secret_factions == ()


def test_rebel_base_is_real_and_does_not_count_as_a_foundation_base(canon):
    location = Location(
        id="rebelbase", name="Distant Rebel Base", kind="base", allegiance="rebel", cell=(8, 8)
    )
    faction = Faction(id="rebels", name="The group", kind="rebel", cells=((8, 8),))
    result = rules.apply(
        canon, choice("rebellion.low.6.1", location=location, faction=faction), "work"
    )
    for identity in ("base0", "base1", "base2"):
        destroyed = world_rules.destroy(result.world, identity, gorgon_cause=False)
        result.world = destroyed.world
    assert any(x.kind == "quadrant_lost_handler_outcome" for x in destroyed.followups)
    assert result.world.locations[-1].condition == "intact"


def test_room_assignments_cover_every_pilot_and_apply_bond_depth_or_overflow_heat(canon):
    canon.bonds["2:3"] = 2
    result = rules.apply(canon, choice("budget.low.5.2", rooms=((2, 3),)), "work")
    assert result.world.rooms == ((2, 3),) and result.bonds["2:3"] == 2
    assert result.sheets["2"].heat == canon.sheets["2"].heat + 2
    assert result.sheets["3"].heat == canon.sheets["3"].heat + 2
    with pytest.raises(ValueError, match="every current Girl"):
        rules.apply(canon, choice("budget.low.5.2", rooms=((2, 2),)), "work")


def test_supply_delay_tags_every_pilot_and_handler_exactly_once_with_stable_ids(canon):
    selected = choice(
        "budget.high.2.2", tags=tuple(rules.TagChoice(owner=x, label="Hungry") for x in (1, 2, 3))
    )
    result = rules.apply(canon, selected, "work")
    assert result.handler_tags[-1].label == "Hungry" and all(
        x.tags[-1].label == "Hungry" for x in result.sheets.values()
    )
    repeat = rules.apply(canon, selected, "work")
    assert repeat.handler_tags[-1].id == result.handler_tags[-1].id
    with pytest.raises(ValueError, match="Every current Girl"):
        rules.apply(canon, selected.model_copy(update={"tags": selected.tags[:-1]}), "work")


def test_returning_gorgon_preserves_old_damage_and_gets_two_assets_new_type_and_core_conditions(
    canon,
):
    dead = gorgon("erratic", "dead", (1, 1)).model_copy(update={"alive": False, "exposed": True})
    canon.world = world_rules.update(canon.world, gorgons=canon.world.gorgons + (dead,))
    assets = tuple(
        Asset(id="new" + str(i), name="New", description="Altered capability", family="gorgon")
        for i in (1, 2)
    )
    result = rules.apply(
        canon,
        choice(
            "void.high.3.1",
            target="dead",
            new_assets=assets,
            new_type="growth",
            core_plan=CorePlan(assets=("new1",), weakness="A new tactical weakness"),
        ),
        "work",
    )
    revived = result.world.gorgons[-1]
    assert revived.alive and not revived.exposed and revived.assets[:-2] == dead.assets
    assert revived.types == ("incubus", "growth")


def test_fired_npc_retains_bonds_and_city_anarchy_does_not_create_gorgon_territory(canon):
    npc = Npc(
        id="npc",
        name="NPC Bond",
        jobs=("base_personnel",),
        detail="Someone known to the Cadre",
        controller=1,
        cell=(0, 0),
        bonds={"pilot:2": 1},
    )
    canon.world = world_rules.introduce_npc(canon.world, npc)
    fired = rules.apply(
        canon, choice("budget.low.6.2", target="npc", npc_jobs=("civilian",)), "work"
    )
    assert fired.world.npcs[0].jobs == ("civilian",) and fired.world.npcs[0].bonds == npc.bonds
    city = rules.apply(fired, choice("budget.high.5.1", target="city0"), "anarchy")
    assert city.world.locations[3].blocked_by == ("anarchy",) and not city.world.territory
    assert city.world.locations[3].condition == "intact"


def test_sanctions_create_named_faction_with_map_area_and_problems(canon):
    faction = Faction(id="faction", name="External government", kind="political", cells=((4, 4),))
    result = rules.apply(canon, choice("budget.high.3.2", faction=faction), "work")
    assert result.world.factions[-1].description == "An actual human-described source event"
    with pytest.raises(ValueError, match="UNSUPPORTED_RULE"):
        rules.apply(canon, choice("budget.low.1.1"), "unimplemented")
