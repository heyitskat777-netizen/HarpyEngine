"""Printed p33: actual boarding does not compel the guest's optional Dive effect."""

import asyncio

import pytest
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_mockingbird_communion import respond, source

from girlframe.discord_adapter.m3_mockingbird_communion import open_call
from girlframe.services.m3_mockingbird_communion import CallService
from girlframe.services.onboarding import WorkflowError


def test_native_boarded_guest_may_decline_extra_choice_without_losing_boarding(ledger, monkeypatch):
    game, _, _, action = source(ledger, monkeypatch)
    service = CallService(game)
    session = state(game).mockingbird.calls[-1].id
    respond(service, OTHER, session, "accept")
    before = state(game)
    boarded_call = before.mockingbird.calls[-1]
    passenger = next(x for x in before.passengers if x.id == boarded_call.passenger)
    assert passenger.state == "boarded" and passenger.accepted_event
    assert passenger.actor == boarded_call.guest
    receipt = game.inspect(PLAYER, action)["receipt"]
    revision = service.get(OTHER, session)["revision"]
    assert service.get(OTHER, session)["phase"] == "effect"
    with pytest.raises(WorkflowError):
        respond(service, PLAYER, session, "decline_effect")
    with pytest.raises(WorkflowError, match="unapplied"):
        respond(service, OTHER, session, "decline_effect", option="void_and_unmark_all")
    assert service.get(OTHER, session)["revision"] == revision

    async def run():
        interaction = current(3, 267301)
        await interaction.response.defer(ephemeral=True)
        await open_call(interaction, service, session)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert ("decline_effect", "Stay aboard without an extra Dive choice") in form.fields[
            0
        ].options
        form.values.update(
            option=("decline_effect",), account="I stay aboard, choosing no extra effect"
        )
        await form.confirm.callback(current(3, 267302))
        assert form.completed

    asyncio.run(run())
    after = state(game)
    call = after.mockingbird.calls[-1]
    assert call.phase == "complete" and call.choice_event == call.completed_event
    assert call.option is None and call.effect_json is None
    assert call.answer == "I stay aboard, choosing no extra effect"
    assert after.sheets == before.sheets
    assert after.placements == before.placements
    assert after.passengers == before.passengers
    assert after.scene_casts == before.scene_casts
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, action)["receipt"] == receipt and game.dice.calls == 1
    with pytest.raises(WorkflowError):
        service.respond(
            OTHER,
            "stale-optional-choice",
            session,
            revision,
            "decline_effect",
            {"account": "Cannot apply twice"},
        )
    assert state(game) == after
