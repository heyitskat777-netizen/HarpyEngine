"""One real ordinary intoxication Tag can use the printed self-mark exception."""

import asyncio
from uuid import uuid4

import pytest
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_malleable import prepared
from test_malleable_player_source import current

from girlframe.discord_adapter.m3_malleable import open_malleable
from girlframe.engine import m3_malleable as rules
from girlframe.engine.m2 import PlayInput
from girlframe.services.m3_malleable_self_tag import prove
from girlframe.services.onboarding import WorkflowError


def test_real_ordinary_intoxication_tag_owner_classification_and_self_mark(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, dosing, controls = prepared(ledger, tmp_path, monkeypatch)
    game.dice.faces = (4, 5)
    original = game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="put_someone_beneath_you",
            target=2,
            heat=0,
            context="Actual confrontation with the intoxicated original Stim",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        OTHER,
        "beneath_select",
        options=("tag", "status"),
        fields={"tag": "PRIVATE_ACTUAL_INTOXICATION"},
        text="Actual established intoxication",
    )
    assert game.inspect(OTHER, original)["state"] == "complete"
    tick(worker, gateway, 5)
    tag = state(game).sheets["2"].tags[-1]
    before = state(game)
    with pytest.raises(WorkflowError):
        controls.classify_intoxication_tag(
            OTHER, str(uuid4()), tag.id, before.revision, "Cannot classify someone else's owned Tag"
        )
    with pytest.raises(WorkflowError):
        controls.classify_intoxication_tag(
            PLAYER, str(uuid4()), tag.id, before.revision - 1, "Stale original source"
        )
    assert state(game) == before

    async def classify():
        opened = current(2, 881001)
        await opened.response.defer(ephemeral=True)
        await open_malleable(opened, controls)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        menu.values["action"] = ("intoxication:" + tag.id,)
        selected = current(2, 881002)
        await menu.confirm.callback(selected)
        form = selected.edit_original_response.call_args.kwargs["view"]
        form.values["account"] = (
            "My actual original Tag represents the scene's established intoxication"
        )
        await form.confirm.callback(current(2, 881003))
        assert form.completed

    asyncio.run(classify())
    classified = rules.records(state(game), rules.IntoxicationTag)[-1]
    assert classified.id == tag.id and classified.action == original and classified.controller == 2
    assert state(game).sheets == before.sheets
    assert not rules.records(state(game), rules.Alteration)  # no invented physiology
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), classified).id == tag.id
    with pytest.raises(WorkflowError):
        controls.classify_intoxication_tag(
            PLAYER, str(uuid4()), tag.id, state(game).revision, "No duplicate classification"
        )
    game.dice.faces = (3, 4)
    calls = game.dice.calls
    keep = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            heat=0,
            context="Actual dangerous evasive reaction",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    answer(
        game,
        PLAYER,
        "tag_window",
        options=("tag",),
        denied=(tag.id,),
        number=1,
        text="The actual intoxication shapes my response to the danger",
    )
    answer(game, OTHER, "tag_window", options=("pass",))
    answer(game, ADMIN, "tag_window", options=("pass",))
    answer(game, PLAYER, "actor_keep", options=("tough", "in_control"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual danger adjudication")
    assert game.inspect(PLAYER, keep)["state"] == "complete"
    assert game.dice.calls == calls + 1
    marked = next(x for x in state(game).sheets["2"].tags if x.id == tag.id)
    assert marked.marked and marked.scene_used
    assert marked.giver_actor == tag.giver_actor and marked.label == tag.label
    assert "PRIVATE_ACTUAL_INTOXICATION" not in str(gateway.messages)
