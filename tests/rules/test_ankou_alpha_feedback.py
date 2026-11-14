"""Native Brutalize last mark retains real Feedback costs and owned damage outcomes."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ankou_feedback import begin_mark, choose, finish_keep
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_ui import open_play
from girlframe.discord_adapter.m3_alpha import open_alpha_choice
from girlframe.engine import m3_alpha as alpha
from girlframe.engine import m3_ankou_feedback as feedback
from girlframe.engine.m2 import ChoiceAnswer, higher
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.services.m2_game import GameService
from girlframe.services.m3_ankou_alpha import source_binding
from girlframe.services.m3_ankou_feedback import FeedbackService, prove
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    import test_alpha_brutalize

    original = test_alpha_brutalize.service
    monkeypatch.setattr(
        test_alpha_brutalize,
        "service",
        lambda *args, **kwargs: original(*args, **(kwargs | {"frame": "PROJECT ANKOU"})),
    )
    game, worker, gateway = test_alpha_brutalize.ready(store, tmp_path, monkeypatch, (3, 3))
    approved(store, game, tmp_path, monkeypatch, extra=(feedback.RULE, alpha.RULE))
    return game, worker, gateway


def last_brutalize(game, worker, gateway):
    identities = [x.id for x in state(game).sheets["2"].identities if not x.marked]
    for identity in identities[:-1]:
        game.dice = Dice((4, 4))
        prior = begin_mark(game, identity)
        tick(worker, gateway, 3)
        finish_keep(game, worker, gateway, prior)

    async def native_brutalize():
        first = current(PLAYER.user_id, 99681)
        first.channel_id = 900
        await first.response.defer(ephemeral=True)
        await open_play(first, game, _pilot=True)
        form = first.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            play=("brutalize",),
            alpha_target=(current_ref(state(game), OTHER.user_id).token,),
            identity=(identities[-1],),
            gain=("3",),
            pair_share=("0",),
            heat=("2",),
            disposable_heat=("0",),
            piloting=("no",),
            witnessed=("no",),
            trigger=("yes",),
            context="PRIVATE_ALPHA_SOURCE: I tear into her using my last unmarked Identity",
        )
        response = current(PLAYER.user_id, 99682)
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
    action = asyncio.run(native_brutalize())
    tick(worker, gateway, 3)
    if not any(x.action == action for x in feedback.sources(state(game))):
        game.roll(PLAYER, "m2.confirmed_roll:" + action, action)
    value = next(x for x in feedback.sources(state(game)) if x.action == action)
    assert value.phase == "choice" and value.alpha_source is not None
    assert value.heat_before == before.sheets["2"].heat
    assert value.heat_committed == state(game).sheets["2"].heat == value.heat_before + 1
    assert next(x for x in state(game).sheets["2"].identities if x.id == identities[-1]).marked
    assert game.dice.calls == 0 and game.inspect(PLAYER, action)["receipt"] is None
    assert state(game).sheets["3"].assets == before.sheets["3"].assets
    assert state(game).order == before.order
    with game.store.engine.connect() as c:
        saved = game.action(c, action)
        assert prove(game, c, state(game), value.id) == value
        assert source_binding(game, c, state(game), saved) == value.alpha_source
        directed = copy.deepcopy(saved)
        directed["data"]["alpha"]["princess_direction"] = "not-the-native-source"
        with pytest.raises(WorkflowError, match="SOURCE_ANKOU_ALPHA_PORT_REQUIRED"):
            source_binding(game, c, state(game), directed)
        wrong_person = copy.deepcopy(saved)
        wrong_person["data"]["alpha"]["target"] = value.actor.model_dump(mode="json")
        with pytest.raises(WorkflowError, match="actual native Alpha"):
            source_binding(game, c, state(game), wrong_person)
        wrong_controller = copy.deepcopy(saved)
        wrong_controller["data"]["alpha"]["target_controller"] = ADMIN.user_id
        with pytest.raises(WorkflowError, match="bodies and controllers"):
            source_binding(game, c, state(game), wrong_controller)
    return action, value


@pytest.mark.parametrize("given", [True, False])
def test_native_brutalize_feedback_preserves_cost_and_actual_damage(
    ledger, tmp_path, monkeypatch, given
):
    game, worker, gateway = ready(ledger, tmp_path, monkeypatch)
    action, value = last_brutalize(game, worker, gateway)
    counterpart = current_ref(state(game), OTHER.user_id)
    before_order = state(game).order
    original_assets = copy.deepcopy(state(game).sheets["3"].assets)
    committed = state(game).sheets["2"].model_copy(deep=True)
    game.abort(ADMIN, str(uuid4()), action)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == action)
    assert not saved["rolled"] and not saved["cancellable"]
    recovery.recover(PLAYER, "recover-original-alpha-feedback", action, saved["revision"])
    tick(worker, gateway, 3)
    assert game.dice.calls == 0 and state(game).sheets["2"] == committed
    choose(game, "purpose", counterpart)
    private = FeedbackService(game).view(OTHER, value.id)
    assert not {"prepared", "identity", "heat_before", "heat_committed"} & set(private)
    answer(
        game,
        OTHER,
        "ankou_feedback_purpose",
        flag=given,
        text="PRIVATE_ALPHA_PURPOSE: stand up to me" if given else "I give no purpose",
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
        asset = next(x for x in original_assets if x.family == "girl" and not x.damaged)
        row = next(x for x in game.choices(PLAYER) if x["kind"] == "alpha_damage")
        with pytest.raises(WorkflowError):
            game.respond(
                OTHER,
                str(uuid4()),
                row["id"],
                row["revision"],
                ChoiceAnswer(options=(asset.id,)),
            )

        async def native_damage():
            first = current(PLAYER.user_id, 99683)
            await first.response.defer(ephemeral=True)
            await open_alpha_choice(first, game, row["id"])
            form = first.edit_original_response.call_args.kwargs["view"]
            form.values["asset"] = (asset.id,)
            response = current(PLAYER.user_id, 99684)
            await form.confirm.callback(response)
            assert form.completed, response.edit_original_response.call_args_list

        asyncio.run(native_damage())
        actual = state(game)
        assert next(x for x in actual.sheets["3"].assets if x.id == asset.id).damaged
        assert alpha.conditions(actual, counterpart, value.actor)
        assert higher(actual, PLAYER.user_id, OTHER.user_id)
        assert not is_helpless(actual, counterpart, value.actor)
        assert game.inspect(PLAYER, action)["result"]["tier"] == "mid"
    else:
        receipt = None
        assert is_helpless(state(game), value.actor, counterpart)
        assert game.inspect(PLAYER, action)["result"]["blocked_before_roll"]
        assert state(game).sheets["3"].assets == original_assets
        assert not alpha.conditions(state(game), counterpart, value.actor)
        assert state(game).order == before_order
        assert feedback.get(state(game), value.id).phase == "ended"
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.inspect(PLAYER, action)["receipt"] == receipt
    restarted = GameService(game.store, dice=game.dice)
    assert restarted.inspect(PLAYER, action) == game.inspect(PLAYER, action)
    if given:
        assert restarted.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt
        assert game.dice.calls == 1
    else:
        assert game.dice.calls == 0
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
        assert prove(restarted, c, state(restarted), value.id).receipt == (
            receipt["id"] if given else None
        )
    restarted.close_scene(ADMIN, "close-finished-alpha-feedback-scene", 900)
    rebound = restarted.bind_scene(ADMIN, "rebind-finished-alpha-feedback-channel", 900)["scene"]
    assert rebound != value.cast.id
    with ledger.engine.connect() as c:
        assert prove(restarted, c, state(restarted), value.id).receipt == (
            receipt["id"] if given else None
        )
    assert "PRIVATE_ALPHA" not in json.dumps(gateway.messages)
