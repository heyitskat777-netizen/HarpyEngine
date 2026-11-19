"""Original Mother paid birth and later source-backed Sprite development."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_world import CLASS_ASSETS, damage_gorgon, update, validate_initial_gorgon
from girlframe.engine.m3_world_state import Asset, Cell, CorePlan, Gorgon

RULE = "gorgon-type.mother.mother-type"
KIND = "mother_sprite_birth"
TRAVEL = "mother_sprite_travel"
REVIEW = "mother_sprite_escape_review"
MATURITY = "mother_sprite_maturity"


class BirthPlan(Model):
    payment: str
    name: str = Field(min_length=1, max_length=120)
    asset: str = Field(min_length=1, max_length=120)
    weakness: str = Field(min_length=1, max_length=1200)


class Birth(Model):
    mother: ActorRef
    sprite: ActorRef
    cell: Cell
    action: str
    scene: str
    event: str
    paid_asset: str


class Travel(Model):
    sprite: ActorRef
    scene: str
    event: str
    origin: Cell
    destination: Cell


class Adult(Model):
    gorgon_class: Literal["benevolent", "dormant", "erratic"]
    extra_assets: tuple[str, ...]


class Review(Model):
    sprite: ActorRef
    movement: str
    judge: int
    appointment: str
    event: str
    adult: Adult | None
    account: str = Field(min_length=1, max_length=1200)


class Maturity(Model):
    sprite: ActorRef
    escape: str
    period: str
    event: str


def records(state: GameState) -> tuple[Birth, ...]:
    return tuple(
        Birth.model_validate_json(row["body"]) for row in state.facts if row.get("kind") == KIND
    )


def check(mother: Gorgon, choice: BirthPlan) -> None:
    if (
        not mother.alive
        or "mother" not in mother.types
        or not choice.name.strip()
        or not choice.asset.strip()
        or not choice.weakness.strip()
        or not any(x.id == choice.payment and not x.damaged for x in mother.assets)
    ):
        raise ValueError(
            "Use the original Mother's actual intact Asset and a complete Sprite design."
        )


def spawn(
    state: GameState,
    mother: Gorgon,
    cell: Cell | None,
    choice: BirthPlan,
    *,
    action: str,
    scene: str,
    event: str,
) -> Birth:
    check(mother, choice)
    if (
        state.world is None
        or cell is None
        or not state.world.board.contains(cell)
        or any(x.action == action for x in records(state))
    ):
        raise ValueError("Use one actual new Sprite from the original Mother's present square.")
    identity = "mother-sprite:" + action
    asset = Asset(
        id=identity + ":asset",
        name=choice.asset.strip(),
        family="gorgon",
        description="The original capability of " + choice.name.strip(),
    )
    sprite = Gorgon(
        id=identity,
        name=choice.name.strip(),
        cell=cell,
        position_event=event,
        gorgon_class="sprite",
        types=mother.types,
        assets=(asset,),
        follows=mother.id,
        core_plan=CorePlan(assets=(asset.id,), weakness=choice.weakness.strip()),
    )
    validate_initial_gorgon(sprite)
    paid = damage_gorgon(state.world, mother.id, choice.payment, indirect=True)
    state.world = update(paid, gorgons=(*paid.gorgons, sprite))
    result = Birth(
        mother=ActorRef(kind="gorgon", entity=mother.id),
        sprite=ActorRef(kind="gorgon", entity=sprite.id),
        cell=cell,
        action=action,
        scene=scene,
        event=event,
        paid_asset=choice.payment,
    )
    state.facts.append(dict(kind=KIND, id=sprite.id, body=result.model_dump_json()))
    return result


def moves(state: GameState) -> tuple[Travel, ...]:
    return tuple(
        Travel.model_validate_json(row["body"]) for row in state.facts if row.get("kind") == TRAVEL
    )


def reviews(state: GameState) -> tuple[Review, ...]:
    return tuple(
        Review.model_validate_json(row["body"]) for row in state.facts if row.get("kind") == REVIEW
    )


def maturities(state: GameState) -> tuple[Maturity, ...]:
    return tuple(
        Maturity.model_validate_json(row["body"])
        for row in state.facts
        if row.get("kind") == MATURITY
    )


def travel(
    state: GameState, actor: ActorRef, origin: Cell, destination: Cell, scene: str, event: str
) -> None:
    if (
        actor.kind == "gorgon"
        and origin != destination
        and any(x.sprite == actor for x in records(state))
        and not any(x.sprite == actor and x.adult is not None for x in reviews(state))
    ):
        value = Travel(
            sprite=actor, scene=scene, event=event, origin=origin, destination=destination
        )
        state.facts.append(dict(kind=TRAVEL, id=event, body=value.model_dump_json()))


def pending(state: GameState) -> tuple[tuple[Gorgon, Birth, Travel], ...]:
    if state.world is None:
        return ()
    movements = {x.sprite: x for x in moves(state)}
    resolved = {x.movement for x in reviews(state)}
    escaped = {x.sprite for x in reviews(state) if x.adult is not None}
    bodies = {x.id: x for x in state.world.gorgons if x.alive and x.gorgon_class == "sprite"}
    return tuple(
        (body, birth, movement)
        for birth in records(state)
        if birth.sprite not in escaped
        and (movement := movements.get(birth.sprite)) is not None
        and movement.event not in resolved
        and (body := bodies.get(birth.sprite.entity)) is not None
        and body.cell == movement.destination
    )


def adult_body(body: Gorgon, adult: Adult, source: str) -> Gorgon:
    names = tuple(x.strip() for x in adult.extra_assets)
    if (
        body.gorgon_class != "sprite"
        or not body.alive
        or len(body.assets) + len(names) != CLASS_ASSETS[adult.gorgon_class]
        or any(not 1 <= len(name) <= 120 for name in names)
        or len({x.casefold() for x in names}) != len(names)
        or {x.casefold() for x in names} & {x.name.casefold() for x in body.assets}
    ):
        raise ValueError(
            "Supply distinct new Assets up to the selected adult Class's printed count."
        )
    additions = tuple(
        Asset(id=f"adult:{source}:{i}", name=name, description=name, family="gorgon")
        for i, name in enumerate(names)
    )
    return Gorgon.model_validate_json(
        body.model_copy(
            update=dict(
                gorgon_class=adult.gorgon_class,
                assets=(*body.assets, *additions),
                follows=None,
                sprite_group=False,
            )
        ).model_dump_json()
    )


def mature(state: GameState, period: str, event: str) -> None:
    if state.world is None:
        return
    if pending(state):
        raise ValueError("Resolve the actual moved Sprite's private escape review before Off-Duty.")
    seen = {x.sprite for x in maturities(state)}
    worlds = {x.id: x for x in state.world.gorgons}
    changed = False
    for source in reviews(state):
        body = worlds.get(source.sprite.entity)
        if source.adult is None or source.sprite in seen or body is None or not body.alive:
            continue
        worlds[body.id] = adult_body(body, source.adult, source.event)
        changed = True
        result = Maturity(sprite=source.sprite, escape=source.event, period=period, event=event)
        state.facts.append(dict(kind=MATURITY, id=body.id, body=result.model_dump_json()))
    if changed:
        state.world = update(state.world, gorgons=tuple(worlds.values()))
