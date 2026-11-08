"""Call classification is a real Dive option with one receipt and real Void followups."""

import asyncio

from test_dive import choose, rolled
from test_ledger import PLAYER
from test_ledger import ledger as ledger
from test_m2_game import state
from test_mission_ui import current

from girlframe.discord_adapter.m2_ui import open_choice
from girlframe.services import m3_mockingbird_call as call


def test_actual_native_dive_classification_moves_both_directions_once(ledger, monkeypatch):
    monkeypatch.setattr(call, "enabled", lambda state, actor: True)
    game, _, _, identity = rolled(ledger)
    original = state(game).sheets["2"]
    girl = next(x for x in original.assets if x.family == "girl")
    frame = next(x for x in original.assets if x.family == "frame")
    receipt = game.inspect(PLAYER, identity)["receipt"]
    choose(game, PLAYER, call.CLASSIFY)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "dive_effect")

    async def run():
        owner = current(2, 880201)
        await owner.response.defer(ephemeral=True)
        await open_choice(owner, game, row["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        form.values.update(moves=(girl.id, frame.id))
        await form.confirm.callback(current(2, 880202))
        assert form.completed

    asyncio.run(run())
    after = state(game).sheets["2"]
    assert next(x for x in after.assets if x.id == girl.id).family == "frame"
    assert next(x for x in after.assets if x.id == frame.id).family == "girl"
    assert [x.id for x in after.assets] == [x.id for x in original.assets]
    assert [(x.void, x.damaged, x.description) for x in after.assets] == [
        (x.void, x.damaged, x.description) for x in original.assets
    ]
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert game.inspect(PLAYER, identity)["receipt"] == receipt and game.dice.calls == 1


def test_classification_new_all_void_frame_uses_actual_threshold_and_real_keep(ledger, monkeypatch):
    import sqlalchemy as sa
    from test_beneath_service import ready
    from test_m2_game import answer, pass_tags, tick
    from test_void_keep import keep

    from girlframe.database import tables as t
    from girlframe.engine import m3_physical as physical
    from girlframe.engine.m2 import PlayInput
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_physical_state import InitialPlacement
    from girlframe.engine.m3_world_state import Board, World
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_void import VoidService

    monkeypatch.setattr(call, "enabled", lambda state, actor: True)
    game, worker, gateway = ready(ledger, (4, 5))
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = World(board=Board(minimum=(-2, -2), maximum=(2, 2)), locations=())
        actor = ActorRef(kind="pilot", entity="2", incarnation=canon.sheets["2"].character_id)
        view = resolve(canon, actor, profiles(c, ledger.campaign_id), require_current_profile=False)
        canon = physical.initial(
            canon,
            profiles(c, ledger.campaign_id),
            InitialPlacement(
                actor=actor,
                frame_instance=view.frame_instance,
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                mode="inside_frame",
                account="Actual existing original cockpit position",
                facts_confirmed=True,
            ),
            "call-body",
            "call-owner-facts",
            "call-gm-review",
        )
        frames = [x for x in canon.sheets["2"].assets if x.family == "frame"]
        frames[0].void = True
        moved = frames[-1].id
        game.event(c, 1, "actual-call-before", "synthetic.state", canon)
    identity = game.begin(
        PLAYER,
        "actual-classification-threshold",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="dive_deep", context="Actual owned Call connection", heat=0, trigger_confirmed=True
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    choose(game, PLAYER, call.CLASSIFY)
    answer(game, PLAYER, "dive_effect", options=(moved,))
    with ledger.engine.connect() as c:
        row = (
            c.execute(
                sa.select(t.m3["m3_required_work"]).where(
                    t.m3["m3_required_work"].c.kind == "void_threshold"
                )
            )
            .mappings()
            .one()
        )
    assert VoidService(ledger).get(PLAYER, row["id"])["stage"] == "resist_pending"
    child = keep(game, worker, gateway, identity, row["id"])
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, identity)["state"] == "complete" and game.dice.calls == 2


def test_risk_immunity_preserves_outside_girl_while_actual_fully_void_frame_becomes_gorgon(ledger):
    from test_dive import threshold_source
    from test_ledger import ADMIN
    from test_void import gorgon
    from test_void_service import respond

    from girlframe.services.m3_void import VoidService

    game, _, _, identity, work = threshold_source(
        ledger, girl="MOCKINGBIRD", placement="outside_frame", girl_cell=(1, 1), frame_cell=(0, 0)
    )
    service = VoidService(ledger)
    assert service.get(PLAYER, work)["stage"] == "abandoned"
    before = state(game)
    original = before.placements[0]
    grown = gorgon(before, "proposed-frame-source")
    respond(
        service,
        work,
        "abandoned",
        dict(
            gorgon=grown.model_dump(mode="json"),
            account="Actual already-unoccupied original Frame grows into this Gorgon",
        ),
        viewer=ADMIN,
    )
    after = state(game)
    body = next(x for x in after.placements if x.actor == original.actor)
    assert body.girl_cell == original.girl_cell == (1, 1)
    assert body.frame_cell == original.frame_cell == (0, 0)
    assert "2" in after.sheets and not after.harpy_states
    assert any(x.id == grown.id for x in after.world.gorgons)
    assert after.sheets["2"].frame_scrapped
