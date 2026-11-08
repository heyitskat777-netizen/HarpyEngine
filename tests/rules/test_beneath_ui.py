"""Native exact-tier choices and an actual pinned character response Play."""

import asyncio
from uuid import uuid4

import pytest
from test_beneath_service import rolled
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.services.onboarding import WorkflowError


def test_native_high_uses_one_base_and_one_extra_and_holds_lock_through_real_response_play(ledger):
    game, worker, gateway, identity = rolled(ledger, (6, 6))

    async def run():
        owner = current(2, 17101)
        await owner.response.defer(ephemeral=True)
        await open_choice(owner, game, game.choices(PLAYER)[0]["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        fields = {x.key: x for x in form.fields}
        assert fields["options"].minimum == fields["options"].maximum == 1
        assert fields["beneath_extra"].minimum == fields["beneath_extra"].maximum == 1
        assert set(dict(fields["options"].options)) == {"tag", "status", "bond"}
        assert not await form.interaction_check(current(3))
        form.values.update(
            options=("tag",),
            beneath_extra=("pin",),
            text="Actual pin",
            **{"fields.tag": "PRIVATE_PIN_TAG"},
        )
        await form.confirm.callback(current(2, 17102))
        assert form.completed
        target = current(3, 17103)
        target.channel_id = 900
        await target.response.defer(ephemeral=True)
        await open_choice(target, game, game.choices(OTHER)[0]["id"])
        response = target.edit_original_response.call_args.kwargs["view"]
        response.values.update(options=("play",))
        await response.confirm.callback(current(3, 17104))
        assert response.completed and game.dice.calls == 1
        child_request = game.choices(OTHER)[0]
        assert child_request["kind"] == "beneath_response_play"
        await open_choice(target, game, child_request["id"])
        child_form = target.edit_original_response.call_args.kwargs["view"]
        child_form.values.update(
            play=("keep_your_head",),
            context="Endure the actual pin",
            gain=("0",),
            pair_share=("0",),
            heat=("0",),
            piloting=("no",),
            witnessed=("no",),
            trigger=("yes",),
        )
        await child_form.confirm.callback(current(3, 17105))
        assert child_form.completed

    asyncio.run(run())
    game.dice.faces = (4, 5)
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, OTHER, "actor_keep", options=("tough", "vicious"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Enough to stay composed")
    result = game.inspect(PLAYER, identity)
    assert result["state"] == "complete" and game.dice.calls == 2
    assert result["receipt"]["faces"] == [6, 6] and "response_play" in result["result"]
    assert "escaped" not in result["result"]
    tick(worker, gateway, 6)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_social_participants_cannot_start_another_scene_play_while_their_effect_is_pending(ledger):
    game, _, _, _ = rolled(ledger)
    for viewer in (PLAYER, OTHER):
        with pytest.raises(WorkflowError, match="ACTOR_BUSY"):
            game.begin(
                viewer,
                str(uuid4()),
                901,
                state(game).sheets[str(viewer.user_id)].revision,
                PlayInput(
                    play="keep_your_head",
                    context="Cannot bypass the actual pending effect",
                    trigger_confirmed=True,
                    heat=0,
                ),
            )


def test_failed_effect_history_rolls_back_choice_and_real_tag_without_resampling(
    ledger, monkeypatch
):
    game, _, _, identity = rolled(ledger)
    row = game.choices(PLAYER)[0]
    before = state(game)
    original = game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic failure after effect history")

    monkeypatch.setattr(game, "event", fail)
    data = ChoiceAnswer(
        options=("tag", "status"), fields={"tag": "One actual Tag"}, text="Actual outcome"
    )
    with pytest.raises(RuntimeError):
        game.respond(PLAYER, "retry-social-effect", row["id"], row["revision"], data)
    assert state(game) == before and game.dice.calls == 1
    monkeypatch.setattr(game, "event", original)
    result = game.respond(PLAYER, "retry-social-effect", row["id"], row["revision"], data)
    assert game.respond(PLAYER, "retry-social-effect", row["id"], row["revision"], data) == result
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1
