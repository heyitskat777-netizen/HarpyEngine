"""Genuine Engage damage and Flirt gift feed native Kicked Puppy without resolving debt."""

import asyncio
from uuid import uuid4

from test_enforcer_requisitions import approved
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, pass_tags, state, tick
from test_mission_service import service
from test_mission_ui import current
from test_world import initial

from girlframe.delivery.m2_worker import GameWorker
from girlframe.discord_adapter.m2_receipt_text import expression
from girlframe.discord_adapter.m2_ui import open_choice, open_play
from girlframe.discord_adapter.m3_kicked_puppy import open_purchase
from girlframe.engine import m3_kicked_puppy as rules
from girlframe.engine.m2 import PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_physical_state import InitialPlacement
from girlframe.services.m3_access import Access
from girlframe.services.m3_kicked_puppy import KickedPuppyService
from girlframe.services.m3_physical import PhysicalService
from girlframe.services.m3_world import WorldService


def test_actual_damage_and_owed_tag_feed_kicked_puppy_owned_care_flirt(
    ledger, tmp_path, monkeypatch
):
    missions, game = service(ledger, girl="ALPHA", frame="WYVERN 0.4")
    approved(ledger, game, tmp_path, monkeypatch, extra=(rules.RULE,))
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    missions.access = Access(ledger)
    world = initial()
    WorldService(missions).initialize(
        ADMIN, str(uuid4()), state(game).revision, world.board, world.locations, world.gorgons[0]
    )
    physical = PhysicalService(ledger)
    for viewer in (PLAYER, OTHER):
        data = physical.preview(viewer)
        proposed = physical.propose(
            viewer,
            str(uuid4()),
            data["game_revision"],
            InitialPlacement(
                actor=ActorRef.model_validate(data["actor"]),
                frame_instance=data["frame_instance"],
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                mode="piloting",
                account="Actual original cockpit and body position",
                facts_confirmed=True,
            ),
        )
        physical.decide(
            ADMIN,
            str(uuid4()),
            proposed["id"],
            1,
            "accept",
            "Confirm these original actual physical facts",
        )
    with ledger.transaction() as c:
        actual = state(game)
        actor = actual.sheets["2"]
        actor.permissions = 2
        actor.heat = 4
        game.event(c, 1, str(uuid4()), "synthetic.prior_kicked_puppy_resources", actual)
    worker, gateway = GameWorker(game), Gateway()
    girl_asset = next(
        x for x in state(game).sheets["2"].assets if x.family == "girl" and not x.damaged
    )
    game.dice.faces = (1, 2)
    damage_action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="engage",
            piloting=True,
            target_actor=current_ref(state(game), 3),
            heat=1,
            context="Actual cover costs this Girl Asset",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=("cover",),
        fields={"cover": girl_asset.id},
        denied=(girl_asset.id,),
        text="I use this actual Girl Asset for cover",
    )
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, damage_action)["state"] == "complete"
    assert next(x for x in state(game).sheets["2"].assets if x.id == girl_asset.id).damaged
    game.dice.faces = (6, 6)
    gift_action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="flirt",
            piloting=True,
            target=3,
            heat=0,
            context="I actually Flirt with this original person",
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
    answer(game, OTHER, "target_flirt", text="Her own original answer")
    answer(game, OTHER, "flirt_owe_tag", text="Her actual source-backed gift")
    tick(worker, gateway, 5)
    assert game.inspect(PLAYER, gift_action)["state"] == "complete"
    actual = state(game)
    gifted = next(x for x in actual.sheets["2"].tags if x.label == "Her actual source-backed gift")
    giver = current_ref(actual, 3)
    assert gifted.giver_actor == giver and not gifted.marked
    debt = next(
        x
        for x in actual.obligations
        if x.kind == "cannot_refuse_until_tag_resolved" and x.details.get("tag") == gifted.id
    )
    damaged = sum(x.family == "girl" and x.damaged for x in actual.sheets["2"].assets)
    assert damaged == 1
    prior_rolls = game.dice.calls
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
            piloting=("yes",),
            witnessed=("no",),
            trigger=("yes",),
            context="I actually flirt with the person who gave me this Tag",
        )
        await form.confirm.callback(current(2, 999504))
        assert form.completed and game.dice.calls == prior_rolls

    asyncio.run(prepare())
    assert state(game).sheets["2"].permissions == 0
    game.dice.faces = (3, 3)
    tick(worker, gateway, 3)
    identity = game.choices(PLAYER)[0]["action_id"]
    raw = game.inspect(PLAYER, identity)["receipt"]
    assert raw["heat"] == 0 and raw["base_modifier"] == damaged and raw["pre_total"] == 6 + damaged
    assert "no Heat spent" in expression(raw) and state(game).sheets["2"].heat == 3
    own_tag = next(x for x in game.choices(PLAYER) if x["kind"] == "tag_window")

    async def own_tag_and_question():
        own = current(2, 999505)
        await own.response.defer(ephemeral=True)
        await open_choice(own, game, own_tag["id"])
        form = own.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            options=("tag",),
            denied=(gifted.id,),
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
    assert (
        final["state"] == "complete"
        and final["receipt"] == raw
        and game.dice.calls == prior_rolls + 1
    )
    assert final["result"]["question"] == rules.QUESTION
    assert (
        final["result"]["target_answer"]
        == "I want to care for you with actual shared rest and attention"
    )
    assert final["modifiers"][-1]["amount"] == 1
    tag = next(x for x in state(game).sheets["2"].tags if x.id == gifted.id)
    assert tag.marked and tag.giver_actor == giver
    assert next(x for x in state(game).obligations if x.id == debt.id) == debt
    assert debt.state == "pending"
    assert any(
        x.kind == "flirt_followthrough" and x.state == "pending" for x in state(game).obligations
    )
    tick(worker, gateway, 4)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
