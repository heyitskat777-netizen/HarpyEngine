"""Actual neighbouring map contents and regional responsibility, PDF157/155."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_harpy_defeat_state import NativeHarpyFacts
from girlframe.engine.m3_world_state import (
    AdversaryPilot,
    AreaFeature,
    Board,
    Cell,
    Faction,
    Gorgon,
    Location,
    Npc,
    Region,
    World,
)

RULE = "handler-advancement.handler-advancement.promotional-opportunity"
Boon = Literal["useful", "mysterious", "defended_base", "two_cities", "personnel"]
Threat = Literal["rebels", "dormant", "erratic", "territory", "harpy"]
BOONS: tuple[Boon, ...] = ("useful", "mysterious", "defended_base", "two_cities", "personnel")
THREATS: tuple[Threat, ...] = ("rebels", "dormant", "erratic", "territory", "harpy")


class Site(Model):
    location: Location
    detail: str = Field(min_length=1, max_length=1200)


class Defence(Site):
    guards: tuple[Npc, ...] = Field(min_length=1)


class HarpySetup(Model):
    person: AdversaryPilot
    facts: NativeHarpyFacts


class Setup(Model):
    bounds: Board
    boons: tuple[Boon, Boon, Boon]
    threats: tuple[Threat, Threat]
    rival: Npc
    useful: Site | None = None
    mysterious: Site | None = None
    defended_base: Defence | None = None
    cities: tuple[Location, ...] = ()
    personnel: tuple[Npc, ...] = ()
    rebels: Faction | None = None
    dormant: Gorgon | None = None
    erratic: Gorgon | None = None
    territory: tuple[Cell, ...] = ()
    harpy: HarpySetup | None = None
    account: str = Field(min_length=1, max_length=1800)

    @model_validator(mode="after")
    def printed_contents(self) -> "Setup":
        if len(set(self.boons)) != 3 or len(set(self.threats)) != 2:
            raise ValueError("Choose exactly three distinct boons and two distinct threats")
        for key in ("useful", "mysterious", "defended_base"):
            if (getattr(self, key) is not None) != (key in self.boons):
                raise ValueError(
                    "Author each selected actual site, without adding unselected boons"
                )
        if len(self.cities) != (2 if "two_cities" in self.boons else 0) or bool(self.personnel) != (
            "personnel" in self.boons
        ):
            raise ValueError("Two cities are two real cities; personnel are actual named people")
        for key in ("rebels", "dormant", "erratic", "harpy"):
            if (getattr(self, key) is not None) != (key in self.threats):
                raise ValueError("Create each selected real threat and its actual resources")
        if len(self.territory) != (8 if "territory" in self.threats else 0) or len(
            set(self.territory)
        ) != len(self.territory):
            raise ValueError("Select eight distinct real Gorgon territory squares")
        sites = self.sites()
        people = self.people()
        if (
            not self.rival.alive
            or self.rival.jobs != ("handler",)
            or self.rival.captive_of is not None
            or not self.rival.revealed
            or any(not self.bounds.contains(x.cell) for x in (*sites, *people))
            or any(
                x.condition != "intact"
                or x.ship
                or x.blocked_by
                or x.fallout_sources
                or x.protection_sources
                for x in sites
            )
            or any(not x.alive or x.captive_of for x in people)
            or any(x.kind != "city" for x in self.cities)
            or any(x.location.kind != "important" for x in (self.useful, self.mysterious) if x)
            or self.defended_base
            and (
                self.defended_base.location.kind != "base"
                or any("guard" not in x.jobs for x in self.defended_base.guards)
            )
        ):
            raise ValueError(
                "Author the real office, intact sites, physical defences and actual staff"
            )
        for kind in ("dormant", "erratic"):
            threat = getattr(self, kind)
            if threat is not None:
                from girlframe.engine.m3_world import validate_initial_gorgon

                validate_initial_gorgon(threat)
            if threat and (
                threat.gorgon_class != kind
                or not threat.alive
                or threat.exposed
                or threat.cell is None
                or not self.bounds.contains(threat.cell)
                or not threat.assets
                or threat.cell in {x.cell for x in sites}
            ):
                raise ValueError(
                    "Use the printed living Gorgon Class with real resources in wilderness"
                )
        if any(not self.bounds.contains(cell) for cell in self.territory):
            raise ValueError("Gorgon territory belongs to this actual unlocked map")
        if self.dormant and self.territory and self.dormant.cell not in self.territory:
            raise ValueError("The actual dormant Gorgon occupies the selected Gorgon territory")
        if self.rebels and (
            self.rebels.kind != "rebel"
            or not self.rebels.active
            or not self.rebels.cells
            or any(not self.bounds.contains(x) for x in self.rebels.cells)
        ):
            raise ValueError("Create a real active regional Rebel faction and footprint")
        if self.harpy:
            p, f = self.harpy.person, self.harpy.facts
            if (
                p.kind != "harpy"
                or p.girl.lower() != "harpy"
                or p.frame.lower() != "harpy"
                or not p.alive
                or not self.bounds.contains(p.cell)
                or p.tags
                or f.tags
                or p.custody != "free"
                or p.exposed
                or p.faction
                or p.rebel_resources_json
                or not any(x.family == "girl" for x in p.assets)
                or not any(x.family == "frame" for x in p.assets)
                or any(x.family == "gorgon" for x in p.assets)
                or f.actor != ActorRef(kind="external_pilot", entity=p.id)
                or not f.linked
                or f.girl_cell != p.cell
                or f.frame_cell != p.cell
                or f.custody != "free"
                or f.frame_shutdown
                or f.body_incapacitated
                or not f.identities
            ):
                raise ValueError(
                    "Author the living active Harpy's actual body, Frame and original resources"
                )
        return self

    def sites(self) -> tuple[Location, ...]:
        return (
            tuple(x.location for x in (self.useful, self.mysterious, self.defended_base) if x)
            + self.cities
        )

    def people(self) -> tuple[Npc, ...]:
        return (
            (self.rival,)
            + (self.defended_base.guards if self.defended_base else ())
            + self.personnel
        )


class Acquisition(Model):
    id: str
    award: str
    handler: ActorRef
    appointment: str
    event: str
    account: str
    setup: Setup
    original_board: Board


class Takeover(Model):
    id: str
    acquisition: str
    handler: ActorRef
    event: str
    death_work: str
    death_event: str


def acquisitions(state: GameState) -> tuple[Acquisition, ...]:
    return tuple(
        Acquisition.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "promotional_opportunity_acquisition"
    )


def takeovers(state: GameState) -> tuple[Takeover, ...]:
    return tuple(
        Takeover.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "promotional_opportunity_takeover"
    )


def put(state: GameState, value: Acquisition | Takeover) -> None:
    kind = (
        "promotional_opportunity_acquisition"
        if isinstance(value, Acquisition)
        else "promotional_opportunity_takeover"
    )
    if any(x.get("kind") == kind and x.get("id") == value.id for x in state.facts):
        raise ValueError("Preserve the original regional source and takeover")
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))


def expanded(old: Board, added: Board) -> Board:
    horizontal = (added.minimum[1], added.maximum[1]) == (old.minimum[1], old.maximum[1]) and (
        added.minimum[0] == old.maximum[0] + 1 or added.maximum[0] == old.minimum[0] - 1
    )
    vertical = (added.minimum[0], added.maximum[0]) == (old.minimum[0], old.maximum[0]) and (
        added.minimum[1] == old.maximum[1] + 1 or added.maximum[1] == old.minimum[1] - 1
    )
    if not (horizontal or vertical):
        raise ValueError(
            "Author a disjoint adjoining rectangular map; preserve the old map coordinates"
        )
    return Board(
        minimum=(min(old.minimum[0], added.minimum[0]), min(old.minimum[1], added.minimum[1])),
        maximum=(max(old.maximum[0], added.maximum[0]), max(old.maximum[1], added.maximum[1])),
    )


def unlock(world: World, source: Acquisition) -> World:
    if world.regions or world.quadrant12 or world.board != source.original_board:
        raise ValueError("Unlock this new region once, preserving the actual original map")
    setup = source.setup
    territory = frozenset(setup.territory) | (
        frozenset((setup.dormant.cell,)) if setup.dormant and setup.dormant.cell else frozenset()
    )
    features = tuple(
        AreaFeature(
            id=x.location.id + ":purpose",
            zone=source.id,
            cell=x.location.cell,
            label=x.location.name,
            description=x.detail,
            source_event=source.event,
            grant=source.id,
        )
        for x in (setup.useful, setup.mysterious, setup.defended_base)
        if x
    )
    region = Region(
        bounds=setup.bounds,
        acquisition=source.id,
        source_event=source.event,
        rival=ActorRef(kind="npc", entity=setup.rival.id),
        boons=setup.boons,
        threats=setup.threats,
        location_ids=tuple(x.id for x in setup.sites()),
        staff_ids=tuple(x.id for x in setup.people() if x.id != setup.rival.id),
    )
    return World.model_validate_json(
        world.model_copy(
            update=dict(
                board=expanded(world.board, setup.bounds),
                quadrant12=world.board,
                regions=(region,),
                locations=world.locations + setup.sites(),
                npcs=world.npcs + setup.people(),
                gorgons=world.gorgons + tuple(x for x in (setup.dormant, setup.erratic) if x),
                factions=world.factions + ((setup.rebels,) if setup.rebels else ()),
                pilots=world.pilots + ((setup.harpy.person,) if setup.harpy else ()),
                territory=world.territory | territory,
                features=world.features + features,
            )
        ).model_dump_json()
    )


def in_responsibility(state: GameState, cell: Cell) -> bool:
    if state.world is None or not state.world.board.contains(cell):
        return False
    world = state.world
    if (world.quadrant12 or world.board).contains(cell):
        return True
    from girlframe.engine.m3_handler_consequences import same_handler_body

    region = next((x for x in world.regions if x.bounds.contains(cell)), None)
    if region is None or region.responsible is None or region.takeover_event is None:
        return False
    takeover = next(
        (
            x
            for x in takeovers(state)
            if x.acquisition == region.acquisition
            and x.event == region.takeover_event
            and x.handler == region.responsible
        ),
        None,
    )
    if takeover is None:
        raise ValueError("Recover the actual original source of regional responsibility")
    return same_handler_body(state, region.responsible)


def responsibility_edge(state: GameState, cell: Cell) -> bool:
    return in_responsibility(state, cell) and any(
        not in_responsibility(state, (cell[0] + dx, cell[1] + dy))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
    )
