"""One actual counterpart source; AM has no duplicate Sex roll or resource charge."""

import asyncio
from uuid import uuid4

import pytest
from test_alpha_brutalize import ready
from test_enforcer_requisitions import approved
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import pass_tags, state, tick
from test_mission_ui import current

from girlframe.discord_adapter.m3_am_sex import open_am_sex
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_alpha_sex import SexService as AlphaService
from girlframe.services.m3_am_sex import RULE, SexService
from girlframe.services.onboarding import WorkflowError


def test_actual_confirmed_counterpart_roll_private_native_am_readback_without_extra_roll(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway = ready(ledger, tmp_path, monkeypatch, (4, 5))
    approved(ledger, game, tmp_path, monkeypatch, extra=(RULE, "girl.alpha.sex-play"))
    with ledger.transaction() as c:
        actual = state(game)
        # Synthetic prior AM subtype only; consent and the real Play use production services.
        actual.sheets["3"].girl = "AM"
        game.event(c, 1, str(uuid4()), "synthetic.actual_counterpart_AM", actual)
    controls = SexService(game)
    assert controls.menu(OTHER, 900)["sources"] == [] and game.dice.calls == 0
    alpha = AlphaService(game)
    identity = alpha.invite(
        PLAYER,
        str(uuid4()),
        900,
        current_ref(state(game), 3),
        state(game).revision,
        "The Alpha's own voluntary actual source proposal",
    )["id"]
    alpha.respond(
        OTHER,
        str(uuid4()),
        identity,
        state(game).revision,
        True,
        "The AM's own source confirmation; no circuit access",
    )
    heat = state(game).sheets["3"].heat
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="alpha_sex",
            source_work=identity,
            target_actor=current_ref(state(game), 3),
            heat=0,
            context="Actual confirmed counterpart source",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    saved = controls.menu(OTHER, 900)
    assert saved["no_additional_roll"] and saved["sources"][0]["id"] == action
    assert saved["sources"][0]["receipt"] and game.dice.calls == 1
    assert state(game).sheets["3"].heat == heat
    with pytest.raises(WorkflowError):
        controls.menu(PLAYER, 900)

    async def native():
        view = current(3, 85201)
        view.channel_id = 900
        await view.response.defer(ephemeral=True)
        await open_am_sex(view, controls)
        form = view.edit_original_response.call_args.kwargs["view"]
        form.values["source"] = (action,)
        selected = current(3, 85202)
        selected.channel_id = 900
        await form.confirm.callback(selected)
        assert form.completed
        message = selected.edit_original_response.call_args.kwargs["content"]
        assert "AM makes no additional Sex roll" in message and "receipt" in message
        assert "voluntary actual source proposal" not in message
        mentions = selected.edit_original_response.call_args.kwargs["allowed_mentions"]
        assert not mentions.everyone and not mentions.users and not mentions.roles
        assert not mentions.replied_user

    asyncio.run(native())
    assert game.dice.calls == 1 and state(game).sheets["3"].heat == heat
