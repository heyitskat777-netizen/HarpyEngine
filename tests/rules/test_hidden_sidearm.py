"""Revealed actual ordinary gun has distinct Helpless, lethal and paused-shot endpoints."""

import asyncio
from uuid import uuid4

import pytest
from test_cast_service import change
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Dice, answer, pass_tags, state, tick
from test_mission_ui import current
from test_secretary import ready as ordinary_award

from girlframe.discord_adapter.inbox import InboxView
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_hidden_sidearm import open_sidearm
from girlframe.engine import m3_handler_advancements as awards
from girlframe.engine import m3_handler_ordinary as ordinary_rules
from girlframe.engine import m3_hidden_sidearm as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
from girlframe.services.inbox import InboxService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_hidden_sidearm import HiddenSidearmService
from girlframe.services.m3_items import prove_item
from girlframe.services.m3_missions import MissionService
from girlframe.services.onboarding import WorkflowError


def native(service, identity=None, **values):
    async def run():
        own = current(1, int(uuid4().int % 1000000000))
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_sidearm(own, service, identity)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(values)
        confirmed = current(1, int(uuid4().int % 1000000000))
        await form.confirm.callback(confirmed)
        assert form.completed, confirmed.edit_original_response.call_args

    asyncio.run(run())


def ready(store, tmp_path, monkeypatch, *, last_asset=False):
    game, _, worker, gateway = ordinary_award(store, tmp_path, monkeypatch)
    approved(store, game, tmp_path, monkeypatch, extra=(ordinary_rules.RULE, rules.RULE))
    casts = CastService(ActorService(MissionService(store)))
    change(casts, ADMIN, "join", current_ref(state(game), 1))
    if last_asset:
        with store.transaction() as c:
            canon = state(game)
            girl = [x for x in canon.sheets["3"].assets if x.family == "girl"]
            assert len(girl) > 1
            for asset in girl[:-1]:
                asset.damaged = True
            game.event(c, 1, "actual-prior-girl-injuries", "synthetic.prior_injuries", canon)
    service = HiddenSidearmService(store, game)
    award = next(x for x in awards.awards(state(game)) if x.phase == "held")
    revision = state(game).revision
    before_assets = {uid: sheet.assets for uid, sheet in state(game).sheets.items()}
    native(
        service,
        award=(award.id,),
        actual=("actual",),
        account="My actual ordinary sidearm is concealed beneath my coat",
    )
    receipt = rules.acquisitions(state(game))[0]
    assert {uid: sheet.assets for uid, sheet in state(game).sheets.items()} == before_assets
    with store.engine.connect() as c:
        gun = prove_item(c, game, state(game), receipt.gun)
        assert gun.weapon and gun.holder == receipt.handler and gun.asset_id is None
    with pytest.raises(WorkflowError):
        service.buy(ADMIN, str(uuid4()), award.id, revision, "Do not charge twice", actual=True)
    game.dice = Dice((4, 5))
    return game, service, worker, gateway, receipt


def reveal(service, game, receipt, viewer, choice, action=None):
    original = current_ref(state(game), viewer.user_id)
    values = dict(
        scene=("900",),
        target=(original.token,),
        choice=(choice,),
        actual=("actual",),
        account="My original body is present; I reveal the gun beneath my coat in actual reach",
    )
    if action:
        values["action"] = (action,)
    native(service, receipt.id, **values)
    return rules.reveals(state(game))[-1]


def conceal(service, receipt):
    native(
        service,
        receipt.id,
        actual=("actual",),
        account="Afterward I actually conceal the same ordinary gun beneath my coat again",
    )


def hostile(game, viewer):
    return game.begin(
        viewer,
        str(uuid4()),
        900,
        state(game).sheets[str(viewer.user_id)].revision,
        PlayInput(
            play="engage",
            heat=0,
            target_actor=current_ref(state(game), 1),
            context="I actually go after the original Handler in this room",
            trigger_confirmed=True,
        ),
    )["action_id"]


