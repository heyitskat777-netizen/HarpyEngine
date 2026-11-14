"""Native self/vein Dose final marks retain real costs, Orders and owned cocktail results."""

import asyncio
import copy
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ankou_feedback import begin_mark, choose, finish_keep, ready
from test_dose_up import contact, native_choice
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_dose_up import open_dose_up
from girlframe.engine import m3_ankou_feedback as feedback
from girlframe.engine import m3_dose_up as dose
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.services.m3_ankou_feedback import prove as prove_feedback
from girlframe.services.m3_disposable_psyche import prove_disposal
from girlframe.services.m3_dose_up import DoseUpService, feedback_source_binding, pre_roll, prove
from girlframe.services.onboarding import WorkflowError


def actual_dose_source(ledger, tmp_path, monkeypatch, *, other=False):
    _, game, worker, gateway, _, _ = ready(ledger, tmp_path, monkeypatch)
    identities = [x.id for x in state(game).sheets["2"].identities if not x.marked]
    for identity in identities[:-1]:
        game.dice = Dice((4, 4))
        prior = begin_mark(game, identity)
        tick(worker, gateway, 3)
        finish_keep(game, worker, gateway, prior)
    # Start the new source RNG accounting after the genuine prerequisite Plays.
    game.dice = Dice((3, 4) if other else (2, 2))
    controls = DoseUpService(ledger, game)
    order, reach = None, None
    if other:
        reach = contact(controls, game, native=True)
    else:
        order = game.issue_order(
            ADMIN, str(uuid4()), 900, PLAYER.user_id, "Actually dose yourself now", dose_up=True
        )["order_id"]
        tick(worker, gateway, 3)
        answer(game, PLAYER, "order_response", options=("obedient",))
        tick(worker, gateway, 5)

    async def start_native():
        first = current(PLAYER.user_id, 99801)
        first.channel_id = 900
        await first.response.defer(ephemeral=True)
        await open_dose_up(first, controls)
        menu = first.edit_original_response.call_args.kwargs["view"]
        menu.values["action"] = ("other:" + reach if reach else "self",)
        opened = current(PLAYER.user_id, 99802)
        await menu.confirm.callback(opened)
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert {"identity", "gain", "disposable_heat"} <= {x.key for x in form.fields}
        form.values.update(
            identity=(identities[-1],),
            gain=("1",),
            disposable_heat=("0" if other else "3",),
            heat=("1" if other else "4",),
            account="PRIVATE_DOSE_FEEDBACK: inject the actual combat cocktail",
        )
        if order:
            form.values["order"] = (order,)
        response = current(PLAYER.user_id, 99803)
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
    assert source.phase == "choice" and source.dose_source is not None and game.dice.calls == 0
    assert game.inspect(PLAYER, action)["receipt"] is None
    assert state(game).sheets["2"].heat == source.heat_committed == 0
    assert not dose.records(state(game), dose.OrderUse)
    assert not dose.records(state(game), dose.Dose)
    assert not dose.drug_tags(state(game), current_ref(state(game), 2))
    with ledger.engine.connect() as c:
        assert prove_feedback(game, c, state(game), source.id) == source
        if not other:
            assert prove_disposal(game, c, state(game), action).receipt is None
    return game, worker, gateway, controls, action, source, order, reach


