"""Native Doll last mark, actual Feedback, original observer and real quiet/secret effects."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ankou_feedback import choose, finish_keep
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current
from test_vatgrown import choose as choose_doll
from test_vatgrown import target_attempt

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_vatgrown import open_vatgrown
from girlframe.engine import m3_ankou_feedback as feedback
from girlframe.engine import m3_vatgrown as doll
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.services.m2_game import GameService
from girlframe.services.m3_ankou_doll import source_binding
from girlframe.services.m3_ankou_feedback import FeedbackService, prove
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.m3_vatgrown import DollService
from girlframe.services.m3_vatgrown import prove as prove_doll
from girlframe.services.onboarding import WorkflowError


def ready(store, tmp_path, monkeypatch):
    import test_vatgrown

    original = test_vatgrown.service
    monkeypatch.setattr(
        test_vatgrown,
        "service",
        lambda *args, **kwargs: original(*args, **(kwargs | {"frame": "PROJECT ANKOU"})),
    )
    game, worker, gateway, controls = test_vatgrown.ready(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(feedback.RULE, doll.RULE))
    return game, worker, gateway, controls


def last_doll(game, worker, gateway):
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

    async def native_doll():
        first = current(PLAYER.user_id, 99481)
        first.channel_id = 900
        await first.response.defer(ephemeral=True)
        await open_vatgrown(first, DollService(game))
        menu = first.edit_original_response.call_args.kwargs["view"]
        menu.values["source"] = ("play",)
        opened = current(PLAYER.user_id, 99482)
        await menu.confirm.callback(opened)
        form = opened.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            target=(current_ref(state(game), OTHER.user_id).token,),
            identity=(identities[-1],),
            gain=("1",),
            heat=("2",),
            account="PRIVATE_DOLL_SOURCE: I fade into the background using my last Identity",
        )
        response = current(PLAYER.user_id, 99483)
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
    action = asyncio.run(native_doll())
    tick(worker, gateway, 3)
    if not any(x.action == action for x in feedback.sources(state(game))):
        game.roll(PLAYER, "m2.confirmed_roll:" + action, action)
    value = next(x for x in feedback.sources(state(game)) if x.action == action)
    assert value.phase == "choice" and value.doll_source is not None
    assert value.heat_before == before.sheets["2"].heat
    assert value.heat_committed == state(game).sheets["2"].heat == value.heat_before - 1
    assert next(x for x in state(game).sheets["2"].identities if x.id == identities[-1]).marked
    assert game.dice.calls == 0 and game.inspect(PLAYER, action)["receipt"] is None
    assert not doll.records(state(game), doll.Source)
    assert state(game).order == before.order
    with game.store.engine.connect() as c:
        saved = game.action(c, action)
        assert prove(game, c, state(game), value.id) == value
        assert source_binding(game, c, state(game), saved) == value.doll_source
        directed = copy.deepcopy(saved)
        directed["data"]["vatgrown"]["princess_direction"] = "not-the-native-source"
        with pytest.raises(WorkflowError, match="SOURCE_ANKOU_DOLL_PORT_REQUIRED"):
            source_binding(game, c, state(game), directed)
        substituted = copy.deepcopy(saved)
        substituted["data"]["vatgrown"]["counterpart"] = ADMIN.user_id
        with pytest.raises(WorkflowError, match="observer controllers"):
            source_binding(game, c, state(game), substituted)
    return action, value


@pytest.mark.parametrize("given", [True, False])
def test_native_doll_feedback_preserves_cost_and_owned_observer_effects(
    ledger, tmp_path, monkeypatch, given
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    action, value = last_doll(game, worker, gateway)
    counterpart = current_ref(state(game), OTHER.user_id)
    before_order = state(game).order
    committed = state(game).sheets["2"].model_copy(deep=True)
    game.abort(ADMIN, str(uuid4()), action)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == action)
    assert not saved["rolled"] and not saved["cancellable"]
    recovery.recover(PLAYER, "recover-original-doll-feedback", action, saved["revision"])
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
        text="PRIVATE_DOLL_PURPOSE: stay close to me" if given else "I give no purpose",
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
        choose_doll(game, PLAYER, "vat_doll_benefits", ("quiet", "information"), native=True)
        question = next(x for x in game.choices(OTHER) if x["kind"] == "vat_doll_information")
        with pytest.raises(WorkflowError):
            game.respond(
                PLAYER,
                str(uuid4()),
                question["id"],
                question["revision"],
                ChoiceAnswer(text="Cannot supply the actual observer's private secret"),
            )
        choose_doll(
            game,
            OTHER,
            "vat_doll_information",
            text="PRIVATE_DOLL_SECRET: I keep a spare key beside my desk",
            native=True,
        )
        result = controls.view(PLAYER, action)
        assert result["quiet"] and result["information"]["answer"].startswith("PRIVATE_DOLL_SECRET")
        with pytest.raises(WorkflowError):
            controls.view(ADMIN, action)
        with ledger.engine.connect() as c:
            original = prove_doll(game, c, state(game), action)
            assert original.complete and original.target == counterpart
            assert original.counterpart == OTHER.user_id and original.total == 8
            assert prove(game, c, state(game), value.id).receipt == receipt["id"]
        assert state(game).sheets["3"].character_id == counterpart.incarnation
    else:
        receipt = None
        assert is_helpless(state(game), value.actor, counterpart)
        assert game.inspect(PLAYER, action)["result"]["blocked_before_roll"]
        assert not doll.records(state(game), doll.Source)
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
    if given:
        with pytest.raises(WorkflowError, match="attention"):
            target_attempt(restarted)
        assert game.dice.calls == 1
    # Real channel reuse cannot invalidate the historical source and its receipt.
    restarted.close_scene(ADMIN, "close-finished-doll-scene", 900)
    rebound = restarted.bind_scene(ADMIN, "rebind-finished-doll-channel", 900)["scene"]
    assert rebound != value.cast.id
    with ledger.engine.connect() as c:
        historical = prove(restarted, c, state(restarted), value.id)
        assert historical.receipt == (receipt["id"] if given else None)
    # Targeted historical-read regression: a later same-incarnation profile
    # revision is supplied without forging a gameplay transition or new receipt.
    from girlframe.services import m3_ankou_doll, m3_dose_up, m3_vatgrown

    with ledger.engine.connect() as c:
        before = state(restarted)
        bindings = m3_ankou_doll.profiles(c, ledger.campaign_id)
        later = tuple(
            person.model_copy(update={"profile_revision": person.profile_revision + 1})
            if person.owner == PLAYER.user_id
            else person
            for person in bindings
        )
        with monkeypatch.context() as changed_profile:
            for module in (m3_ankou_doll, m3_dose_up, m3_vatgrown):
                changed_profile.setattr(module, "profiles", lambda *_: later)
            assert prove(restarted, c, before, value.id).receipt == (
                receipt["id"] if given else None
            )
            if given:
                assert prove_doll(restarted, c, before, action).complete
            # The live native body resolver still rejects the stale profile.
            with pytest.raises(ValueError, match="STALE_ACTOR"):
                m3_dose_up._native(restarted, c, before, value.actor)
        assert state(restarted) == before
    assert "PRIVATE_DOLL" not in json.dumps(gateway.messages)
