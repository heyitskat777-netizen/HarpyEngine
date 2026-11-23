"""The Growth Gorgon changes intact Core guards or consumes an owned damaged Asset."""

from pydantic import Field

from girlframe.engine.m3_actor_state import Model
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import Asset, CorePlan, Gorgon, World, WorldTag

RULE = "gorgon-type.growth.growth-type"
KINDS = frozenset(("growth_adapt", "growth_regrow"))


class Adaptation(Model):
    guards: CorePlan
    tag: str = Field(min_length=1, max_length=120)


class Regrowth(Model):
    asset: str
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1200)


def adapt(body: Gorgon, choice: Adaptation, source: str) -> Gorgon:
    if (
        not body.alive
        or "growth" not in body.types
        or body.exposed
        or not set(choice.guards.assets) <= {x.id for x in body.assets}
        or not choice.tag.strip()
        or (set(choice.guards.assets), choice.guards.weakness.strip())
        == (set(body.core_plan.assets), body.core_plan.weakness.strip())
    ):
        raise ValueError("Adapt a living Growth's unexposed Core to different actual requirements.")
    tag = WorldTag(id="growth:" + source, label=choice.tag.strip(), giver_entity=body.id)
    return body.model_copy(update={"core_plan": choice.guards, "tags": (*body.tags, tag)})


def regrow(body: Gorgon, choice: Regrowth, source: str) -> Gorgon:
    eaten = next((x for x in body.assets if x.id == choice.asset and x.damaged), None)
    if (
        not body.alive
        or "growth" not in body.types
        or eaten is None
        or not choice.name.strip()
        or not choice.description.strip()
    ):
        raise ValueError("Choose your Growth's current damaged Asset and describe its replacement.")
    replacement = Asset(
        id="growth:" + source,
        name=choice.name.strip(),
        description=choice.description.strip(),
        family="gorgon",
    )
    return body.model_copy(
        update=dict(
            assets=tuple(replacement if x.id == eaten.id else x for x in body.assets),
            destroyed_assets=(*body.destroyed_assets, eaten),
        )
    )


def save(world: World, body: Gorgon) -> World:
    checked = Gorgon.model_validate_json(body.model_dump_json())
    return update(world, gorgons=tuple(checked if x.id == checked.id else x for x in world.gorgons))