def response(game, viewer, choice, asset=None):
    async def run():
        row = next(x for x in game.choices(viewer) if x["kind"] == "sidearm_reconsider")
        own = current(viewer.user_id, int(uuid4().int % 1000000000))
        await own.response.defer(ephemeral=True)
        await open_choice(own, game, row["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            response=(choice,),
            account="I actually withdraw this action"
            if choice == "reconsider"
            else "I actually continue despite the real gun and take its shot",
        )
        if asset:
            form.values["asset"] = (asset,)
        confirmed = current(viewer.user_id, int(uuid4().int % 1000000000))
        await form.confirm.callback(confirmed)
        assert form.completed, confirmed.edit_original_response.call_args
        # Exact replay cannot repeat shot/cancellation or gain another roll.
        answer_value = ChoiceAnswer(
            options=(choice,), fields={"asset": asset} if asset else {}, text=form.values["account"]
        )
        before = state(game).model_dump_json()
        game.respond(viewer, str(confirmed.id), row["id"], row["revision"], answer_value)
        assert state(game).model_dump_json() == before

    asyncio.run(run())


def test_actual_helpless_recovery_then_immediate_lethal_reveal_real_history(
    ledger, tmp_path, monkeypatch
):
    game, service, worker, gateway, receipt = ready(ledger, tmp_path, monkeypatch)
    original = current_ref(state(game), 2)
    first = reveal(service, game, receipt, PLAYER, "helpless")
    assert first.phase == "helpless" and is_helpless(state(game), original, receipt.handler)
    assert game.dice.calls == 0
    game.recover_helpless(
        PLAYER,
        str(uuid4()),
        state(game).sheets["2"].revision,
        "I actually take a moment alone to compose myself",
        None,
    )
    assert not is_helpless(state(game), original, receipt.handler)
    conceal(service, receipt)
    target = current_ref(state(game), 3)
    second = reveal(service, game, receipt, OTHER, "kill")
    actual = state(game)
    archive = next(x for x in actual.career_archives if x.id == second.archive)
    assert second.phase == "death" and archive.actor == target and archive.ending == "death"
    assert "3" not in actual.sheets and 3 not in actual.order and game.dice.calls == 0
    assert len(actual.held_items) == 1 and len(rules.reveals(actual)) == 2

    async def history():
        inbox = InboxService(ledger)
        item = next(
            x
            for x in inbox.items(OTHER)
            if x.task == "m3_hidden_sidearm" and x.identity == second.id
        )
        assert not item.incoming
        own = current(3, 44200)
        await own.response.defer(ephemeral=True)
        await InboxView(inbox, 3).route(own, item)
        assert "death" in str(own.edit_original_response.call_args)

    asyncio.run(history())


def test_actual_pause_withdraw_shot_continuation_and_last_girl_asset_helpless(
    ledger, tmp_path, monkeypatch
):
    game, service, worker, gateway, receipt = ready(ledger, tmp_path, monkeypatch, last_asset=True)
    before = state(game).sheets["2"]
    first = hostile(game, PLAYER)
    reveal(service, game, receipt, PLAYER, "pause", first)
    with pytest.raises(WorkflowError, match="SIDEARM_PAUSE"):
        game.roll(PLAYER, str(uuid4()), first)
    tick(worker, gateway, 1)
    response(game, PLAYER, "reconsider")
    assert game.inspect(PLAYER, first)["state"] == "complete" and game.dice.calls == 0
    assert state(game).sheets["2"] == before
    tick(worker, gateway, 5)
    conceal(service, receipt)
    second = hostile(game, PLAYER)
    reveal(service, game, receipt, PLAYER, "pause", second)
    tick(worker, gateway, 1)
    girl = next(x for x in state(game).sheets["2"].assets if x.family == "girl" and not x.damaged)
    response(game, PLAYER, "continue", girl.id)
    assert game.inspect(PLAYER, second)["state"] == "ready_to_roll" and game.dice.calls == 0
    assert next(x for x in state(game).sheets["2"].assets if x.id == girl.id).damaged
    game.roll(PLAYER, str(uuid4()), second)
    pass_tags(game)
    asset = next(x for x in state(game).sheets["2"].assets if not x.damaged)
    answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=("cover", "advance"),
        fields={"cover": asset.id, "advance": asset.id},
        text="Actual continuation after the real gunshot",
    )
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, second)["state"] == "complete" and game.dice.calls == 1
    conceal(service, receipt)
    third = hostile(game, OTHER)
    reveal(service, game, receipt, OTHER, "pause", third)
    tick(worker, gateway, 1)
    last = next(x for x in state(game).sheets["3"].assets if x.family == "girl" and not x.damaged)
    response(game, OTHER, "continue", last.id)
    actual = state(game)
    assert is_helpless(actual, current_ref(actual, 3), receipt.handler)
    assert game.inspect(OTHER, third)["state"] == "complete" and game.dice.calls == 1
    assert [x.phase for x in rules.reveals(actual)] == ["withdrawn", "shot", "shot_helpless"]
    assert not actual.career_archives
    tick(worker, gateway, 5)
