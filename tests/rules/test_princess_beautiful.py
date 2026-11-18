"""Printed p30: a native Princess can mark her own Tag when she Flirts."""

import asyncio
from uuid import uuid4

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, setup_game, start, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_mockingbird import give_tag
from girlframe.services.m3_actors import profiles
from girlframe.services.onboarding import WorkflowError


def test_native_princess_own_tag_flirt_changes_tier_and_preserves_receipt(ledger):
    game, worker, gateway, dice = setup_game(ledger, girl="PRINCESS", faces=(3, 4))
    tag, event = str(uuid4()), str(uuid4())
    with ledger.transaction() as c:
        before = state(game)
        tagged = give_tag(
            before,
            profiles(c, ledger.campaign_id),
            current_ref(before, PLAYER.user_id),
            current_ref(before, OTHER.user_id),
            "Poised",
            tag,
            event,
            (1, 2, 3),
        )
        game.event(c, OTHER.user_id, str(uuid4()), "synthetic.actual_tag", tagged, event_id=event)

    keep = start(game)
    tick(worker, gateway)
    with pytest.raises(WorkflowError, match="printed self-mark exception"):
        answer(
            game,
            PLAYER,
            "tag_window",
            options=("tag",),
            denied=(tag,),
            number=1,
            text="I try to mark my own Tag",
        )
    assert not next(x for x in state(game).sheets["2"].tags if x.id == tag).marked
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("in_control",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual contextual ruling")
    assert "sexy" in game.inspect(PLAYER, keep)["result"]["positive"]
    tick(worker, gateway, 6)

    flirt = start(game, play="flirt", target=OTHER.user_id)
    tick(worker, gateway)
    receipt = game.inspect(PLAYER, flirt)["receipt"]
    assert receipt["pre_total"] == 7
    choice = next(row for row in game.choices(PLAYER) if row["kind"] == "tag_window")

    async def choose():
        shown = current(PLAYER.user_id, 88011001)
        shown.channel_id = 900
        await shown.response.defer(ephemeral=True)
        await open_choice(shown, game, choice["id"])
        form = shown.edit_original_response.call_args.kwargs["view"]
        assert tag in {
            value for value, label in next(f for f in form.fields if f.key == "denied").options
        }
        assert not await form.interaction_check(current(OTHER.user_id, 88011002))
        form.values.update(
            options=("tag",),
            denied=(tag,),
            number=("1",),
            text="My composure is relevant",
        )
        submitted = current(PLAYER.user_id, 88011003)
        submitted.channel_id = 900
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(choose())
    assert not next(x for x in state(game).sheets["2"].tags if x.id == tag).marked
    for viewer in (OTHER, ADMIN):
        answer(game, viewer, "tag_window", options=("pass",))
    assert next(x for x in state(game).sheets["2"].tags if x.id == tag).marked
    with ledger.engine.connect() as c:
        applied = game.action(c, flirt)["data"]
        assert applied["result"]["total"] == 8
        assert applied["modifiers"][0]["tag"] == tag
    answer(game, PLAYER, "actor_flirt", options=("name",))
    answer(game, OTHER, "target_flirt", text="The target's own answer")
    done = game.inspect(PLAYER, flirt)
    assert done["state"] == "complete" and done["receipt"] == receipt
    assert done["result"]["total"] == 8
    assert dice.calls == 2
