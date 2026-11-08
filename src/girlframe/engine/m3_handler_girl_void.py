"""Actual Girl-rules Handler body resources and zero-Asset factual registration."""

from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_handler_girl_void_state import ExistingAsset, HandlerGirlVoid
from girlframe.engine.m3_item_state import HeldItem
from girlframe.engine.m3_items import actual_asset, mechanical_assets, same_holder


def girl_assets(state: GameState, actor: ActorRef) -> tuple[AssetState, ...]:
    return tuple(x for x in mechanical_assets(state, actor) if x.family == "girl")


def require(
    state: GameState,
    actor: ActorRef,
    *,
    work: str,
    event: str,
    appointment: str,
    judge: int,
    judge_actor: ActorRef | None,
    caster: ActorRef,
    caster_controller: int,
) -> tuple[GameState, str]:
    body = active_handler(state)
    context = (
        next(
            (
                x
                for x in state.director_contexts
                if x.active and x.id == actor.incarnation and x.handler == int(actor.entity)
            ),
            None,
        )
        if actor.kind == "handler"
        else None
    )
    if body is None or context is None or not same_handler_body(state, actor):
        raise ValueError("Only the actual source Handler Girl-rules context owns this Void effect")
    identity = str(uuid5(NAMESPACE_URL, "girlframe:handler-girl-void:" + work + ":" + actor.token))
    if any(x.work == work for x in state.handler_girl_void):
        raise ValueError("Resume the original Handler Girl Void source without duplicating it")
    values = girl_assets(state, actor)
    all_void = bool(values) and all(x.void for x in values)
    phase: Literal["allure", "asset", "facts"] = (
        "allure" if all_void else "asset" if values else "facts"
    )
    changed = GameState.model_validate_json(state.model_dump_json())
    changed.handler_girl_void.append(
        HandlerGirlVoid(
            id=identity,
            work=work,
            actor=actor,
            body=body,
            controller=int(actor.entity),
            caster=caster,
            caster_controller=caster_controller,
            context_source=context.source_event,
            source_event=event,
            appointment=appointment,
            judge=judge,
            judge_actor=judge_actor,
            phase=phase,
            allure=all_void,
            corruption_event=event if all_void else None,
        )
    )
    return changed, identity


def propose(original: GameState, identity: str, proposal: ExistingAsset) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    if not all(x.strip() for x in (proposal.name, proposal.description, proposal.evidence)):
        raise ValueError(
            "Describe the actual existing Asset and evidence before factual registration"
        )
    current = next((x for x in state.handler_girl_void if x.id == identity), None)
    if current is None or current.phase != "facts" or len(girl_assets(state, current.actor)) >= 4:
        raise ValueError(
            "Only this missing actual source Asset can be factually registered within four"
        )
    revised = current.model_copy(
        update={"phase": "review", "proposals": (*current.proposals, proposal)}
    )
    state.handler_girl_void = [revised if x.id == identity else x for x in state.handler_girl_void]
    return state


def review(
    original: GameState, identity: str, event: str, *, allow: bool, account: str
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    current = next((x for x in state.handler_girl_void if x.id == identity), None)
    if current is None or current.phase != "review" or not account.strip():
        raise ValueError("The original source judge reviews these actual preexisting Asset facts")
    proposal = current.proposals[-1]
    if proposal.state != "proposed":
        raise ValueError("Review only the original unresolved factual proposal")
    asset = None
    if allow:
        if len(girl_assets(state, current.actor)) >= 4:
            raise ValueError("Factual registration cannot bypass the actual four Girl Asset limit")
        asset = AssetState(
            id="handler-girl:" + proposal.id,
            family="girl",
            name=proposal.name,
            description=proposal.description,
            damaged=proposal.damaged,
        )
        item = HeldItem(
            id="handler-girl-item:" + proposal.id,
            holder=current.actor,
            name=proposal.name,
            description=proposal.description,
            source_event=event,
            source_owner=current.actor,
            origin_event=proposal.proposal_event,
            origin_asset_json=asset.model_dump_json(),
            state_event=event,
            proposed_event=proposal.proposal_event,
            confirmed_by=current.judge_actor,
            confirmed_controller=current.judge,
            confirmed_event=event,
            asset_json=asset.model_dump_json(),
            asset_id=asset.id,
            asset_owner=current.actor,
            factual_source_action=current.work,
            weapon=proposal.weapon,
        )
        state.held_items.append(item)
    revised_proposal = proposal.model_copy(
        update={
            "state": "accepted" if allow else "rejected",
            "review_event": event,
            "review": account.strip(),
            "item": item.id if allow else None,
            "asset_json": asset.model_dump_json() if asset else None,
        }
    )
    revised = current.model_copy(
        update={
            "phase": "asset" if allow else "facts",
            "proposals": (*current.proposals[:-1], revised_proposal),
        }
    )
    state.handler_girl_void = [revised if x.id == identity else x for x in state.handler_girl_void]
    return state


def select_asset(original: GameState, identity: str, asset_id: str, event: str) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    current = next((x for x in state.handler_girl_void if x.id == identity), None)
    if current is None or current.phase != "asset":
        raise ValueError("The original caster chooses the actual source Asset")
    selected = next(
        (x for x in girl_assets(state, current.actor) if x.id == asset_id and not x.void), None
    )
    if selected is None:
        raise ValueError("Choose one actual currently uncorrupted Girl Asset")
    value = current.model_copy(
        update={
            "phase": "rewrite",
            "asset": asset_id,
            "asset_before": selected.model_dump_json(),
            "asset_choice_event": event,
        }
    )
    state.handler_girl_void = [value if x.id == identity else x for x in state.handler_girl_void]
    return state


def corrupt(
    original: GameState, identity: str, asset_id: str, description: str, event: str
) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    current = next((x for x in state.handler_girl_void if x.id == identity), None)
    if (
        current is None
        or current.phase != "rewrite"
        or current.asset != asset_id
        or not description.strip()
    ):
        raise ValueError("The actual affected Handler Girl rewrites one existing uncorrupted Asset")
    selected = next(
        (x for x in girl_assets(state, current.actor) if x.id == asset_id and not x.void), None
    )
    if selected is None:
        raise ValueError("Select an actual current uncorrupted mechanical Girl Asset")
    matches = [
        x
        for x in state.held_items
        if same_holder(state, x.holder, current.actor)
        and x.location_mode == "carried"
        and (actual := actual_asset(state, x)) is not None
        and actual.id == asset_id
    ]
    if len(matches) != 1:
        raise ValueError("One actual held Item must own this source mechanical Asset")
    revised = selected.model_copy(update={"void": True, "description": description.strip()})
    state.held_items = [
        x.model_copy(update={"asset_json": revised.model_dump_json(), "state_event": event})
        if x.id == matches[0].id
        else x
        for x in state.held_items
    ]
    values = girl_assets(state, current.actor)
    allure = bool(values) and all(x.void for x in values)
    value = current.model_copy(
        update={
            "phase": "allure" if allure else "complete",
            "asset": selected.id,
            "asset_before": selected.model_dump_json(),
            "rewrite": description.strip(),
            "corruption_event": event,
            "allure": allure,
        }
    )
    state.handler_girl_void = [value if x.id == identity else x for x in state.handler_girl_void]
    return state


def end_actor(original: GameState, actor: ActorRef, event: str) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    state.handler_girl_void = [
        x.model_copy(update={"phase": "ended", "ended_event": event})
        if actor in (x.actor, x.body) and x.phase not in ("complete", "ended")
        else x
        for x in state.handler_girl_void
    ]
    return state
