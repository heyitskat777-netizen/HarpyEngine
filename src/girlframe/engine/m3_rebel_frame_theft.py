"""The original random Frame, its custody and original Pilot survive the theft story."""

from typing import Literal

from pydantic import Field, model_validator

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_promotional_opportunity import in_responsibility
from girlframe.engine.m3_world_state import AdversaryPilot, Cell, Location

RULE = "strain.rebellion.high.6.1"
KIND = "strain_rebel_frame_theft"


class Frame(Model):
    owner: ActorRef
    instance: str


class Pass(Model):
    girl: ActorRef
    source: str
    account: str = Field(min_length=1, max_length=1200)


class Theft(Model):
    id: str
    source: str
    period: str
    handler: ActorRef
    thief: ActorRef
    controller: int
    base: str
    cell: Cell
    population: tuple[Frame, ...]
    index: int = Field(ge=0)
    rng_source: Literal["os", "test_injected"]
    case_account: str = Field(min_length=1, max_length=1200)
    cast: SceneCast | None = None
    defenders: tuple[ActorRef, ...] = ()
    attempt: str | None = None
    attempt_account: str = Field(default="", max_length=1200)
    passes: tuple[Pass, ...] = ()
    stopped_by: str | None = None
    lost: str | None = None
    loss_account: str = Field(default="", max_length=1200)
    return_offer: str | None = None
    return_account: str = Field(default="", max_length=1200)
    returned: str | None = None
    recovery_account: str = Field(default="", max_length=1200)

    @model_validator(mode="after")
    def saved_draw(self) -> "Theft":
        if self.index >= len(self.population) or len({x.instance for x in self.population}) != len(
            self.population
        ):
            raise ValueError("Save one actual draw from distinct original Frame instances")
        return self

    @property
    def frame(self) -> Frame:
        return self.population[self.index]


def thefts(state: GameState) -> tuple[Theft, ...]:
    return tuple(Theft.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND)


def missing(state: GameState, owner: ActorRef, instance: str | None) -> bool:
    return any(
        theft.frame.owner == owner
        and theft.frame.instance == instance
        and theft.lost is not None
        and theft.returned is None
        for theft in thefts(state)
    )


def save(state: GameState, value: Theft) -> None:
    state.facts = [x for x in state.facts if (x.get("kind"), x.get("id")) != (KIND, value.id)] + [
        dict(kind=KIND, id=value.id, body=value.model_dump_json())
    ]


def base(state: GameState, identity: str | None) -> Location:
    site = (
        next((x for x in state.world.locations if x.id == identity), None) if state.world else None
    )
    if (
        site is None
        or site.kind != "base"
        or not site.foundation_operational
        or not in_responsibility(state, site.cell)
    ):
        raise ValueError("Use an operational Foundation base in this Handler's actual region")
    return site


def thief(state: GameState, identity: str | None, cell: Cell) -> AdversaryPilot:
    world = state.world
    pilot = next((x for x in world.pilots if x.id == identity), None) if world else None
    if (
        world is None
        or pilot is None
        or pilot.kind != "rebel"
        or not pilot.alive
        or pilot.custody != "free"
        or pilot.controller == state.handler
        or not any(x.id == pilot.faction and x.active and x.kind == "rebel" for x in world.factions)
    ):
        raise ValueError("Choose the original living Rebel under independent control")
    body = resolve(state, ActorRef(kind="external_pilot", entity=pilot.id), ())
    if body.cell != cell or body.inside_frame is not False or body.offstage_source:
        raise ValueError("The actual Rebel must be on foot at the base")
    return pilot


def population(
    state: GameState,
    originals: tuple[ActorRef, ...],
    site: Location,
    *,
    reserved_for: str | None = None,
) -> tuple[Frame, ...]:
    from girlframe.engine.m3_actors import frame_position

    active = {
        x.frame.instance
        for x in thefts(state)
        if x.id != reserved_for and not (x.stopped_by or x.returned)
    }
    result = []
    for original in originals:
        sheet = state.sheets.get(original.entity)
        if sheet is None or sheet.character_id != original.incarnation or sheet.frame_scrapped:
            continue
        instance = (
            sheet.frame_runtime.id
            if sheet.frame_runtime
            else "initial:" + str(original.incarnation)
        )
        pose = next(
            (x for x in state.placements if x.actor == original and x.frame_instance == instance),
            None,
        )
        if (
            instance in active
            or pose is None
            or pose.mode != "outside_frame"
            or frame_position(state, original, instance) != site.cell
            or pose.frame_cell != site.cell
            or any(x.frame_instance == instance and x.active for x in state.frame_locks)
            or any(x.occupied_frame_instance == instance for x in state.placements)
            or any(x.frame == instance and x.state == "boarded" for x in state.passengers)
        ):
            continue
        result.append(Frame(owner=original, instance=instance))
    return tuple(result)


def position(state: GameState, value: Theft, event: str, destination: Cell | None) -> None:
    pose = next(
        (
            x
            for x in state.placements
            if x.actor == value.frame.owner and x.frame_instance == value.frame.instance
        ),
        None,
    )
    sheet = state.sheets.get(value.frame.owner.entity)
    expected = value.cell if destination is None else None
    instance = (
        (sheet.frame_runtime.id if sheet.frame_runtime else "initial:" + str(sheet.character_id))
        if sheet
        else None
    )
    if (
        pose is None
        or sheet is None
        or sheet.character_id != value.frame.owner.incarnation
        or sheet.frame_scrapped
        or instance != value.frame.instance
        or pose.mode != "outside_frame"
        or pose.frame_cell != expected
        or any(x.frame_instance == value.frame.instance and x.active for x in state.frame_locks)
        or any(x.occupied_frame_instance == value.frame.instance for x in state.placements)
        or any(x.frame == value.frame.instance and x.state == "boarded" for x in state.passengers)
    ):
        raise ValueError("Recover the exact original unoccupied Frame and its saved position")
    state.placements = [
        x.model_copy(update=dict(frame_cell=destination, source_event=event)) if x == pose else x
        for x in state.placements
    ]
