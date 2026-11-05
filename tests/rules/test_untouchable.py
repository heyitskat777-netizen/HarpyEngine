"""One genuine native acquisition and Engage substitution through actual native Confirm."""

import asyncio
import copy
from uuid import uuid4

from test_enforcer_requisitions import approved
from test_ledger import PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.discord_adapter.m3_untouchable import open_purchase
from girlframe.engine import m3_untouchable as rules
from girlframe.engine.m2 import PlayInput, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_untouchable import UntouchableService


def test_native_paid_untouchable_actual_engage_marks_owned_tag_preserves_assets_and_receipt(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, girl="ALPHA", frame="THE ENFORCER")
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    with ledger.transaction() as c:
        actual = state(game)
        actual.sheets["2"].permissions = 2
        actual.sheets["2"].tags.append(
            TagState(id="actual-own-tag", label="PRIVATE_OWN_UNMARKED_TAG", giver=2)
        )
        game.event(c, 1, str(uuid4()), "synthetic.actual_existing_permissions_and_tag", actual)
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
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    assert game.dice.calls == 1
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
            untouchable_tag=("actual-own-tag",),
            text="My actual owned capability creates battlefield cover",
        )
        await form.confirm.callback(current(2, 999104))
        assert form.completed

    asyncio.run(respond())
    after = state(game)
    assert after.sheets["2"].assets == original_assets
    assert next(x for x in after.sheets["2"].tags if x.id == "actual-own-tag").marked
    result = game.inspect(PLAYER, identity)
    assert (
        result["state"] == "complete"
        and result["receipt"] == original_roll
        and game.dice.calls == 1
    )
    assert result["result"]["maneuvers"] == {"cover": original_assets[0].id}
    assert result["result"]["damaged"] == []
    assert len([x for x in after.facts if x.get("kind") == "untouchable_frame_used"]) == 1
    tick(worker, gateway, 4)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
