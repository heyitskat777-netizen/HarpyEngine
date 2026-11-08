"""Actual battlefield choices retain one roll, one resource owner and real source damage."""

import json
from uuid import uuid4

import pytest
from test_battle_service import prepared
from test_harpy_actor_plays import begin as begin_harpy
from test_harpy_actor_plays import ready as harpy_ready
from test_ledger import PLAYER
from test_ledger import ledger as ledger
from test_m2_game import Gateway, answer, state, tick
from test_m2_game import pass_tags as shared_pass_tags

from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine import m3_engage as rules
from girlframe.engine.m2 import MANEUVERS, ChoiceAnswer, PlayInput
from girlframe.engine.m3_actor_state import ActorRef, ActorView, AssetView
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError


def pass_tags(game):
    shared_pass_tags(game)
    # These battlefield traces explicitly decline the fixture Mockingbird's optional Risk.
    if any(x["kind"] == "mockingbird_risk" for x in game.choices(PLAYER)):
        answer(game, PLAYER, "mockingbird_risk")


def test_last_actual_harpy_frame_asset_opens_real_defeat_then_escape_finishes_original_engage(
    ledger,
):
    import sqlalchemy as sa
    from test_harpy_defeat import choose

    from girlframe.database import tables as t
    from girlframe.engine.m3_harpy_defeat import harpy
    from girlframe.engine.m3_world_state import Asset
    from girlframe.services.m3_harpy_defeat import HarpyDefeatService

    svc, game, _, actor = harpy_ready(ledger, faces=(1, 2))
    with ledger.transaction() as c:
        canon = state(game)
        native = next(x for x in canon.world.pilots if x.id == actor.entity)
        canon.world = canon.world.model_copy(
            update={
                "pilots": (
                    native.model_copy(
                        update={
                            "assets": (
                                *native.assets,
                                Asset(
                                    id="last-real-frame",
                                    name="Actual last Frame capability",
                                    family="frame",
                                    description="Existing Frame Asset",
                                ),
                            )
                        }
                    ),
                )
            }
        )
        game.event(c, 1, "actual-harpy-frame-fixture", "synthetic.state", canon)
    identity = begin_harpy(svc, actor, play="engage", target_actor=harpy_opponent(game))
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=("cover",),
        fields={"cover": "last-real-frame"},
        denied=("last-real-frame",),
        text="Actual battlefield cover before my Frame gives out",
    )
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    with ledger.engine.connect() as c:
        work = (
            c.execute(
                sa.select(t.m3["m3_required_work"]).where(
                    t.m3["m3_required_work"].c.kind == "harpy_defeat"
                )
            )
            .mappings()
            .one()
        )
    defeat = HarpyDefeatService(ledger, game)
    game.dice.faces = (3, 4)
    child = defeat.begin(PLAYER, "actual-engage-defeat", work["id"], channel=900)["action_id"]
    defeat.roll(PLAYER, "actual-engage-defeat-roll", child)
    from test_ledger import ADMIN, OTHER

    for viewer in (PLAYER, OTHER, ADMIN):
        choose(defeat, game, viewer, "tag_window", options=("pass",))
    target = harpy_opponent(game)
    choose(
        defeat,
        game,
        PLAYER,
        "harpy_defeat_select",
        options=("message",),
        fields={"girl": target.token},
        text="My final actual message before escape",
    )
    assert harpy(state(game), actor).cell is None
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert game.dice.calls == 2
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def view(*, harpy=False):
    return ActorView(
        ref=ActorRef(kind="external_pilot", entity="harpy")
        if harpy
        else ActorRef(kind="pilot", entity="2", incarnation="original"),
        controller=2,
        label="Actual combatant",
        alive=True,
        rules="external_pilot" if harpy else "girl_frame",
        girl="harpy" if harpy else "mockingbird",
        assets=(AssetView(id="owned", name="Owned", family="frame", damaged=False, void=False),),
        source_sha256="a" * 64,
    )


@pytest.mark.parametrize("maneuver", MANEUVERS)
def test_each_printed_maneuver_uses_the_actual_asset_and_keeps_circumstances(maneuver):
    choice = ChoiceAnswer(
        options=(maneuver,),
        fields={maneuver: "owned"},
        denied=("owned",),
        text="Actual battlefield circumstances",
    )
    assert rules.select(view(), "low", choice) == ({maneuver: "owned"}, "owned")


