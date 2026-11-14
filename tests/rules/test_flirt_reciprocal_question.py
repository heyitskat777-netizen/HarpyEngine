"""Printed reciprocal Flirt question through owned native controls and saved sources."""

import asyncio
import json
from uuid import uuid4

import pytest
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, setup_game, start, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError


def native_form(game, viewer, row, number):
    async def show():
        interaction = current(viewer.user_id, number)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, row["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        assert not await form.interaction_check(current(1, number + 1))
        return form

    return asyncio.run(show())


def submit(form, viewer, number, **values):
    async def save():
        interaction = current(viewer.user_id, number)
        interaction.channel_id = 900
        form.values.update(values)
        await form.confirm.callback(interaction)
        assert form.completed, interaction.edit_original_response.call_args_list

    asyncio.run(save())


@pytest.mark.parametrize("faces", [(4, 4), (6, 6)])
def test_native_both_flirt_questions_keep_owned_answers_followthrough_and_high_work(ledger, faces):
    game, worker, gateway, dice = setup_game(ledger, faces=faces)
    high = sum(faces) > 10
    if high:
        with ledger.transaction() as c:
            actual = state(game)
            actual.bonds["2:3"] = 2
            game.event(c, 1, str(uuid4()), "synthetic.prior_mutual_intense_bond", actual)
    action = start(game, play="flirt", target=3)
    tick(worker, gateway, 3)
    pass_tags(game)
    receipt = game.inspect(PLAYER, action)["receipt"]
    answer(
        game,
        PLAYER,
        "actor_flirt",
        options=("name",),
        fields={"extra": "owe"} if high else {},
        text="I actually go too far" if high else "",
    )
    row = next(x for x in game.choices(OTHER) if x["kind"] == "target_flirt")
    form = native_form(game, OTHER, row, 997001)
    selector = next(x for x in form.fields if x.key == "options")
    assert selector.minimum == 0 and selector.maximum == 1 and not selector.required
    question = "intimacy" if high else "be"
    assert question in dict(selector.options)
    submit(form, OTHER, 997003, text="PRIVATE_FLIRT_TARGET My chosen name", options=(question,))

    returned = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_flirt_answer")
    with pytest.raises(WorkflowError):
        game.decision(OTHER, returned["id"])
    reopened = GameService(ledger).decision(PLAYER, returned["id"])
    assert reopened["result"]["return_question"] == question
    reciprocal = native_form(game, PLAYER, returned, 997010)
    assert "Return question:" in reciprocal.text()
    assert ("Do you want to be intimate" if high else "Who would you like me to be") in (
        reciprocal.text()
    )
    if high:
        # The high result's real cost can complete before the reciprocal reply;
        # the source remains held instead of rolling back either person's answer.
        answer(game, OTHER, "flirt_owe_tag", text="A genuine owed Tag")
        assert game.inspect(PLAYER, action)["state"] != "complete"
        original = state(game)
        with pytest.raises(WorkflowError, match="Consent is not inferred"):
            game.respond(
                PLAYER,
                "no-inferred-reciprocal-consent",
                returned["id"],
                returned["revision"],
                ChoiceAnswer(text="PRIVATE_FLIRT_RETURN My own answer", flag=False),
            )
        assert state(game) == original
        assert "flag" in {x.key for x in reciprocal.fields}

    values = {"text": "PRIVATE_FLIRT_RETURN My own answer"}
    if high:
        values["flag"] = ("yes",)
    submit(reciprocal, PLAYER, 997012, **values)
    final = state(game)
    game.respond(
        PLAYER,
        "997012",
        returned["id"],
        returned["revision"],
        ChoiceAnswer(text="PRIVATE_FLIRT_RETURN My own answer", flag=True if high else None),
    )
    assert state(game) == final
    follow = [
        x for x in final.obligations if x.action == action and x.kind == "flirt_followthrough"
    ]
    assert {(x.owner, x.target) for x in follow} == {(2, 3), (3, 2)}
    assert next(x for x in follow if x.owner == 3).details["wanted"] == (
        "PRIVATE_FLIRT_RETURN My own answer"
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, action)["receipt"] == receipt and dice.calls == 1
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert all(
        x not in json.dumps(gateway.messages)
        for x in ("PRIVATE_FLIRT_TARGET", "PRIVATE_FLIRT_RETURN")
    )
