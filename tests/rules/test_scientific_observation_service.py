import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Dice, Gateway, pass_tags, start, state, tick
from test_off_duty_cycle import activate
from test_supply_service import prepared

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m3_scientific_observation import Demand
from girlframe.engine.m3_strain_effects import Choice
from girlframe.services.m3_observation import ObservationService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def ready(store):
    return prepared(store, budget_column=1)


def choice(subjects=(2, 3), **fields):
    values = dict(
        rule_id="strain.budget.low.3.1",
        account="PRIVATE_SCIENTIFIC_DEMAND",
        scientific_demand=Demand(subjects=subjects, hiding={str(x): x == 3 for x in subjects}),
    )
    values.update(fields)
    return Choice(**values)


def apply(effects, game, identity, data=None, key="actual-science"):
    return effects.apply(ADMIN, key, identity, 1, state(game).revision, data or choice())


@pytest.mark.parametrize("subjects", ((2,), (2, 3)))
def test_one_or_two_actual_orders_have_distinct_real_events_and_remain_pending_recovery(
    ledger, subjects
):
    effects, cycle, game, period, identity, selector = ready(ledger)
    before = state(game)
    rev = before.revision
    data = choice(subjects)
    outcome = effects.apply(ADMIN, "science-once", identity, 1, rev, data)
    assert effects.apply(ADMIN, "science-once", identity, 1, rev, data) == outcome
    current = state(game)
    assert (
        current.sheets == before.sheets
        and current.order == before.order
        and current.world == before.world
    )
    assert selector.calls == 0 and not current.supply_losses
    debts = [x for x in current.obligations if x.kind == "void_observation"]
    assert len(debts) == len(subjects) and all(x.state == "pending" for x in debts)
    with ledger.engine.connect() as c:
        saved = cycle.periods._get(c, period)
        assert saved.phase == "preparing" and all(
            saved.progress[str(uid)].roll is None for uid in subjects
        )
        orders = list(
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == ledger.campaign_id,
                    t.events.c.command_key == "science-once",
                    t.events.c.kind == "m3.scientific_observation_ordered",
                )
            ).mappings()
        )
        assert len(orders) == len(subjects) and len({x["id"] for x in orders}) == len(subjects)
        assert {x["event_index"] for x in orders} == set(range(1, len(subjects) + 1))
        assert {x.action for x in debts} == {x["id"] for x in orders}
        assert {saved.progress[str(uid)].observation.source_event for uid in subjects} == {
            x["id"] for x in orders
        }
        metadata = str(list(c.scalars(sa.select(t.events.c.payload_json))))
        metadata += str(list(c.scalars(sa.select(t.commands.c.outcome_json))))
        assert "PRIVATE_SCIENTIFIC_DEMAND" not in metadata
    activate(cycle, game, period)
    before_roll = state(game)
    with pytest.raises(WorkflowError, match="Observation replaces"):
        start(game, play="go_off_duty", off_duty_id=period)
    assert state(game) == before_roll and game.dice.calls == 0
    assert effects.get(ADMIN, identity)["state"] == "resolved"
    assert not cycle.review(PLAYER, period)["own"]["recovered"]


def test_overlapping_real_order_keeps_one_roll_and_two_unfulfilled_causes(ledger):
    effects, cycle, game, period, identity, _ = ready(ledger)
    review = cycle.review(ADMIN, period)
    ObservationService(cycle.periods).order(
        ADMIN,
        "prior-actual-order",
        period,
        review["revision"],
        review["game_revision"],
        2,
        True,
        "Original suspicion",
    )
    original = cycle.review(PLAYER, period)["own"]["observation"]
    apply(effects, game, identity, choice((2,)))
    changed = cycle.review(PLAYER, period)["own"]["observation"]
    assert changed["source_event"] == original["source_event"]
    assert len(changed["obligations"]) == 2 and not changed["suspects_hiding"]
    activate(cycle, game, period)
    game.dice = Dice((4, 4))
    action = start(game, play="void_observation", off_duty_id=period)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    assert state(game).order == (3, 2) and game.dice.calls == 1
    pass_tags(game)
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["pre_total"] == 8 and game.dice.calls == 1
    assert all(
        x.state == "pending" for x in state(game).obligations if x.kind == "void_observation"
    )
    assert not cycle.review(PLAYER, period)["own"]["recovered"]


