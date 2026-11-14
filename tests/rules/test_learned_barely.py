"""An earned Casualty lesson repairs a real asset without granting ideal body parts."""

import asyncio
from uuid import uuid4

import pytest
from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state, tick
from test_mission_ui import current
from test_vatgrown_plays import native_choice, ready, sex

from girlframe.discord_adapter.m3_casualty import open_casualty
from girlframe.engine import m3_casualty as rules
from girlframe.engine import m3_vatgrown_plays as vat
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_girl_runtime_state import has_rule
from girlframe.engine.m3_handler_play_state import Effect
from girlframe.services.m3_casualty import CasualtyService
from girlframe.services.m3_handler_plays import HandlerPlayService
from girlframe.services.m3_learned_plays import available
from girlframe.services.onboarding import WorkflowError


def test_earned_barely_native_repair_private_receipt_and_once_use(ledger, tmp_path, monkeypatch):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch, teacher="CASUALTY")
    approved(
        ledger,
        game,
        tmp_path,
        monkeypatch,
        extra=(vat.EXPERIMENT, vat.INVESTMENT, vat.SEX, vat.BRUTALIZE, rules.BARELY),
    )
    session, action = sex(game, worker, gateway, controls, (5, 5))
    original = state(game)
    native_choice(
        game,
        OTHER,
        "vat_sex_learn",
        identities=(original.sheets["3"].identities[1].id,),
        replacements=(original.sheets["2"].identities[0].id,),
        play=(rules.BARELY,),
        account="The actual Casualty teaches her own Barely a Girl once",
    )
    assert game.inspect(PLAYER, action)["state"] == "complete"
    learned = vat.records(state(game), vat.LearnedPlay)[-1]
    assert learned.rule_id == rules.BARELY
    controls.send_away(
        OTHER,
        str(uuid4()),
        session,
        state(game).revision,
        "The actual counterpart releases the learner",
    )
    tick(worker, gateway, 3)
    # Real Handler damage supplies the actual repair target, not an inventory edit.
    handler = HandlerPlayService(ledger)
    original = state(game)
    actor = current_ref(original, PLAYER.user_id)
    source = handler.start(ADMIN, str(uuid4()), original.revision, (actor,))["id"]
    asset = next(x for x in original.sheets["2"].assets if x.family == "girl")
    handler.submit(
        ADMIN,
        str(uuid4()),
        source,
        state(game).revision,
        "mess",
        Effect(
            kind="damage",
            account="Actual damage before the learned repair",
            target=actor,
            asset=asset.id,
        ),
    )
    service = CasualtyService(game)
    before = state(game)
    erased = before.sheets["2"].identities[0]
    assert not has_rule(before.sheets["2"], rules.BARELY, "CASUALTY")
    assert rules.body(before, actor) is None
    assert service.menu(PLAYER, 900)["barely_lessons"][0]["id"] == learned.id
    with pytest.raises(WorkflowError):
        service.barely(
            PLAYER, str(uuid4()), before.revision, erased.id, asset.id, "No grant selected"
        )
    assert state(game) == before
    key = uuid4().int % 1000000000
    account = "PRIVATE_LEARNED_BARELY: my actual Identity sacrifice"

    async def repair():
        opened = current(PLAYER.user_id, uuid4().int % 1000000000)
        await opened.response.defer(ephemeral=True)
        await open_casualty(opened, service)
        menu = opened.edit_original_response.call_args.kwargs["view"]
        options = dict(menu.fields[0].options)
        assert "barely" in options and "body" not in options and "sex" not in options
        menu.values["source"] = ("barely",)
        selected = current(PLAYER.user_id, uuid4().int % 1000000000)
        await menu.confirm.callback(selected)
        form = selected.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            lesson=(learned.id,), identity=(erased.id,), asset=(asset.id,), account=account
        )
        response = current(PLAYER.user_id, key)
        await form.confirm.callback(response)
        assert form.completed, response.edit_original_response.call_args_list

    asyncio.run(repair())
    after = state(game)
    record = rules.records(after, rules.Barely)[-1]
    assert record.lesson == learned.id and record.identity == erased
    assert all(x.id != erased.id for x in after.sheets["2"].identities)
    assert not next(x for x in after.sheets["2"].assets if x.id == asset.id).damaged
    use = next(x for x in after.sheets["2"].girl_runtime.learned_plays if x.id == learned.id)
    assert use.used_event == record.event and use.claimed_source == record.id
    assert use.rolled_event is None and use.claimed_action is None
    assert after.sheets["2"].heat == before.sheets["2"].heat
    assert after.sheets["3"] == before.sheets["3"] and rules.body(after, actor) is None
    assert (
        service.barely(
            PLAYER, str(key), before.revision, erased.id, asset.id, account, lesson=learned.id
        )["id"]
        == record.id
    )
    assert state(game) == after
    with ledger.engine.connect() as c:
        assert available(game, c, after, actor, rules.BARELY) is None
    assert not service.menu(PLAYER, 900)["barely_available"]
    assert service.view(PLAYER, record.id)["record"]["account"] == account
    with pytest.raises(WorkflowError):
        service.view(OTHER, record.id)
