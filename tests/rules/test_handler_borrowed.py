"""A borrowed Handler Play shares the actual effect without changing the book."""

import asyncio

import pytest
from handler_award_scenario import ordinary_pr_award
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_handler_advancements import AcquireMore, open_advancement
from girlframe.discord_adapter.m3_handler_plays import open_handler_plays
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_advocate_alone import RULE as ALONE
from girlframe.engine.m3_dogrunner import owners
from girlframe.engine.m3_frantic_breakdown import RULE as BREAK_DOWN
from girlframe.engine.m3_handler_advancements import awards
from girlframe.engine.m3_handler_borrowed import RULE, acquisitions
from girlframe.engine.m3_handler_ordinary import RULE as ordinary_rule
from girlframe.engine.m3_handler_play_state import DRESS_RULE, Effect
from girlframe.services.inbox import InboxService
from girlframe.services.m3_advocate_alone import AdvocateAloneService
from girlframe.services.m3_frantic_breakdown import FranticBreakdownService
from girlframe.services.m3_handler_advancements import HandlerAdvancementService
from girlframe.services.m3_handler_borrowed import BorrowedHandlerService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.onboarding import WorkflowError


async def buy_native(ledger, award, play):
    click = current(1, 48600)
    await click.response.defer(ephemeral=True)
    await open_advancement(click, HandlerAdvancementService(ledger), award)
    form = click.edit_original_response.call_args.kwargs["view"]
    more = next(x for x in form.children if isinstance(x, AcquireMore))
    menu_click = current(1, 48601)
    await menu_click.response.defer(ephemeral=True)
    await more.callback(menu_click)
    menu = menu_click.edit_original_response.call_args.kwargs["view"]
    menu.values.update(advancement=("borrow",))
    picked = current(1, 48602)
    await menu.confirm.callback(picked)
    payment = picked.edit_original_response.call_args.kwargs["view"]
    assert play in dict(payment.fields[0].options)
    payment.values.update(play=(play,), account="Actual borrowed Play.")
    sent = current(1, 48603)
    await payment.confirm.callback(sent)
    assert payment.completed, (sent.followup.send.call_args, sent.edit_original_response.call_args)


def test_borrowed_dress_them_down_uses_original_play_and_ordinary_rank(
    ledger, tmp_path, monkeypatch
):
    game, *_ = ordinary_pr_award(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ordinary_rule, RULE))
    owner = BorrowedHandlerService(ledger)
    plays = HandlerPlayService(ledger)
    before = state(game)
    (award,) = awards(before)
    victim = current_ref(before, 2)
    assert not plays.options(ADMIN)["dress_them_down"]
    with pytest.raises(WorkflowError, match="paid Dress"):
        plays.start(ADMIN, "unowned-borrowed-effect", before.revision, (victim,), dress_scene=900)
    with pytest.raises(WorkflowError, match="from another book"):
        owner.buy(
            ADMIN,
            "not-a-play",
            award.id,
            before.revision,
            "handler-playbook.dogrunner.no-rest-for-hounds",
            "A passive.",
        )
    assert not acquisitions(state(game)) and awards(state(game))[0].phase == "held"

    asyncio.run(buy_native(ledger, award.id, DRESS_RULE))
    assert (
        owner.buy(ADMIN, "48603", award.id, before.revision, DRESS_RULE, "Actual borrowed Play.")[
            "play"
        ]
        == DRESS_RULE
    )
    assert HandlerAdvancementService(ledger).view(ADMIN, award.id)["acquired_rule"] == RULE
    ledger.engine.dispose()
    assert plays.options(ADMIN)["dress_them_down"]
    choice = plays.start(
        ADMIN, "actual-learned-dress", state(game).revision, (victim,), dress_scene=900
    )
    inbox = InboxService(ledger)
    assert not any(x.identity == choice["id"] for x in inbox.items(OTHER))

    async def use():
        click = current(1, 48610)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(ADMIN) if x.identity == choice["id"])
        await InboxView(inbox, 1).route(click, item)
        menu = click.edit_original_response.call_args.kwargs["view"]
        await menu.open_item(click, "dress_them_down")
        form = click.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            target=(victim.token,),
            dress_steps=("competency",),
            tag="New Dog",
            account="Actual words.",
        )
        sent = current(1, 48611)
        await form.confirm.callback(sent)
        assert form.completed, (sent.followup.send.call_args, sent.edit_original_response.call_args)

    asyncio.run(use())
    after = state(game)
    assert after.order == (3, 2) and after.handler_persona.draft.playbook == "Scientist"
    assert owners(after) is None and plays.notice(PLAYER, choice["id"])["tag"] == "New Dog"
    with pytest.raises(WorkflowError):
        plays.notice(OTHER, choice["id"])
    with pytest.raises(WorkflowError):
        plays.submit(
            ADMIN,
            "stale-borrowed-effect",
            choice["id"],
            choice["game_revision"],
            "dress_them_down",
            Effect(
                kind="dress_them_down",
                dress_steps=("competency",),
                target=victim,
                tag="New Dog",
                account="Actual words.",
            ),
        )


