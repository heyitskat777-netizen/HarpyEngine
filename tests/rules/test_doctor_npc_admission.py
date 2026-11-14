"""Unsupported NPC treatment is refused before dice, costs or a scene lock."""

import asyncio
from uuid import uuid4

import pytest
from test_doctor_npc_nanobot import setup
from test_ledger import PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.m3_doctor import open_roll
from girlframe.engine.m2 import PlayInput
from girlframe.services.m3_doctor import DoctorService
from girlframe.services.onboarding import WorkflowError


def test_npc_nanobot_unavailable_before_roll_without_partial_effects(ledger, tmp_path, monkeypatch):
    game, _, _, patient, _ = setup(ledger, tmp_path, monkeypatch)
    before = state(game)
    calls = game.dice.calls
    menu = DoctorService(game).menu(PLAYER, 900)
    # The genuine reachable NPC remains available to other care workflows.
    assert patient.token in {row["token"] for row in menu["nurse_targets"]}
    assert menu["npc_nanobot_targets"] == []
    assert "nanobot_injection" in {row["id"] for row in menu["choices"]}

    async def inspect_native_form():
        interaction = current(PLAYER.user_id, 926701)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_roll(interaction, DoctorService(game))
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert "New NPC Nanobot Injection is unavailable" in form.instructions
        assert (
            "Previously rolled NPC actions retain their pending recovery choices"
            in form.instructions
        )
        assert "Nanobot mid-result effect removal only" not in form.instructions

    asyncio.run(inspect_native_form())
    with ledger.engine.connect() as c:
        lock = game.lock(c, 900)
        pending = game.pending_actions(c)
    with pytest.raises(WorkflowError, match="NPC Nanobot Injection is unavailable before rolling"):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            before.sheets["2"].revision,
            PlayInput(
                play="nanobot_injection",
                target_actor=patient,
                heat=1,
                context="An actual reachable NPC patient, not a pilot resource sheet",
                trigger_confirmed=True,
            ),
        )
    assert state(game) == before
    assert game.dice.calls == calls
    with ledger.engine.connect() as c:
        assert game.pending_actions(c) == pending
        assert game.lock(c, 900) == lock
