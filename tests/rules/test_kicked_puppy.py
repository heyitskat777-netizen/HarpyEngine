"""One native Class Flirt: real damaged basis, original-giver self Tag and human care answer."""

import asyncio
from uuid import uuid4

from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_mission_service import service
from test_mission_ui import current

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_receipt_text import expression
from girlframe.discord_adapter.m2_ui import open_choice, open_play
from girlframe.discord_adapter.m3_kicked_puppy import open_purchase
from girlframe.engine import m3_kicked_puppy as rules
from girlframe.engine.m2 import TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.services.m3_kicked_puppy import KickedPuppyService


def test_native_kicked_puppy_flirt_no_heat_self_gift_tag_and_owned_care_answer(
    ledger, tmp_path, monkeypatch
):
    _, game = service(ledger, girl="ALPHA", frame="WYVERN 0.4")
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    with ledger.transaction() as c:
        actual = state(game)
        actor = actual.sheets["2"]
        actor.permissions = 2
        actor.heat = 5
        for asset in actor.assets:
            if asset.family == "girl":
                asset.damaged = True
        damaged = sum(x.family == "girl" and x.damaged for x in actor.assets)
        giver = current_ref(actual, 3)
        actor.tags.append(
            TagState(
                id="actual-target-gift",
                label="PRIVATE_TARGET_GIVEN_TAG",
                giver=3,
                giver_actor=giver,
                giver_character=giver.incarnation,
                observers=(2, 3),
            )
        )
        game.event(c, 3, str(uuid4()), "synthetic.actual_prior_damage_resources_and_gift", actual)
    source = KickedPuppyService(game)

    async def prepare():
        own = current(2, 999501)
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_purchase(own, source)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(account="Actual native Kicked Puppy acquisition")
        await form.confirm.callback(current(2, 999502))
        assert form.completed
        own = current(2, 999503)
        own.channel_id = 900
        await own.response.defer(ephemeral=True)
        await open_play(own, game)
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            play=("flirt",),
            target=("3",),
            heat=("0",),
            kicked_puppy_basis=("damaged",),
            gain=("0",),
            pair_share=("0",),
            piloting=("no",),
            witnessed=("no",),
            trigger=("yes",),
            context="I actually flirt with the person who gave me this Tag",
        )
        await form.confirm.callback(current(2, 999504))
        assert form.completed and game.dice.calls == 0

    asyncio.run(prepare())
    assert state(game).sheets["2"].permissions == 0
    game.dice.faces = (3, 3)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    identity = game.choices(PLAYER)[0]["action_id"]
    raw = game.inspect(PLAYER, identity)["receipt"]
    assert raw["heat"] == 0 and raw["base_modifier"] == damaged and raw["pre_total"] == 6 + damaged
    assert "no Heat spent" in expression(raw) and state(game).sheets["2"].heat == 5
    own_tag = next(x for x in game.choices(PLAYER) if x["kind"] == "tag_window")

    async def own_tag_and_question():
        own = current(2, 999505)
        await own.response.defer(ephemeral=True)
        await open_choice(own, game, own_tag["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            options=("tag",),
            denied=("actual-target-gift",),
            number=("1",),
            text="Their actual original gift describes why I seek their care",
        )
        await form.confirm.callback(current(2, 999506))
        assert form.completed
        for viewer in (ADMIN, OTHER):
            answer(game, viewer, "tag_window", options=("pass",))
        choice = next(x for x in game.choices(PLAYER) if x["kind"] == "actor_flirt")
        own = current(2, 999507)
        await own.response.defer(ephemeral=True)
        await open_choice(own, game, choice["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(options=(rules.QUESTION,))
        await form.confirm.callback(current(2, 999508))
        assert form.completed
        choice = next(x for x in game.choices(OTHER) if x["kind"] == "target_flirt")
        target = current(3, 999509)
        await target.response.defer(ephemeral=True)
        await open_choice(target, game, choice["id"])
        form = target.edit_original_response.call_args.kwargs["view"]
        assert rules.QUESTION_TEXT in form.text()
        form.values.update(text="I want to care for you with actual shared rest and attention")
        await form.confirm.callback(current(3, 999510))
        assert form.completed

    asyncio.run(own_tag_and_question())
    final = game.inspect(PLAYER, identity)
    assert final["state"] == "complete" and final["receipt"] == raw and game.dice.calls == 1
    assert final["result"]["question"] == rules.QUESTION
    assert (
        final["result"]["target_answer"]
        == "I want to care for you with actual shared rest and attention"
    )
    assert final["modifiers"][-1]["amount"] == 1
    tag = next(x for x in state(game).sheets["2"].tags if x.id == "actual-target-gift")
    assert tag.marked and tag.giver_actor == giver
    assert any(
        x.kind == "flirt_followthrough" and x.state == "pending" for x in state(game).obligations
    )
    tick(worker, gateway, 4)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