@pytest.mark.parametrize("level,count", [("low", 1), ("mid", 2), ("high", 3)])
@pytest.mark.parametrize("harpy", [False, True])
def test_exact_distinct_maneuvers_allow_one_real_asset_for_multiple_uses(level, count, harpy):
    actor = view(harpy=harpy)
    for extra in range(1 + int(harpy)):
        maneuvers = ("pin", "advance", "drive_back", "cover")[: count + extra]
        selected = ChoiceAnswer(
            options=maneuvers,
            fields=dict.fromkeys(maneuvers, "owned"),
            denied=("owned",) if level != "mid" else (),
            text="The actual opponent is held behind the broken barrier",
        )
        result, damage = rules.select(actor, level, selected)
        assert result == selected.fields and damage == ("owned" if level != "mid" else None)
        with pytest.raises(ValueError):
            rules.select(
                actor,
                level,
                selected.model_copy(update={"fields": dict.fromkeys(maneuvers, "borrowed")}),
            )


@pytest.mark.parametrize("level", ["low", "mid", "high"])
def test_harpy_assault_extra_is_optional_and_adds_no_second_damage_rule(level):
    actor = view(harpy=True)
    assert rules.select(actor, level, ChoiceAnswer(), assault_extra=True) == ({}, None)
    chosen = ChoiceAnswer(
        options=("cover",), fields={"cover": "owned"}, text="Hide behind real cover"
    )
    assert rules.select(actor, level, chosen, assault_extra=True) == ({"cover": "owned"}, None)
    with pytest.raises(ValueError):
        rules.select(
            actor, level, chosen.model_copy(update={"denied": ("owned",)}), assault_extra=True
        )
    with pytest.raises(ValueError):
        rules.select(view(), level, chosen, assault_extra=True)


def pilot_start(game, target):
    return game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="engage",
            context="PRIVATE_BATTLEFIELD",
            trigger_confirmed=True,
            heat=0,
            target_actor=target,
        ),
    )["action_id"]


@pytest.mark.parametrize("faces,count", [((1, 2), 1), ((4, 4), 2), ((6, 6), 3)])
def test_pilot_engage_records_actual_maneuvers_damages_used_asset_and_releases_chat(
    ledger, faces, count
):
    game, worker, gateway, _, _, declaration = prepared(ledger)
    game.dice.faces = faces
    identity = pilot_start(game, declaration.target)
    tick(worker, gateway, 3)
    if game.inspect(PLAYER, identity)["receipt"] is None:
        game.roll(PLAYER, "explicit-engage-check", identity)
    pass_tags(game)
    asset = next(x for x in state(game).sheets["2"].assets if not x.damaged)
    maneuvers = ("pin", "advance", "drive_back")[:count]
    selected = next(x for x in game.choices(PLAYER) if x["kind"] == "engage_maneuvers")
    result = game.respond(
        PLAYER,
        "actual-maneuver-once",
        selected["id"],
        selected["revision"],
        ChoiceAnswer(
            options=maneuvers,
            fields=dict.fromkeys(maneuvers, asset.id),
            denied=(asset.id,) if count != 2 else (),
            text="PRIVATE_CIRCUMSTANCES: actually held behind the ruins",
        ),
    )
    assert result["state"] == "complete"
    assert GameService(ledger).inspect(PLAYER, identity)["state"] == "complete"
    canon = state(game)
    facts = [
        rules.Maneuver.model_validate_json(x["body"])
        for x in canon.facts
        if x.get("kind") == "engage_maneuver"
    ]
    assert len(facts) == count and all(
        x.opponent == declaration.target and x.source_action == identity for x in facts
    )
    assert next(x for x in canon.sheets["2"].assets if x.id == asset.id).damaged == (count != 2)
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    assert "PRIVATE_" not in str(gateway.messages) and game.dice.calls == 1


def harpy_opponent(game):
    return next(
        role.actor
        for role in state(game).scene_casts[0].roles
        if role.actor.kind == "pilot" and role.actor.entity == "3"
    )


