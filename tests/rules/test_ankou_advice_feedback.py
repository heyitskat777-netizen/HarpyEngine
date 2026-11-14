"""Native Oldgen advice, actual last mark, owned Feedback and unchanged advice outcomes."""

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
from test_oldgen import native_choice

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_ui import open_play
from girlframe.engine import m3_ankou_feedback as feedback
from girlframe.engine import m3_oldgen as advice
from girlframe.engine.m2 import ChoiceAnswer
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.services.m2_game import GameService
from girlframe.services.m3_ankou_advice import source_binding
from girlframe.services.m3_ankou_feedback import FeedbackService, prove
from girlframe.services.m3_oldgen import prove_advice
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    import test_oldgen

    original = test_oldgen.service
    monkeypatch.setattr(
        test_oldgen,
        "service",
        lambda *args, **kwargs: original(*args, **(kwargs | {"frame": "PROJECT ANKOU"})),
    )
    game, worker, gateway, _ = test_oldgen.ready(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(feedback.RULE, advice.RULE, advice.ADVICE))
    return game, worker, gateway


def last_advice(game, worker, gateway):
    identities = [x.id for x in state(game).sheets["2"].identities if not x.marked]
    for identity in identities[:-1]:
        game.dice = Dice((4, 4))
        prior = begin_mark(game, identity)
        tick(worker, gateway, 3)
        finish_keep(game, worker, gateway, prior)

    async def native_advice():
        first = current(PLAYER.user_id, 99281)
        first.channel_id = 900
        await first.response.defer(ephemeral=True)
        await open_play(first, game, _pilot=True)
        form = first.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            play=(advice.PLAY,),
            target=(str(OTHER.user_id),),
            identity=(identities[-1],),
            gain=("1",),
            pair_share=("0",),
            heat=("1",),
            disposable_heat=("0",),
            piloting=("no",),
            witnessed=("no",),
            trigger=("yes",),
            context="PRIVATE_ADVICE_SOURCE: I advise her using my last unmarked Identity",
        )
        response = current(PLAYER.user_id, 99282)
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

    game.dice = Dice((3, 4))
    before = state(game)
    action = asyncio.run(native_advice())
    tick(worker, gateway, 3)
    if not any(x.action == action for x in feedback.sources(state(game))):
        game.roll(PLAYER, "m2.confirmed_roll:" + action, action)
    value = next(x for x in feedback.sources(state(game)) if x.action == action)
    assert value.phase == "choice" and value.advice_source is not None
    assert value.heat_before == value.heat_committed == before.sheets["2"].heat
    assert state(game).sheets["2"].heat == before.sheets["2"].heat
    assert next(x for x in state(game).sheets["2"].identities if x.id == identities[-1]).marked
    assert game.dice.calls == 0 and game.inspect(PLAYER, action)["receipt"] is None
    assert not advice.records(state(game), advice.Advice)
    assert state(game).order == before.order
    with game.store.engine.connect() as c:
        saved = game.action(c, action)
        assert prove(game, c, state(game), value.id) == value
        assert source_binding(game, c, state(game), saved) == value.advice_source
        directed = copy.deepcopy(saved)
        directed["data"]["oldgen"]["princess_direction"] = "not-the-native-source"
        with pytest.raises(WorkflowError, match="SOURCE_ANKOU_ADVICE_PORT_REQUIRED"):
            source_binding(game, c, state(game), directed)
        wrong_person = copy.deepcopy(saved)
        wrong_person["data"]["oldgen"]["target"] = value.actor.model_dump(mode="json")
        with pytest.raises(WorkflowError, match="actual native adviser"):
            source_binding(game, c, state(game), wrong_person)
    return action, value


@pytest.mark.parametrize("given", [True, False])
def test_native_advice_feedback_preserves_real_cost_and_owned_result(
    ledger, tmp_path, monkeypatch, given
):
    game, worker, gateway = ready(ledger, tmp_path, monkeypatch)
    action, value = last_advice(game, worker, gateway)
    counterpart = current_ref(state(game), OTHER.user_id)
    before_order = state(game).order
    committed = state(game).sheets["2"].model_copy(deep=True)
    controls = FeedbackService(game)
    # Actual staff interruption releases chat, not the owned mark or mandatory source.
    game.abort(ADMIN, str(uuid4()), action)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == action)
    assert not saved["rolled"] and not saved["cancellable"]
    recovery.recover(PLAYER, "recover-original-advice-feedback", action, saved["revision"])
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
        text="PRIVATE_ADVICE_PURPOSE: keep me safe" if given else "I give no purpose",
    )
    assert game.dice.calls == 0
    if given:
        replacement = next(x.id for x in state(game).sheets["2"].identities if not x.protected)
        answer(game, PLAYER, "ankou_feedback_identity", fields={"replace": replacement})
        ready_sheet = state(game).sheets["2"].model_copy(deep=True)
        tick(worker, gateway, 3)
        pass_tags(game)
        receipt = game.inspect(PLAYER, action)["receipt"]
        assert receipt["heat"] == 1 and game.dice.calls == 1
        assert state(game).sheets["2"].heat == ready_sheet.heat
        assert state(game).sheets["2"].identities == ready_sheet.identities
        assert state(game).order == (2, 3)
        native_choice(
            game, PLAYER, "oldgen_write_maxim", "PRIVATE_ADVICE_MAXIM: follow the safer route"
        )
        row = next(x for x in game.choices(OTHER) if x["kind"] == "oldgen_listen")
        with pytest.raises(WorkflowError):
            game.respond(
                PLAYER,
                str(uuid4()),
                row["id"],
                row["revision"],
                ChoiceAnswer(text="Cannot author another person's listening"),
            )
        native_choice(game, OTHER, "oldgen_listen", "I actually sit and hear her advice")
        maxim = advice.records(state(game), advice.Maxim)[-1]
        assert maxim.owner == value.actor and maxim.subject == counterpart
        with ledger.engine.connect() as c:
            assert prove_advice(game, c, state(game), action).maxim == maxim.id
    else:
        receipt = None
        assert is_helpless(state(game), value.actor, counterpart)
        assert game.inspect(PLAYER, action)["result"]["blocked_before_roll"]
        assert not advice.records(state(game), advice.Advice)
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
    with ledger.engine.connect() as c:
        assert prove(restarted, c, state(restarted), value.id).receipt == (
            receipt["id"] if given else None
        )
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert "PRIVATE_ADVICE" not in json.dumps(gateway.messages)
