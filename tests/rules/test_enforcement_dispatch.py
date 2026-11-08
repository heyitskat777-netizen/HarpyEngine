"""Shared dispatcher source boundaries and complete real Initiative continuations."""

from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import PLAYER
from test_ledger import ledger as ledger
from test_m2_game import setup_game, state

from girlframe.database import tables as t
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.onboarding import WorkflowError


def test_typed_initiative_target_never_becomes_an_unrelated_play_authority_or_spends_rng(ledger):
    game, _, _, _ = setup_game(ledger)
    before = state(game).model_dump_json()
    with pytest.raises(WorkflowError, match="does not take a fictional actor target"):
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="keep_your_head",
                target_actor=ActorRef(kind="handler", entity="1"),
                context="An unrelated typed target",
                trigger_confirmed=True,
                heat=0,
            ),
        )
    assert game.dice.calls == 0 and state(game).model_dump_json() == before


def test_generic_native_actual_target_and_each_owned_low_response_preserve_one_roll(
    ledger,
    tmp_path,
    monkeypatch,
):
    import asyncio

    from test_enforcement_initiative import ready
    from test_ledger import ADMIN, OTHER
    from test_m2_game import answer, pass_tags, tick
    from test_mission_ui import current

    from girlframe.discord_adapter.m2_ui import open_choice, open_play

    game, worker, gateway = ready(ledger, tmp_path, monkeypatch, (1, 1))

    async def begin():
        caller = current(2, 99701)
        caller.channel_id = 900
        await caller.response.defer(ephemeral=True)
        await open_play(caller, game)
        form = caller.edit_original_response.call_args.kwargs["view"]
        fields = {x.key: x for x in form.fields}
        assert "enforcement_initiative" in dict(fields["play"].options)
        targets = dict(fields["enforcer_target"].options)
        assert len(targets) == 1
        assert not await form.interaction_check(current(3))
        form.values.update(
            play=("enforcement_initiative",),
            enforcer_target=(next(iter(targets)),),
            gain=("0",),
            pair_share=("0",),
            heat=("0",),
            piloting=("no",),
            witnessed=("no",),
            context="Actual native take hold; unknown cells stay unknown",
            trigger=("yes",),
        )
        await form.confirm.callback(current(2, 99702))
        assert form.completed

    asyncio.run(begin())
    with ledger.engine.connect() as c:
        actions = t.m2["m2_actions"]
        identity = c.scalar(
            sa.select(actions.c.id).where(
                actions.c.campaign_id == ledger.campaign_id,
                sa.func.json_extract(actions.c.body_json, "$.play") == "enforcement_initiative",
            )
        )
        assert identity is not None
        meta = game.action(c, identity)["data"]
    assert meta["prepared"]["target_actor"]["entity"] == "3" and game.dice.calls == 0
    tick(worker, gateway, 3)
    pass_tags(game)

    async def choose():
        own = next(x for x in game.choices(PLAYER) if x["kind"] == "enforcer_select")
        caller = current(2, 99703)
        await caller.response.defer(ephemeral=True)
        await open_choice(caller, game, own["id"])
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert form.fields[0].minimum == form.fields[0].maximum == 2
        form.values["options"] = ("tag", "disapproval")
        await form.confirm.callback(current(2, 99704))
        assert form.completed
        target = next(x for x in game.choices(OTHER) if x["kind"] == "enforcer_tag")
        responder = current(3, 99705)
        await responder.response.defer(ephemeral=True)
        await open_choice(responder, game, target["id"])
        reply = responder.edit_original_response.call_args.kwargs["view"]
        assert not await reply.interaction_check(current(2))
        reply.values["account"] = "Actual target's chosen Tag"
        await reply.confirm.callback(current(3, 99706))
        assert reply.completed

    asyncio.run(choose())
    answer(game, ADMIN, "enforcer_disapproval", text="Actual source Handler disapproval")
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 1
    assert state(game).sheets["2"].tags[-1].giver_actor.entity == "3"


def test_actual_mid_grip_routes_private_native_release_without_moving_or_healing(
    ledger,
    tmp_path,
    monkeypatch,
):
    import asyncio

    from test_enforcement_initiative import rolled
    from test_ledger import OTHER
    from test_mission_ui import current

    from girlframe.discord_adapter.inbox import InboxView
    from girlframe.engine.m3_actor_bonds import current_ref, is_helpless
    from girlframe.services.inbox import InboxService

    game, _, _, _ = rolled(ledger, tmp_path, monkeypatch, (4, 5))
    before = state(game)
    item = next(x for x in InboxService(ledger).items(PLAYER) if x.task == "m3_enforcer_grasp")
    assert item.incoming and not any(
        x.identity == item.identity for x in InboxService(ledger).items(OTHER)
    )

    async def release():
        caller = current(2, 99711)
        await caller.response.defer(ephemeral=True)
        await InboxView(InboxService(ledger), 2).route(caller, item)
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3))
        form.values["account"] = "I voluntarily release my actual grip"
        await form.confirm.callback(current(2, 99712))
        assert form.completed

    asyncio.run(release())
    after = state(game)
    assert not after.enforcer_grasps[-1].held and after.placements == before.placements
    assert is_helpless(after, current_ref(after, 3), current_ref(after, 2))
    assert game.dice.calls == 1