def test_actual_harpy_extra_engage_never_damages_controllers_other_pc(ledger):
    svc, game, _, actor = harpy_ready(ledger, faces=(4, 4))
    original = state(game).sheets
    identity = begin_harpy(svc, actor, play="engage", target_actor=harpy_opponent(game))
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=("cover", "advance", "lure"),
        fields=dict.fromkeys(("cover", "advance", "lure"), "actual-harpy-asset"),
        text="Actual extra Harpy maneuver",
    )
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert state(game).sheets == original and game.dice.calls == 1


def test_engage_rejects_stale_target_before_roll_without_spending_or_reroll(ledger):
    game, worker, gateway, _, _, declaration = prepared(ledger)
    identity = pilot_start(game, declaration.target)
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["3"].assets[0].damaged = True
        game.event(c, 3, "target-changed-before-engage", "synthetic.state", canon)
    # Acquire only: the worker cannot turn a rejected declaration into a roll.
    tick(worker, gateway)
    with pytest.raises(WorkflowError, match="STALE_ENGAGE"):
        game.roll(PLAYER, "stale-engage-roll", identity)
    assert game.dice.calls == 0


def test_pilot_last_frame_engage_requires_actual_defeat_and_escape_before_parent_releases(ledger):
    game, worker, gateway, _, _, declaration = prepared(ledger)
    with ledger.transaction() as c:
        canon = state(game)
        frames = [x for x in canon.sheets["2"].assets if x.family == "frame"]
        for asset in frames[1:]:
            asset.damaged = True
        game.event(c, 1, "prior-frame-damage", "synthetic.state", canon)
    game.dice.faces = (1, 2)
    identity = pilot_start(game, declaration.target)
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "engage_maneuvers",
        options=("advance",),
        fields={"advance": frames[0].id},
        denied=(frames[0].id,),
        text="My last Frame capability closes the distance before failing",
    )
    assert game.inspect(PLAYER, identity)["state"] != "complete"
    assert any(x["kind"] == "battle_defeat" for x in game.choices(PLAYER))
    work = json.loads(
        next(x for x in game.choices(PLAYER) if x["kind"] == "battle_defeat")["body_json"]
    )["work_id"]
    game.dice.faces = (3, 3)
    child = game.begin(
        PLAYER,
        "actual-engage-pilot-defeat",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="defeat",
            context="Actual exhaustion during Engage",
            trigger_confirmed=True,
            heat=0,
            parent=identity,
            source_work=work,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "defeat_select",
        options=("escape_cockpit_choose_location",),
        text="Actual escape from the damaged cockpit",
    )
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 2
    tick(worker, gateway, 5)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


def test_native_harpy_engage_target_and_owned_asset_controls_execute_actual_choice(ledger):
    import asyncio

    from test_mission_ui import current

    from girlframe.discord_adapter.m2_ui import open_choice
    from girlframe.discord_adapter.m3_actor_plays import open_actor_play

    _, game, _, actor = harpy_ready(ledger, faces=(4, 4))

    async def start():
        caller = current(2, 301001)
        caller.channel_id = 900
        await caller.response.defer(ephemeral=True)
        await open_actor_play(caller, game, actor)
        picker = caller.edit_original_response.call_args.kwargs["view"]
        chosen = current(2, 301002)
        await chosen.response.defer(ephemeral=True)
        await picker.open_item(chosen, "engage")
        form = chosen.edit_original_response.call_args.kwargs["view"]
        form.values.update(
            context="Native actual battlefield",
            opponent=(harpy_opponent(game).token,),
            heat=("0",),
            gain=("1",),
            confirm=("yes",),
        )
        await form.confirm.callback(current(2, 301003))
        assert form.completed

    asyncio.run(start())
    tick(GameWorker(game), Gateway(), 3)
    pass_tags(game)
    selected = next(x for x in game.choices(PLAYER) if x["kind"] == "engage_maneuvers")

    async def choose():
        caller = current(2, 301004)
        await caller.response.defer(ephemeral=True)
        await open_choice(caller, game, selected["id"])
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3))
        form.values.update(
            maneuvers=("cover", "advance", "lure"),
            asset_cover=("actual-harpy-asset",),
            asset_advance=("actual-harpy-asset",),
            asset_lure=("actual-harpy-asset",),
            text="Actual native Harpy extra",
        )
        await form.confirm.callback(current(2, 301005))
        assert form.completed

    asyncio.run(choose())
    assert game.inspect(PLAYER, selected["action_id"])["state"] == "complete"
