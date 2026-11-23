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
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_advocate_alone import RULE as ALONE
from girlframe.engine.m3_frantic_breakdown import RULE as BREAK_DOWN
from girlframe.engine.m3_frantic_breakdown import records
from girlframe.engine.m3_handler_advancements import awards
from girlframe.engine.m3_handler_borrowed import RULE as BORROW
from girlframe.engine.m3_handler_ordinary import RULE as ORDINARY
from girlframe.engine.m3_handler_ordinary import sessions
from girlframe.engine.m3_handler_play_state import DRESS_RULE, Effect
from girlframe.engine.m3_successor import RULE as SUCCESSOR
from girlframe.services.inbox import InboxService
from girlframe.services.m3_frantic_breakdown import FranticBreakdownService
from girlframe.services.m3_handler_book_swap import RULE, HandlerBookSwapService
from girlframe.services.m3_handler_borrowed import BorrowedHandlerService
from girlframe.services.m3_handler_creation import HandlerCreationService
from girlframe.services.m3_handler_ordinary import HandlerOrdinaryService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_successor import SuccessorService
from girlframe.services.onboarding import WorkflowError


async def change_native(inbox, award, book, retain, account):
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
    assert book in dict(payment.fields[0].options) and retain in dict(payment.fields[1].options)
    payment.values.update(book=(book,), retain=(retain,), account=account)
    sent = current(1, 48713)
    await payment.confirm.callback(sent)
    assert payment.completed, (sent.followup.send.call_args, sent.edit_original_response.call_args)


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

    asyncio.run(change_native(inbox, award, "Frantic", DRESS_RULE, account))
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


def test_native_book_swap_retains_original_native_play_and_allows_new_purchase(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway = ordinary_pr_award(ledger, tmp_path, monkeypatch, playbook="Frantic")
    approved(ledger, game, tmp_path, monkeypatch, extra=(ORDINARY, BORROW, RULE))
    before = state(game)
    (first,) = awards(before)
    inbox = InboxService(ledger)
    asyncio.run(change_native(inbox, first.id, "Dogrunner", BREAK_DOWN, "New book, same Handler."))
    after = state(game)
    assert after.handler_persona.id == before.handler_persona.id
    assert (
        after.handler_persona.playbook,
        after.handler_persona.book_change.native_rule,
    ) == ("Dogrunner", BREAK_DOWN)
    assert after.sheets == before.sheets and after.order == before.order
    ledger.engine.dispose()
    plays = HandlerPlayService(ledger)
    options = plays.options(ADMIN)
    assert options["frantic_breakdown"] and options["dress_them_down"]
    assert not options["frantic_private"] and options["dogrunner_private"]
    ordinary = HandlerOrdinaryService(ledger)
    ordinary.end_session(
        ADMIN, "end-native-retention", sessions(after)[0].id, after.revision, "Actual end."
    )
    second = session_native(ordinary, "Actual later earned advancement", 48730)
    channel = 900 + len(state(game).sheets["2"].identities)
    later = fill_identity_slot(game, ordinary, worker, gateway, second)
    purchase = BorrowedHandlerService(ledger).buy(
        ADMIN, "borrow-after-swap", later, state(game).revision, ALONE, "Choose a new skill."
    )
    assert purchase["play"] == ALONE and plays.options(ADMIN)["advocate_alone"]
    assert not plays.options(ADMIN)["advocate_private"]
    game.dice = Dice((4, 4))
    result = FranticBreakdownService(ledger, game).start(
        ADMIN, "real-retained-breakdown", state(game).revision, channel, "Actual crisis."
    )
    (record,) = records(state(game))
    assert result["id"] == record.id and record.faces == (4, 4)
    assert record.handler.incarnation == before.handler_persona.id


def test_native_book_swap_can_retain_an_earned_advancement(ledger, tmp_path, monkeypatch):
    game, worker, gateway = ordinary_pr_award(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ORDINARY, BORROW, RULE, SUCCESSOR))
    before = state(game)
    (first,) = awards(before)
    successor = SuccessorService(ledger)
    earned = successor.buy(
        ADMIN, "earned-successor", first.id, before.revision, "Actual advancement."
    )
    ordinary = HandlerOrdinaryService(ledger)
    ordinary.end_session(
        ADMIN, "end-earned-advancement", sessions(before)[0].id, state(game).revision, "Actual end."
    )
    session = session_native(ordinary, "Actual advancement for a change of book", 48740)
    channel = 900 + len(state(game).sheets["2"].identities)
    award = fill_identity_slot(game, ordinary, worker, gateway, session)
    inp = "award:" + first.id
    swap = HandlerBookSwapService(ledger)
    revision, _, retentions = swap.options(ADMIN, award)
    assert set(dict(retentions)) == {inp}
    asyncio.run(
        change_native(InboxService(ledger), award, "Advocate", inp, "Keep the original program.")
    )
    after = state(game)
    assert after.handler_persona.id == before.handler_persona.id
    assert after.handler_persona.playbook == "Advocate"
    assert after.handler_persona.book_change.retained_advancement
    assert (
        swap.swap(ADMIN, "48713", award, revision, "Advocate", inp, "Keep the original program.")[
            "retained"
        ]
        == inp
    )
    assert swap.advancement.view(ADMIN, first.id)["acquisition"] == earned["id"]
    plays = HandlerPlayService(ledger)
    options = plays.options(ADMIN)
    assert options["successor"] and options["advocate_alone"] and not options["scientist_private"]
    girl = current_ref(after, 2)
    choice = plays.start(
        ADMIN, "new-book-old-advice", after.revision, (girl,), advice_scene=channel
    )
    plays.submit(
        ADMIN,
        "kept-advice",
        choice["id"],
        choice["game_revision"],
        "successor_advice",
        Effect(kind="successor_advice", account="Keep your response focused on the mission."),
    )
    assert "Keep your response focused" in plays.notice(PLAYER, choice["id"])["account"]
    with pytest.raises(WorkflowError):
        plays.notice(OTHER, choice["id"])
