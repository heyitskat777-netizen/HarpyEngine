"""Actual native performance and departure paths; no synthetic source receipts."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_disposable_psyche import real_period
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current
from test_off_duty_cycle import call, roll_for
from test_vatgrown_plays import native_choice, ready, sex

from girlframe.database import tables as t
from girlframe.discord_adapter.m2_forms import NativeForm
from girlframe.discord_adapter.m3_vatgrown_plays import open_vatgrown_plays
from girlframe.engine import m3_vatgrown_plays as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_vatgrown_plays import prove, prove_investment, side_condition
from girlframe.services.onboarding import WorkflowError


def open_source(controls, viewer, identity, number):
    async def show():
        interaction = current(viewer.user_id, number)
        interaction.channel_id = 900
        await interaction.response.defer(ephemeral=True)
        await open_vatgrown_plays(interaction, controls, identity)
        form = interaction.edit_original_response.call_args.kwargs["view"]
        assert isinstance(form, NativeForm)
        return form

    return asyncio.run(show())


def submit(form, viewer, number, values):
    async def respond():
        form.values.update(values)
        interaction = current(viewer.user_id, number)
        await form.confirm.callback(interaction)
        assert form.completed, interaction.edit_original_response.call_args_list

    asyncio.run(respond())


def action_for(game, key):
    with game.store.engine.connect() as c:
        outcome = c.scalar(
            sa.select(t.commands.c.outcome_json).where(
                t.commands.c.campaign_id == game.store.campaign_id,
                t.commands.c.interaction_key == str(key),
            )
        )
    return json.loads(outcome)["action_id"]


def test_actual_native_prime_keep_completes_before_separate_original_investor_judgment(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    cycle, period = real_period(MissionService(ledger), game)
    roll_for(cycle, game, period, PLAYER, (5, 5))
    actor = current_ref(state(game), 2)
    identity = rules.identity("investment", period, actor.token)
    handler = current_ref(state(game), 1)
    review = cycle.review(PLAYER, period)
    cycle.scene(
        PLAYER,
        str(uuid4()),
        period,
        review["revision"],
        state(game).revision,
        "prime_high",
        (2, 1),
        "The actual Investor and original Vatgrown complete their source scene",
        investor=handler,
    )
    call(cycle, game, PLAYER, period, "acknowledge", 2)
    call(cycle, game, ADMIN, period, "acknowledge", 2)
    controls.new_desire(
        ADMIN,
        str(uuid4()),
        identity,
        state(game).revision,
        "A controlled endurance demonstration",
        "The actual original Investor authors this new desire",
    )
    before = state(game)
    with pytest.raises(WorkflowError):
        open_source(controls, OTHER, identity, 64000)
    assert state(game) == before
    form = open_source(controls, PLAYER, identity, 64001)
    assert "does not declare the desire fulfilled" in form.instructions
    selected = next(x for x in before.sheets["2"].identities if not x.marked)
    game.dice.faces = (4, 4)
    values = dict(
        identity=(selected.id,),
        gain=("1",),
        pair_share=("0",),
        heat=(str(before.sheets["2"].heat + 1),),
        piloting=("no",),
        context="I endure the actual dangerous drill requested by the original Investor",
        trigger=("yes",),
    )
    submit(form, PLAYER, 64002, values)
    action = action_for(game, 64002)
    confirmed = state(game)
    assert not next(x for x in confirmed.sheets["2"].identities if x.id == selected.id).marked
    with ledger.engine.connect() as c:
        source = game.action(c, action)
        assert source["parent_id"] is None
        assert source["data"]["prepared"]["source_work"] == identity
        assert source["data"]["investment_performance"]["actor"] == actor.model_dump(mode="json")
    submit(form, PLAYER, 64003, values)
    assert state(game) == confirmed
    tick(worker, gateway, 3)
    assert next(x for x in state(game).sheets["2"].identities if x.id == selected.id).marked
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", text="I actually endure the dangerous performance")
    answer(
        game,
        ADMIN,
        "handler_keep",
        flag=True,
        text="The actual Handler adjudicates the real endurance demonstration",
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    waiting = controls.view(PLAYER, identity)["investment"]
    assert waiting["phase"] == "fulfilment_judgment" and waiting["good"] is None
    assert not rules.records(state(game), rules.RequisitionOffer)
    tick(worker, gateway, 6)
    judgment = open_source(controls, ADMIN, identity, 64004)
    submit(
        judgment,
        ADMIN,
        64005,
        dict(
            fulfilled=("yes",),
            gift=("creature_comforts",),
            account="My actual completed demonstration fulfilled the desire; this gift is suitable",
        ),
    )
    saved = state(game)
    with ledger.engine.connect() as c:
        actual = prove_investment(game, c, saved, identity)
    assert actual.performance_action == action and actual.performance_event
    assert actual.phase == "complete" and actual.good and actual.controller == ADMIN.user_id
    assert actual.judgment_event != actual.performance_event
    assert rules.records(saved, rules.RequisitionOffer)[-1].investment == identity
    assert controls.view(PLAYER, identity)["investment"]["judgment_event"] == actual.judgment_event


def test_actual_native_high_departure_disobeys_before_original_actor_leaves_cast(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    session, original_play = sex(game, worker, gateway, controls, (5, 5))
    before = state(game)
    teacher = before.sheets["3"].identities[1]
    replaced = before.sheets["2"].identities[0]
    native_choice(
        game,
        OTHER,
        "vat_sex_learn",
        identities=(teacher.id,),
        replacements=(replaced.id,),
        play=(rules.BRUTALIZE,),
        account="The actual original counterpart makes the printed learning choices",
    )
    assert game.inspect(PLAYER, original_play)["state"] == "complete"
    tick(worker, gateway, 6)
    original = state(game)
    actor = current_ref(original, 2)
    with ledger.engine.connect() as c:
        source = prove(game, c, original, session)
        assert side_condition(game, c, original, actor)
    form = open_source(controls, PLAYER, session, 64100)
    assert form.title == "Attempt to leave"
    game.dice.faces = (6, 6)
    submit(
        form,
        PLAYER,
        64101,
        dict(departure="I actually try to leave the original counterpart's side", heat=("0",)),
    )
    action = action_for(game, 64101)
    pending = state(game)
    assert any(
        x.actor == actor
        for x in next(x for x in pending.scene_casts if x.id == source.cast.id).roles
    )
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_disobey", flag=True)
    answer(game, ADMIN, "handler_disobey", flag=True)
    assert game.inspect(PLAYER, action)["result"]["can_disobey"]
    final = state(game)
    assert not any(
        x.actor == actor for x in next(x for x in final.scene_casts if x.id == source.cast.id).roles
    )
    assert (
        final.placements == original.placements
        and final.sheets["2"].character_id == actor.incarnation
    )
    with ledger.engine.connect() as c:
        assert side_condition(game, c, final, actor) is None
        saved = prove(game, c, final, session)
        assert saved == source
        assert PLAYER.user_id not in game.scene(c, 900)["participants"]
    assert controls.view(PLAYER, session)["side"]["leaving_action"] == action
    tick(worker, gateway, 6)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
