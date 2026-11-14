"""Original Handler non-Play use and original Newgirl's independently optional Bond."""

import asyncio
import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_cast_service import change as cast_change
from test_easy_target import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick
from test_mission_ui import current

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_easy_target import open_choice
from girlframe.engine import m3_easy_target as rules
from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, depth
from girlframe.services.inbox import InboxService
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_easy_target import EasyTargetService
from girlframe.services.m3_easy_target_handler_use import prove
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_movement import MovementService
from girlframe.services.onboarding import WorkflowError


def actual_source(ledger, tmp_path, monkeypatch):
    game, worker, gateway, service = ready(ledger, tmp_path, monkeypatch)
    handler = current_ref(state(game), ADMIN.user_id)
    casts = CastService(ActorService(MissionService(ledger)))
    cast_change(casts, ADMIN, "join", handler)
    with ledger.transaction() as c:
        before = state(game)
        before.facts.append(
            dict(
                kind="recorded_handler_recovery_position",
                actor=handler.model_dump_json(),
                cell=json.dumps([-1, 0]),
            )
        )
        game.event(c, 1, str(uuid4()), "synthetic.original_handler_prior_position", before)
    MovementService(game).move(
        ADMIN,
        str(uuid4()),
        state(game).revision,
        900,
        handler,
        (0, 0),
        account="The actual original Handler walks to the two present Girls",
    )
    before = state(game)
    game.dice.faces = (3, 4)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        before.sheets["2"].revision,
        PlayInput(
            play=rules.PLAY,
            heat=1,
            trigger_confirmed=True,
            context="PRIVATE_HANDLER_USE I muddle the actual filing system",
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "easy_target_select", options=(handler.token,), text="The actual Handler")
    answer(game, ADMIN, "easy_target_tag", text="PRIVATE_HANDLER_USE clumsy assistant")
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["faces"] == [3, 4]
    return game, worker, gateway, service, action, handler, receipt, before


@pytest.mark.parametrize("deepen", [True, False])
def test_native_handler_use_waits_for_actual_performance_then_owned_optional_bond(
    ledger, tmp_path, monkeypatch, deepen
):
    game, worker, gateway, service, action, handler, receipt, before = actual_source(
        ledger, tmp_path, monkeypatch
    )
    row = next(x for x in game.choices(ADMIN) if x["kind"] == "easy_target_react:" + handler.token)
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            str(uuid4()),
            row["id"],
            row["revision"],
            ChoiceAnswer(options=("use",), text="A forged reaction"),
        )

    async def reaction():
        opened = current(ADMIN.user_id, uuid4().int % 1000000000)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        await open_choice(opened, game, row["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(PLAYER.user_id))
        form.values.update(
            urge=("use",),
            context="PRIVATE_HANDLER_USE The Handler uses the Newgirl to hold files while sorting",
            account="PRIVATE_HANDLER_USE I choose this actual ordinary non-Play use",
        )
        await form.confirm.callback(current(ADMIN.user_id, uuid4().int % 1000000000))
        assert form.completed

    asyncio.run(reaction())
    reaction_value = next(
        x
        for x in rules.records(state(game), rules.Reaction)
        if x.session == action and x.actor == handler
    )
    assert reaction_value.performer == handler and reaction_value.play is None
    validate = next(
        x for x in game.choices(ADMIN) if x["kind"] == "easy_target_validate:" + handler.token
    )
    assert game.decision(ADMIN, validate["id"])["detail"]["handler_use"]
    answer(
        game,
        ADMIN,
        validate["kind"],
        flag=True,
        text="This ordinary filing use triggers no separate Play, injury, payment or other effect",
    )
    assert not any(x["kind"].startswith("easy_target_bond") for x in game.choices(PLAYER))
    pending = next(
        x for x in game.choices(ADMIN) if x["kind"] == "easy_target_child:" + handler.token
    )
    assert any(x.identity == pending["id"] for x in InboxService(ledger).items(ADMIN))
    saved = state(game)
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            str(uuid4()),
            pending["id"],
            pending["revision"],
            ChoiceAnswer(text="Invented Handler performance"),
        )
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN,
            str(uuid4()),
            pending["id"],
            pending["revision"],
            ChoiceAnswer(text="Invented injury", fields={"damage": "1"}),
        )
    assert state(game) == saved and game.dice.calls == 1

    async def performance():
        opened = current(ADMIN.user_id, uuid4().int % 1000000000)
        opened.channel_id = 900
        await opened.response.defer(ephemeral=True)
        reopened = GameService(ledger, dice=game.dice)
        await open_choice(opened, reopened, pending["id"])
        form = opened.edit_original_response.call_args.kwargs["view"]
        assert "original Handler" in form.text()
        form.values.update(account="PRIVATE_HANDLER_USE I have now finished sorting with her help")
        submitted = current(ADMIN.user_id, uuid4().int % 1000000000)
        await form.confirm.callback(submitted)
        assert form.completed
        committed = state(game)
        await form.confirm.callback(submitted)
        assert state(game) == committed

    asyncio.run(performance())
    actual = state(game)
    record = next(x for x in rules.records(actual, rules.HandlerUse) if x.session == action)
    assert record.actor == handler and record.controller == ADMIN.user_id
    with ledger.engine.connect() as c:
        assert prove(game, c, actual, record.id) == record
        assert (
            c.scalar(
                sa.select(sa.func.count())
                .select_from(t.m2["m2_actions"])
                .where(t.m2["m2_actions"].c.campaign_id == ledger.campaign_id)
            )
            == 1
        )
        assert (
            c.scalar(
                sa.select(sa.func.count())
                .select_from(t.m2["m2_receipts"])
                .where(t.m2["m2_receipts"].c.campaign_id == ledger.campaign_id)
            )
            == 1
        )
    assert game.inspect(PLAYER, action)["state"] != "complete"
    assert actual.sheets["2"].heat == before.sheets["2"].heat - 1
    assert "1" not in actual.sheets and actual.handler_heat == before.handler_heat
    original_depth = depth(actual, current_ref(actual, 2), handler)
    bond = next(x for x in game.choices(PLAYER) if x["kind"].startswith("easy_target_bond"))
    with pytest.raises(WorkflowError):
        game.respond(
            ADMIN,
            str(uuid4()),
            bond["id"],
            bond["revision"],
            ChoiceAnswer(flag=True, text="Invented Newgirl choice"),
        )
    answer(
        game,
        PLAYER,
        bond["kind"],
        flag=deepen,
        text="I make my own optional Bond decision after the actual use",
    )
    final = state(game)
    assert depth(final, current_ref(final, 2), handler) == min(2, original_depth + int(deepen))
    assert game.inspect(PLAYER, action)["state"] == "complete"
    assert game.roll(PLAYER, str(uuid4()), action)["receipt"] == receipt and game.dice.calls == 1
    reopened = EasyTargetService(GameService(ledger))
    assert reopened.view(ADMIN, reaction_value.id)["handler_use"][0]["account"] == record.account
    assert reopened.view(PLAYER, reaction_value.id)["handler_use"][0]["event"] == record.event
    with pytest.raises(WorkflowError):
        reopened.view(OTHER, reaction_value.id)
    tick(worker, gateway, 6)
    assert "PRIVATE_HANDLER_USE" not in json.dumps(gateway.messages)
