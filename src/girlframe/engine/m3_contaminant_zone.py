"""Actual quarantined territory, source-bound relief, people and protected studies."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_harpy_defeat_state import NativeHarpyFacts, NativeHarpyRuntime
from girlframe.engine.m3_strain import copy as strain_copy
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import AdversaryPilot, Cell, FieldStudy, Location

RULE = "handler-advancement.handler-advancement.contaminant-zone"
Effect = Literal["void_relief", "dormancy", "rebel_replacement", "field_study"]
EFFECTS: tuple[Effect, ...] = ("void_relief", "dormancy", "rebel_replacement", "field_study")


class Acquisition(Model):
    id: str
    award: str
    handler: ActorRef
    appointment: str
    event: str
    account: str = Field(min_length=1, max_length=1200)


class HarpyReplacement(Model):
    group: str
    person: AdversaryPilot
    facts: NativeHarpyFacts

    @model_validator(mode="after")
    def actual_person(self) -> "HarpyReplacement":
        if (
            self.person.kind != "harpy"
            or self.person.girl.lower() != "harpy"
            or self.person.frame.lower() != "harpy"
            or not self.person.alive
            or self.person.custody != "free"
            or self.person.faction is not None
            or self.person.tags
            or self.facts.tags
            or self.person.exposed
            or self.person.rebel_resources_json is not None
            or not self.person.assets
            or not any(x.family == "frame" for x in self.person.assets)
            or any(x.family == "gorgon" for x in self.person.assets)
            or self.facts.actor != ActorRef(kind="external_pilot", entity=self.person.id)
            or self.facts.frame_cell != self.person.cell
            or self.facts.custody != "free"
        ):
            raise ValueError("Author the actual new world Harpy, Frame and factual resources")
        return self


class StudySetup(Model):
    location: Location
    manager: str


class Quarantine(Model):
    cells: tuple[Cell, ...] = Field(min_length=2)
    effects: tuple[Effect, Effect]
    perimeter: str = Field(min_length=1, max_length=1200)
    account: str = Field(min_length=1, max_length=1200)
    replacements: tuple[HarpyReplacement, ...] = ()
    study: StudySetup | None = None

    @model_validator(mode="after")
    def actual_area(self) -> "Quarantine":
        cells = set(self.cells)
        if len(cells) != len(self.cells) or len(set(self.effects)) != 2:
            raise ValueError(
                "Choose distinct actual squares and exactly two distinct printed rules"
            )
        reached = {self.cells[0]}
        while additions := {
            cell
            for cell in cells - reached
            if any(abs(cell[0] - x[0]) + abs(cell[1] - x[1]) == 1 for x in reached)
        }:
            reached |= additions
        if reached != cells or not self.perimeter.strip() or not self.account.strip():
            raise ValueError("Define one contiguous actual area and its real quarantine perimeter")
        if (self.study is not None) != ("field_study" in self.effects):
            raise ValueError("The selected study rule requires its actual location and manager")
        if self.replacements and "rebel_replacement" not in self.effects:
            raise ValueError("Only selected Rebel replacement creates actual Harpies")
        return self


class Zone(Model):
    id: str
    acquisition: str
    handler: ActorRef
    appointment: str
    event: str
    cells: tuple[Cell, ...]
    effects: tuple[Effect, Effect]
    perimeter: str
    account: str
    gorgons: dict[str, str] = Field(default_factory=dict)
    groups: dict[str, str] = Field(default_factory=dict)
    harpies: tuple[str, ...] = ()
    harpy_groups: dict[str, str] = Field(default_factory=dict)
    study: str | None = None
    broken_event: str | None = None
    breach_actor: ActorRef | None = None
    breach_cell: Cell | None = None
    breach_account: str | None = None


class WarpGrant(Model):
    id: str
    zone: str
    acquisition: str
    handler: ActorRef
    appointment: str
    event: str
    scene: str | None = None


def records[T: Model](state: GameState, kind: str, cls: type[T]) -> tuple[T, ...]:
    return tuple(cls.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == kind)


def acquisitions(state: GameState) -> tuple[Acquisition, ...]:
    return records(state, "contaminant_acquisition", Acquisition)


def zones(state: GameState) -> tuple[Zone, ...]:
    return records(state, "contaminant_zone", Zone)


def grants(state: GameState) -> tuple[WarpGrant, ...]:
    return records(state, "contaminant_warp_grant", WarpGrant)


def put(state: GameState, value: Acquisition | Zone | WarpGrant) -> None:
    kind = {
        Acquisition: "contaminant_acquisition",
        Zone: "contaminant_zone",
        WarpGrant: "contaminant_warp_grant",
    }[type(value)]
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))


def apply_quarantine(
    original: GameState, receipt: Acquisition, identity: str, event: str, request: Quarantine
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    world = state.world
    if world is None or any(not world.board.contains(x) for x in request.cells):
        raise ValueError("Choose actual cells on the existing map")
    cells = set(request.cells)
    gorgons: dict[str, str] = {}
    for body in world.gorgons:
        if not body.alive or "dormancy" not in request.effects:
            continue
        actual = resolve(state, ActorRef(kind="gorgon", entity=body.id), ())
        if actual.cell is None:
            raise ValueError("Resolve actual unknown/offstage Gorgon positions before quarantine")
        if actual.cell in cells:
            if any(
                x.get("kind") == "dormant_awakening" and x.get("gorgon") == body.id
                for x in state.facts
            ):
                raise ValueError(
                    "An already-awakened Dormant needs its distinct re-dormancy adapter"
                )
            gorgons[body.id] = body.model_dump_json()
    groups = {
        x.id: x
        for x in world.factions
        if x.kind == "rebel"
        and x.active
        and x.cells
        and set(x.cells) <= cells
        and "rebel_replacement" in request.effects
    }
    if "rebel_replacement" in request.effects and any(
        x.kind == "rebel" and x.active and set(x.cells) & cells and not set(x.cells) <= cells
        for x in world.factions
    ):
        raise ValueError("Resolve an actual partially overlapping Rebel footprint explicitly")
    if len(request.replacements) != len(groups) or {x.group for x in request.replacements} != set(
        groups
    ):
        raise ValueError("Create exactly one actual Harpy for every contained real Rebel Group")
    pilots = list(world.pilots)
    for replacement in request.replacements:
        person, facts = replacement.person, replacement.facts
        if (
            person.controller != int(receipt.handler.entity)
            or person.cell not in groups[replacement.group].cells
        ):
            raise ValueError("The source owner authors the actual new world Harpy at its group")
        if any(
            person.id == x.id
            for x in (*world.locations, *world.npcs, *world.gorgons, *world.pilots, *world.factions)
        ):
            raise ValueError(
                "A replacement Harpy is a genuinely new world person, never an old alias"
            )
        pilots.append(person)
        state.native_harpies.append(
            NativeHarpyRuntime(
                id=person.id,
                controller=person.controller,
                source_event=event,
                proposed_event=event,
                world_source_sha256=fingerprint(person),
                body_vessel="contaminant-body:" + person.id,
                frame_instance="initial:" + person.id,
                cell=facts.girl_cell,
                frame_cell=facts.frame_cell,
                linked=facts.linked,
                heat=facts.heat,
                identities=facts.identities,
                tags=facts.tags,
                frame_shutdown=facts.frame_shutdown,
                body_incapacitated=facts.body_incapacitated,
                condition_event=event,
                physical_source_event=event,
            )
        )
    locations, studies = list(world.locations), list(world.field_studies)
    study_id = None
    if request.study is not None:
        site = request.study.location
        manager = resolve(state, ActorRef(kind="npc", entity=request.study.manager), ())
        if (
            site.kind != "important"
            or site.cell not in cells
            or not site.operational
            or site.protection_sources
            or site.allegiance != "foundation"
            or manager.cell != site.cell
            or manager.offstage_source
            or manager.custody not in (None, "free")
            or "director" in manager.jobs
        ):
            raise ValueError("Set up the actual protected site with its living available NPC there")
        study_id = "contaminant-study:" + identity
        locations.append(site.model_copy(update=dict(protection_sources=(identity,))))
        studies.append(
            FieldStudy(
                id=study_id,
                zone=identity,
                location=site.id,
                manager=request.study.manager,
                source_event=event,
            )
        )
    state.world = update(
        world,
        territory=world.territory | frozenset(cells),
        locations=tuple(locations),
        field_studies=tuple(studies),
        pilots=tuple(pilots),
        factions=tuple(
            x.model_copy(update=dict(active=False)) if x.id in groups else x for x in world.factions
        ),
        gorgons=tuple(
            x.model_copy(
                update=dict(
                    gorgon_class="dormant",
                    goal=None,
                    protected_asset=None,
                    follows=None,
                    sprite_group=False,
                )
            )
            if x.id in gorgons
            else x
            for x in world.gorgons
        ),
    )
    if "void_relief" in request.effects:
        if state.strain is None:
            raise ValueError("Configure actual Strain before applying temporary Void relief")
        state.strain = strain_copy(
            state.strain, void_relief_sources=state.strain.void_relief_sources + (identity,)
        )
    put(
        state,
        Zone(
            id=identity,
            acquisition=receipt.id,
            handler=receipt.handler,
            appointment=receipt.appointment,
            event=event,
            cells=request.cells,
            effects=request.effects,
            perimeter=request.perimeter,
            account=request.account,
            gorgons=gorgons,
            groups={k: v.model_dump_json() for k, v in groups.items()},
            harpies=tuple(x.person.id for x in request.replacements),
            harpy_groups={x.person.id: x.group for x in request.replacements},
            study=study_id,
        ),
    )
    return state


def break_zone(
    original: GameState, identity: str, event: str, actor: ActorRef, cell: Cell, account: str
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    zone = next((x for x in zones(state) if x.id == identity and x.broken_event is None), None)
    if zone is None or state.world is None or cell not in zone.cells or not account.strip():
        raise ValueError("Record the actual breach of this still-intact quarantine")
    return _finish_breach(state, zone, event, actor, cell, account)


def _finish_breach(
    state: GameState, zone: Zone, event: str, actor: ActorRef | None, cell: Cell, account: str
) -> GameState:
    identity = zone.id
    assert state.world is not None
    put(
        state,
        zone.model_copy(
            update=dict(
                broken_event=event,
                breach_actor=actor,
                breach_cell=cell,
                breach_account=account.strip(),
            )
        ),
    )
    if state.strain is not None:
        state.strain = strain_copy(
            state.strain,
            void_relief_sources=tuple(x for x in state.strain.void_relief_sources if x != identity),
        )
    state.world = update(
        state.world,
        locations=tuple(
            x.model_copy(
                update=dict(
                    protection_sources=tuple(s for s in x.protection_sources if s != identity)
                )
            )
            for x in state.world.locations
        ),
        field_studies=tuple(
            x.model_copy(update=dict(protected=False)) if x.zone == identity else x
            for x in state.world.field_studies
        ),
    )
    return state


def warp_identity(grant: str) -> str:
    return "contaminant-feature:" + str(uuid5(NAMESPACE_URL, grant))


def break_by_blast(
    original: GameState, identity: str, event: str, cell: Cell, account: str
) -> GameState:
    """Trusted source service proves the actual nuclear crossing/perimeter destruction first."""
    state = GameState.model_validate_json(original.model_dump_json())
    zone = next((x for x in zones(state) if x.id == identity and x.broken_event is None), None)
    if zone is None or cell not in zone.cells or not account.strip():
        raise ValueError("Prove a real intact perimeter and actual blast breach")
    return _finish_breach(state, zone, event, None, cell, account)
