"""Characterize the statement path without inventing a scene-history audience."""

import asyncio

import pytest
from test_cast_service import change
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, state
from test_mission_ui import current
from test_secretary import acquire, form, play, ready

from girlframe.discord_adapter.inbox import InboxView
from girlframe.engine import m3_secretary as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_secretary import SecretaryService
from girlframe.services.onboarding import WorkflowError


def test_authoritative_statement_records_owner_history_without_implied_scene_delivery(
    ledger, tmp_path, monkeypatch
):
    game, service, _, _ = ready(ledger, tmp_path, monkeypatch)
    secretary = acquire(service, game)
    casts = CastService(ActorService(MissionService(ledger)))
    change(casts, OTHER, "withdraw", current_ref(state(game), 3))
    play(
        service,
        secretary.id,
        "appear",
        scene=("900",),
        place=("base0",),
        account="The Secretary joins the actual briefing scene",
    )
    before = state(game)
    dice = Dice(())
    service.game.dice = dice
    statement = "The original Handler confirms the briefing begins now."
    step = form(service, secretary.id, play=("authority",))

    async def record():
        view = step.edit_original_response.call_args.kwargs["view"]
        assert "Statements are saved only in your History" in view.instructions
        assert "share them in the scene yourself" in view.instructions
        view.values.update(scene=("900",), target=("statement",), text=statement)
        result = current(1, 41299)
        await result.response.defer(ephemeral=True)
        await view.confirm.callback(result)
        assert view.completed, result.edit_original_response.call_args
        confirmation = result.edit_original_response.call_args.kwargs["content"]
        assert "Statement recorded in your History only" in confirmation
        assert "Share it in the scene yourself" in confirmation

    asyncio.run(record())
    after = state(game)
    spoken = next(x for x in rules.performances(after) if x.play == "authority")
    assert spoken.actor == secretary.actor and spoken.principal == secretary.handler
    assert spoken.account == statement and spoken.scene == before.scene_casts[0].id
    assert spoken.order is None and spoken.recipients == ()
    assert after.model_dump(exclude={"revision", "facts"}) == before.model_dump(
        exclude={"revision", "facts"}
    )
    assert after.facts[:-1] == before.facts and after.facts[-1]["id"] == spoken.id
    assert dice.calls == 0 and game.choices(PLAYER) == []

    # This records the current limitation, not a ruling that speech must stay private.
    # A future audience change must specify recipients instead of trusting current cast.
    with ledger.engine.connect() as c:
        assert 2 in game.scene(c, 900)["participants"]
        assert 3 not in game.scene(c, 900)["participants"]
    reopened = SecretaryService(ledger)
    inbox = InboxService(ledger)
    for viewer in (PLAYER, OTHER):
        assert not any(x.identity == spoken.id for x in inbox.items(viewer))
        with pytest.raises(WorkflowError, match="original recipients"):
            reopened.menu(viewer, spoken.id)

    async def history():
        item = next(
            x for x in inbox.items(ADMIN) if x.task == "m3_secretary" and x.identity == spoken.id
        )
        own = current(1, 41300)
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 1).route(own, item)
        response = own.edit_original_response.call_args.kwargs
        assert statement in response["content"]
        assert not response["allowed_mentions"].everyone

    asyncio.run(history())
    assert state(game) == after