@pytest.mark.parametrize(
    "rule,code,source_book",
    [(BREAK_DOWN, "frantic_breakdown", "Frantic"), (ALONE, "advocate_alone", "Advocate")],
)
def test_borrowed_frantic_and_advocate_plays_keep_actual_native_choices(
    ledger, tmp_path, monkeypatch, rule, code, source_book
):
    from test_m2_game import Dice, answer, tick

    from girlframe.engine.m3_advocate_alone import records as conversations
    from girlframe.engine.m3_frantic_breakdown import records as breakdowns
    from girlframe.services.m3_advocate_empathy import CHOICE

    game, worker, gateway = ordinary_pr_award(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ordinary_rule, RULE))
    before = state(game)
    (award,) = awards(before)
    service = BorrowedHandlerService(ledger)
    plays = HandlerPlayService(ledger)
    plays.game = game
    assert not plays.options(ADMIN)[code]
    with pytest.raises(WorkflowError, match="original Handler"):
        service.buy(PLAYER, "wrong-advancement-owner", award.id, before.revision, rule, "No.")
    asyncio.run(buy_native(ledger, award.id, rule))
    duplicate = service.buy(
        ADMIN, "48603", award.id, before.revision, rule, "Actual borrowed Play."
    )
    assert duplicate["play"] == rule and len(acquisitions(state(game))) == 1
    ledger.engine.dispose()
    assert plays.options(ADMIN)[code] and not plays.options(ADMIN)["dress_them_down"]
    assert not plays.options(ADMIN)[f"{source_book.lower()}_private"]
    assert state(game).handler_persona.playbook == "Scientist"
    game.dice = Dice((4, 4))
    if rule == ALONE:
        game.leave_scene(OTHER, "borrowed-private-scene", 900)

    async def start():
        click = current(1, 48610)
        click.channel_id = 900
        await click.response.defer(ephemeral=True)
        await open_handler_plays(click, plays)
        hub = click.edit_original_response.call_args.kwargs["view"]
        await hub.open_item(click, code)
        form = click.edit_original_response.call_args.kwargs["view"]
        if rule == BREAK_DOWN:
            form.values.update(account="Actual occurred breakdown in the named scene.")
        else:
            form.values.update(
                question="Private question in the authorized scene.", order=("silence",)
            )
        sent = current(1, 48611)
        await form.confirm.callback(sent)
        assert form.completed, sent.followup.send.call_args

    asyncio.run(start())
    if rule == BREAK_DOWN:
        (value,) = breakdowns(state(game))
        breakdown = FranticBreakdownService(ledger, game)
        assert game.dice.calls == 1 and value.faces == (4, 4)
        assert breakdown.get(ADMIN, value.id)["phase"] == "choice"
        assert value.handler.incarnation == before.handler_persona.id
        with pytest.raises(WorkflowError, match="saved original owner"):
            breakdown.select(
                OTHER, "wrong-breakdown-owner", value.id, state(game).revision, ("office",)
            )
    else:
        (value,) = conversations(state(game))
        alone = AdvocateAloneService(ledger, game)
        assert game.dice.calls == 0 and value.girl.entity == str(PLAYER.user_id)
        with pytest.raises(WorkflowError):
            alone.get(OTHER, value.id)
        alone.answer(
            PLAYER, "actual-private-answer", value.id, state(game).revision, "Owned answer."
        )
        receipt = alone.issue(
            ADMIN,
            "actual-private-order",
            value.id,
            state(game).revision,
            "",
            "Private original Tag",
        )
        tick(worker, gateway, 3)
        answer(game, PLAYER, "order_response", options=("obedient",))
        assert not any(x["kind"] == CHOICE for x in game.choices(ADMIN))
        tick(worker, gateway, 3)
        assert game.inspect(PLAYER, receipt["action_id"])["state"] == "complete"
        assert any(x.label == "Private original Tag" for x in state(game).sheets["2"].tags)
