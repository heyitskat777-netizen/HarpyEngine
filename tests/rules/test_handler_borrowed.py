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
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_dogrunner import owners
from girlframe.engine.m3_handler_advancements import awards
from girlframe.engine.m3_handler_borrowed import RULE, acquisitions
from girlframe.engine.m3_handler_ordinary import RULE as ordinary_rule
from girlframe.engine.m3_handler_play_state import DRESS_RULE, Effect
from girlframe.services.inbox import InboxService
from girlframe.services.m3_handler_advancements import HandlerAdvancementService
from girlframe.services.m3_handler_borrowed import BorrowedHandlerService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.onboarding import WorkflowError


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

    async def learn():
        click = current(1, 48600)
        await click.response.defer(ephemeral=True)
        await open_advancement(click, HandlerAdvancementService(ledger), award.id)
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
        payment.values.update(play=(DRESS_RULE,), account="Actual borrowed Play.")
        sent = current(1, 48603)
        await payment.confirm.callback(sent)
        assert payment.completed, (
            sent.followup.send.call_args,
            sent.edit_original_response.call_args,
        )

    asyncio.run(learn())
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
