"""Exercise the Activity adapter with HarpyEngine's reviewed-contact fixture."""

import asyncio
from uuid import uuid4

import pytest
from battlefield import Battlefield
from test_janus_battery import connected
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import pass_tags, state

from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


@pytest.mark.parametrize(
    "faces, picks",
    [
        ((1, 1), ["question"]),
        ((2, 2), ["cognition", "question"]),
        ((6, 6), ["cognition", "offset", "heat", "question"]),
    ],
)
def test_living_battery_uses_actual_contact_and_owns_private_reply(
    ledger, tmp_path, monkeypatch, faces, picks
):
    game, worker, gateway, core, _ = connected(ledger, tmp_path, monkeypatch, faces=faces)
    activity = Battlefield(MissionService(ledger), ADMIN, PLAYER, OTHER, shared=True)
    activity.game = game
    option = next(
        item for item in activity.view(PLAYER)["actions"] if item["id"] == "living_battery"
    )
    assert option["targets"][0]["ref"] == core.model_dump(mode="json")
    started = activity.perform(
        PLAYER,
        str(uuid4()),
        "living_battery",
        {
            "target": option["targets"][0]["ref"],
            "sheet_revision": state(game).sheets["2"].revision,
            "account": "Use the established neural connection.",
            "confirmed": True,
        },
    )["action_id"]
    lock = worker.claim("m2_locks", ("acquiring",))
    asyncio.run(worker.acquire(lock, gateway))
    game.roll(PLAYER, str(uuid4()), started)
    delivery = worker.claim("m2_outbox", ("pending",))
    if delivery:
        asyncio.run(worker.deliver(delivery, gateway))
    pass_tags(game)
    if faces == (1, 1):
        erase = next(
            item for item in activity.view(PLAYER)["choices"] if item["kind"] == "janus_erase"
        )
        activity.perform(
            PLAYER,
            str(uuid4()),
            "choice",
            {
                "role": "pilot",
                "id": erase["id"],
                "revision": erase["revision"],
                "answer": {"options": [erase["schema"][0]["options"][0][0]]},
            },
        )
    benefit = next(
        item for item in activity.view(PLAYER)["choices"] if item["kind"] == "janus_select"
    )
    assert benefit["schema"][0]["minimum"] == len(picks)
    activity.perform(
        PLAYER,
        str(uuid4()),
        "choice",
        {
            "role": "pilot",
            "id": benefit["id"],
            "revision": benefit["revision"],
            "answer": {
                "options": picks,
                "number": int("heat" in picks),
                "text": "What did you hear?",
            },
        },
    )
    question = next(
        item for item in activity.view(OTHER)["choices"] if item["kind"] == "janus_answer"
    )
    assert question["prompt"] == "What did you hear?"
    answer = {
        "role": "pilot",
        "id": question["id"],
        "revision": question["revision"],
        "answer": {"text": "There were three signals."},
    }
    with pytest.raises(WorkflowError, match="another participant"):
        activity.perform(PLAYER, str(uuid4()), "choice", answer)
    activity.perform(OTHER, str(uuid4()), "choice", answer)
    result = activity.view(PLAYER)["play"]
    assert result["state"] == "complete"
    assert result["receipt"]["faces"] == list(faces)
    assert result["result"]["brain_answer"] == "There were three signals."
    with ledger.engine.connect() as connection:
        assert started in activity.recent_actions(connection, OTHER, state(game))
