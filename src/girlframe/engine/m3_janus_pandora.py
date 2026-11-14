"""One real implanted-womb pregnancy and Handler-authored source-bound newborn."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_gorgon_catalog import ASSETS
from girlframe.engine.m3_world_state import Asset, Cell, CorePlan, Gorgon, GorgonClass, GorgonType


class Pregnancy(Model):
    id: str
    actor: ActorRef
    frame: str
    purchase: str
    period: str
    source_event: str
    phase: Literal["inseminated", "birth_rolled", "born"] = "inseminated"
    birth_action: str | None = None
    roll_event: str | None = None
    tier: Literal["low", "mid", "high"] | None = None
    birth_cell: Cell | None = None
    judge: int
    appointment: str
    child: ActorRef | None = None
    child_event: str | None = None


class ChildProposal(Model):
    name: str = Field(min_length=1, max_length=120)
    gorgon_type: GorgonType
    gorgon_class: GorgonClass
    assets: tuple[str, ...] = Field(min_length=1, max_length=3)
    descriptions: tuple[str, ...] = Field(min_length=1, max_length=3)
    core_assets: tuple[int, ...] = Field(min_length=1, max_length=2)
    weakness: str = Field(min_length=1, max_length=1200)
    account: str = Field(min_length=1, max_length=1200)


def pregnancies(state: GameState) -> tuple[Pregnancy, ...]:
    return tuple(
        Pregnancy.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "janus_pandora_pregnancy"
    )


def get(state: GameState, identity: str) -> Pregnancy:
    value = next((x for x in pregnancies(state) if x.id == identity), None)
    if value is None:
        raise ValueError("Recover the actual source Inseminated Frame")
    return value


def put(state: GameState, value: Pregnancy) -> None:
    fact = dict(kind="janus_pandora_pregnancy", body=value.model_dump_json())
    if any(x.id == value.id for x in pregnancies(state)):
        state.facts = [
            fact
            if x.get("kind") == "janus_pandora_pregnancy"
            and Pregnancy.model_validate_json(x["body"]).id == value.id
            else x
            for x in state.facts
        ]
    else:
        state.facts.append(fact)


def child_record(state: GameState, actor: ActorRef) -> Pregnancy | None:
    return next((x for x in pregnancies(state) if x.child == actor and x.phase == "born"), None)


def mother(state: GameState, value: Pregnancy) -> ActorRef | None:
    sheet = state.sheets.get(value.actor.entity)
    from girlframe.engine.m3_careers import binding

    current = binding(state, int(value.actor.entity))
    archived = any(x.actor == value.actor for x in state.career_archives)
    if (
        sheet is not None
        and sheet.character_id == value.actor.incarnation
        and int(value.actor.entity) in state.order
        and (
            current is None
            and not archived
            or current is not None
            and current.active
            and current.character == value.actor.incarnation
        )
    ):
        return value.actor
    from girlframe.engine.m3_tag_permissions import conversion

    for body in state.harpy_states:
        actor = ActorRef(kind="external_pilot", entity=body.id)
        if body.origin == value.actor and body.alive:
            conversion(state, actor)
            return actor
    return None


def newborn_controller(state: GameState, actor: ActorRef) -> int | None:
    """Obedient newborn follows its actual original living mother, never her successor."""
    value = child_record(state, actor)
    return (
        int(value.actor.entity)
        if value is not None and value.tier == "mid" and mother(state, value)
        else None
    )


def require_can_harm(state: GameState, actor: ActorRef, target: ActorRef) -> None:
    value = child_record(state, actor)
    if value is not None and value.tier == "high" and target in (value.actor, mother(state, value)):
        raise ValueError("This actual PANDORA child will not harm its original mother")


def require_can_move(state: GameState, actor: ActorRef, destination: Cell | None) -> None:
    value = child_record(state, actor)
    if value is not None and value.tier == "low" and destination != value.birth_cell:
        raise ValueError("This actual low-result child stays at its original birthplace")


def vicious(state: GameState, actor: ActorRef) -> bool:
    value = child_record(state, actor)
    return value is not None and value.tier == "mid"


def write_child(
    original: GameState, identity: str, proposal: ChildProposal, event: str
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    value = get(state, identity)
    if value.phase != "birth_rolled" or value.tier is None or state.world is None or not event:
        raise ValueError("Write the actual known birth result on its existing world")
    if value.birth_cell is None:
        raise ValueError("Recover the original recorded birthplace before authoring this child")
    count = {"low": 1, "mid": 2, "high": 3}[value.tier]
    classes = {"low": ("dormant",), "mid": ("benevolent",), "high": ("aggressive", "erratic")}[
        value.tier
    ]
    if (
        proposal.gorgon_class not in classes
        or len(proposal.assets) != count
        or len(proposal.descriptions) != count
        or len(set(proposal.assets)) != count
        or not set(proposal.assets) <= set(ASSETS[proposal.gorgon_type])
        or len(set(proposal.core_assets)) != len(proposal.core_assets)
        or not set(proposal.core_assets) <= set(range(count))
        or not proposal.account.strip()
        or not proposal.weakness.strip()
    ):
        raise ValueError("The actual Handler writes precisely this tier's Class, Type and Assets")
    child = "pandora:" + value.id
    assets = tuple(
        Asset(
            id=child + ":asset:" + str(n),
            name=name,
            description=proposal.descriptions[n],
            family="gorgon",
        )
        for n, name in enumerate(proposal.assets)
    )
    body = Gorgon(
        id=child,
        name=proposal.name,
        cell=value.birth_cell,
        position_event=value.roll_event,
        gorgon_class=proposal.gorgon_class,
        types=(proposal.gorgon_type,),
        assets=assets,
        core_plan=CorePlan(
            assets=tuple(assets[n].id for n in proposal.core_assets), weakness=proposal.weakness
        ),
        revealed=True,
    )
    state.world = state.world.model_copy(update={"gorgons": (*state.world.gorgons, body)})
    put(
        state,
        value.model_copy(
            update=dict(
                phase="born", child=ActorRef(kind="gorgon", entity=child), child_event=event
            )
        ),
    )
    return state
