"""Typed canonical world records; contained in GameState, never a second authority."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from girlframe.engine.identity import Snowflake
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_janus_link_state import BatteryAsset

Coordinate = Annotated[int, Field(ge=-100_000, le=100_000)]
Cell = tuple[Coordinate, Coordinate]
GorgonClass = Literal["aggressive", "dormant", "erratic", "directed", "sprite", "benevolent"]
GorgonType = Literal[
    "incubus", "doppleganger", "jackdaw", "mother", "sentinel", "leviathan", "growth", "parasite"
]
NPC_JOBS = (
    "base_personnel",
    "civilian",
    "creep",
    "doctor",
    "ex_pilot",
    "family",
    "fan",
    "guard",
    "handler",
    "intelligence_agent",
    "journalist",
    "mechanic",
    "patron",
    "pilot_candidate",
    "prisoner",
    "protestor",
    "psychologist",
    "public_relations",
    "scientist",
    "smuggler",
    "director",
)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class Board(Model):
    minimum: Cell
    maximum: Cell

    @model_validator(mode="after")
    def bounds(self) -> "Board":
        if any(self.minimum[i] >= self.maximum[i] for i in (0, 1)):
            raise ValueError("The map needs two increasing coordinate bounds")
        return self

    def contains(self, cell: Cell) -> bool:
        return all(self.minimum[i] <= cell[i] <= self.maximum[i] for i in (0, 1))


class Entity(Model):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def nonblank(self) -> "Entity":
        if not self.name.strip() or not self.id.strip():
            raise ValueError("World entities need a nonblank ID and name")
        return self


class PlacedEntity(Entity):
    cell: Cell


class ShipHull(Model):
    acquisition: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    armoured: bool = True
    airborne: bool = False
    damage_count: int = Field(default=0, ge=0)
    rearm_period: str | None = None
    rearm_event: str | None = None


class ShipAuthority(Model):
    acquisition: str = Field(min_length=1)
    base: str = Field(min_length=1)
    source_event: str = Field(min_length=1)


class ShipPin(Model):
    id: str = Field(min_length=1)
    ship: str = Field(min_length=1)
    threat: str = Field(min_length=1)
    ram: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    released_event: str | None = None
    release_action: str | None = None


class Fallout(Model):
    id: str
    cells: tuple[Cell, ...]
    event: str
    temporary: bool
    expired_event: str | None = None


class Location(PlacedEntity):
    kind: Literal["base", "city", "important"]
    allegiance: Literal["foundation", "rebel", "independent"] = "foundation"
    condition: Literal["intact", "damaged", "destroyed"] = "intact"
    blocked_by: tuple[str, ...] = ()
    fallout_sources: tuple[str, ...] = Field(default=(), exclude_if=lambda x: not x)
    protection_sources: tuple[str, ...] = Field(default=(), exclude_if=lambda x: not x)
    ship: ShipHull | None = Field(default=None, exclude_if=lambda x: x is None)

    @property
    def operational(self) -> bool:
        return self.condition != "destroyed" and not self.blocked_by and not self.fallout_sources


class Asset(Model):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1200)
    family: Literal["girl", "frame", "gorgon"]
    damaged: bool = False
    void: bool = False
    classification_event: str | None = Field(
        default=None, min_length=1, exclude_if=lambda value: value is None
    )

    battery_asset: BatteryAsset | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def exact_mental_source(self) -> "Asset":
        if self.battery_asset is not None and (
            self.family != "girl"
            or self.id != self.battery_asset.asset_id
            or self.name != self.battery_asset.name
        ):
            raise ValueError("Use the exact printed source-linked mental Girl Asset")
        return self


class WorldTag(Model):
    id: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=120)
    giver_entity: str
    marked: bool = Field(default=False, exclude_if=lambda value: not value)
    trigger_scene: str | None = Field(default=None, exclude_if=lambda value: value is None)
    rejection_pending: bool = Field(default=False, exclude_if=lambda value: not value)


class Npc(PlacedEntity):
    jobs: tuple[str, ...] = Field(min_length=1)
    detail: str = Field(min_length=1, max_length=1200)
    controller: Snowflake
    alive: bool = True
    revealed: bool = False
    faction: str | None = None
    tags: tuple[WorldTag, ...] = ()
    bonds: dict[str, Literal[1, 2]] = Field(default_factory=dict)
    captive_of: str | None = None
    secret_factions: tuple[str, ...] = ()
    employment: Literal["unrecorded", "foundation", "unemployed"] = "unrecorded"
    custody_event: str | None = None

    @model_validator(mode="after")
    def known_jobs(self) -> "Npc":
        if not set(self.jobs) <= set(NPC_JOBS) or len(set(self.jobs)) != len(self.jobs):
            raise ValueError("Choose distinct printed NPC playbooks")
        return self


class Goal(Model):
    kind: Literal["cell", "location", "npc"]
    cell: Cell | None = None
    entity_id: str | None = None

    @model_validator(mode="after")
    def exact(self) -> "Goal":
        if (self.kind == "cell") != (self.cell is not None) or (self.kind == "cell") == (
            self.entity_id is not None
        ):
            raise ValueError("A Directed goal needs exactly its location, NPC or cell")
        return self


class CorePlan(Model):
    assets: tuple[str, ...] = Field(min_length=1, max_length=2)
    weakness: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def distinct(self) -> "CorePlan":
        if len(set(self.assets)) != len(self.assets) or not self.weakness.strip():
            raise ValueError("Specify distinct Assets and the actual conversational weakness")
        return self


class Gorgon(Entity):
    tags: tuple[WorldTag, ...] = ()
    cell: Cell | None = None
    position_event: str | None = None
    gorgon_class: GorgonClass
    types: tuple[GorgonType, ...] = Field(min_length=1)
    assets: tuple[Asset, ...]
    destroyed_assets: tuple[Asset, ...] = ()
    core_plan: CorePlan
    flesh_layers: tuple[str, str] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    flesh_layers_event: str | None = Field(
        default=None, min_length=1, exclude_if=lambda value: value is None
    )
    exposed: bool = False
    alive: bool = True
    revealed: bool = False
    goal: Goal | None = None
    protected_asset: str | None = None
    sprite_group: bool = False
    follows: str | None = None
    core_strike_failed: bool = False
    collateral_city: str | None = None
    collateral_successes: int = Field(default=0, ge=0, le=2)
    collateral_resolved: bool = False

    @model_validator(mode="after")
    def source_shape(self) -> "Gorgon":
        records = (*self.assets, *self.destroyed_assets)
        ids = {asset.id for asset in records}
        if len(ids) != len(records) or len(set(self.types)) != len(self.types):
            raise ValueError("Gorgon Assets and Types must be distinct")
        if not set(self.core_plan.assets) <= ids or any(a.family != "gorgon" for a in records):
            raise ValueError("Core exposure must name current or destroyed original Gorgon Assets")
        if (self.flesh_layers is None) != (self.flesh_layers_event is None):
            raise ValueError("Actual flesh layers need their original source event")
        if self.flesh_layers is not None and (
            "leviathan" not in self.types
            or len(set(self.flesh_layers)) != 2
            or not set(self.flesh_layers) <= ids
            or not self.flesh_layers_event
            or not self.flesh_layers_event.strip()
        ):
            raise ValueError("Use two distinct actual original Leviathan flesh-layer Assets")
        if self.gorgon_class == "directed" and (
            self.goal is None or self.protected_asset not in ids
        ):
            raise ValueError("Directed Gorgons need a real goal and their protective Asset")
        if self.gorgon_class != "directed" and (
            self.goal is not None or self.protected_asset is not None
        ):
            raise ValueError("Directed setup belongs only to that Class")
        if self.gorgon_class == "sprite" and (self.follows is None or self.follows == self.id):
            raise ValueError("A Sprite follows another actual Gorgon")
        if self.gorgon_class != "sprite" and (self.follows is not None or self.sprite_group):
            raise ValueError("Sprite group/leader setup belongs only to Sprites")
        return self


class Faction(Entity):
    kind: Literal["rebel", "foundation", "political", "cult"]
    cells: tuple[Cell, ...]
    leader: str | None = None
    underfunded: bool = False
    active: bool = True
    description: str = Field(default="", max_length=2400)


class AdversaryPilot(PlacedEntity):
    """An external Pilot; a PC uses its canonical sheet instead of a copied sheet."""

    tags: tuple[WorldTag, ...] = ()
    kind: Literal["harpy", "rebel", "foundation"]
    girl: str
    frame: str
    assets: tuple[Asset, ...]
    faction: str | None = None
    controller: Snowflake
    revealed: bool = False
    exposed: bool = False
    alive: bool = True
    custody: Literal["free", "captured", "transported", "converted"] = "free"
    custodian: Snowflake | None = None
    custody_event: str | None = None
    rebel_resources_json: str | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode="after")
    def provenance(self) -> "AdversaryPilot":
        if self.custody == "free" and (
            self.custodian is not None or self.custody_event is not None
        ):
            raise ValueError("A free Pilot has no active custody event")
        if self.custody != "free" and (self.custodian is None or not self.custody_event):
            raise ValueError("Custody needs an actual event and custodian")
        if len({x.id for x in self.assets}) != len(self.assets) or any(
            x.family == "gorgon" for x in self.assets
        ):
            raise ValueError("External Pilots need distinct Girl/Frame Assets")
        return self


class NpcRecruitment(Model):
    id: str
    source_work: str
    city: str
    faction: str


class StartingNpcLink(Model):
    owner: Snowflake
    character_id: str = Field(min_length=1)
    slot: int = Field(ge=0, le=3)
    npc: str


class NpcRoleOffer(Model):
    id: str = Field(min_length=1, max_length=100)
    proposer: Snowflake
    npc: Npc
    source_event: str
    state: Literal["pending", "accepted", "declined", "withdrawn"] = "pending"
    response_event: str | None = None


class FieldStudy(Model):
    id: str = Field(min_length=1)
    zone: str = Field(min_length=1)
    location: str = Field(min_length=1)
    manager: str = Field(min_length=1)
    source_event: str = Field(min_length=1)
    protected: bool = True


class AreaFeature(Model):
    id: str = Field(min_length=1)
    zone: str = Field(min_length=1)
    cell: Cell
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1200)
    source_event: str = Field(min_length=1)
    grant: str = Field(min_length=1)


class Region(Model):
    """One unlocked neighbouring map in the same canonical geographical World."""

    id: Literal["quadrant13"] = "quadrant13"
    name: str = "Quadrant 13"
    bounds: Board
    acquisition: str
    source_event: str
    rival: ActorRef
    responsible: ActorRef | None = None
    takeover_event: str | None = None
    boons: tuple[str, ...]
    threats: tuple[str, ...]
    location_ids: tuple[str, ...]
    staff_ids: tuple[str, ...]

    @model_validator(mode="after")
    def real_office(self) -> "Region":
        if (
            self.rival.kind != "npc"
            or len(set(self.boons)) != 3
            or len(set(self.threats)) != 2
            or (self.responsible is None) != (self.takeover_event is None)
            or self.responsible is not None
            and self.responsible.kind != "handler"
        ):
            raise ValueError("Retain the actual regional office, three boons and two threats")
        return self


class World(Model):
    quadrant12: Board | None = Field(default=None, exclude_if=lambda x: x is None)
    regions: tuple[Region, ...] = Field(default=(), exclude_if=lambda x: not x)
    fallout: tuple[Fallout, ...] = Field(default=(), exclude_if=lambda x: not x)
    board: Board
    features: tuple[AreaFeature, ...] = Field(default=(), exclude_if=lambda x: not x)
    ship_pins: tuple[ShipPin, ...] = Field(default=(), exclude_if=lambda x: not x)
    ship_sources: tuple[ShipAuthority, ...] = Field(default=(), exclude_if=lambda x: not x)
    field_studies: tuple[FieldStudy, ...] = Field(default=(), exclude_if=lambda x: not x)
    locations: tuple[Location, ...]
    npcs: tuple[Npc, ...] = ()
    gorgons: tuple[Gorgon, ...] = ()
    pilots: tuple[AdversaryPilot, ...] = ()
    factions: tuple[Faction, ...] = ()
    territory: frozenset[Cell] = frozenset()
    completed_off_duty: tuple[str, ...] = ()
    npc_recruitment: tuple[NpcRecruitment, ...] = ()
    rooms: tuple[tuple[Snowflake, ...], ...] = ()
    starting_npc_links: tuple[StartingNpcLink, ...] = ()
    npc_role_offers: tuple[NpcRoleOffer, ...] = ()

    @model_validator(mode="after")
    def references(self) -> "World":
        if self.regions:
            if self.quadrant12 is None or len(self.regions) != 1:
                raise ValueError("Preserve the original Quadrant12 and one actual unlocked map")
            for region in self.regions:
                if (
                    not self.board.contains(region.bounds.minimum)
                    or not self.board.contains(region.bounds.maximum)
                    or any(
                        region.bounds.contains(cell)
                        for cell in (self.quadrant12.minimum, self.quadrant12.maximum)
                    )
                    or not any(
                        x.id == region.rival.entity and "handler" in x.jobs for x in self.npcs
                    )
                    or not set(region.location_ids) <= {x.id for x in self.locations}
                    or not set(region.staff_ids) <= {x.id for x in self.npcs}
                ):
                    raise ValueError("An unlocked region retains its real map, office and contents")
        if any(not self.board.contains(cell) for zone in self.fallout for cell in zone.cells):
            raise ValueError("Actual fallout occupies on-board cells")
        if any(
            site.condition != "destroyed" and zone.id not in site.fallout_sources
            for zone in self.fallout
            if zone.expired_event is None
            for site in self.locations
            if site.cell in zone.cells
        ):
            raise ValueError("An uncleared blast area cannot become an operational site")
        entities = (*self.locations, *self.npcs, *self.gorgons, *self.pilots, *self.factions)
        if len({x.id for x in entities}) != len(entities):
            raise ValueError("World entity IDs are globally distinct within a campaign")
        candidates = [x.npc for x in self.npc_role_offers if x.state == "pending"]
        if len({x.id for x in self.npc_role_offers}) != len(self.npc_role_offers) or len(
            {x.id for x in (*entities, *candidates)}
        ) != len(entities) + len(candidates):
            raise ValueError("Pending NPC role offers reserve distinct actual entity IDs")
        if any(not self.board.contains(x.cell) for x in candidates):
            raise ValueError("An offered NPC still requires an actual map square")
        ground = [
            x
            for x in self.locations
            if x.ship is None or not (x.ship.airborne or x.condition == "destroyed")
        ]
        if len({x.cell for x in ground}) != len(ground):
            raise ValueError("Each major location occupies its own square")
        if any(
            not self.board.contains(x.cell) for x in (*self.locations, *self.npcs, *self.pilots)
        ) or any(x.cell is not None and not self.board.contains(x.cell) for x in self.gorgons):
            raise ValueError("Entities must occupy squares on the current map")
        factions, npcs = {x.id for x in self.factions}, {x.id for x in self.npcs}
        sites = {x.id: x for x in self.locations}
        if (
            len({x.acquisition for x in self.ship_sources}) != len(self.ship_sources)
            or any(x.base not in sites for x in self.ship_sources)
            or any(
                not any(
                    a.acquisition == x.ship.acquisition
                    and a.base == x.id
                    and a.source_event == x.ship.source_event
                    for a in self.ship_sources
                )
                for x in self.locations
                if x.ship is not None
            )
        ):
            raise ValueError("A flying Base requires its actual existing source-bound authority")
        if any(x.ship is not None and x.kind != "base" for x in self.locations):
            raise ValueError("A Ship-Base preserves its actual existing Base identity")
        if len({x.id for x in self.ship_pins}) != len(self.ship_pins) or any(
            x.ship not in sites
            or sites[x.ship].ship is None
            or not any(g.id == x.threat for g in self.gorgons)
            for x in self.ship_pins
        ):
            raise ValueError("A real ship pin retains its actual Base, threat and source")
        if (
            len({x.id for x in self.features}) != len(self.features)
            or any(not self.board.contains(x.cell) for x in self.features)
            or len({x.id for x in self.field_studies}) != len(self.field_studies)
        ):
            raise ValueError("Keep distinct source-owned features and actual study sites")
        for study in self.field_studies:
            if study.location not in sites or study.manager not in npcs:
                raise ValueError("An actual field study requires its real site and NPC manager")
        for site in self.locations:
            if len(set(site.protection_sources)) != len(site.protection_sources) or set(
                site.protection_sources
            ) != {x.zone for x in self.field_studies if x.location == site.id and x.protected}:
                raise ValueError("Protected locations require their actual source-owned study")
        if any(x.npc not in npcs for x in self.starting_npc_links) or len(
            {(x.owner, x.character_id, x.slot) for x in self.starting_npc_links}
        ) != len(self.starting_npc_links):
            raise ValueError("Starting NPC slots link once to actual persistent NPCs")
        for affiliation in [x.faction for x in self.npcs] + [x.faction for x in self.pilots]:
            if affiliation is not None and affiliation not in factions:
                raise ValueError("An affiliation must name a real faction")
        for npc in self.npcs:
            if not set(npc.secret_factions) <= factions:
                raise ValueError("Secret memberships still reference real factions")
        for faction in self.factions:
            if faction.leader is not None and faction.leader not in npcs:
                raise ValueError("A faction leader must be a real NPC")
            if len(set(faction.cells)) != len(faction.cells) or any(
                not self.board.contains(c) for c in faction.cells
            ):
                raise ValueError("Faction areas use distinct actual map squares")
        gorgons = {x.id: x for x in self.gorgons}
        locations = {x.id for x in self.locations}
        if any(x.captive_of is not None and x.captive_of not in gorgons for x in self.npcs):
            raise ValueError("An NPC captive must have an actual Gorgon captor")
        if len({x.id for x in self.npc_recruitment}) != len(self.npc_recruitment):
            raise ValueError("Pending affiliation triggers are distinct")
        for hook in self.npc_recruitment:
            if hook.city not in locations or hook.faction not in factions:
                raise ValueError("An affiliation trigger needs its actual city and Rebel Group")
        for gorgon in self.gorgons:
            if gorgon.collateral_city is not None and not any(
                x.id == gorgon.collateral_city and x.kind == "city" for x in self.locations
            ):
                raise ValueError("A two-use city threat must refer to an actual city")
            if gorgon.follows is not None and (
                gorgon.follows not in gorgons
                or gorgons[gorgon.follows].gorgon_class == "sprite"
                or gorgon.types != gorgons[gorgon.follows].types
            ):
                raise ValueError("Sprites inherit the Type of a real non-Sprite leader")
            if gorgon.goal is not None:
                goal = gorgon.goal
                if goal.kind == "cell" and (
                    goal.cell is None or not self.board.contains(goal.cell)
                ):
                    raise ValueError("The Directed goal must be on the map")
                if goal.kind != "cell" and goal.entity_id not in (
                    locations if goal.kind == "location" else npcs
                ):
                    raise ValueError("The Directed goal must name a real target")
        if len(set(self.completed_off_duty)) != len(self.completed_off_duty):
            raise ValueError("World end-of-period effects cannot repeat")
        return self


def region_for(world: World, cell: Cell) -> Region | None:
    return next((x for x in world.regions if x.bounds.contains(cell)), None)


def base_responsible(world: World, cell: Cell, handler: ActorRef) -> bool:
    region = region_for(world, cell)
    return region is None or region.responsible == handler and region.takeover_event is not None


def quadrant12_contains(world: World, cell: Cell) -> bool:
    return (world.quadrant12 or world.board).contains(cell)
