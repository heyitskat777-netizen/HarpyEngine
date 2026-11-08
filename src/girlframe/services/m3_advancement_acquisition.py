"""Shared held-award consumption and immutable original acquisition proof.

Consumers still own their eligibility, schema, effects and actual transaction/event.
"""

from collections.abc import Callable
from typing import NamedTuple, Protocol

from sqlalchemy import Connection

from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m2_game import GameService
from girlframe.services.m3_access import Access
from girlframe.services.m3_handler_advancements import HandlerAdvancementService, _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class Receipt(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def award(self) -> str: ...

    @property
    def handler(self) -> ActorRef: ...

    @property
    def appointment(self) -> str: ...

    @property
    def event(self) -> str: ...

    @property
    def account(self) -> str: ...


class HeldAward(NamedTuple):
    state: GameState
    handler: ActorRef
    appointment: str
    award: awards.Award


def held(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    award_id: str,
    revision: int,
    account: str,
    *,
    failure: str,
) -> HeldAward:
    service = HandlerAdvancementService(game.store)
    _, state, handler, appointment, award = service._source(c, viewer, award_id)
    service._current(c, state, handler, appointment)
    if state.revision != revision or award is None or award.phase != "held" or not account.strip():
        raise WorkflowError(failure)
    return HeldAward(state, handler, appointment, award)


def record_spend(state: GameState, award: awards.Award, receipt: Receipt, rule: str) -> None:
    """Record the common Award receipt after the consumer's explicit rules.put."""
    existing = next((x for x in awards.awards(state) if x.id == award.id), None)
    if (
        existing != award
        or award.phase != "held"
        or receipt.award != award.id
        or receipt.handler != award.handler
        or receipt.appointment != award.appointment
        or not receipt.id
        or not receipt.event
        or not receipt.account.strip()
    ):
        raise WorkflowError("Preserve the exact held Award and its original acquisition receipt")
    awards.put(
        state,
        awards.Award.model_validate_json(
            award.model_copy(
                update=dict(
                    phase="spent",
                    acquired_rule=rule,
                    acquisition=receipt.id,
                    spend_event=receipt.event,
                    spend_account=receipt.account.strip(),
                )
            ).model_dump_json()
        ),
    )


def prove[T: Receipt](
    game: GameService,
    c: Connection,
    state: GameState,
    identity: str,
    *,
    rule: str,
    receipts: Callable[[GameState], tuple[T, ...]],
    missing: str,
    failure: str,
) -> T:
    value = next((x for x in receipts(state) if x.id == identity), None)
    if value is None:
        raise WorkflowError(missing)
    gate = Access(game.store)
    assert gate.registry is not None
    gate.registry.require_available(rule)
    born = next((x for x in receipts(_history(c, game, value.event)) if x.id == identity), None)
    _, _, handler, appointment, award = HandlerAdvancementService(game.store)._proof(c, value.award)
    if (
        born != value
        or award is None
        or award.acquired_rule != rule
        or award.acquisition != value.id
        or award.spend_event != value.event
        or (handler, appointment) != (value.handler, value.appointment)
    ):
        raise WorkflowError(failure)
    return value
