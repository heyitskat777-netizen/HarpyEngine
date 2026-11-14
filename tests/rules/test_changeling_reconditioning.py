"""Paid Live Reconditioning follows actual cockpit damage and grants only absent Tags."""

import asyncio
from uuid import uuid4

import pytest
from test_changeling import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m3_changeling import open_changeling
from girlframe.engine import m3_changeling as rules
from girlframe.engine.m2 import PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_changeling import ChangelingService, prove_acquisition
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError


def test_native_paid_reconditioning_after_actual_cockpit_damage_rejects_existing_tag(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    actor, target = current_ref(state(game), 2), current_ref(state(game), 3)
    # Prior world, original cockpit/resources and this existing Tag are explicit
    # synthetic setup, not invented acquisition, damage or Reconditioning proof.
    with ledger.transaction() as c:
        prior = state(game)
        prior.sheets["2"].tags.append(
            TagState(id="prior-pet", label="pEt", giver=3, giver_actor=target, observers=(2, 3))
        )
        game.event(c, 1, str(uuid4()), "synthetic.prior_existing_reconditioning_tag", prior)
    permissions = state(game).sheets["2"].permissions
    before_rolls = game.dice.calls

    async def purchase():
        own = current(2, 991801)
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_changeling(own, controls)
        menu = own.edit_original_response.call_args.kwargs["view"]
        assert "buy:" + rules.RECONDITION in dict(menu.fields[0].options)
        menu.values["entry"] = ("buy:" + rules.RECONDITION,)
        response = current(2, 991802)
        response.channel_id = 900
        await menu.confirm.callback(response)
        form = response.edit_original_response.call_args.kwargs["view"]
        form.values["account"] = "I pay for the actual Live Reconditioning Module"
        await form.confirm.callback(current(2, 991803))
        assert form.completed

    asyncio.run(purchase())
    acquired = rules.held(state(game), actor, rules.RECONDITION)
    assert acquired and state(game).sheets["2"].permissions == permissions - 2
    assert game.dice.calls == before_rolls
    with ledger.engine.connect() as c:
        prove_acquisition(game, c, state(game), acquired)
    assert not rules.records(state(game), rules.Reconditioning)
    assert not state(game).scene_casts  # Real legacy joins, not a fabricated materialized cast.
    asset = next(x for x in state(game).sheets["2"].assets if x.family == "girl" and not x.damaged)
    game.dice = Dice((1, 2))
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="engage",
            heat=0,
            target_actor=target,
            context="I cover the other Girl from inside my original cockpit",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=("cover",),
        fields={"cover": asset.id},
        denied=(asset.id,),
        text="I take the actual damage on this owned Girl Asset",
    )
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert next(x for x in state(game).sheets["2"].assets if x.id == asset.id).damaged
    values = rules.records(state(game), rules.Reconditioning)
    assert len(values) == 1
    entitlement = values[0]
    assert entitlement.actor == actor and entitlement.subject.actor == actor
    assert entitlement.asset == asset.id and entitlement.frame == rules.frame(state(game), actor)
    assert entitlement.controller == 2 and entitlement.completed_event is None
    assert entitlement.source == action and entitlement.cast.channel == 900
    assert {actor, target} <= {role.actor for role in entitlement.cast.roles}
    assert all(role.source_event for role in entitlement.cast.roles)
    with ledger.engine.connect() as c:
        assert (
            rules.record(_history(c, game, entitlement.event), rules.Reconditioning, entitlement.id)
            == entitlement
        )
    receipt = game.inspect(PLAYER, action)["receipt"]
    rolls = game.dice.calls
    before = state(game).model_dump_json()
    assert "Pet" not in controls.view(PLAYER, entitlement.id)["tags"]
    with pytest.raises(WorkflowError, match="already has this Tag"):
        controls.recondition(PLAYER, str(uuid4()), state(game).revision, entitlement.id, "Pet")
    with pytest.raises(WorkflowError):
        controls.recondition(OTHER, str(uuid4()), state(game).revision, entitlement.id, "Obedient")
    with pytest.raises(WorkflowError):
        controls.view(ADMIN, entitlement.id)
    assert state(game).model_dump_json() == before

    async def accept_and_reopen():
        own = current(2, 991804)
        await own.response.defer(ephemeral=True)
        await open_changeling(own, controls, entitlement.id)
        form = own.edit_original_response.call_args.kwargs["view"]
        assert set(dict(form.fields[0].options)) == {"pass", "Masochistic", "Obedient"}
        assert not await form.interaction_check(current(3, 991805))
        form.values["tag"] = ("Obedient",)
        await form.confirm.callback(current(2, 991806))
        assert form.completed
        reopened = current(2, 991807)
        await reopened.response.defer(ephemeral=True)
        await open_changeling(reopened, ChangelingService(game), entitlement.id)
        history = reopened.edit_original_response.call_args.kwargs["view"]
        assert "Completed" in history.text() and "Obedient" in history.text()

    asyncio.run(accept_and_reopen())
    final = state(game)
    saved = rules.record(final, rules.Reconditioning, entitlement.id)
    assert saved.completed_event and saved.label == "Obedient"
    tags = final.sheets["2"].tags
    assert [x.label for x in tags if x.label.casefold() == "pet"] == ["pEt"]
    granted = next(x for x in tags if x.label == "Obedient")
    assert granted.id == saved.completed_event and granted.giver_actor == actor
    assert final.sheets["2"].permissions == permissions - 2
    assert game.dice.calls == rolls and game.inspect(PLAYER, action)["receipt"] == receipt
    with pytest.raises(WorkflowError):
        controls.recondition(PLAYER, str(uuid4()), final.revision, entitlement.id, "Masochistic")
    assert state(game).model_dump_json() == final.model_dump_json()
