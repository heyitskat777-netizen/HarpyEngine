"""The original Mercenary's pocket-money outcome changes actual custody and Status."""

from typing import Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_ancillary_cadre as rank
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_harpy_defeat import give_tag
from girlframe.engine.m3_item_state import HeldItem
from girlframe.engine.m3_items import take
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_items import prove_item
from girlframe.services.onboarding import WorkflowError


class Cash(Model):
    cash: str
    possession: str
    label: str


class Payment(Cash):
    cadre: str
    instruction: str
    tag: str


def cash_options(
    game: GameService, c: Connection, state: GameState, holder: ActorRef
) -> dict[str, HeldItem]:
    actual = {}
    for item in state.held_items:
        if (
            item.holder != holder
            or item.location_mode != "carried"
            or item.condition != "intact"
            or item.weapon
            or item.asset_json is not None
            or item.confirmed_event is None
        ):
            continue
        try:
            actual[item.id] = prove_item(c, game, state, item.id)
        except WorkflowError:
            continue
    return actual


def bind_cash(
    game: GameService, c: Connection, state: GameState, source: ActorRef, value: str
) -> Cash:
    owned = cash_options(game, c, state, source).get(value)
    if owned is None or not owned.state_event:
        raise WorkflowError("Choose actual carried and confirmed fictional cash.")
    return Cash(cash=owned.id, possession=owned.state_event, label=owned.name)


def terms(
    game: GameService,
    c: Connection,
    state: GameState,
    mercenary: ActorRef,
    source: ActorRef,
    cash: str,
    instruction: str,
    tag: str,
) -> Payment:
    item = bind_cash(game, c, state, source, cash)
    cadre = rank.current(state, mercenary)
    if cadre is None or not 0 < len(tag.strip()) <= 120 or not instruction.strip():
        raise WorkflowError("Choose actual carried fictional cash, an instruction and a Tag.")
    return Payment(
        **item.model_dump(),
        cadre=cadre.id,
        instruction=instruction.strip(),
        tag=tag.strip(),
    )


def transfer_cash(
    game: GameService,
    c: Connection,
    state: GameState,
    *,
    cash: Cash,
    source: ActorRef,
    recipient: ActorRef,
    case: str,
    event: str,
    account: str,
    kind: Literal["mercenary_pocket_money", "mercenary_recompense"],
) -> GameState:
    actual = bind_cash(game, c, state, source, cash.cash)
    if (actual.possession, actual.label) != (cash.possession, cash.label):
        raise WorkflowError("Recover the exact original reviewed fictional cash.")
    history = t.m2["m2_state_history"]
    original = c.scalar(
        sa.select(history.c.event_id).where(
            history.c.campaign_id == game.store.campaign_id,
            history.c.revision == state.revision,
        )
    )
    if original is None:
        raise WorkflowError("Recover the original physical cash source before transferring it.")
    state = take(
        state,
        source,
        recipient,
        profiles(c, game.store.campaign_id),
        cash.cash,
        case,
        event,
        account,
        origin_event=original,
    )
    state.item_transfers[-1] = state.item_transfers[-1].model_copy(update=dict(source_kind=kind))
    return state


def apply(
    game: GameService,
    c: Connection,
    state: GameState,
    *,
    payment: Payment,
    mercenary: ActorRef,
    source: ActorRef,
    audience: tuple[int, int],
    case: str,
    event: str,
    account: str,
) -> tuple[GameState, str]:
    actual = terms(
        game, c, state, mercenary, source, payment.cash, payment.instruction, payment.tag
    )
    if payment != actual:
        raise WorkflowError("Recover the exact original paid instruction, cash and Cadre.")
    state = transfer_cash(
        game,
        c,
        state,
        cash=payment,
        source=source,
        recipient=mercenary,
        case=case,
        event=event,
        account=account,
        kind="mercenary_pocket_money",
    )
    rank.shift(state, mercenary, 1, event)
    tag = str(uuid4())
    return give_tag(state, mercenary, source, payment.tag, event, tag, audience), tag
