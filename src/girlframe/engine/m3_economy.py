"""Pure Permission charges; durable ownership grants/quote authorization belong to services."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState, Model, PilotSheet
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_core import clone, owned_asset

StandardItem = Literal[
    "creature_comforts",
    "privacy",
    "visiting_home",
    "retirement",
    "asset_installment",
    "ability_unlock",
    "frame_grafting",
    "frame_swap",
]
# Unpriced entries use the owner's explicit campaign ruling, not an asserted printed price.
PRICES: dict[StandardItem, int] = {
    "creature_comforts": 1,
    "privacy": 1,
    "visiting_home": 2,
    "retirement": 20,
    "asset_installment": 1,
    "ability_unlock": 2,
    "frame_grafting": 3,
    "frame_swap": 4,
}
RULING_PRICED = frozenset({"creature_comforts", "privacy", "asset_installment"})


class Charge(Model):
    sheet: PilotSheet
    item: str
    cost: int = Field(ge=0)
    provenance: Literal["printed_price", "owner_approved_campaign_ruling", "handler_quote"]


class RepairQuote(Model):
    id: str = Field(min_length=1, max_length=80)
    handler_id: int = Field(gt=0)
    owner_id: int = Field(gt=0)
    asset_id: str = Field(min_length=1)
    sheet_revision: int = Field(ge=1)
    quote_revision: int = Field(ge=1)
    cost: int = Field(ge=0)


def charge_standard(sheet: PilotSheet, item: StandardItem) -> Charge:
    if item not in PRICES:
        raise ValueError("UNSUPPORTED_RULE: unknown standard Requisition")
    cost = PRICES[item]
    if sheet.permissions < cost:
        raise ValueError("Insufficient Permissions; no purchase was applied")
    updated = clone(sheet)
    updated.permissions -= cost
    updated.revision += 1
    return Charge(
        sheet=updated,
        item=item,
        cost=cost,
        provenance="owner_approved_campaign_ruling" if item in RULING_PRICED else "printed_price",
    )


def _validate_quote(
    sheet: PilotSheet, quote: RepairQuote, *, current_handler: int, expected_quote_revision: int
) -> None:
    if quote.handler_id != current_handler or quote.owner_id != sheet.owner:
        raise ValueError("A repair quote must come from the current Handler for this owner")
    if quote.sheet_revision != sheet.revision or quote.quote_revision != expected_quote_revision:
        raise ValueError("STALE_QUOTE: review the current repair price before confirming")
    asset = owned_asset(sheet, quote.asset_id)
    if not asset.damaged:
        raise ValueError("A paid extra repair requires a damaged Asset")


def quoted_repair(
    sheet: PilotSheet, quote: RepairQuote, *, current_handler: int, expected_quote_revision: int
) -> Charge:
    _validate_quote(
        sheet,
        quote,
        current_handler=current_handler,
        expected_quote_revision=expected_quote_revision,
    )
    updated = clone(sheet)
    asset = owned_asset(updated, quote.asset_id)
    if updated.permissions < quote.cost:
        raise ValueError("Insufficient Permissions; the quoted repair was not applied")
    asset.damaged = False
    updated.permissions -= quote.cost
    updated.revision += 1
    return Charge(
        sheet=updated, item="extra_asset_repair", cost=quote.cost, provenance="handler_quote"
    )


def quoted_repair_in_state(
    state: GameState,
    actor: ActorRef,
    quote: RepairQuote,
    *,
    current_handler: int,
    expected_quote_revision: int,
    event: str,
    source: str,
) -> Charge:
    from girlframe.engine.m3_intracadre_marriage import debit, payment_for

    sheet = state.sheets[actor.entity]
    if actor.incarnation != sheet.character_id:
        raise ValueError("Use the original quoted body's actual current incarnation")
    _validate_quote(
        sheet,
        quote,
        current_handler=current_handler,
        expected_quote_revision=expected_quote_revision,
    )
    payment = payment_for(state, actor, "extra_asset_repair", quote.cost, quote.id)
    debit(state, actor, quote.cost, event=event, source=source, payment=payment)
    updated = clone(state.sheets[actor.entity])
    owned_asset(updated, quote.asset_id).damaged = False
    updated.revision += 1
    state.sheets[actor.entity] = updated
    return Charge(
        sheet=updated, item="extra_asset_repair", cost=quote.cost, provenance="handler_quote"
    )