@pytest.mark.parametrize("given", [True, False])
def test_native_ordered_dose_feedback_purpose_keeps_single_disposal_and_real_order(
    ledger, tmp_path, monkeypatch, given
):
    game, worker, gateway, controls, action, source, order, _ = actual_dose_source(
        ledger, tmp_path, monkeypatch
    )
    assert not any(x.id == source.identity.id for x in state(game).sheets["2"].identities)
    target = current_ref(state(game), OTHER.user_id)
    choose(game, "purpose", target)
    answer(
        game,
        OTHER,
        "ankou_feedback_purpose",
        flag=given,
        text="PRIVATE_DOSE_PURPOSE: protect the civilians" if given else "I refuse this purpose",
    )
    assert game.dice.calls == 0 and not dose.records(state(game), dose.OrderUse)
    if not given:
        assert is_helpless(state(game), source.actor, target)
        assert feedback.get(state(game), source.id).phase == "ended"
        assert game.inspect(PLAYER, action)["state"] == "complete"
        assert game.inspect(PLAYER, action)["receipt"] is None
        tick(worker, gateway, 5)
        assert game.dice.calls == 0 and not dose.records(state(game), dose.Dose)
        assert not dose.records(state(game), dose.OrderUse)
        with ledger.engine.connect() as c:
            assert game.lock(c, 900)["state"] == "released"
        return
    answer(game, PLAYER, "ankou_feedback_identity")
    before = state(game).sheets["2"].model_copy(deep=True)
    assert game.inspect(PLAYER, action)["state"] == "ready_to_roll"
    with ledger.engine.connect() as c:
        actual = game.action(c, action)
        changed = copy.deepcopy(actual)
        changed["data"]["dose_up"]["chooser"] = OTHER.user_id
        with pytest.raises(WorkflowError, match="unchanged actual Dose"):
            pre_roll(game, c, PLAYER, state(game), changed, commit=False)
        pre_roll(game, c, PLAYER, state(game), actual, commit=False)
        assert game.lock(c, 900)["state"] == "held"
    tick(worker, gateway, 3)
    assert game.dice.calls == 1
    pass_tags(game)
    # The actual issuer, not the roller or Feedback respondent, owns the Order override.
    assert not any(x["kind"] == "dose_up_components" for x in game.choices(PLAYER))
    native_choice(game, ADMIN, ("quick", "calm"))
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["heat"] == 4 and receipt["pre_total"] == 8
    actual = state(game)
    assert actual.sheets["2"].heat == before.heat == 0
    assert actual.sheets["2"].identities == before.identities
    assert len(dose.drug_tags(actual, source.actor)) == 2
    assert dose.records(actual, dose.OrderUse) == (dose.OrderUse(id=order, action=action),)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    with ledger.engine.connect() as c:
        value = prove(game, c, actual, action)
        assert value.order == order and value.heat == 4
        assert [(x.role, x.chooser) for x in value.selections] == [("issuer", ADMIN.user_id)]
        assert prove_disposal(game, c, actual, action).receipt == receipt["id"]
        assert prove_feedback(game, c, actual, source.id).receipt == receipt["id"]
        assert (
            feedback_source_binding(game, c, actual, game.action(c, action)) == source.dose_source
        )
    assert game.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt
    tick(worker, gateway, 5)
    assert game.dice.calls == 1
    assert controls.view(PLAYER, action)["components"] == [
        dose.LABELS[x] for x in ("quick", "calm")
    ]
    assert "PRIVATE_DOSE" not in json.dumps(gateway.messages)


def test_native_vein_dose_feedback_tear_retains_contact_then_actual_recipient_tags(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls, action, source, _, reach = actual_dose_source(
        ledger, tmp_path, monkeypatch, other=True
    )
    target = current_ref(state(game), OTHER.user_id)
    asset = next(x for x in state(game).sheets["2"].assets if x.family == "frame" and not x.void)
    choose(game, "tear", target, asset=asset.id)
    value = feedback.get(state(game), source.id)
    assert value.phase == "child" and state(game).sheets["2"].heat == 5
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
            context="PRIVATE_DOSE_REPRISAL: demand the actual person's true name",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_flirt", options=("name",))
    answer(game, OTHER, "target_flirt", text="PRIVATE_DOSE_REPRISAL_ANSWER")
    assert game.inspect(PLAYER, child)["state"] == "complete" and game.dice.calls == 1
    assert feedback.get(state(game), source.id).phase == "resolved"
    assert not dose.records(state(game), dose.Dose)
    before = state(game).sheets["2"].model_copy(deep=True)
    game.dice.faces = (3, 4)
    tick(worker, gateway, 3)
    pass_tags(game)
    native_choice(game, PLAYER, ("strong", "bliss"))
    actual = state(game)
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["heat"] == 1 and receipt["pre_total"] == 8 and game.dice.calls == 2
    assert actual.sheets["2"].heat == before.heat == 0
    assert actual.sheets["2"].identities == before.identities
    assert not any(x.id == asset.id for x in actual.sheets["2"].assets)
    assert not dose.drug_tags(actual, source.actor)
    assert len(dose.drug_tags(actual, target)) == 2
    with ledger.engine.connect() as c:
        value = prove(game, c, actual, action)
        assert value.contact == reach and value.target == target and value.order is None
        assert prove_feedback(game, c, actual, source.id).receipt == receipt["id"]
    assert controls.view(OTHER, action)["components"] == [
        dose.LABELS[x] for x in ("strong", "bliss")
    ]
    assert game.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt
    tick(worker, gateway, 5)
    assert game.dice.calls == 2 and "PRIVATE_DOSE" not in json.dumps(gateway.messages)
