import asyncio

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_ui import current
from test_replacement import supplied
from test_replacement_service import pending, propose, quote

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_punishments import Picker
from girlframe.discord_adapter.m3_replacement import PackageReview, open_replacement
from girlframe.engine.m3_frame_state import Preferences
from girlframe.services.m2_state import public_sheet
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def test_native_free_replacement_requires_proposal_handler_package_and_owner_confirmation(ledger):
    svc, game, _, identity = pending(ledger)
    with ledger.transaction() as c:
        saved = state(game)
        saved.sheets["2"].public_fields = ("frame_name", "frame_appearance")
        game.event(c, 2, "synthetic-public-consent", "synthetic.public", saved)

    async def run():
        owner = current(2)
        await owner.response.defer(ephemeral=True)
        await open_replacement(owner, svc, identity)
        picker = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(picker, Picker)
        assert "DOCTORDOCTOR MK. II" not in dict(picker.options)
        await picker.open_item(owner, "THE ENFORCER")
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and state(game).sheets["2"].frame_scrapped
        form.values = {"frame_name": "RENASCENT", "frame_appearance": "Dull iron"}
        await form.confirm.callback(current(2, 15001))
        package_id = svc.get(PLAYER, identity)["package_id"]
        handler = current(1)
        await handler.response.defer(ephemeral=True)
        await open_replacement(handler, svc, package_id)
        picker = handler.edit_original_response.call_args.kwargs["view"]
        await picker.open_item(handler, "0")
        form = handler.edit_original_response.call_args.kwargs["view"]
        form.values = {"rules": ("none",), "explanation": "Explicit zero-Asset package"}
        await form.confirm.callback(current(1, 15002))
        assert form.completed and state(game).sheets["2"].frame_scrapped
        await open_replacement(owner, svc, identity)
        picker = owner.edit_original_response.call_args.kwargs["view"]
        await picker.open_item(owner, "review")
        review = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(review, PackageReview)
        assert "RENASCENT" in " ".join(review.pages)
        assert "No extra unlocked abilities" in " ".join(review.pages)
        await review.confirm.callback(current(2, 15003))
        assert state(game).sheets["2"].frame == "THE ENFORCER"
        public = public_sheet(state(game).sheets["2"], state(game))
        assert public["frame_name"] == "RENASCENT" and public["frame_appearance"] == "Dull iron"

    asyncio.run(run())


def test_exact_package_review_pages_do_not_truncate_descriptions_and_reject_changed_quotes(ledger):
    svc, game, _, identity = pending(ledger)
    request = propose(svc, identity)
    original = supplied(5)
    descriptions = tuple("Description " + str(i) + "x" * 680 for i in range(5))
    long_package = original.model_copy(
        update={
            "assets": tuple(
                asset.model_copy(update={"description": descriptions[i]})
                for i, asset in enumerate(original.assets)
            ),
            "explanation": "E" * 1200,
        }
    )
    quote(svc, request["package_id"], long_package)

    async def run():
        review = PackageReview(2, svc, svc.get(PLAYER, identity))
        assert len(review.pages) >= 7 and all(len(page) <= 1950 for page in review.pages)
        assert all("Synthetic " + str(i) in " ".join(review.pages) for i in range(5))
        assert all(text in "\n".join(review.pages) for text in descriptions)
        assert not await review.interaction_check(current(3))
        quote(svc, request["package_id"], supplied(1), "revised-package")
        assert not await review.interaction_check(current(2))
        stale = current(2, 15004)
        await review.confirm.callback(stale)
        assert state(game).sheets["2"].frame_scrapped
        assert "STALE_WORK" in stale.edit_original_response.call_args.kwargs["content"]

    asyncio.run(run())


def test_package_requests_wait_for_owner_and_unrelated_player_cannot_open_them(ledger):
    from girlframe.services.inbox import InboxService

    svc, _, _, identity = pending(ledger)
    request = propose(svc, identity)
    quote(svc, request["package_id"])
    items = InboxService(ledger).items(ADMIN)
    package = next(x for x in items if x.identity == request["package_id"])
    assert package.task == "m3_replacement" and not package.incoming
    assert not any(x.task == "m3_replacement" for x in InboxService(ledger).items(OTHER))

    async def run():
        with pytest.raises(WorkflowError):
            await open_replacement(current(3), svc, identity)

    asyncio.run(run())


def test_wyvern_native_package_allows_five_ordinary_assets_plus_printed_enormous(ledger):
    svc, game, _, identity = pending(ledger)
    request = propose(svc, identity, Preferences(frame="WYVERN 0.4"))

    async def run():
        handler = current(1)
        await handler.response.defer(ephemeral=True)
        await open_replacement(handler, svc, request["package_id"])
        picker = handler.edit_original_response.call_args.kwargs["view"]
        assert "5" in dict(picker.options) and "6" not in dict(picker.options)
        await picker.open_item(handler, "5")
        form = handler.edit_original_response.call_args.kwargs["view"]
        assert "outside that limit" in form.text()
        form.values = {"rules": ("none",), "explanation": "Five ordinary Assets plus Enormous"}
        for index in range(5):
            form.values.update(
                {
                    f"name{index}": ("custom",),
                    f"custom{index}": "Ordinary " + str(index),
                    f"description{index}": "Explicit supplied gear",
                    f"damaged{index}": ("no",),
                    f"void{index}": ("no",),
                }
            )
        await form.confirm.callback(current(1, 15011))
        assert form.completed
        owner = current(2)
        await owner.response.defer(ephemeral=True)
        review = PackageReview(2, svc, svc.get(PLAYER, identity))
        await review.confirm.callback(current(2, 15012))
        assets = [x for x in state(game).sheets["2"].assets if x.family == "frame"]
        assert len(assets) == 6
        assert sum(x.intrinsic == "wyvern_enormous" for x in assets) == 1

    asyncio.run(run())