def test_actual_observation_scene_fulfills_both_causes_once_before_real_recovery(ledger):
    from test_frame_reward_service import own as frame_work
    from test_frame_reward_service import submit as frame_submit
    from test_observation_service import apply as apply_observation
    from test_observation_service import pending as observation_effect
    from test_observation_service import select
    from test_off_duty_cycle import call

    from girlframe.engine.m3_frame_rewards import Claim
    from girlframe.engine.m3_observation_state import Details
    from girlframe.engine.m3_off_duty import RecoveryChoice
    from girlframe.services.m3_frame_rewards import RewardService

    effects, cycle, game, period, identity, _ = ready(ledger)
    observations = ObservationService(cycle.periods)
    current = cycle.review(ADMIN, period)
    observations.order(
        ADMIN,
        "first-source-order",
        period,
        current["revision"],
        current["game_revision"],
        2,
        False,
        "Original actual suspicion",
    )
    apply(effects, game, identity, choice((2,)))
    activate(cycle, game, period)
    game.dice = Dice((1, 1))
    action = start(game, play="void_observation", off_duty_id=period)
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    pass_tags(game)
    tick(worker, gateway, 5)
    select(observations, PLAYER, period, ("public_display_tag",))
    work = observation_effect(observations, ADMIN, period)
    apply_observation(
        observations,
        ADMIN,
        work,
        Details(account="Actual public response", tag="Publicly observed"),
    )
    call(
        cycle,
        game,
        PLAYER,
        period,
        "scene",
        "observation:public_display_tag",
        (2, 1),
        "Actual observed scene",
    )
    call(cycle, game, PLAYER, period, "acknowledge", 2)
    assert any(
        x.kind == "void_observation" and x.state == "pending" for x in state(game).obligations
    )
    call(cycle, game, ADMIN, period, "acknowledge", 2)
    assert not any(
        x.kind == "void_observation" and x.state == "pending" for x in state(game).obligations
    )
    rewards = RewardService(cycle.periods)
    frame_submit(
        rewards,
        PLAYER,
        frame_work(rewards, PLAYER, period)["id"],
        Claim(fulfilled=False, account="No qualifying Frame event"),
    )
    call(cycle, game, PLAYER, period, "recover", RecoveryChoice())
    assert cycle.review(PLAYER, period)["own"]["recovered"]
    assert game.dice.calls == 1 and game.inspect(PLAYER, action)["receipt"]["pre_total"] == 2


def test_second_order_failure_rolls_back_all_canonical_period_work_and_source_events(
    ledger, monkeypatch
):
    effects, cycle, game, period, identity, _ = ready(ledger)
    before = state(game)
    with ledger.engine.connect() as c:
        old_period = cycle.periods._get(c, period)
    original = effects.game.event
    calls = []

    def fail(*args, **kwargs):
        result = original(*args, **kwargs)
        if len(args) > 3 and args[3] == "m3.scientific_observation_ordered":
            calls.append(result)
            if len(calls) == 2:
                raise RuntimeError("synthetic second-order failure")
        return result

    monkeypatch.setattr(effects.game, "event", fail)
    with pytest.raises(RuntimeError):
        apply(effects, game, identity)
    assert state(game) == before and effects.get(ADMIN, identity)["state"] == "pending"
    with ledger.engine.connect() as c:
        assert cycle.periods._get(c, period) == old_period
        assert (
            c.scalar(
                sa.select(sa.func.count()).select_from(t.events).where(t.events.c.id.in_(calls))
            )
            == 0
        )
    monkeypatch.setattr(effects.game, "event", original)
    apply(effects, game, identity)
    assert len([x for x in state(game).obligations if x.kind == "void_observation"]) == 2


def test_foreign_target_unrelated_fields_new_character_and_stale_state_do_not_order_observation(
    ledger,
):
    from test_actor_service import replace_profile_id

    effects, _, game, _, identity, _ = ready(ledger)
    before = state(game)
    for data in (choice((4,)), choice(target="2"), choice(scientific_demand=None)):
        with pytest.raises(WorkflowError):
            apply(effects, game, identity, data)
    with pytest.raises(WorkflowError, match="STALE_STATE"):
        effects.apply(ADMIN, "stale-science", identity, 1, before.revision - 1, choice())
    replace_profile_id(ledger, 3)
    with pytest.raises(WorkflowError):
        apply(effects, game, identity)
    assert state(game) == before


def test_pause_scope_revocation_and_concurrent_selection_preserve_exact_orders(ledger):
    effects, _, game, _, identity, _ = ready(ledger)
    ledger.safety(OTHER, "pause-science", ledger.status(OTHER)["revision"], pause=True)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        apply(effects, game, identity)
    ledger.safety(OTHER, "resume-science", ledger.status(OTHER)["revision"], pause=False)
    policy = ledger.policy
    ledger.policy = policy.model_copy(update={"m3_approval": None})
    with pytest.raises(WorkflowError, match="REVIEW_PENDING"):
        apply(effects, game, identity)
    ledger.policy = policy
    rev = state(game).revision

    def run(i):
        try:
            effects.apply(ADMIN, "race-science-" + str(i), identity, 1, rev, choice())
            return True
        except WorkflowError:
            return False

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(run, range(2))) == [False, True]
    assert len([x for x in state(game).obligations if x.kind == "void_observation"]) == 2


def test_native_scientific_targets_require_each_explicit_hiding_answer_before_confirmation(ledger):
    from test_mission_ui import current

    from girlframe.discord_adapter.m3_strain_effects import open_effect

    effects, cycle, game, period, identity, _ = ready(ledger)

    async def run():
        viewer = current(1)
        await viewer.response.defer(ephemeral=True)
        await open_effect(viewer, effects, identity)
        form = viewer.edit_original_response.call_args.kwargs["view"]
        form.values["subjects"] = ("2", "3")
        form.controls()
        assert {x.key for x in form.fields} == {"subjects", "hide:2", "hide:3", "account"}
        form.values.update({"hide:2": ("no",), "hide:3": ("yes",), "account": "Actual demand"})
        assert not state(game).obligations
        await form.confirm.callback(current(1, 18201))
        assert form.completed
        assert cycle.review(PLAYER, period)["own"]["observation"]["suspects_hiding"] is False
        assert cycle.review(OTHER, period)["own"]["observation"]["suspects_hiding"] is True

    asyncio.run(run())
