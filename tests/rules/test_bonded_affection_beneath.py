"""Actual witnessed-affection Beneath completes before source-owned Silence."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

from test_bonded import pass_tags, pause_tick, propose, ready
from test_ledger import PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick

from girlframe.discord_adapter import m3_bonded as adapter
from girlframe.engine import m3_bonded as bonded
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref


def test_witnessed_affection_actual_beneath_then_silence(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, three=True)
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            )
        }
    )
    source = propose(controls, game, "intimacy", observer=4)
    controls.activate(
        PLAYER,
        str(uuid4()),
        source,
        state(game).revision,
        "My real affection is seen by the onlooker",
    )
    pause_tick(game, gateway)
    context = "I put the actual onlooker beneath me"
    controls.choose(
        PLAYER,
        str(uuid4()),
        source,
        state(game).revision,
        ChoiceAnswer(
            options=("child",),
            text=json.dumps(
                {
                    "account": "My owned response",
                    "play": "put_someone_beneath_you",
                    "context": context,
                }
            ),
        ),
    )
    child = controls.view(PLAYER, source)["child"]
    target = current_ref(state(game), 4)
    game.dice.faces = (4, 4)
    # Exercise the native child opener and its actual form submission payload.
    # Delivery/viewer are mocked; field values are direct, not Discord dispatch.
    opened = []
    results = []
    original_begin = game.begin

    async def capture_reply(interaction, text, form=None):
        opened.append(form)

    def capture_begin(viewer, request, channel, revision, prepared):
        assert prepared.target_actor is None
        assert prepared.target == 4
        assert prepared.source_work == child["id"]
        result = original_begin(viewer, request, channel, revision, prepared)
        results.append(result)
        return result

    monkeypatch.setattr(adapter, "reply", capture_reply)
    monkeypatch.setattr(adapter, "viewer_from_interaction", lambda _: PLAYER)
    monkeypatch.setattr(game, "begin", capture_begin)

    async def submit_native():
        interaction = SimpleNamespace(user=SimpleNamespace(id=2), id=882781, channel_id=900)
        await adapter.open_child(interaction, game, child["id"])
        assert len(opened) == 1
        await opened[0].submit_action(interaction, {"heat": ("0",), "context": context})

    asyncio.run(submit_native())
    action = results[0]["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    assert controls.view(PLAYER, source)["phase"] == "child"
    assert bonded.can_disclose(state(game), target, source)
    before_tags = len(state(game).sheets["4"].tags)
    choice = next(x for x in game.choices(PLAYER) if x["kind"] == "beneath_select")
    game.respond(
        PLAYER,
        str(uuid4()),
        choice["id"],
        choice["revision"],
        ChoiceAnswer(
            options=("tag", "status"),
            fields={"tag": "Discreet"},
            text="I confront the actual onlooker",
        ),
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert controls.view(PLAYER, source)["phase"] == "complete"
    assert not bonded.can_disclose(state(game), target, source)
    assert len(state(game).sheets["4"].tags) == before_tags + 1
    assert state(game).sheets["4"].tags[-1].giver == 2
    assert game.dice.calls == 1
