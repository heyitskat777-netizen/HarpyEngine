"""Printed p48 mid Doll optional benefits retain the actual owned roll and proof."""

import asyncio
from uuid import uuid4

import pytest
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current
from test_vatgrown import choose, ready, roll

from girlframe.engine import m3_vatgrown as rules
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.services.m3_vatgrown import _selected_benefits, prove
from girlframe.services.onboarding import WorkflowError


def test_mid_doll_owner_declines_both_benefits_with_native_choice_and_durable_proof(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    before = state(game)
    action = roll(game, worker, gateway, faces=(4, 5), heat=1, native=True)
    receipt = game.inspect(PLAYER, action)["receipt"]
    calls = game.dice.calls
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "vat_doll_benefits")
    detail = game.decision(PLAYER, row["id"])["detail"]
    assert "decline" in dict(detail["options"])
    assert (detail["minimum"], detail["maximum"]) == (1, 2)
    frozen = state(game).model_dump_json()
    for viewer, response in (
        (OTHER, ChoiceAnswer(options=("decline",))),
        (PLAYER, ChoiceAnswer(options=("decline", "quiet"))),
        (PLAYER, ChoiceAnswer(options=("quiet",))),
        (PLAYER, ChoiceAnswer(options=("decline",), text="Not a real information choice")),
    ):
        with pytest.raises(WorkflowError):
            game.respond(viewer, str(uuid4()), row["id"], row["revision"], response)
        assert state(game).model_dump_json() == frozen
    choose(game, PLAYER, "vat_doll_benefits", ("decline",), native=True)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    assert game.dice.calls == calls
    after = state(game)
    assert after.sheets["2"].heat == before.sheets["2"].heat - 1
    assert after.sheets["3"] == before.sheets["3"]
    assert not [x for x in rules.records(after, rules.Effect) if x.action == action]
    assert not [x for x in rules.records(after, rules.Information) if x.action == action]
    saved = controls.view(PLAYER, action)
    assert saved["benefits"] == ()
    assert not saved["quiet"] and not saved["object"] and saved["leave"] is None
    assert saved["information"] is None
    with ledger.engine.connect() as c:
        actual = prove(game, c, after, action)
        assert actual.complete and actual.benefit_choice and actual.benefit_event
        forged = state(game)
        rules.put(forged, actual.model_copy(update={"benefits": ("quiet",)}))
        with pytest.raises(WorkflowError):
            prove(game, c, forged, action)

    async def reopen():
        from girlframe.discord_adapter.m3_vatgrown import open_vatgrown

        interaction = current(2, 97820)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_vatgrown(interaction, controls, action)
        content = interaction.edit_original_response.call_args.kwargs["content"]
        assert "declined; no benefits taken" in content and "not selected" not in content

    asyncio.run(reopen())
    # Retain existing high/low admission; do not newly interpret their wording here.
    for total in (7, 11):
        with pytest.raises(WorkflowError):
            _selected_benefits(total, ("decline",))
        assert _selected_benefits(total, ("quiet",)) == ("quiet",)
    assert _selected_benefits(9, ("quiet", "leave")) == ("quiet", "leave")
