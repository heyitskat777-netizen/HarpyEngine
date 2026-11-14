"""Actual native self-Dose counter disposal remains committed through ANKOU Feedback."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ankou_dose_counter_feedback import ready
from test_dose_up import native_choice
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_alpha import open_alpha_choice
from girlframe.engine import m3_alpha as alpha
from girlframe.engine import m3_ankou_feedback as feedback
from girlframe.engine import m3_disposable_psyche as psyche
from girlframe.engine import m3_dose_up as dose
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.services.m2_game import GameService
from girlframe.services.m3_ankou_feedback import prove
from girlframe.services.m3_disposable_psyche import PsycheService, prove_disposal
from girlframe.services.m3_dose_up import prove as prove_dose
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.onboarding import WorkflowError


@pytest.mark.parametrize("given,extra", [(True, 4), (False, 3)])
def test_native_disposable_dose_counter_preserves_real_removal(
    ledger, tmp_path, monkeypatch, given, extra
):
    game, worker, gateway, identity = ready(ledger, tmp_path, monkeypatch)
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(feedback.RULE, alpha.RULE, dose.RULE, dose.SELF_RULE, psyche.RULE),
    )
    actor, attacker = current_ref(state(game), 3), current_ref(state(game), 2)
    game.dice = Dice((1, 1))
    parent = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="brutalize",
            target_actor=actor,
            heat=0,
            context="PRIVATE_DISPOSABLE_COUNTER: original Alpha pressure",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 4)
    pass_tags(game)
    parent_receipt = game.inspect(PLAYER, parent)["receipt"]
    assert parent_receipt and game.dice.calls == 1
    answer(game, OTHER, "alpha_low", options=("counter_broken",))
    request = next(x for x in game.choices(OTHER) if x["kind"] == "alpha_counter_play")
    before = state(game).sheets["3"].model_copy(deep=True)
    gain = 3 if given else 1
    spent = before.heat + gain + extra

    async def native():
        opened = current(OTHER.user_id, 99601)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_alpha_choice(opened, game, request["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        disposal = next(x for x in form.fields if x.key == "disposable_heat")
        assert {x[0] for x in disposal.options} == {"0", "3", "4"}
        heat = next(x for x in form.fields if x.key == "heat")
        assert str(before.heat + 7) in {x[0] for x in heat.options}
        assert not await form.interaction_check(current(PLAYER.user_id, 99600))
        form.values.update(
            play=(dose.PLAY,),
            identity=(identity,),
            gain=(str(gain),),
            disposable_heat=(str(extra),),
            heat=(str(spent),),
            context="PRIVATE_DISPOSABLE_COUNTER: self-Dose with actual Identity removal",
        )
        invalid = dict(form.values, play=("keep_your_head",))
        with pytest.raises(WorkflowError, match="own self-Dose counter"):
            await form.submit_action(current(OTHER.user_id, 99599), invalid)
        assert state(game).sheets["3"] == before
        submitted = current(OTHER.user_id, 99602)
        await form.confirm.callback(submitted)
        assert form.completed, submitted.edit_original_response.call_args_list
        saved = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == saved

    game.dice.faces = (6, 6)
    asyncio.run(native())
    with ledger.engine.connect() as c:
        actions = t.m2["m2_actions"]
        child = c.scalar(
            sa.select(actions.c.id).where(
                actions.c.campaign_id == ledger.campaign_id,
                actions.c.parent_id == parent,
                actions.c.actor_id == "3",
            )
        )
    tick(worker, gateway, 4)
    if not any(x.action == child for x in feedback.sources(state(game))):
        game.roll(OTHER, "m2.confirmed_roll:" + child, child)
    value = next(x for x in feedback.sources(state(game)) if x.action == child)
    committed = state(game).sheets["3"].model_copy(deep=True)
    assert value.phase == "choice" and value.dose_source is not None
    assert value.prepared.disposable_heat == extra
    assert not any(x.id == identity for x in committed.identities)
    assert committed.heat == before.heat + gain + extra - spent == value.heat_committed
    assert game.dice.calls == 1 and game.inspect(OTHER, child)["receipt"] is None
    with ledger.engine.connect() as c:
        removal = prove_disposal(game, c, state(game), child)
        assert removal.commit_event == value.mark_event and removal.receipt is None
        assert (removal.gain, removal.extra, removal.spent) == (gain, extra, spent)
        assert prove(game, c, state(game), value.id) == value
    with pytest.raises(WorkflowError, match="original owner"):
        PsycheService(ledger, game).view(PLAYER, child)
    game.abort(ADMIN, str(uuid4()), parent)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = next(x for x in recovery.saved(PLAYER) if x["id"] == parent)
    assert saved["rolled"] and not saved["cancellable"]
    recovery.recover(PLAYER, "recover-original-disposable-counter", parent, saved["revision"])
    tick(worker, gateway, 3)
    assert state(game).sheets["3"] == committed and game.dice.calls == 1
    answer(
        game,
        OTHER,
        "ankou_feedback_choice",
        options=("purpose",),
        fields={"target": attacker.token},
        text="PRIVATE_DISPOSABLE_COUNTER: actual purpose plea",
    )
    answer(
        game,
        PLAYER,
        "ankou_feedback_purpose",
        flag=given,
        text="PRIVATE_DISPOSABLE_COUNTER: keep us safe" if given else "I give no purpose",
    )
    if given:
        # Removal opened a real slot; do not erase a second Identity for the new purpose.
        answer(game, OTHER, "ankou_feedback_identity")
        before_roll = state(game).sheets["3"].model_copy(deep=True)
        assert len(before_roll.identities) == len(before.identities)
        tick(worker, gateway, 4)
        pass_tags(game)
        receipt = game.inspect(OTHER, child)["receipt"]
        assert receipt["heat"] == spent and receipt["disposable_psyche"] == child
        assert state(game).sheets["3"].heat == before_roll.heat
        assert state(game).sheets["3"].identities == before_roll.identities
        assert game.dice.calls == 2
        native_choice(game, OTHER, ("quick", "strong"))
        assert game.inspect(PLAYER, parent)["state"] != "complete"
        assert not alpha.conditions(state(game), attacker, actor)
        native_choice(game, ADMIN, ("calm",))
        with ledger.engine.connect() as c:
            original = prove_dose(game, c, state(game), child)
            assert original.actor == original.target == actor
            assert original.total == 12 + spent and original.heat == spent
        assert {x.component for x in dose.drug_tags(state(game), actor)} == {
            "quick",
            "strong",
            "calm",
        }
        assert alpha.conditions(state(game), attacker, actor)
    else:
        receipt = None
        assert game.dice.calls == 1 and is_helpless(state(game), actor, attacker)
        assert not alpha.conditions(state(game), attacker, actor)
        assert not dose.records(state(game), dose.Dose)
        assert not dose.drug_tags(state(game), actor)
        assert game.inspect(OTHER, child)["result"]["blocked_before_roll"]
        assert state(game).sheets["3"].heat == committed.heat
    assert not any(x.id == identity for x in state(game).sheets["3"].identities)
    assert game.inspect(PLAYER, parent)["receipt"] == parent_receipt
    assert game.inspect(OTHER, child)["receipt"] == receipt
    assert (
        game.inspect(OTHER, child)["state"] == game.inspect(PLAYER, parent)["state"] == "complete"
    )
    restarted = GameService(ledger, dice=game.dice)
    assert restarted.inspect(OTHER, child) == game.inspect(OTHER, child)
    if given:
        assert restarted.roll(OTHER, str(uuid4()), child)["receipt"] == receipt
        assert game.dice.calls == 2
    with ledger.engine.connect() as c:
        final_removal = prove_disposal(restarted, c, state(restarted), child)
        assert final_removal.receipt == (receipt["id"] if given else None)
        assert final_removal.identity == removal.identity
        assert final_removal.commit_event == removal.commit_event
        assert len(psyche.disposals(state(game))) == 1
        assert game.action(c, child)["data"]["alpha_counter_completed"]
        assert game.action(c, parent)["data"]["alpha"]["counter_child"] == child
    tick(worker, gateway, 8)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert "PRIVATE_DISPOSABLE_COUNTER" not in json.dumps(gateway.messages)
