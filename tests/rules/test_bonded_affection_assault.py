"""Actual witnessed-affection All Out Assault completes before source-owned Silence."""

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

from test_bonded import PEOPLE, pass_tags, pause_tick, propose, ready
from test_ledger import ADMIN, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick

from girlframe.discord_adapter import m3_bonded as adapter
from girlframe.engine import m3_bonded as bonded
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_battle_state import Declaration
from girlframe.services.m3_battle import BattleService


def test_witnessed_affection_actual_assault_then_silence(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, three=True)
    source = propose(controls, game, "intimacy", observer=4)
    controls.activate(
        PLAYER,
        str(uuid4()),
        source,
        state(game).revision,
        "My real affection is seen by the onlooker",
    )
    pause_tick(game, gateway)
    context = "I take an actual opening against the onlooker"
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
                    "play": "all_out_assault",
                    "context": context,
                }
            ),
        ),
    )
    # Synthetic initial resources/positions are inherited; battle facts are genuinely
    # proposed by the owner and confirmed by the human facilitator service.
    battle = BattleService(game.store)
    preview = battle.preview(PLAYER, 900)
    actor = next(x for x in preview["actors"] if x["ref"]["entity"] == "2")
    target_row = next(x for x in preview["actors"] if x["ref"]["entity"] == "4")
    declaration = Declaration(
        play="all_out_assault",
        actor=ActorRef.model_validate(actor["ref"]),
        target=ActorRef.model_validate(target_row["ref"]),
        attacking_asset=actor["assets"][0]["id"],
        target_asset=target_row["assets"][0]["id"],
        actor_sha256=actor["sha256"],
        target_sha256=target_row["sha256"],
        account="I take an actual opening against the onlooker",
    )
    proposed = battle.propose(PLAYER, str(uuid4()), preview["revision"], 900, declaration)
    battle.confirm(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        proposed["id"],
        opening=True,
        reach=True,
        outside_permission=True,
        indirect=False,
        evidence="Actual opening, reach and outside-Frame capability",
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
        assert prepared.target_actor == target
        assert prepared.target is None
        assert prepared.source_work == child["id"]
        assert prepared.battle_context == proposed["id"]
        assert prepared.attacking_asset == declaration.attacking_asset
        assert prepared.target_asset == declaration.target_asset
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
        await opened[0].submit_action(
            interaction, {"heat": ("0",), "context": context, "battle": (proposed["id"],)}
        )

    asyncio.run(submit_native())
    action = results[0]["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    assert controls.view(PLAYER, source)["phase"] == "child"
    assert bonded.can_disclose(state(game), target, source)
    for viewer in (ADMIN, *PEOPLE.values()):
        choice = next(x for x in game.choices(viewer) if x["kind"] == "battle_assault_table")
        game.respond(
            viewer,
            str(uuid4()),
            choice["id"],
            choice["revision"],
            ChoiceAnswer(flag=False, text="My actual table judgment"),
        )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert controls.view(PLAYER, source)["phase"] == "complete"
    assert not bonded.can_disclose(state(game), target, source)
    assert next(
        x for x in state(game).sheets["4"].assets if x.id == declaration.target_asset
    ).damaged
    assert game.dice.calls == 1
