"""Persisted actual combat openings resume through original-owned private controls."""

import asyncio
from uuid import uuid4

from test_battle_service import prepared
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.services.inbox import InboxService


def test_actual_declared_opening_routes_review_then_original_owner_start_without_rng(ledger):
    game, _, _, service, data, declaration = prepared(ledger)
    identity = service.propose(PLAYER, str(uuid4()), data["revision"], 900, declaration)["id"]
    inbox = InboxService(ledger)
    review = next(x for x in inbox.items(ADMIN) if x.identity == identity)
    own = next(x for x in inbox.items(PLAYER) if x.identity == identity)
    assert review.incoming and review.task == "m3_battle_context" and not own.incoming
    assert not any(x.identity == identity for x in inbox.items(OTHER))

    async def confirm():
        caller = current(1, 98701)
        await caller.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(caller, review)
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm) and not await form.interaction_check(current(2))
        form.values.update(
            opening=("yes",),
            reach=("yes",),
            outside=("no",),
            indirect=("no",),
            evidence="Actual opening and reach agreed by original source human",
        )
        await form.confirm.callback(current(1, 98702))
        assert form.completed
        start = next(x for x in inbox.items(PLAYER) if x.identity == identity)
        assert start.incoming and not any(x.identity == identity for x in inbox.items(ADMIN))
        owner = current(2, 98703)
        await owner.response.defer(ephemeral=True)
        await InboxView(inbox, 2).route(owner, start)
        menu = owner.edit_original_response.call_args.kwargs["view"]
        assert isinstance(menu, NativeForm) and menu.title == "Start confirmed battle"
        assert not await menu.interaction_check(current(3))

    before = state(game).sheets["2"].model_dump_json()
    asyncio.run(confirm())
    assert state(game).sheets["2"].model_dump_json() == before and game.dice.calls == 0
