"""Actual Flirt owed-Tag marks in native Untouchable damage substitution, not rejection."""

import asyncio
import copy
from uuid import uuid4

from test_enforcer_requisitions import approved
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_untouchable import open_purchase
from girlframe.engine import m3_untouchable as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_untouchable import UntouchableService


def test_actual_flirt_owed_tag_marks_for_untouchable_without_resolving_debt(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, girl="ALPHA", frame="THE ENFORCER")
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].permissions = 2
        game.event(c, 1, str(uuid4()), "synthetic.prior_untouchable_permissions", actual)
    purchase = UntouchableService(game)

    async def buy():
        own = current(2, 999101)
        await own.response.defer(ephemeral=True)
        await open_purchase(own, purchase)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(account="Actual native Autocrat Untouchable acquisition")
        await form.confirm.callback(current(2, 999102))
        assert form.completed

    asyncio.run(buy())
    acquired = state(game)
    actor = current_ref(acquired, 2)
    receipt = rules.held(acquired, actor)
    assert receipt and receipt.price == 2 and acquired.sheets["2"].permissions == 0
    worker, gateway = GameWorker(game), Gateway()
    game.dice.faces = (6, 6)
    flirt = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        acquired.sheets["2"].revision,
        PlayInput(
            play="flirt",
            target=3,
            heat=0,
            context="Actual Flirt with original companion",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "actor_flirt",
        options=("name",),
        fields={"extra": "owe"},
        text="I go too far and genuinely owe her",
    )
    answer(game, OTHER, "target_flirt", text="Her own actual desired name")
    answer(game, OTHER, "flirt_owe_tag", text="Actual source-backed debt Tag")
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, flirt)["state"] == "complete"
    acquired = state(game)
    tag = next(x for x in acquired.sheets["2"].tags if x.label == "Actual source-backed debt Tag")
    assert not tag.marked and tag.giver_actor == current_ref(acquired, 3)
    debt = next(
        x
        for x in acquired.obligations
        if x.kind == "cannot_refuse_until_tag_resolved" and x.details.get("tag") == tag.id
    )
    assert debt.state == "pending"
    rolls_before = game.dice.calls
    original_assets = copy.deepcopy(acquired.sheets["2"].assets)
    game.dice.faces = (1, 2)
    identity = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        acquired.sheets["2"].revision,
        PlayInput(
            play="engage",
            heat=0,
            target_actor=current_ref(acquired, 3),
            context="Actual battlefield cover maneuver",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    assert game.dice.calls == rolls_before + 1
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "engage_maneuvers")
    original_roll = copy.deepcopy(game.inspect(PLAYER, identity)["receipt"])

    async def respond():
        own = current(2, 999103)
        await own.response.defer(ephemeral=True)
        await open_choice(own, game, row["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            maneuvers=("cover",),
            asset_cover=(original_assets[0].id,),
            untouchable_tag=(tag.id,),
            text="My actual owned capability creates battlefield cover",
        )
        await form.confirm.callback(current(2, 999104))
        assert form.completed

    asyncio.run(respond())
    after = state(game)
    assert after.sheets["2"].assets == original_assets
    assert next(x for x in after.sheets["2"].tags if x.id == tag.id).marked
    result = game.inspect(PLAYER, identity)
    assert (
        result["state"] == "complete"
        and result["receipt"] == original_roll
        and game.dice.calls == rolls_before + 1
    )
    assert result["result"]["maneuvers"] == {"cover": original_assets[0].id}
    assert result["result"]["damaged"] == []
    assert next(x for x in after.obligations if x.id == debt.id) == debt
    assert next(x for x in after.sheets["2"].tags if x.id == tag.id).giver_actor == tag.giver_actor
    assert rules.held(after, actor) == receipt
    assert after.sheets["2"].permissions == acquired.sheets["2"].permissions
    assert len([x for x in after.facts if x.get("kind") == "untouchable_frame_used"]) == 1
    tick(worker, gateway, 4)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
