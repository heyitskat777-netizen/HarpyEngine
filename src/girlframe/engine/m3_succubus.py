"""Target-specific Succubus Orders and actual ordinary NPC refusal resources."""

from typing import Literal

from pydantic import Field

from girlframe.engine import m3_class_grafts as grafts
from girlframe.engine.m2 import GameState, higher
from girlframe.engine.m3_actor_bonds import depth
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_requisition_state import FrameRuleReceipt
from girlframe.engine.m3_world_state import Npc, WorldTag

RULE = "frame.class.autocrat.succubus-protocol"
RESPONSES = (
    ("obedient", "Obey"),
    ("immediate", "Act immediately and without thinking"),
    ("hesitant", "Obey hesitantly"),
    ("mouthing_off", "Obey while mouthing off"),
    ("gritted_teeth", "Obey through gritted teeth"),
)


class Authority(Model):
    issuer: ActorRef
    target: ActorRef
    purchase: str
    event: str
    frame: str


class Order(Model):
    id: str
    action: str
    issuer: ActorRef
    target: ActorRef
    controller: int = Field(gt=0)
    handler: ActorRef
    cast: SceneCast
    authority: Authority | None
    instruction: str = Field(min_length=1, max_length=1200)
    event: str
    registry: str


class RankLoss(Model):
    target: ActorRef
    action: str
    witness: ActorRef
    handler: ActorRef
    before: int = Field(ge=1)
    after: int = Field(ge=2)
    event: str


def npc(state: GameState, actor: ActorRef) -> Npc:
    actual = (
        next((x for x in state.world.npcs if x.id == actor.entity), None)
        if state.world and actor.kind == "npc"
        else None
    )
    if actual is None or not actual.alive or "director" in actual.jobs:
        raise ValueError("Use an actual living ordinary NPC, without a Director rules proxy")
    return actual


def held(state: GameState, actor: ActorRef) -> FrameRuleReceipt | None:
    return grafts.held(state, actor, RULE)


def authority(state: GameState, issuer: ActorRef, target: ActorRef) -> Authority:
    receipt = held(state, issuer)
    if issuer == target or receipt is None:
        raise ValueError("Use this original Pilot's actual active Succubus source")
    if target.kind == "pilot":
        sheet = state.sheets.get(target.entity)
        if (
            sheet is None
            or sheet.character_id != target.incarnation
            or depth(state, issuer, target) != 2
        ):
            raise ValueError("This exact original Girl must have an actual Intense Bond with you")
    elif target.kind == "npc":
        npc(state, target)
        if depth(state, issuer, target) < 1:
            raise ValueError("This exact actual NPC must have a current Bond with you")
    else:
        raise ValueError("This order needs an implemented original Girl or ordinary NPC recipient")
    return Authority(
        issuer=issuer,
        target=target,
        purchase=receipt.id,
        event=receipt.source_event,
        frame=receipt.frame_instance,
    )


def rank_losses(state: GameState, actor: ActorRef) -> tuple[RankLoss, ...]:
    return tuple(
        RankLoss.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "succubus_npc_rank_loss" and x.get("target") == actor.token
    )


def expanded_status(state: GameState, actor: ActorRef) -> int:
    """Read the real default/changed expanded rank, without changing Cadre rank."""
    if actor.kind == "pilot":
        sheet = state.sheets.get(actor.entity)
        if sheet is None or sheet.character_id != actor.incarnation:
            raise ValueError("Recover the actual original Girl's Status")
        return 5
    if actor.kind == "handler":
        from girlframe.engine.m3_handler_consequences import active_handler

        if active_handler(state) != actor:
            raise ValueError("Recover the actual appointed original Handler")
        return 3
    actual = npc(state, actor)
    ranks = {
        "patron": 2,
        "handler": 3,
        "doctor": 4,
        "intelligence_agent": 4,
        "psychologist": 4,
        "scientist": 4,
        "mechanic": 4,
        "guard": 5,
        "ex_pilot": 6,
    }
    rank = min(ranks.get(x, 6) for x in actual.jobs)
    for loss in rank_losses(state, actor):
        if loss.target != actor or loss.before != rank or loss.after != rank + 1:
            raise ValueError("Recover the actual append-only expanded Status history")
        rank = loss.after
    return rank


def ordinary_higher(state: GameState, issuer: ActorRef, target: ActorRef) -> bool:
    if issuer.kind == target.kind == "pilot":
        return higher(state, int(issuer.entity), int(target.entity))
    return expanded_status(state, issuer) < expanded_status(state, target)


def lower_status(state: GameState, value: RankLoss) -> None:
    if value.before != expanded_status(state, value.target) or value.after != value.before + 1:
        raise ValueError("Lower this actual NPC's current expanded Status by one step")
    if any(x.action == value.action for x in rank_losses(state, value.target)):
        raise ValueError("This exact noticed refusal already lowered Status")
    state.facts.append(
        dict(kind="succubus_npc_rank_loss", target=value.target.token, body=value.model_dump_json())
    )


def tag(state: GameState, actor: ActorRef, identity: str, label: str) -> None:
    actual = npc(state, actor)
    if not label.strip() or len(label) > 120:
        raise ValueError("Author the actual NPC's own Tag in 1–120 characters")
    if any(x.id == identity for x in actual.tags):
        raise ValueError("This actual refusal already granted its Tag")
    changed = actual.model_copy(
        update={
            "tags": (
                *actual.tags,
                WorldTag(id=identity, label=label.strip(), giver_entity=actor.model_dump_json()),
            )
        }
    )
    assert state.world is not None
    state.world = state.world.model_copy(
        update={"npcs": tuple(changed if x.id == actual.id else x for x in state.world.npcs)}
    )


def reject(state: GameState, actor: ActorRef, identity: str) -> None:
    actual = npc(state, actor)
    selected = next((x for x in actual.tags if x.id == identity), None)
    if selected is None or selected.rejection_pending:
        raise ValueError("Choose an actual own NPC Tag without another pending source restriction")
    # This exact Disobey result is the specific exception to ordinary NPC self-removal.
    assert state.world is not None
    changed = actual.model_copy(update={"tags": tuple(x for x in actual.tags if x.id != identity)})
    state.world = state.world.model_copy(
        update={"npcs": tuple(changed if x.id == actual.id else x for x in state.world.npcs)}
    )


def tier(total: int) -> Literal["low", "mid", "high"]:
    return "high" if total >= 11 else "mid" if total >= 8 else "low"
