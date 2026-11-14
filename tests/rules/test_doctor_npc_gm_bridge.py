"""An unsupported actual NPC result gets a durable GM decision, not invented resources."""

import asyncio
from uuid import uuid4

import pytest
from test_doctor_npc_nanobot import roll_nanobot, setup
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m3_doctor import open_choice
from girlframe.services.m3_doctor import DoctorService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.p1_facilitator import FacilitatorService


def test_high_npc_nanobot_opens_durable_gm_request_without_completing_treatment(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, patient, _ = setup(ledger, tmp_path, monkeypatch)
    facilitator = FacilitatorService(game)
    facilitator.configure(ADMIN, str(uuid4()), "user", OTHER.user_id)
    before = state(game)
    game.dice.faces = (6, 6)
    action = roll_nanobot(game, patient, 1)
    tick(worker, gateway, 3)
    pass_tags(game)
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "doctor_patient")
    receipt = game.inspect(PLAYER, action)["receipt"]

    async def open_pending(viewer, key):
        interaction = current(viewer.user_id, key)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, DoctorService(game), row["id"])
        return interaction

    with pytest.raises(WorkflowError):
        asyncio.run(open_pending(PLAYER, 819901))
    assert facilitator.tasks(ADMIN) == []
    interaction = asyncio.run(open_pending(ADMIN, 819902))
    assert "Human adjudication" in interaction.edit_original_response.call_args.kwargs["content"]
    requests = facilitator.tasks(ADMIN)
    assert len(requests) == 1
    identity = requests[0]["id"]
    packet = facilitator.view(ADMIN, identity)
    assert packet["request"]["source"] == action
    assert packet["request"]["rule"] == "choice:doctor_patient"
    assert packet["request"]["status"] == "awaiting_ruling"
    assert packet["request"]["mandatory"]
    assert facilitator.view(OTHER, identity)["request"]["source"] != action
    # Restarted services expose the same request; reopening cannot duplicate the source.
    asyncio.run(open_pending(ADMIN, 819903))
    assert [x["id"] for x in FacilitatorService(game).tasks(ADMIN)] == [identity]
    packet = facilitator.view(ADMIN, identity)
    facilitator.change(
        ADMIN, str(uuid4()), identity, packet["revision"], state(game).revision, "share"
    )
    packet = facilitator.view(OTHER, identity)
    facilitator.change(
        OTHER,
        str(uuid4()),
        identity,
        packet["revision"],
        state(game).revision,
        "rule",
        "GM decision: keep the NPC resource outcome pending; do not invent a pilot sheet.",
        adapter="blocked",
    )
    packet = facilitator.view(ADMIN, identity)
    assert "GM decision" in packet["request"]["ruling"]
    with pytest.raises(WorkflowError):
        facilitator.change(
            ADMIN, str(uuid4()), identity, packet["revision"], state(game).revision, "resume"
        )
    after = state(game)
    assert after.sheets["2"].heat == before.sheets["2"].heat - 1
    assert after.sheets["2"].obsolescence_marked == 1
    assert after.sheets["3"] == before.sheets["3"]
    assert patient.entity not in after.sheets
    assert game.dice.calls == 1
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    assert game.inspect(PLAYER, action)["state"] != "complete"
    assert any(x["id"] == row["id"] for x in game.choices(ADMIN))
