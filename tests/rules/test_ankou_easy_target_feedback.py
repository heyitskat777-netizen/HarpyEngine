"""Actual native Newgirl mistake, last mark, owned Feedback and real requested work."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ankou_feedback import choose, finish_keep
from test_easy_target import child as requested_child
from test_easy_target import choose as choose_urge
from test_easy_target import finish_keep as finish_request
from test_easy_target import validate
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_ui import open_play
from girlframe.engine import m3_ankou_feedback as feedback
from girlframe.engine import m3_easy_target as easy_target
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.services.m2_game import GameService
from girlframe.services.m3_ankou_easy_target import source_binding
from girlframe.services.m3_ankou_feedback import FeedbackService, prove
from girlframe.services.m3_ankou_feedback import prepare_child as feedback_child
from girlframe.services.m3_easy_target import prove as prove_reaction
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    import test_easy_target

    original = test_easy_target.service
    monkeypatch.setattr(
        test_easy_target,
        "service",
        lambda *args, **kwargs: original(*args, **(kwargs | {"frame": "PROJECT ANKOU"})),
    )
    game, worker, gateway, _ = test_easy_target.ready(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(feedback.RULE, easy_target.RULE))
    return game, worker, gateway


def last_mistake(game, worker, gateway):
    identities = [x.id for x in state(game).sheets["2"].identities if not x.marked]
    for identity in identities[:-1]:
        game.dice = Dice((4, 4))
        sheet = state(game).sheets["2"]
        heat = sheet.heat + 1 if sheet.heat + 1 >= 5 else 1
        prior = game.begin(
            PLAYER,
            str(uuid4()),
            900,
            sheet.revision,
            PlayInput(
                play="keep_your_head",
                context="Actual prior danger and reliance on this Identity",
                trigger_confirmed=True,
                identity=identity,
                gain=1,
                heat=heat,
            ),
        )["action_id"]
        tick(worker, gateway, 3)
        finish_keep(game, worker, gateway, prior)

    async def native_mistake():
        first = current(PLAYER.user_id, 99381)
        first.channel_id = 900
        await first.response.defer(ephemeral=True)
        await open_play(first, game, _pilot=True)
        form = first.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            play=(easy_target.PLAY,),
            identity=(identities[-1],),
            gain=("3",),
            pair_share=("0",),
            heat=("2",),
            disposable_heat=("0",),
            piloting=("no",),
            witnessed=("no",),
            trigger=("yes",),
            context="PRIVATE_MISTAKE_SOURCE: I make a foolish mistake using my last Identity",
        )
        response = current(PLAYER.user_id, 99382)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list
        with game.store.engine.connect() as c:
            return json.loads(
                c.scalar(
                    sa.select(t.commands.c.outcome_json).where(
                        t.commands.c.campaign_id == game.store.campaign_id,
                        t.commands.c.interaction_key == str(response.id),
                    )
                )
            )["action_id"]

    game.dice = Dice((3, 3))
    before = state(game)
    action = asyncio.run(native_mistake())
    tick(worker, gateway, 3)
    if not any(x.action == action for x in feedback.sources(state(game))):
        game.roll(PLAYER, "m2.confirmed_roll:" + action, action)
    value = next(x for x in feedback.sources(state(game)) if x.action == action)
    assert value.phase == "choice" and value.easy_target_source is not None
    assert value.heat_before == before.sheets["2"].heat
    assert value.heat_committed == state(game).sheets["2"].heat == value.heat_before + 1
    assert next(x for x in state(game).sheets["2"].identities if x.id == identities[-1]).marked
    assert game.dice.calls == 0 and game.inspect(PLAYER, action)["receipt"] is None
    assert not any(x.get("kind") == "easy_target_session" for x in state(game).facts)
    assert state(game).order == before.order
    with game.store.engine.connect() as c:
        saved = game.action(c, action)
        assert prove(game, c, state(game), value.id) == value
        assert source_binding(game, c, state(game), saved) == value.easy_target_source
        directed = copy.deepcopy(saved)
        directed["data"]["easy_target"]["princess_direction"] = "not-the-native-source"
        with pytest.raises(WorkflowError, match="SOURCE_ANKOU_EASY_TARGET_PORT_REQUIRED"):
            source_binding(game, c, state(game), directed)
        nominated = copy.deepcopy(saved)
        nominated["data"]["prepared"]["source_work"] = "not-this-standalone-source"
        with pytest.raises(WorkflowError, match="SOURCE_ANKOU_EASY_TARGET_PORT_REQUIRED"):
            source_binding(game, c, state(game), nominated)
    return action, value


@pytest.mark.parametrize("given", [True, False])
def test_native_easy_target_feedback_preserves_cost_and_real_requested_work(
    ledger, tmp_path, monkeypatch, given
):
    game, worker, gateway = ready(ledger, tmp_path, monkeypatch)
    action, value = last_mistake(game, worker, gateway)
    counterpart = current_ref(state(game), OTHER.user_id)
    before_order = state(game).order
    committed = state(game).sheets["2"].model_copy(deep=True)
    controls = FeedbackService(game)
    game.abort(ADMIN, str(uuid4()), action)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == action)
    assert not saved["rolled"] and not saved["cancellable"]
    recovery.recover(PLAYER, "recover-original-mistake-feedback", action, saved["revision"])
    tick(worker, gateway, 3)
    assert game.dice.calls == 0 and state(game).sheets["2"] == committed
    choose(game, "purpose", counterpart)
    private = controls.view(OTHER, value.id)
    assert not {"prepared", "identity", "heat_before", "heat_committed"} & set(private)
    answer(
        game,
        OTHER,
        "ankou_feedback_purpose",
        flag=given,
        text="PRIVATE_MISTAKE_PURPOSE: keep me safe" if given else "I give no purpose",
    )
    assert game.dice.calls == 0
    if given:
        replacement = next(x.id for x in state(game).sheets["2"].identities if not x.protected)
        answer(game, PLAYER, "ankou_feedback_identity", fields={"replace": replacement})
        ready_sheet = state(game).sheets["2"].model_copy(deep=True)
        tick(worker, gateway, 3)
        pass_tags(game)
        receipt = game.inspect(PLAYER, action)["receipt"]
        assert receipt["heat"] == 2 and game.dice.calls == 1
        assert state(game).sheets["2"].heat == ready_sheet.heat
        assert state(game).sheets["2"].identities == ready_sheet.identities
        answer(
            game,
            PLAYER,
            "easy_target_select",
            options=(counterpart.token,),
            text="I choose this actual original person",
        )
        tag = next(x for x in game.choices(OTHER) if x["kind"] == "easy_target_tag")
        with pytest.raises(WorkflowError):
            game.respond(
                PLAYER,
                str(uuid4()),
                tag["id"],
                tag["revision"],
                ChoiceAnswer(text="Cannot author another person's Tag"),
            )
        answer(game, OTHER, "easy_target_tag", text="PRIVATE_MISTAKE_TAG: vulnerable")
        choose_urge(game, OTHER, counterpart, "request")
        validate(game, counterpart)
        work = easy_target.identity(action, counterpart)
        reaction = easy_target.get(state(game), easy_target.Reaction, work)
        requested = PlayInput(
            play=reaction.play,
            parent=action,
            source_work=work,
            context=reaction.context,
            heat=0,
            trigger_confirmed=True,
        )
        with ledger.engine.connect() as c:
            resolved = prove(game, c, state(game), value.id)
            assert resolved.phase == "resolved" and resolved.rolled_event and resolved.receipt
            assert feedback_child(game, c, PLAYER, state(game), requested, 900) is None
            with pytest.raises(WorkflowError, match="actual source-owned reprisal"):
                feedback_child(
                    game,
                    c,
                    PLAYER,
                    state(game),
                    requested.model_copy(update={"source_work": value.id}),
                    900,
                )
            with pytest.raises(WorkflowError, match="original actual performer"):
                feedback_child(game, c, OTHER, state(game), requested, 900)
        requested_child(game, worker, gateway, work)
        finish_request(game)
        answer(
            game,
            OTHER,
            "easy_target_judge:" + counterpart.token,
            flag=True,
            text="She actually performed my requested work well",
        )
        assert state(game).order[0] == PLAYER.user_id and game.dice.calls == 2
        with ledger.engine.connect() as c:
            reaction = prove_reaction(game, c, state(game), work)
            assert reaction.performance_event and reaction.consequence == "well"
            assert reaction.completed_event
    else:
        receipt = None
        assert is_helpless(state(game), value.actor, counterpart)
        assert game.inspect(PLAYER, action)["result"]["blocked_before_roll"]
        assert not any(x.get("kind") == "easy_target_session" for x in state(game).facts)
        assert state(game).order == before_order
        assert feedback.get(state(game), value.id).phase == "ended"
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    restarted = GameService(game.store, dice=game.dice)
    assert restarted.inspect(PLAYER, action) == game.inspect(PLAYER, action)
    if given:
        assert restarted.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt
        assert game.dice.calls == 2
    else:
        assert game.dice.calls == 0
    with ledger.engine.connect() as c:
        assert prove(restarted, c, state(restarted), value.id).receipt == (
            receipt["id"] if given else None
        )
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert "PRIVATE_MISTAKE" not in json.dumps(gateway.messages)


def test_native_mistake_feedback_active_tear_keeps_exact_reprisal_authority(
    ledger, tmp_path, monkeypatch
):
    """Authored deferred gate: an active tear cannot masquerade as a result child."""
    game, worker, gateway = ready(ledger, tmp_path, monkeypatch)
    action, value = last_mistake(game, worker, gateway)
    target = current_ref(state(game), OTHER.user_id)
    asset = next(x for x in state(game).sheets["2"].assets if x.family == "girl")
    choose(game, "tear", target, asset=asset.id)
    prepared = PlayInput(
        play="flirt",
        parent=action,
        source_work=value.id,
        target=OTHER.user_id,
        context="Actual Feedback demand for the other original person's name",
        heat=state(game).sheets["2"].heat,
        trigger_confirmed=True,
    )
    with ledger.engine.connect() as c:
        active = prove(game, c, state(game), value.id)
        assert active.phase == "child" and active.rolled_event is None and active.child is None
        assert feedback_child(game, c, PLAYER, state(game), prepared, 900)["source"] == value.id
        with pytest.raises(WorkflowError, match="actual source-owned reprisal"):
            feedback_child(
                game,
                c,
                PLAYER,
                state(game),
                prepared.model_copy(update={"source_work": "not-a-real-mistake-reaction"}),
                900,
            )
        with pytest.raises(WorkflowError, match="actual source-owned reprisal"):
            feedback_child(game, c, OTHER, state(game), prepared, 900)
    assert game.dice.calls == 0
    assert game.inspect(PLAYER, action)["receipt"] is None
