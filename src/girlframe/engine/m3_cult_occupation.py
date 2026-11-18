"""High Void's cult captures a site and venerates an actual Harpy."""

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_promotional_opportunity import in_responsibility
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import AdversaryPilot, Faction, WorldLoss

RULE = "strain.void.high.3.2"
KIND = "strain_cult_occupation"


class Occupation(Model):
    work: str
    event: str
    site: str
    faction: str
    messiah: ActorRef


def occupations(state: GameState) -> tuple[Occupation, ...]:
    return tuple(
        Occupation.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KIND
    )


def occupy(
    state: GameState,
    *,
    work: str,
    event: str,
    site_id: str | None,
    faction: Faction | None,
    harpy: str | None,
    new: AdversaryPilot | None,
    account: str,
) -> None:
    world = state.world
    site = next((x for x in world.locations if x.id == site_id), None) if world else None
    if (
        world is None
        or site is None
        or not site.operational
        or site.protection_sources
        or not in_responsibility(state, site.cell)
        or faction is None
        or faction.kind != "cult"
        or not faction.active
        or faction.underfunded
        or faction.cells != (site.cell,)
        or not harpy
        or any(x.work == work for x in occupations(state))
    ):
        raise ValueError("Choose a new cult, its actual available location and a living Harpy")
    ref = ActorRef(kind="external_pilot", entity=harpy)
    if new is not None:
        if (
            new.id != harpy
            or new.kind != "harpy"
            or new.girl.upper() != "HARPY"
            or new.controller != state.handler
            or new.cell != site.cell
            or new.custody != "free"
            or not new.alive
            or new.exposed
            or new.revealed
            or new.faction is not None
            or new.tags
            or new.rebel_resources_json is not None
            or not new.frame.strip()
            or {x.family for x in new.assets} != {"girl", "frame"}
            or any(x.damaged for x in new.assets)
            or any(x.id == harpy for x in state.harpy_states)
            or any(x.id == harpy for x in state.janus_cores)
        ):
            raise ValueError("Only a new living Harpy with her real components can be introduced")
        world = update(world, pilots=(*world.pilots, new))
        state.world = world
    actual = resolve(state, ref, (), require_current_profile=False)
    if actual.girl is None or actual.girl.casefold() != "harpy":
        raise ValueError("Choose the actual Harpy the cult venerates")

    occupation = Occupation(work=work, event=event, site=site.id, faction=faction.id, messiah=ref)
    captured = site.model_copy(
        update={
            "control_loss": WorldLoss(
                source=event, event=event, kind="captured", threat=ref, account=account
            ),
        }
    )
    state.world = update(
        world,
        factions=(*world.factions, faction),
        locations=tuple(captured if x.id == site.id else x for x in world.locations),
    )
    state.facts.append(dict(kind=KIND, id=work, body=occupation.model_dump_json()))


def public_occupations(state: GameState) -> list[dict[str, str]]:
    if state.world is None:
        return []
    sites = {x.id: x for x in state.world.locations}
    factions = {x.id: x for x in state.world.factions}
    result = []
    for record in occupations(state):
        site, faction = sites.get(record.site), factions.get(record.faction)
        if (
            site is not None
            and site.condition != "destroyed"
            and site.control_loss is not None
            and site.control_loss.event == record.event
            and faction is not None
            and faction.active
        ):
            result.append(dict(kind="cult_occupation", site=site.id, name=faction.name))
    return result
