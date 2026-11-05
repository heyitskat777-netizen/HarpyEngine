"""Real source damage → owned Defeat roll → actual outcome → released parent scene."""

import asyncio
from uuid import uuid4

import pytest
from test_beneath_service import ready
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.services.onboarding import WorkflowError


def required(store):
    game, worker, gateway = ready(store, (1, 1))
    with store.transaction() as c:
        canon = state(game)
        frames = [x for x in canon.sheets["2"].assets if x.family == "frame"]
        for asset in frames[1:]:
            asset.damaged = True
        game.event(c, 1, "actual-old-frame-damage", "synthetic.state", canon)
    identity = game.begin(
        PLAYER,
        "actual-source-social-play",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=3,
            heat=0,
            piloting=True,
            context="Actual confrontation while piloting",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "beneath_select", options=("damage",), text="Actual counterattack")
    answer(game, PLAYER, "beneath_details", denied=(frames[0].id,))
    assert game.choices(PLAYER)[0]["kind"] == "beneath_defeat"
    return game, worker, gateway, identity


def rolled(store, faces=(3, 3)):
    game, worker, gateway, parent = required(store)
    game.dice.faces = faces
    identity = game.begin(
        PLAYER,
        "actual-defeat-child",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="defeat",
            heat=0,
            context="Actual source Defeat",
            trigger_confirmed=True,
            parent=parent,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    return game, worker, gateway, parent, identity


def test_real_defeat_roll_uses_girl_assets_and_escape_finishes_parent_without_second_source_roll(
    ledger,
):
    game, worker, gateway, parent, identity = rolled(ledger)
    receipt = game.inspect(PLAYER, identity)["receipt"]
    assert receipt["pre_total"] == 8 and receipt["base_modifier"] == 2
    assert receipt["modifier_source"] == "Undamaged Girl Assets"
    assert game.dice.calls == 2
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("escape_cockpit_choose_location",),
        text="Pry out and shelter behind the damaged Frame",
    )
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert state(game).placements[0].mode == "outside_frame"
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_native_defeat_start_and_result_have_no_heat_field_and_preserve_original_receipt(ledger):
    game, worker, gateway, parent = required(ledger)

    async def start():
        owner = current(2, 21101)
        await owner.response.defer(ephemeral=True)
        await open_choice(owner, game, game.choices(PLAYER)[0]["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert not any(x.key in ("heat", "identity", "gain") for x in form.fields)
        form.values.update(account="Actual required Defeat")
        await form.confirm.callback(current(2, 21102))
        assert form.completed

    asyncio.run(start())
    game.dice.faces = (3, 3)
    tick(worker, gateway, 3)
    pass_tags(game)

    async def choose():
        owner = current(2, 21103)
        await owner.response.defer(ephemeral=True)
        await open_choice(owner, game, game.choices(PLAYER)[0]["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(options=("escape_cockpit_choose_location",), account="Actual escape")
        response = current(2, 21104)
        await form.confirm.callback(response)
        assert form.completed, str(response.edit_original_response.call_args) + str(
            response.followup.send.call_args
        )

    asyncio.run(choose())
    assert game.inspect(PLAYER, parent)["state"] == "complete" and game.dice.calls == 2


def test_defeat_cannot_be_started_freely_or_with_heat_and_failed_attempts_do_not_draw_rng(ledger):
    game, _, _ = ready(ledger, (3, 3))
    with pytest.raises(WorkflowError, match="actual source"):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(play="defeat", heat=0, context="No actual source", trigger_confirmed=True),
        )
    assert game.dice.calls == 0


def test_actual_death_archives_original_and_finishes_parent_without_replacement_authority(
    ledger,
):
    game, worker, gateway, parent, identity = rolled(ledger, faces=(1, 1))
    original = state(game).sheets["2"].character_id
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("death",),
        text="Actual owned consequence: die from injuries",
    )
    canon = state(game)
    assert "2" not in canon.sheets and 2 not in canon.order
    assert canon.career_archives[-1].actor.incarnation == original
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    tick(worker, gateway, 5)
    with pytest.raises(WorkflowError):
        game.sheet(PLAYER)


def test_high_invited_girl_owns_optional_tag_and_scene_waits_for_real_reply(ledger):
    game, _, _, parent, identity = rolled(ledger, faces=(6, 6))
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("lower_status", "another_girl_gives_tag"),
        fields={"tag_giver": "3"},
        text="Actual Handler rescue",
    )
    assert game.inspect(PLAYER, parent)["state"] == "awaiting_choices"
    with pytest.raises(WorkflowError):
        invited = game.choices(OTHER)[0]
        game.respond(
            PLAYER,
            "cannot-forge-gift",
            invited["id"],
            invited["revision"],
            ChoiceAnswer(options=("give",), text="Cannot forge another human"),
        )
    answer(game, OTHER, "defeat_tag_gift", options=("give",), text="Survivor")
    assert state(game).sheets["2"].tags[-1].giver == 3
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
