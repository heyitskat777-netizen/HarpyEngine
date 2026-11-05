"""Source-owned inventory facts and volunteering offers use real private native controls."""

import asyncio
from uuid import uuid4

from test_enforcement_initiative import ready
from test_enforcer_volunteer import source
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.inbox import InboxService
from girlframe.services.m3_items import ItemService


def test_actual_holder_fact_has_one_original_gm_review_without_invented_asset_stats(
    ledger,
    tmp_path,
    monkeypatch,
):
    game, _, _ = ready(ledger, tmp_path, monkeypatch)
    items = ItemService(game)
    before = state(game)
    proposal = items.propose(
        OTHER,
        str(uuid4()),
        current_ref(before, 3),
        "Existing carried tool",
        "Actual possession on her person",
        weapon=True,
    )
    inbox = InboxService(ledger)
    reviews = [x for x in inbox.items(ADMIN) if x.identity == proposal["id"]]
    assert len(reviews) == 1 and reviews[0].task == "m3_item_fact" and reviews[0].incoming
    assert not next(x for x in inbox.items(OTHER) if x.identity == proposal["id"]).incoming
    assert not any(x.identity == proposal["id"] for x in inbox.items(PLAYER))

    async def review():
        caller = current(1, 99801)
        await caller.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(caller, reviews[0])
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and not await form.interaction_check(current(3))
        form.values.update(exists=("yes",), account="Actual human GM confirms existing weapon")
        await form.confirm.callback(current(1, 99802))
        assert form.completed

    asyncio.run(review())
    after = state(game)
    assert after.held_items[-1].holder == current_ref(before, 3)
    assert after.held_items[-1].asset_json is None and after.held_items[-1].weapon
    assert after.sheets["3"].assets == before.sheets["3"].assets and game.dice.calls == 0


def test_volunteer_offer_original_chooser_has_exact_one_native_acceptance_and_real_case(
    ledger,
    tmp_path,
    monkeypatch,
):
    game, service, work = source(ledger, tmp_path, monkeypatch)
    offer = service.volunteer(PLAYER, str(uuid4()), work, "Actual Enforcer offers to execute")
    inbox = InboxService(ledger)
    rows = [x for x in inbox.items(ADMIN) if x.identity == offer["id"]]
    assert len(rows) == 1 and rows[0].task == "m3_enforcer_volunteer" and rows[0].incoming
    assert next(x for x in inbox.items(PLAYER) if x.identity == offer["id"]).incoming
    # The volunteer may withdraw; only the original chooser can accept this offer.
    assert not service.get_offer(PLAYER, offer["id"])["can_decide"]
    assert service.get_offer(PLAYER, offer["id"])["can_withdraw"]
    assert not any(x.identity == offer["id"] for x in inbox.items(OTHER))
    assert not state(game).role_punishments

    async def accept():
        caller = current(1, 99803)
        await caller.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(caller, rows[0])
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and not await form.interaction_check(current(2))
        form.values.update(accept=("yes",), account="Original chooser accepts this actual executor")
        await form.confirm.callback(current(1, 99804))
        assert form.completed

    asyncio.run(accept())
    case = state(game).role_punishments[-1]
    assert case.source_work == work and case.chooser == current_ref(state(game), 1)
    assert case.executor == current_ref(state(game), 2) and case.completion_event is None
