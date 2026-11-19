"""A real second award changes the Handler book and retains its one chosen Play."""

import asyncio

import pytest
from handler_award_scenario import ordinary_pr_award
from test_enforcer_requisitions import approved
from test_handler_ordinary import session_native
from test_handler_pr import fill_identity_slot
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, state
from test_mission_ui import current

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_handler_advancements import AcquireMore
from girlframe.engine.m3_frantic_breakdown import records
from girlframe.engine.m3_handler_advancements import awards
from girlframe.engine.m3_handler_borrowed import RULE as BORROW
from girlframe.engine.m3_handler_ordinary import RULE as ORDINARY
from girlframe.engine.m3_handler_ordinary import sessions
from girlframe.engine.m3_handler_play_state import DRESS_RULE
from girlframe.services.inbox import InboxService
from girlframe.services.m3_frantic_breakdown import FranticBreakdownService
from girlframe.services.m3_handler_book_swap import RULE, HandlerBookSwapService
from girlframe.services.m3_handler_borrowed import BorrowedHandlerService
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_handler_ordinary import HandlerOrdinaryService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.onboarding import WorkflowError


def test_native_book_swap_retains_original_play_and_unlocks_actual_new_play(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway = ordinary_pr_award(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ORDINARY, BORROW, RULE))
    (first,) = awards(state(game))
    owner = BorrowedHandlerService(ledger)
    learned = owner.buy(
        ADMIN, "swap-pr-payment", first.id, state(game).revision, DRESS_RULE, "Keep these words."
    )
    ordinary = HandlerOrdinaryService(ledger)
    ordinary.end_session(
        ADMIN, "swap-pr-end", sessions(state(game))[0].id, state(game).revision, "Actual end."
    )
    second = session_native(ordinary, "Actual book change Session", 48700)
    channel = 900 + len(state(game).sheets["2"].identities)
    award = fill_identity_slot(game, ordinary, worker, gateway, second)
    before = state(game)
    service = HandlerBookSwapService(ledger)
    plays = HandlerPlayService(ledger)
    assert not plays.options(ADMIN)["frantic_breakdown"]
    assert plays.options(ADMIN)["dress_them_down"]
    account = "Actual original Handler changes approach."
    args = (award, before.revision, "Frantic", DRESS_RULE, account)
    with pytest.raises(WorkflowError, match="original Handler"):
        service.swap(PLAYER, "unowned-book-swap", *args)
    with pytest.raises(WorkflowError, match="actual retained Play"):
        service.swap(
            ADMIN, "unowned-keepsake", award, before.revision, "Frantic", "unsigned", account
        )
    ledger.safety(OTHER, "pause-book-swap", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="(?i)paused"):
        service.swap(ADMIN, "paused-book-swap", *args)
    ledger.safety(OTHER, "resume-book-swap", ledger.status(OTHER)["revision"], pause=False)
    assert state(game) == before
    inbox = InboxService(ledger)
    assert not any(x.identity == award for x in inbox.items(PLAYER))

    async def change():
        click = current(1, 48710)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(ADMIN) if x.identity == award)
        await InboxView(inbox, 1).route(click, item)
        form = click.edit_original_response.call_args.kwargs["view"]
        more = next(x for x in form.children if isinstance(x, AcquireMore))
        menu_click = current(1, 48711)
        await menu_click.response.defer(ephemeral=True)
        await more.callback(menu_click)
        menu = menu_click.edit_original_response.call_args.kwargs["view"]
        menu.values.update(advancement=("swap",))
        choose = current(1, 48712)
        await menu.confirm.callback(choose)
        payment = choose.edit_original_response.call_args.kwargs["view"]
        payment.values.update(book=("Frantic",), retain=(DRESS_RULE,), account=account)
        sent = current(1, 48713)
        await payment.confirm.callback(sent)
        assert payment.completed, (
            sent.followup.send.call_args,
            sent.edit_original_response.call_args,
        )

    asyncio.run(change())
    after = state(game)
    assert after.handler_persona.id == before.handler_persona.id
    assert after.handler_persona.draft == before.handler_persona.draft
    assert after.handler_persona.book_change.retained == learned["id"]
    assert after.handler_persona.playbook == "Frantic"
    assert after.sheets == before.sheets and after.order == before.order
    assert service.swap(ADMIN, "48713", *args)["retained"] == DRESS_RULE
    with pytest.raises(WorkflowError, match="fresh held award"):
        service.swap(ADMIN, "stale-book-swap", *args)
    ledger.engine.dispose()
    assert service.advancement.view(ADMIN, award)["acquired_rule"] == RULE
    assert HandlerCreationService(ledger).view(ADMIN)["playbook"] == "Frantic"
    assert plays.options(ADMIN)["dress_them_down"]
    assert plays.options(ADMIN)["frantic_breakdown"]
    game.dice = Dice((4, 4))
    breakdown = FranticBreakdownService(ledger, game)
    made = breakdown.start(ADMIN, "actual-frantic-start", after.revision, channel, "Actual crisis.")
    (record,) = records(state(game))
    assert made["id"] == record.id and made["total"] == 10
    assert record.handler.incarnation == before.handler_persona.id and record.faces == (4, 4)
