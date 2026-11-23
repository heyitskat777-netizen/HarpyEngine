"""The private Last / Resort reserve has an actual award, base and death threshold."""

import asyncio

import pytest
from handler_award_scenario import ordinary_pr_award
from test_enforcer_requisitions import approved
from test_girl_insurance import actual_death
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m3_handler_advancements import AcquireMore, open_advancement
from girlframe.engine.m3_handler_advancements import awards
from girlframe.engine.m3_handler_ordinary import RULE as ordinary_rule
from girlframe.engine.m3_last_resort import RULE, acquisitions
from girlframe.services.inbox import InboxService
from girlframe.services.m3_handler_advancements import HandlerAdvancementService
from girlframe.services.m3_last_resort import LastResortService
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


def test_last_resort_reserve_is_owned_and_counts_actual_cadre_death(ledger, tmp_path, monkeypatch):
    game, *_ = ordinary_pr_award(ledger, tmp_path, monkeypatch)
    approved(ledger, game, tmp_path, monkeypatch, extra=(ordinary_rule, RULE))
    original = state(game)
    (award,) = awards(original)
    service = LastResortService(ledger)
    inbox = InboxService(ledger)
    with pytest.raises(WorkflowError):
        service.buy(OTHER, "other-reserve", award.id, original.revision, "base0", "Wrong owner.")
    with pytest.raises(WorkflowError, match="actual operational Base"):
        service.buy(ADMIN, "unknown-site", award.id, original.revision, "unknown", "Wrong base.")
    assert not acquisitions(state(game))

    async def reserve():
        click = current(1, 48500)
        await click.response.defer(ephemeral=True)
        await open_advancement(click, HandlerAdvancementService(ledger), award.id)
        form = click.edit_original_response.call_args.kwargs["view"]
        more = next(x for x in form.children if isinstance(x, AcquireMore))
        menu_click = current(1, 48501)
        await menu_click.response.defer(ephemeral=True)
        await more.callback(menu_click)
        menu = menu_click.edit_original_response.call_args.kwargs["view"]
        menu.values.update(advancement=("last_resort",))
        selected = current(1, 48502)
        await menu.confirm.callback(selected)
        purchase = selected.edit_original_response.call_args.kwargs["view"]
        purchase.values.update(base=("base0",), account="PRIVATE_RESERVE_ACCOUNT")
        sent = current(1, 48503)
        await purchase.confirm.callback(sent)
        assert purchase.completed, (
            sent.followup.send.call_args,
            sent.edit_original_response.call_args,
        )

    asyncio.run(reserve())
    (acquisition,) = acquisitions(state(game))
    assert service.buy(
        ADMIN, "48503", award.id, original.revision, "base0", "PRIVATE_RESERVE_ACCOUNT"
    ) == dict(id=acquisition.id, phase="reserved")
    assert HandlerAdvancementService(ledger).view(ADMIN, award.id)["acquisition"] == acquisition.id
    for outsider in (PLAYER, OTHER):
        assert acquisition.id not in {x.identity for x in inbox.items(outsider)}
        with pytest.raises(WorkflowError):
            service.menu(outsider, acquisition.id)
    ledger.engine.dispose()
    receipt = service.menu(ADMIN, acquisition.id)
    assert receipt["confirmed_losses"] == 0 and receipt["needed"] == 1
    assert not receipt["loss_threshold_met"]

    archive = actual_death(game, MissionService(ledger))
    assert any(x == archive.actor for x in acquisition.cadre)
    after = service.menu(ADMIN, acquisition.id)
    assert after["chassis"] == receipt["chassis"] and after["base_available"]
    assert after["loss_threshold_met"] and after["confirmed_losses"] == 1
    assert not state(game).handler_archives and "1" not in state(game).sheets

    async def reopen():
        click = current(1, 48520)
        await click.response.defer(ephemeral=True)
        item = next(x for x in inbox.items(ADMIN) if x.identity == acquisition.id)
        await InboxView(inbox, 1).route(click, item)
        content = click.edit_original_response.call_args.kwargs["content"]
        assert "1 of 1 required" in content and "PRIVATE_RESERVE_ACCOUNT" not in content

    asyncio.run(reopen())
