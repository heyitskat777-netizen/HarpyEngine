"""Owned tear choices share write-path loss guards, without implying new continuations."""

import asyncio

from test_ankou_feedback import last_source, ready
from test_ledger import PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.m3_ankou_feedback import open_choice
from girlframe.engine import m3_ankou_feedback as rules
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actors import resolve
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_ankou_feedback import _tear_blocker


def test_actual_tear_selector_submits_eligible_loss_and_preserves_loss_boundary(
    ledger, tmp_path, monkeypatch
):
    _, game, worker, gateway, _, _ = ready(ledger, tmp_path, monkeypatch)
    _, source = last_source(game, worker, gateway)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "ankou_feedback_choice")
    data = game.decision(PLAYER, row["id"])["ankou_feedback"]
    eligible = tuple(
        (x["id"], x["name"])
        for x in data["assets"]
        if not x["void"] and x["tear_accessible"] and x["tear_supported"]
    )
    assert eligible
    asset = next(x for x in data["assets"] if x["family"] == "frame" and x["tear_supported"])
    before = state(game)
    target = current_ref(before, 3)

    async def submit():
        opened = current(2, 98621)
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, game, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert next(x for x in form.fields if x.key == "asset").options == eligible
        # Bond rewrite choices remain independent of tear-loss restrictions.
        assert next(x for x in form.fields if x.key == "replace").options == tuple(
            (x["id"], x["name"]) for x in data["assets"] if x["bond_replaceable"]
        )
        form.values.update(
            effect=("tear",),
            target=(target.token,),
            asset=(asset["id"],),
            name="",
            replace=(),
            account="I tear this actual accessible Frame Asset",
        )
        response = current(2, 98622)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(submit())
    after = state(game)
    assert not any(x.id == asset["id"] for x in after.sheets["2"].assets)
    assert rules.get(after, source.id).phase == "child"
    assert rules.get(after, source.id).lost_asset == asset["id"]

    # Explicitly synthetic, in-memory boundary check, not a forged saved transition.
    # Keeping just this Frame Asset must not newly admit unsupported last-Asset loss.
    check = before.model_copy(deep=True)
    sheet = check.sheets["2"]
    only = next(x for x in sheet.assets if x.id == asset["id"])
    sheet.assets = [x for x in sheet.assets if x.family != "frame"] + [only]
    with ledger.engine.connect() as c:
        view = resolve(check, source.actor, profiles(c, ledger.campaign_id))
    assert _tear_blocker(check, source, sheet, only, view) == (
        "SOURCE_ANKOU_LOSS_REQUIRED: attach actual last-Asset/Void continuations first"
    )
