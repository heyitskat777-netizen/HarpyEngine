"""Actual native piloted counter, committed Feedback, final Frame loss and owned Defeat."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ankou_dose_counter_feedback import ready
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_alpha import open_alpha_choice
from girlframe.engine import m3_alpha as alpha
from girlframe.engine import m3_ankou_feedback as feedback
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_physical_state import CockpitAction
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_ankou_feedback import FeedbackService, prepare_child, prove
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.onboarding import WorkflowError


def test_native_piloted_beneath_counter_feedback_requires_real_defeat(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, identity = ready(ledger, tmp_path, monkeypatch)
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            ),
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            ),
        }
    )
    # The reused fixture's map/resources are synthetic initial setup. All later
    # occupancy, damage, marking, Feedback and Defeat use actual owned services.
    physical = PhysicalService(ledger)
    for viewer in (PLAYER, OTHER):
        actual = state(game)
        actor = current_ref(actual, viewer.user_id)
        with ledger.engine.connect() as c:
            body = resolve(actual, actor, profiles(c, ledger.campaign_id))
        physical.operate(
            viewer,
            str(uuid4()),
            actual.revision,
            CockpitAction(
                actor=actor,
                operation="pilot",
                expected_position=body.position_sha256,
                confirmed=True,
                account="I enter and pilot my actual original Frame",
            ),
            channel=900,
        )
    frame_assets = [
        x.id for x in state(game).sheets["3"].assets if x.family == "frame" and not x.damaged
    ]
    assert len(frame_assets) >= 2
    for asset in frame_assets[:-1]:
        game.dice = Dice((1, 1))
        prior = game.begin(
            OTHER,
            str(uuid4()),
            900,
            state(game).sheets["3"].revision,
            PlayInput(
                play="put_someone_beneath_you",
                target=2,
                heat=0,
                piloting=True,
                context="Our actual Frame confrontation and agreed opportunity to strike",
                trigger_confirmed=True,
            ),
        )["action_id"]
        tick(worker, gateway, 4)
        pass_tags(game)
        answer(game, PLAYER, "beneath_select", options=("damage",), text="An actual Frame strike")
        answer(game, OTHER, "beneath_details", denied=(asset,))
        assert game.inspect(OTHER, prior)["state"] == "complete"
        tick(worker, gateway, 6)

    game.dice = Dice((1, 1))
    actor, attacker = current_ref(state(game), 3), current_ref(state(game), 2)
    parent = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="brutalize",
            target_actor=actor,
            piloting=True,
            heat=0,
            context="PRIVATE_PILOTED_DEFEAT: the Alpha tears into me over our Frame comms",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 4)
    pass_tags(game)
    parent_receipt = game.inspect(PLAYER, parent)["receipt"]
    answer(game, OTHER, "alpha_low", options=("counter_broken",))
    counter_choice = next(x for x in game.choices(OTHER) if x["kind"] == "alpha_counter_play")

    async def begin_native_counter():
        opened = current(3, 99701)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_alpha_choice(opened, game, counter_choice["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert "piloting" in {x.key for x in form.fields}
        assert not await form.interaction_check(current(2, 99702))
        form.values.update(
            play=("put_someone_beneath_you",),
            identity=(identity,),
            gain=("1",),
            heat=("1",),
            piloting=("no",),
            context="PRIVATE_PILOTED_DEFEAT: my actual last-Identity counter while piloting",
        )
        before = state(game)
        await form.confirm.callback(current(3, 99703))
        assert not form.completed and state(game) == before and game.dice.calls == 1
        form.values["piloting"] = ("yes",)
        submitted = current(3, 99704)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    asyncio.run(begin_native_counter())
    with ledger.engine.connect() as c:
        actions = t.m2["m2_actions"]
        child = c.scalar(
            sa.select(actions.c.id).where(
                actions.c.campaign_id == ledger.campaign_id, actions.c.parent_id == parent
            )
        )
        assert game.action(c, child)["data"]["prepared"]["piloting"] is True
    tick(worker, gateway, 4)
    if not any(x.action == child for x in feedback.sources(state(game))):
        game.roll(OTHER, "m2.confirmed_roll:" + child, child)
    value = next(x for x in feedback.sources(state(game)) if x.action == child)
    assert value.phase == "choice" and value.beneath_counter_source
    assert game.dice.calls == 1 and game.inspect(OTHER, child)["receipt"] is None
    committed = state(game).sheets["3"].heat
    answer(
        game,
        OTHER,
        "ankou_feedback_choice",
        options=("purpose",),
        fields={"target": attacker.token},
        text="PRIVATE_PILOTED_DEFEAT: my actual plea",
    )
    private = FeedbackService(game).view(PLAYER, value.id)
    assert not {"prepared", "identity", "heat_before", "heat_committed"} & set(private)
    answer(
        game,
        PLAYER,
        "ankou_feedback_purpose",
        flag=True,
        text="PRIVATE_PILOTED_DEFEAT: keep our people safe",
    )
    replace = next(x.id for x in state(game).sheets["3"].identities if not x.protected)
    answer(game, OTHER, "ankou_feedback_identity", fields={"replace": replace})
    tick(worker, gateway, 4)
    pass_tags(game)
    receipt = game.inspect(OTHER, child)["receipt"]
    assert receipt["heat"] == 1 and game.inspect(OTHER, child)["result"] is None
    selection = next(x for x in game.choices(PLAYER) if x["kind"] == "beneath_select")
    assert game.decision(PLAYER, selection["id"])["result"]["tier"] == "low"
    assert state(game).sheets["3"].heat == committed and game.dice.calls == 2
    answer(
        game,
        PLAYER,
        "beneath_select",
        options=("damage",),
        text="PRIVATE_PILOTED_DEFEAT: I strike the final functioning Frame Asset",
    )
    resource = next(x for x in game.choices(OTHER) if x["kind"] == "beneath_details")
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            resource["id"],
            resource["revision"],
            ChoiceAnswer(denied=(frame_assets[-1],)),
        )
    answer(game, OTHER, "beneath_details", denied=(frame_assets[-1],))
    pending = next(x for x in game.choices(OTHER) if x["kind"] == "beneath_defeat")
    assert any(x.identity == pending["id"] for x in InboxService(ledger).items(OTHER))
    before = state(game)
    assert all(x.damaged for x in before.sheets["3"].assets if x.family == "frame")
    assert not alpha.conditions(before, attacker, actor)
    expected = PlayInput(
        play="defeat",
        parent=child,
        piloting=True,
        heat=0,
        trigger_confirmed=True,
        context="PRIVATE_PILOTED_DEFEAT: my actual last-Frame loss",
    )
    with ledger.engine.connect() as c:
        assert prepare_child(game, c, OTHER, before, expected, 900) is None
        for owner, attempt in (
            (PLAYER, expected),
            (OTHER, expected.model_copy(update={"source_work": value.id})),
            (OTHER, expected.model_copy(update={"piloting": False})),
            (OTHER, expected.model_copy(update={"play": "keep_your_head"})),
        ):
            with pytest.raises(WorkflowError):
                prepare_child(game, c, owner, before, attempt, 900)
        missing = before.model_copy(deep=True)
        missing.facts = [
            x
            for x in missing.facts
            if not (x.get("kind") == "beneath_choice" and x.get("action") == child)
        ]
        with pytest.raises(WorkflowError, match="canonical last-Frame damage"):
            prepare_child(game, c, OTHER, missing, expected, 900)
    assert state(game) == before and game.dice.calls == 2
    for source in (parent, child):
        assert game.inspect(OTHER, source)["state"] != "complete"

    reopened = GameService(ledger, dice=game.dice)

    async def begin_native_defeat():
        opened = current(3, 99705)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, reopened, pending["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not {"heat", "identity", "gain"} & {x.key for x in form.fields}
        assert not await form.interaction_check(current(2, 99706))
        form.values["account"] = expected.context
        submitted = current(3, 99707)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        after = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == after

    asyncio.run(begin_native_defeat())
    with ledger.engine.connect() as c:
        defeat = c.scalar(
            sa.select(actions.c.id).where(
                actions.c.campaign_id == ledger.campaign_id, actions.c.parent_id == child
            )
        )
        assert game.action(c, defeat)["data"]["prepared"] == expected.model_dump(mode="json")
    girl_assets = sum(x.family == "girl" and not x.damaged for x in before.sheets["3"].assets)
    assert girl_assets == 2
    game.dice.faces = (3, 3)
    tick(worker, gateway, 4)
    pass_tags(game)
    defeat_receipt = game.inspect(OTHER, defeat)["receipt"]
    assert defeat_receipt["base_modifier"] == girl_assets and defeat_receipt["pre_total"] == 8
    assert defeat_receipt["heat"] == 0 and game.dice.calls == 3
    result_choice = next(x for x in game.choices(OTHER) if x["kind"] == "defeat_select")
    answer_value = ChoiceAnswer(
        options=("escape_cockpit_choose_location",),
        text="PRIVATE_PILOTED_DEFEAT: I pry out and shelter beside the actual wreck",
    )
    with pytest.raises(WorkflowError):
        reopened.respond(
            PLAYER, str(uuid4()), result_choice["id"], result_choice["revision"], answer_value
        )
    key = str(uuid4())
    result = reopened.respond(
        OTHER, key, result_choice["id"], result_choice["revision"], answer_value
    )
    finished = state(game)
    assert (
        reopened.respond(OTHER, key, result_choice["id"], result_choice["revision"], answer_value)
        == result
    )
    assert state(game) == finished
    placement = next(x for x in finished.placements if x.actor == actor)
    prior_placement = next(x for x in before.placements if x.actor == actor)
    assert placement.mode == "outside_frame"
    assert placement.frame_cell == prior_placement.frame_cell
    assert placement.girl_cell == prior_placement.girl_cell
    assert placement.vessel_id == prior_placement.vessel_id
    assert alpha.conditions(finished, attacker, actor)
    for action_id, owner, saved in (
        (parent, PLAYER, parent_receipt),
        (child, OTHER, receipt),
        (defeat, OTHER, defeat_receipt),
    ):
        assert game.inspect(owner, action_id)["state"] == "complete"
        assert reopened.roll(owner, str(uuid4()), action_id)["receipt"] == saved
    assert game.dice.calls == 3 and finished.sheets["3"].heat == committed
    tick(worker, gateway, 8)
    with ledger.engine.connect() as c:
        assert prove(game, c, state(game), value.id).receipt == receipt["id"]
        assert game.action(c, child)["data"]["result"]["response_play"] == defeat
        assert game.lock(c, 900)["state"] == "released"
        choices = t.m2["m2_choices"]
        assert c.scalar(sa.select(choices.c.state).where(choices.c.id == pending["id"])) == (
            "completed_by_child"
        )
    assert "PRIVATE_PILOTED_DEFEAT" not in json.dumps(gateway.messages)
