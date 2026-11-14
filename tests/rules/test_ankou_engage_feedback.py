"""Actual Engage final marks wait for their real Feedback before original combat dice."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
from test_ankou_feedback import begin_mark, choose, finish_keep, ready
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m3_ankou_feedback import open_choice
from girlframe.engine import m3_ankou_feedback as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.engine.m3_actors import resolve
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_ankou_feedback import prove, prove_loss_source
from girlframe.services.m3_engage import pre_roll, source_binding
from girlframe.services.onboarding import WorkflowError


def actual_engage_source(ledger, tmp_path, monkeypatch):
    _, game, worker, gateway, _, _ = ready(ledger, tmp_path, monkeypatch)
    identities = [x.id for x in state(game).sheets["2"].identities if not x.marked]
    for identity in identities[:-1]:
        game.dice = Dice((4, 4))
        previous = begin_mark(game, identity)
        tick(worker, gateway, 3)
        finish_keep(game, worker, gateway, previous)
    target = current_ref(state(game), OTHER.user_id)
    game.dice = Dice((4, 4))
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="engage",
            target_actor=target,
            identity=identities[-1],
            gain=1,
            heat=1,
            context="PRIVATE_ENGAGE_FEEDBACK: hold the actual opposing Girl back",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    source = next(x for x in rules.sources(state(game)) if x.action == action)
    assert game.dice.calls == 0 and game.inspect(PLAYER, action)["receipt"] is None
    assert state(game).sheets["2"].heat == 0
    assert next(x for x in state(game).sheets["2"].identities if x.id == identities[-1]).marked
    with ledger.engine.connect() as c:
        saved = game.action(c, action)
        assert source.engage_source == source_binding(saved["data"]["engage"])
        assert prove(game, c, state(game), source.id) == source
    return game, worker, gateway, action, source, target


def finish_engage(game, worker, gateway, action, calls):
    before = state(game).sheets["2"].model_copy(deep=True)
    tick(worker, gateway, 3)
    assert game.dice.calls == calls
    pass_tags(game)
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["heat"] == 1 and receipt["pre_total"] == 9
    asset = next(x for x in state(game).sheets["2"].assets if not x.damaged)
    answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=("cover", "advance"),
        fields={"cover": asset.id, "advance": asset.id},
        text="I hold my original opponent back using the actual remaining Asset",
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert state(game).sheets["2"].identities == before.identities
    assert state(game).sheets["2"].heat == before.heat
    assert game.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt
    assert game.dice.calls == calls
    effects = [
        json.loads(x["body"])
        for x in state(game).facts
        if x.get("kind") == "engage_maneuver" and json.loads(x["body"])["source_action"] == action
    ]
    assert {x["kind"] for x in effects} == {"cover", "advance"}
    tick(worker, gateway, 5)
    with game.store.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
        source = next(x for x in rules.sources(state(game)) if x.action == action)
        assert prove(game, c, state(game), source.id).receipt == receipt["id"]
    assert "PRIVATE_ENGAGE_FEEDBACK" not in json.dumps(gateway.messages)


@pytest.mark.parametrize("given", [True, False])
def test_actual_engage_feedback_owned_purpose_then_one_roll_or_unrolled_helpless(
    ledger, tmp_path, monkeypatch, given
):
    game, worker, gateway, action, source, target = actual_engage_source(
        ledger, tmp_path, monkeypatch
    )
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "ankou_feedback_choice")

    async def native_choice():
        interaction = current(PLAYER.user_id, 99501)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_choice(interaction, game, row["id"])
        form = interaction.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            effect=("purpose",),
            target=(target.token,),
            account="PRIVATE_ENGAGE_PURPOSE: give me a reason to keep fighting",
        )
        await form.confirm.callback(current(PLAYER.user_id, 99502))
        assert form.completed

    asyncio.run(native_choice())
    response = next(x for x in game.choices(OTHER) if x["kind"] == "ankou_feedback_purpose")
    private = game.decision(OTHER, response["id"])["ankou_feedback"]
    assert private["identities"] == private["assets"] == [] and private["heat"] is None
    answer(
        game,
        OTHER,
        "ankou_feedback_purpose",
        flag=given,
        text="PRIVATE_ENGAGE_PURPOSE: protect the wounded" if given else "I refuse this request",
    )
    assert game.dice.calls == 0
    if not given:
        assert is_helpless(state(game), source.actor, target)
        assert rules.get(state(game), source.id).phase == "ended"
        stopped = game.inspect(PLAYER, action)
        assert stopped["state"] == "complete" and stopped["receipt"] is None
        assert stopped["result"]["blocked_before_roll"]
        tick(worker, gateway, 5)
        with ledger.engine.connect() as c:
            assert game.lock(c, 900)["state"] == "released"
        assert game.dice.calls == 0
        return
    replace = next(
        x.id for x in state(game).sheets["2"].identities if not x.protected and not x.paired
    )
    answer(game, PLAYER, "ankou_feedback_identity", fields={"replace": replace})
    value = rules.get(state(game), source.id)
    assert not next(
        x for x in state(game).sheets["2"].identities if x.id == value.new_identity
    ).marked
    # The relaxation accepts only this source's genuine event, not an edited
    # declaration or an unrelated resource change after Feedback completed.
    with ledger.engine.connect() as c:
        saved = game.action(c, action)
        canon = state(game)
        changed = copy.deepcopy(saved)
        changed["data"]["engage"]["target_sha256"] = "0" * 64
        with pytest.raises(WorkflowError, match="Feedback-held Engage"):
            pre_roll(game, c, canon, changed)
        stale = canon.model_copy(deep=True)
        stale.sheets[target.entity].heat += 1
        with pytest.raises(WorkflowError, match="STALE_ENGAGE"):
            pre_roll(game, c, stale, saved)
        pre_roll(game, c, canon, saved)
    assert game.dice.calls == 0
    finish_engage(game, worker, gateway, action, 1)


def test_actual_engage_feedback_tear_child_changes_target_then_resumes_original_declaration(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, action, source, target = actual_engage_source(
        ledger, tmp_path, monkeypatch
    )
    asset = next(x for x in state(game).sheets["2"].assets if x.family == "frame" and not x.void)
    choose(game, "tear", target, asset=asset.id)
    value = rules.get(state(game), source.id)
    assert value.phase == "child" and not any(
        x.id == asset.id for x in state(game).sheets["2"].assets
    )
    assert state(game).sheets["2"].heat == 5 and game.dice.calls == 0
    with ledger.engine.connect() as c:
        context = prove_loss_source(game, c, state(game), value.choice_event, value.id, value.actor)
        assert context["in_battle"] is True and context["source_action"] == action
    game.dice = Dice((1, 2))
    child = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="flirt",
            parent=action,
            source_work=value.id,
            target=OTHER.user_id,
            heat=5,
            context="PRIVATE_ENGAGE_REPRISAL: demand their actual name",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_flirt", options=("name",))
    answer(game, OTHER, "target_flirt", text="PRIVATE_ENGAGE_REPRISAL_ANSWER")
    assert game.inspect(PLAYER, child)["state"] == "complete" and game.dice.calls == 1
    value = rules.get(state(game), source.id)
    assert value.phase == "resolved" and value.child == child
    with ledger.engine.connect() as c:
        saved = game.action(c, action)
        current_target = resolve(state(game), target, profiles(c, ledger.campaign_id))
        assert current_target.source_sha256 != saved["data"]["engage"]["target_sha256"]
        assert source_binding(saved["data"]["engage"]) == source.engage_source
        pre_roll(game, c, state(game), saved)
    game.dice.faces = (4, 4)
    finish_engage(game, worker, gateway, action, 2)
    assert "PRIVATE_ENGAGE_REPRISAL" not in json.dumps(gateway.messages)


def test_unrelated_opponent_change_during_feedback_cannot_rebase_engage(
    ledger, tmp_path, monkeypatch
):
    game, _, _, action, source, target = actual_engage_source(ledger, tmp_path, monkeypatch)
    choose(game, "purpose", target)
    answer(game, OTHER, "ankou_feedback_purpose", flag=True, text="Protect the wounded")
    with ledger.transaction() as c:
        changed = state(game)
        changed.sheets[target.entity].heat += 1
        changed.sheets[target.entity].revision += 1
        game.event(
            c,
            OTHER.user_id,
            str(uuid4()),
            "synthetic.unrelated_opponent_resource_change",
            changed,
        )
    replace = next(
        x.id for x in state(game).sheets["2"].identities if not x.protected and not x.paired
    )
    answer(game, PLAYER, "ankou_feedback_identity", fields={"replace": replace})
    assert rules.get(state(game), source.id).phase == "resolved"
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="outside the actual Feedback source"):
        game.roll(PLAYER, str(uuid4()), action)
    assert state(game).model_dump_json() == before and game.dice.calls == 0
    assert game.inspect(PLAYER, action)["receipt"] is None
