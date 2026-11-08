"""One real dice receipt, real owned Void payment and unchanged original source effects."""

import pytest
from test_beneath_service import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger
from test_m2_game import answer, pass_tags, state, tick

from girlframe.engine.m2 import ChoiceAnswer, PlayInput
from girlframe.services import m3_mockingbird as service
from girlframe.services.onboarding import WorkflowError


def begin(store, monkeypatch, *, faces=(1, 2)):
    # Synthetic release of this exact in-development rule; production registry stays unavailable.
    monkeypatch.setattr(service, "released", lambda game: True)
    game, worker, gateway = ready(store, faces)
    identity = game.begin(
        PLAYER,
        "owned-risk-keep",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head", context="Actual incoming threat", trigger_confirmed=True, heat=0
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    return game, worker, gateway, identity


def test_actual_shift_preserves_raw_receipt_one_rng_and_original_keep_choices(ledger, monkeypatch):
    game, worker, gateway, identity = begin(ledger, monkeypatch)
    before = game.inspect(PLAYER, identity)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "mockingbird_risk")
    asset = next(x for x in state(game).sheets["2"].assets if not x.void)
    with pytest.raises(WorkflowError):
        game.respond(
            OTHER,
            "wrong-role",
            row["id"],
            row["revision"],
            ChoiceAnswer(number=9, fields={"asset": asset.id}, text="Actual alteration"),
        )
    result = answer(
        game,
        PLAYER,
        "mockingbird_risk",
        number=9,
        fields={"asset": asset.id},
        text="Actual Risk alteration",
    )
    assert result["state"] == "awaiting_choices"
    after = game.inspect(PLAYER, identity)
    assert after["receipt"] == before["receipt"]
    assert game.dice.calls == 1
    assert next(x for x in state(game).sheets["2"].assets if x.id == asset.id).void
    answer(game, PLAYER, "actor_keep", options=("in_control", "vicious"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual defense is enough")
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    tick(worker, gateway, 6)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"
    with pytest.raises(WorkflowError):
        game.respond(
            PLAYER,
            "stale-cost",
            row["id"],
            row["revision"],
            ChoiceAnswer(number=10, fields={"asset": asset.id}, text="Cannot pay twice"),
        )


def test_decline_and_pause_never_pay_or_reroll(ledger, monkeypatch):
    game, _, _, identity = begin(ledger, monkeypatch)
    before = state(game).sheets["2"].model_dump_json()
    answer(game, PLAYER, "mockingbird_risk")
    assert state(game).sheets["2"].model_dump_json() == before
    assert game.dice.calls == 1
    assert next(x for x in game.choices(PLAYER) if x["kind"] == "actor_keep")


def test_last_frame_payment_waits_until_primary_keep_then_actual_source_resistance(
    ledger, monkeypatch
):
    import sqlalchemy as sa

    from girlframe.database import tables as t
    from girlframe.engine import m3_physical as physical
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_physical_state import InitialPlacement
    from girlframe.engine.m3_world_state import Board, World
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_void import VoidService

    monkeypatch.setattr(service, "released", lambda game: True)
    game, worker, gateway = ready(ledger, (1, 2))
    with ledger.transaction() as c:
        canon = state(game)
        canon.world = World(board=Board(minimum=(-2, -2), maximum=(2, 2)), locations=())
        actor = ActorRef(kind="pilot", entity="2", incarnation=canon.sheets["2"].character_id)
        frame = resolve(
            canon, actor, profiles(c, ledger.campaign_id), require_current_profile=False
        ).frame_instance
        canon = physical.initial(
            canon,
            profiles(c, ledger.campaign_id),
            InitialPlacement(
                actor=actor,
                frame_instance=frame,
                girl_cell=(0, 0),
                frame_cell=(0, 0),
                mode="inside_frame",
                account="Actual original body inside own cockpit",
                facts_confirmed=True,
            ),
            "risk-vessel",
            "risk-placement-owner",
            "risk-placement-gm",
        )
        frames = [x for x in canon.sheets["2"].assets if x.family == "frame"]
        for asset in frames[:-1]:
            asset.void = True
        target = frames[-1].id
        game.event(c, 1, "actual-risk-prior-state", "synthetic.state", canon)
    parent = game.begin(
        PLAYER,
        "owned-risk-last",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head", context="Actual incoming threat", trigger_confirmed=True, heat=0
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "mockingbird_risk",
        number=9,
        fields={"asset": target},
        text="Actual final Frame Void cost",
    )
    assert not any(x["kind"] == "mockingbird_void_threshold" for x in game.choices(PLAYER))
    answer(game, PLAYER, "actor_keep", options=("in_control", "tough"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The actual original defense is enough")
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
    void = VoidService(ledger)
    assert void.get(PLAYER, row["id"])["stage"] == "resist_pending"
    assert game.inspect(PLAYER, parent)["state"] != "complete"
    game.dice.faces = (4, 4)
    child = game.begin(
        PLAYER,
        "risk-real-resistance",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            source_work=row["id"],
            parent=parent,
            heat=0,
            context="Actual resistance to the corrupt Frame",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    # A second legal Risk on this actual resistance pays a Girl Asset and joins the existing
    # original threshold instead of inventing another resistance child.
    girl = next(x for x in state(game).sheets["2"].assets if x.family == "girl" and not x.void)
    answer(
        game,
        PLAYER,
        "mockingbird_risk",
        number=9,
        fields={"asset": girl.id},
        text="Actual resistance's additional Void cost",
    )
    answer(game, PLAYER, "actor_keep", options=("in_control", "tough"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The real resistance is enough")
    assert game.inspect(PLAYER, child)["state"] == "complete"
    assert game.inspect(PLAYER, parent)["state"] == "complete"
    assert game.dice.calls == 2
    with ledger.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count(sa.distinct(t.m3["m3_required_work"].c.id)))) == 1
    tick(worker, gateway, 8)
    with ledger.engine.connect() as c:
        assert game.lock(c, 900)["state"] == "released"


@pytest.mark.parametrize("total", [8, 9, 10])
def test_real_risk_native_forms_select_each_result(ledger, monkeypatch, total):
    import asyncio

    from test_mission_ui import current

    from girlframe.discord_adapter.m2_ui import open_choice

    game, _, _, identity = begin(ledger, monkeypatch)
    row = next(x for x in game.choices(PLAYER) if x["kind"] == "mockingbird_risk")
    asset = next(x for x in state(game).sheets["2"].assets if not x.void)

    async def run():
        owner = current(2, 880001)
        await owner.response.defer(ephemeral=True)
        await open_choice(owner, game, row["id"])
        form = owner.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(3, 880002))
        form.values.update(
            total=(str(total),), asset=(asset.id,), description="Actual private Void cost"
        )
        await form.confirm.callback(current(2, 880003))
        assert form.completed

    asyncio.run(run())
    with ledger.engine.connect() as c:
        action = game.action(c, identity)
    assert action["data"]["result"]["total"] == total
    assert action["data"]["receipt"]["faces"] == [1, 2]
    assert game.dice.calls == 1


def test_removed_rule_and_no_real_uncorrupted_cost_never_offer_free_shift(ledger, monkeypatch):
    monkeypatch.setattr(service, "released", lambda game: True)
    game, worker, gateway = ready(ledger, (1, 2))
    with ledger.transaction() as c:
        canon = state(game)
        for asset in canon.sheets["2"].assets:
            asset.void = True
        game.event(c, 1, "actual-no-risk-cost", "synthetic.state", canon)
    identity = game.begin(
        PLAYER,
        "actual-all-void",
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head", context="Actual incoming threat", trigger_confirmed=True, heat=0
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    assert not any(x["kind"] == "mockingbird_risk" for x in game.choices(PLAYER))
    with ledger.engine.connect() as c:
        assert game.action(c, identity)["data"]["risk_factor"]["state"] == "unavailable"
    assert game.dice.calls == 1


def test_actual_retained_harpy_risk_pays_real_carried_asset_at_sole_origin(
    ledger, tmp_path, monkeypatch
):
    import test_harpy_item_resources as item_fixture
    from test_cast_service import change
    from test_dive import threshold_source
    from test_harpy_actor_plays import begin as begin_actor
    from test_m2_game import Gateway
    from test_void_keep import keep
    from test_void_service import five_no, respond

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.engine.m3_actor_state import ActorRef
    from girlframe.engine.m3_harpy_defeat import harpy
    from girlframe.engine.m3_mockingbird import RISK
    from girlframe.services.m3_actor_plays import ActorPlayService
    from girlframe.services.m3_actors import ActorService
    from girlframe.services.m3_cast import CastService
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_void import VoidService

    def converted(store):
        game, worker, gateway, parent, work = threshold_source(store, girl="MOCKINGBIRD")
        keep(game, worker, gateway, parent, work, controlled=False)
        void = VoidService(store)
        five_no(void, work)
        view = void.get(PLAYER, work)
        package = view["rebirth_choice"] | dict(
            retained_plays=[RISK], account="Actual owner retains original Risk Factor"
        )
        respond(void, work, "save_rebirth", dict(choice=package, account="Actual retained rule"))
        respond(void, work, "rebirth", dict(choice=package, account="Actual source transformation"))
        tick(worker, gateway, 8)
        body = state(game).harpy_states[-1]
        return game, worker, gateway, ActorRef(kind="external_pilot", entity=body.id), work, parent

    monkeypatch.setattr(item_fixture, "reborn_with_lock", converted)
    _, game, actor, item = item_fixture.carried(ledger, tmp_path, monkeypatch, converted=True)
    assert RISK in harpy(state(game), actor).plays
    before = state(game)
    assert all(x.void for x in harpy(before, actor).assets)
    assert next(x for x in before.held_items if x.id == item.id).asset_json is not None
    approval = ledger.policy.m3_approval
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"world"}}
            )
        }
    )
    cast = CastService(ActorService(MissionService(ledger)))
    change(cast, PLAYER, "join", actor)
    monkeypatch.setattr(service, "released", lambda game: True)
    actual = ActorPlayService(game)
    game.dice.faces = (1, 2)
    identity = begin_actor(actual, actor)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(
        game,
        PLAYER,
        "mockingbird_risk",
        number=9,
        fields={"asset": item.asset_id},
        text="Actual carried pistol warps into fractal bone",
    )
    after = state(game)
    updated = next(x for x in after.held_items if x.id == item.id)
    from girlframe.engine.m2 import AssetState

    assert AssetState.model_validate_json(updated.asset_json).void
    assert harpy(after, actor).assets == harpy(before, actor).assets
    assert after.sheets["3"] == before.sheets["3"]
    answer(game, PLAYER, "actor_keep", options=("beautiful", "in_control"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Actual source defense is enough")
    assert game.inspect(PLAYER, identity)["state"] == "complete"


def test_actual_off_duty_shift_preserves_status_roll_and_syncs_period_once(ledger, monkeypatch):
    from test_m2_game import start
    from test_off_duty_roll_service import active, saved

    monkeypatch.setattr(service, "released", lambda game: True)
    periods, game, worker, gateway, period = active(ledger, (1, 2))
    identity = start(game, play="go_off_duty", off_duty_id=period)
    tick(worker, gateway, 3)
    pass_tags(game)
    before = game.inspect(PLAYER, identity)["receipt"]
    cost = next(x for x in state(game).sheets["2"].assets if x.family == "frame" and not x.void)
    answer(
        game,
        PLAYER,
        "mockingbird_risk",
        number=9,
        fields={"asset": cost.id},
        text="Actual Status roll's Void cost",
    )
    period_after = saved(periods, period)
    actual = period_after.progress["2"].roll
    assert actual.faces == (1, 2) and actual.modifier == 4 and actual.total == 9
    assert actual.stage == "choices" and len(actual.adjustments) == 1
    assert game.inspect(PLAYER, identity)["receipt"] == before
    assert game.inspect(PLAYER, identity)["state"] == "complete"
    assert game.dice.calls == 1
    with ledger.engine.connect() as c:
        assert game.action(c, identity)["data"]["risk_factor"]["period_roll_synced"]
