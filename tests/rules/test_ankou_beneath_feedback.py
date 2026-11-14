"""Ordinary social last marks keep their source, owned reprisal and original roll."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ankou_feedback import begin_mark, choose, finish_keep, ready
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_ui import open_play
from girlframe.engine import m3_ankou_feedback as feedback
from girlframe.engine.m2 import PlayInput, shift_status
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.services.m3_ankou_feedback import prove
from girlframe.services.m3_beneath import feedback_source_binding, pre_roll
from girlframe.services.onboarding import WorkflowError


def actual_social_source(ledger, tmp_path, monkeypatch):
    _, game, worker, gateway, _, _ = ready(ledger, tmp_path, monkeypatch)
    ledger.policy = ledger.policy.model_copy(
        update={
            "owner_m3_rulings": ledger.policy.owner_m3_rulings.model_copy(
                update={"beneath_private_choices": "affected_owner"}
            )
        }
    )
    identities = [x.id for x in state(game).sheets["2"].identities if not x.marked]
    for identity in identities[:-1]:
        game.dice = Dice((4, 4))
        prior = begin_mark(game, identity)
        tick(worker, gateway, 3)
        finish_keep(game, worker, gateway, prior)
    game.dice = Dice((4, 4))

    async def start_native():
        first = current(PLAYER.user_id, 99901)
        first.channel_id = 900
        await first.response.defer(ephemeral=True)
        await open_play(first, game, _pilot=True)
        form = first.edit_original_response.call_args.kwargs["view"]
        choices = next(x for x in form.fields if x.key == "play").options
        assert any(x[0] == "put_someone_beneath_you" for x in choices)
        form.values.update(
            play=("put_someone_beneath_you",),
            target=(str(OTHER.user_id),),
            identity=(identities[-1],),
            gain=("1",),
            pair_share=("0",),
            heat=("1",),
            disposable_heat=("0",),
            piloting=("no",),
            witnessed=("no",),
            context="PRIVATE_BENEATH_FEEDBACK: confront the actual other Girl",
            trigger=("yes",),
        )
        response = current(PLAYER.user_id, 99902)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list
        with ledger.engine.connect() as c:
            return json.loads(
                c.scalar(
                    sa.select(t.commands.c.outcome_json).where(
                        t.commands.c.campaign_id == ledger.campaign_id,
                        t.commands.c.interaction_key == str(response.id),
                    )
                )
            )["action_id"]

    action = asyncio.run(start_native())
    tick(worker, gateway, 3)
    source = next(x for x in feedback.sources(state(game)) if x.action == action)
    assert source.phase == "choice" and source.beneath_source is not None
    assert game.dice.calls == 0 and game.inspect(PLAYER, action)["receipt"] is None
    assert state(game).sheets["2"].heat == source.heat_committed == 0
    assert next(x for x in state(game).sheets["2"].identities if x.id == identities[-1]).marked
    with ledger.engine.connect() as c:
        saved = game.action(c, action)
        assert source.beneath_source == feedback_source_binding(saved)
        assert prove(game, c, state(game), source.id) == source
        specialised = copy.deepcopy(saved)
        specialised["data"]["beneath"]["special_girl"] = {"purchase": "not-an-ordinary-source"}
        with pytest.raises(WorkflowError, match="SOURCE_ANKOU_BENEATH_PORT_REQUIRED"):
            feedback_source_binding(specialised)
    return game, worker, gateway, action, source


def finished_source(game, worker, gateway, action, source, calls):
    assert game.inspect(PLAYER, action)["state"] == "complete"
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["heat"] == 1 and game.dice.calls == calls
    assert game.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt
    assert game.dice.calls == calls
    tick(worker, gateway, 5)
    with game.store.engine.connect() as c:
        assert prove(game, c, state(game), source.id).receipt == receipt["id"]
        assert feedback_source_binding(game.action(c, action)) == source.beneath_source
        assert game.lock(c, 900)["state"] == "released"
    assert "PRIVATE_BENEATH" not in json.dumps(gateway.messages)


@pytest.mark.parametrize("given", [True, False])
def test_native_beneath_feedback_purpose_preserves_owned_social_effects_or_refusal(
    ledger, tmp_path, monkeypatch, given
):
    game, worker, gateway, action, source = actual_social_source(ledger, tmp_path, monkeypatch)
    target = current_ref(state(game), OTHER.user_id)
    choose(game, "purpose", target)
    answer(
        game,
        OTHER,
        "ankou_feedback_purpose",
        flag=given,
        text="PRIVATE_BENEATH_PURPOSE: defend those behind you" if given else "I refuse",
    )
    assert game.dice.calls == 0
    if not given:
        assert is_helpless(state(game), source.actor, target)
        assert feedback.get(state(game), source.id).phase == "ended"
        assert game.inspect(PLAYER, action)["state"] == "complete"
        assert game.inspect(PLAYER, action)["receipt"] is None
        assert not any(
            x.get("kind") == "beneath_choice" and x.get("action") == action
            for x in state(game).facts
        )
        tick(worker, gateway, 5)
        with ledger.engine.connect() as c:
            assert game.lock(c, 900)["state"] == "released"
        assert game.dice.calls == 0
        return
    replace = next(x.id for x in state(game).sheets["2"].identities if not x.protected)
    answer(game, PLAYER, "ankou_feedback_identity", fields={"replace": replace})
    assert game.inspect(PLAYER, action)["state"] == "ready_to_roll"
    with ledger.engine.connect() as c:
        saved = game.action(c, action)
        changed = copy.deepcopy(saved)
        changed["data"]["beneath"]["target_sha256"] = "not-the-original-target"
        with pytest.raises(WorkflowError, match="original Feedback-held Beneath"):
            pre_roll(game, c, PLAYER, state(game), changed)
        stale = state(game).model_copy(deep=True)
        stale.sheets["3"].heat += 1
        with pytest.raises(WorkflowError, match="STALE_TARGET"):
            pre_roll(game, c, PLAYER, stale, saved)
        pre_roll(game, c, PLAYER, state(game), saved)
    committed = state(game).sheets["2"].model_copy(deep=True)
    tick(worker, gateway, 3)
    pass_tags(game)
    assert game.inspect(PLAYER, action)["receipt"]["pre_total"] == 9
    before = state(game)
    expected = before.model_copy(deep=True)
    shift_status(expected, OTHER.user_id, -1)
    answer(
        game,
        PLAYER,
        "beneath_select",
        options=("tag", "status"),
        fields={"tag": "PRIVATE_BENEATH_TAG: cornered"},
        text="Carry through the actual confrontation after receiving a purpose",
    )
    after = state(game)
    assert after.order == expected.order
    assert len(after.sheets["3"].tags) == len(before.sheets["3"].tags) + 1
    assert after.sheets["3"].tags[-1].giver == PLAYER.user_id
    assert after.sheets["2"].identities == committed.identities
    assert after.sheets["2"].heat == committed.heat
    finished_source(game, worker, gateway, action, source, 1)


def test_beneath_feedback_tear_accepts_real_reprisal_changes_then_owned_counter_damage(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, action, source = actual_social_source(ledger, tmp_path, monkeypatch)
    target = current_ref(state(game), OTHER.user_id)
    lost = next(x for x in state(game).sheets["2"].assets if x.family == "frame" and not x.void)
    choose(game, "tear", target, asset=lost.id)
    assert state(game).sheets["2"].heat == 5
    assert not any(x.id == lost.id for x in state(game).sheets["2"].assets)
    prior_target = state(game).sheets["3"].model_copy(deep=True)
    game.dice = Dice((1, 2))
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="flirt",
            target=OTHER.user_id,
            parent=action,
            source_work=source.id,
            heat=5,
            context="PRIVATE_BENEATH_REPRISAL: demand their actual name",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_flirt", options=("name",))
    answer(game, OTHER, "target_flirt", text="PRIVATE_BENEATH_ANSWER: my actual name")
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert state(game).sheets["3"].revision > prior_target.revision
    assert game.dice.calls == 1 and game.inspect(PLAYER, action)["receipt"] is None
    resolved = feedback.get(state(game), source.id)
    assert resolved.phase == "resolved" and resolved.child == child
    with ledger.engine.connect() as c:
        pre_roll(game, c, PLAYER, state(game), game.action(c, action))
    game.dice.faces = (1, 1)
    tick(worker, gateway, 3)
    pass_tags(game)
    assert game.inspect(PLAYER, action)["receipt"]["pre_total"] == 3
    # The target chooses the low counter. The affected original Pilot alone
    # selects the actual private Asset; Feedback never supplies that decision.
    answer(game, OTHER, "beneath_select", options=("damage",), text="Actual counterattack")
    assert not game.choices(OTHER)
    assert any(x["kind"] == "beneath_details" for x in game.choices(PLAYER))
    asset = next(x for x in state(game).sheets["2"].assets if x.family == "girl" and not x.damaged)
    answer(game, PLAYER, "beneath_details", denied=(asset.id,))
    assert next(x for x in state(game).sheets["2"].assets if x.id == asset.id).damaged
    assert state(game).sheets["2"].heat == 0
    finished_source(game, worker, gateway, action, source, 2)
