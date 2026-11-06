"""Every original Girl loses exactly one actual Asset of each printed family."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_bonds import make_helpless
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_physical_state import Placement

RULE = "strain.budget.endgame.4"


class Context(Model):
    id: str
    work: str
    source_event: str
    handler: ActorRef
    actor: ActorRef
    frame: str
    event: str
    placement: Placement
    inside_frame: bool
    piloting: bool
    in_battle: bool
    opponent: ActorRef | None
    opponent_known: Literal[True]
    account: str = Field(min_length=1, max_length=1200)


class Loss(Model):
    id: str
    work: str
    actor: ActorRef
    frame: str
    context: str
    event: str
    girl_asset: AssetState
    frame_asset: AssetState
    last_girl: bool
    account: str = Field(min_length=1, max_length=1200)
    children: tuple[str, ...] = ()
    bound_event: str | None = None


def contexts(state: GameState) -> tuple[Context, ...]:
    return tuple(
        Context.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "budget_removal_context"
    )


def losses(state: GameState) -> tuple[Loss, ...]:
    return tuple(
        Loss.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "budget_removal_loss"
    )


def put(state: GameState, value: Context | Loss) -> None:
    kind = "budget_removal_context" if isinstance(value, Context) else "budget_removal_loss"
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == value.id)
    ]
    state.facts.append(dict(kind=kind, id=value.id, body=value.model_dump_json()))


def blocked(state: GameState, actor: ActorRef) -> dict[str, str]:
    from girlframe.engine.m3_janus_storage import ids
    from girlframe.engine.m3_supply_drop import current_asset, live

    stored = ids(state, actor)
    temporary = {current_asset(state, x) for x in live(state, actor)}
    held = {x.asset_id for x in state.held_items if x.asset_owner == actor}
    result = {}
    for asset in state.sheets[actor.entity].assets:
        if (
            asset.intrinsic is not None
            or asset.battery_asset is not None
            or asset.id in stored | temporary | held
        ):
            result[asset.id] = (
                "SOURCE_PORT_REQUIRED: original intrinsic/stored/temporary/held source"
            )
    return result


def remove(
    original: GameState,
    context: Context,
    identity: str,
    girl: str,
    frame: str,
    event: str,
    account: str,
) -> tuple[GameState, Loss]:
    state = GameState.model_validate_json(original.model_dump_json())
    sheet = state.sheets.get(context.actor.entity)
    if (
        sheet is None
        or sheet.character_id != context.actor.incarnation
        or any(x.work == context.work and x.actor == context.actor for x in losses(state))
    ):
        raise ValueError("Remove only this original Girl's actual pair once")
    selected = {x.id: x for x in sheet.assets if x.id in (girl, frame)}
    if (
        len(selected) != 2
        or selected[girl].family != "girl"
        or selected[frame].family != "frame"
        or not account.strip()
    ):
        raise ValueError("Choose exactly one real owned Girl Asset and one real Frame Asset")
    if set(selected) & set(blocked(state, context.actor)):
        raise ValueError("SOURCE_PORT_REQUIRED: recover this linked Asset source before removal")
    previous = any(x.family == "girl" and not x.damaged for x in sheet.assets)
    sheet.assets = [x for x in sheet.assets if x.id not in selected]
    sheet.revision += 1
    last = (
        previous
        and not any(x.family == "girl" and not x.damaged for x in sheet.assets)
        and not context.inside_frame
    )
    if last and context.opponent is not None:
        state = make_helpless(state, context.actor, context.opponent, event)
    value = Loss(
        id=identity,
        work=context.work,
        actor=context.actor,
        frame=context.frame,
        context=context.id,
        event=event,
        girl_asset=selected[girl],
        frame_asset=selected[frame],
        last_girl=last,
        account=account.strip(),
    )
    put(state, value)
    return state, value
