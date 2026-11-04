"""Actual d6/column source, one consumption, post-roll Tags and known-roll recovery."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import Dice, Gateway, answer, pass_tags, start, state, tick
from test_mission_ui import current
from test_off_duty_cycle import activate
from test_strain_effect_service import pending, selected

from girlframe.database import tables as t
from girlframe.delivery.m2_worker import GameWorker
from girlframe.engine.m2 import PlayInput, TagState
from girlframe.engine.m3_strain_effects import Choice
from girlframe.services.m2_game import GameService
from girlframe.services.m3_off_duty_cycle import CycleService
from girlframe.services.m3_recovery import RecoveryService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def ready(store, *, apply=True):
    effects, game, period, first = pending(store)
    approval = store.policy.m3_approval
    store.policy = store.policy.model_copy(
        update={
            "m3_approval": approval.model_copy(
                update={"subsystems": approval.subsystems | {"plays"}}
            )
        }
    )
    effects.apply(ADMIN, "void-source", first, 1, state(game).revision, selected())
    request = next(x for x in state(game).strain.requests if x.track == "rebellion")
    effects.strain.roll(ADMIN, "actual-rebellion-die", request.id, 1, state(game).revision)
    effects.strain.choose(ADMIN, "actual-rebellion-column", request.id, 2, state(game).revision, 2)
    identity = request.id + ":effect"
    if apply:
        data = effects.get(ADMIN, identity)
        choice = Choice(rule_id="strain.rebellion.low.1.2", account="PRIVATE_CONTROL_ACCOUNT")
        outcome = effects.apply(
            ADMIN, "actual-control-source", identity, 1, data["game_revision"], choice
        )
        assert (
            effects.apply(
                ADMIN, "actual-control-source", identity, 1, data["game_revision"], choice
            )
            == outcome
        )
    budget = next(x for x in state(game).strain.requests if x.track == "budget")
    effects.strain.dice.face = 5
    effects.strain.roll(ADMIN, "actual-budget-die", budget.id, 1, state(game).revision)
    effects.strain.choose(ADMIN, "actual-budget-column", budget.id, 2, state(game).revision, 2)
    effects.apply(
        ADMIN,
        "budget-source",
        budget.id + ":effect",
        1,
        state(game).revision,
        Choice(rule_id="strain.budget.low.5.2", account="Actual rooms", rooms=((2, 3),)),
    )
    if apply:
        activate(CycleService(effects.strain.periods), game, period)
    return effects, game, identity


def refusal(game, viewer=PLAYER, channel=900, key="actual-refusal", **values):
    with game.store.transaction() as c:
        order_id = str(uuid4())
        # A prior actual recorded order, without inventing a new pending response.
        c.execute(
            t.m2["m2_orders"]
            .insert()
            .values(
                campaign_id=game.store.campaign_id,
                id=order_id,
                issuer_id="1",
                target_id=str(viewer.user_id),
                channel_id=str(channel),
                state="disobey",
                body_json=json.dumps({"text": "Synthetic prior direct order"}),
            )
        )
    prepared = PlayInput(
        play="disobey_orders",
        context="Actual refusal",
        heat=values.pop("heat", 0),
        trigger_confirmed=True,
        order_id=order_id,
        **values,
    )
    return game.begin(
        viewer, key, channel, state(game).sheets[str(viewer.user_id)].revision, prepared
    )["action_id"]


@pytest.mark.parametrize(
    "faces,total,level", (((1, 2), 5, "low"), ((3, 3), 8, "mid"), ((4, 5), 11, "high"))
)
def test_actual_next_refusal_uses_plus_two_separate_from_heat_at_all_tiers(
    ledger, faces, total, level
):
    effects, game, identity = ready(ledger)
    game.dice = Dice(faces)
    action = refusal(game)
    assert state(game).refusal_bonuses[0].action is None and game.dice.calls == 0
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    receipt = game.inspect(PLAYER, action)["receipt"]
    assert receipt["pre_modifiers"] == [{"source": "control_slips", "amount": 2}]
    assert receipt["base_modifier"] == receipt["heat"] == 0 and receipt["pre_total"] == total
    pass_tags(game)
    with ledger.engine.connect() as c:
        result = game.action(c, action)["data"]["result"]
    assert result["tier"] == level
    source = state(game).refusal_bonuses[0]
    assert source.id == identity and source.action == action
    assert source.actor.incarnation == state(game).sheets["2"].character_id
    assert game.dice.calls == 1 and effects.strain.dice.calls == 3


def test_normal_play_does_not_consume_bonus_and_later_refusal_preserves_forced_heat_and_tag_order(
    ledger,
):
    _, game, _ = ready(ledger)
    worker, gateway = GameWorker(game), Gateway()
    ordinary = start(game)
    tick(worker, gateway)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("tough", "vicious"), denied=("desperate",))
    answer(game, ADMIN, "handler_keep", flag=True, text="Enough")
    tick(worker, gateway, 5)
    assert state(game).refusal_bonuses[0].action is None
    with ledger.transaction() as c:
        saved = state(game)
        saved.sheets["2"].heat = 5
        saved.sheets["2"].tags.append(
            TagState(id="known-tag", label="Known resolve", giver=3, observers=(1, 2, 3))
        )
        saved.sheets["2"].revision += 1
        game.event(c, 1, "synthetic-heat-and-tag", "synthetic.resources", saved)
    game.dice = Dice((1, 1))
    action = refusal(game, heat=5)
    tick(worker, gateway)
    assert game.inspect(PLAYER, action)["receipt"]["pre_total"] == 9
    assert state(game).sheets["2"].heat == 0
    answer(game, PLAYER, "tag_window", options=("pass",))
    answer(
        game,
        OTHER,
        "tag_window",
        options=("tag",),
        denied=("known-tag",),
        number=1,
        text="Relevant",
    )
    answer(game, ADMIN, "tag_window", options=("pass",))
    with ledger.engine.connect() as c:
        data = game.action(c, action)["data"]
    assert data["result"]["total"] == 11 and data["modifiers"][0]["amount"] == 2
    assert data["receipt"]["pre_total"] == 9 and game.dice.calls == 1
    assert ordinary != action


def test_pause_lock_and_policy_revocation_do_not_consume_or_roll(ledger):
    _, game, _ = ready(ledger)
    worker, gateway = GameWorker(game), Gateway()
    action = refusal(game)
    with pytest.raises(WorkflowError, match="LOCK_NOT_ACKNOWLEDGED"):
        game.roll(PLAYER, "without-lock", action)
    ledger.safety(OTHER, "pause-refusal", ledger.status(OTHER)["revision"], pause=True)
    tick(worker, gateway)
    assert game.dice.calls == 0 and state(game).refusal_bonuses[0].action is None
    ledger.safety(OTHER, "resume-refusal", ledger.status(OTHER)["revision"], pause=False)
    ledger.policy = ledger.policy.model_copy(update={"m3_approval": None})
    with pytest.raises(WorkflowError, match="M3_REVIEW_PENDING"):
        game.roll(PLAYER, "revoked-before-roll", action)
    assert game.dice.calls == 0 and state(game).refusal_bonuses[0].action is None


def test_known_receipt_replay_restart_and_owned_recovery_never_reconsume_bonus(ledger):
    _, game, identity = ready(ledger)
    worker, gateway = GameWorker(game), Gateway()
    action = refusal(game)
    tick(worker, gateway)
    receipt = game.inspect(PLAYER, action)["receipt"]
    answer(game, PLAYER, "tag_window", options=("pass",))
    before = state(game)
    game.abort(ADMIN, "abort-known-refusal", action)
    tick(worker, gateway, 5)
    restarted = GameService(ledger, dice=game.dice)
    recovery = RecoveryService(restarted)
    saved = recovery.saved(PLAYER)[0]
    recovery.recover(PLAYER, "resume-known-refusal", action, saved["revision"])
    tick(GameWorker(restarted), gateway)
    assert restarted.roll(PLAYER, "read-known-receipt", action)["receipt"] == receipt
    assert state(restarted) == before and game.dice.calls == 1
    assert state(game).refusal_bonuses[0].id == identity
    assert not restarted.choices(PLAYER)


def test_unrolled_cancellation_preserves_bonus_for_next_actual_refusal(ledger):
    _, game, _ = ready(ledger)
    worker, gateway = GameWorker(game), Gateway()
    action = refusal(game)
    game.abort(ADMIN, "abort-unrolled-refusal", action)
    tick(worker, gateway, 5)
    recovery = RecoveryService(game)
    saved = recovery.saved(PLAYER)[0]
    recovery.recover(PLAYER, "cancel-unrolled-refusal", action, saved["revision"], cancel=True)
    assert state(game).refusal_bonuses[0].action is None and game.dice.calls == 0
    actual = refusal(game, key="new-actual-refusal")
    tick(worker, gateway)
    assert state(game).refusal_bonuses[0].action == actual and game.dice.calls == 1


def test_forged_source_event_is_rejected_before_reservation_and_dice(ledger):
    _, game, _ = ready(ledger)
    with ledger.transaction() as c:
        saved = state(game)
        saved.refusal_bonuses[0] = saved.refusal_bonuses[0].model_copy(
            update={"source_event": str(uuid4())}
        )
        game.event(c, 1, "synthetic-invalid-source", "synthetic.source", saved)
    with pytest.raises(WorkflowError, match="SOURCE_CONTROL_MISSING"):
        refusal(game)
    assert game.dice.calls == 0 and state(game).refusal_bonuses[0].action is None


def test_rolled_event_failure_rolls_back_bonus_heat_receipt_and_then_retry_is_single_committed_roll(
    ledger, monkeypatch
):
    _, game, _ = ready(ledger)
    action = refusal(game)
    worker, gateway = GameWorker(game), Gateway()
    job = worker.claim("m2_locks", ("acquiring",))
    asyncio.run(worker.acquire(job, gateway))
    before = state(game)
    original = game.event

    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("synthetic failed roll transaction")

    monkeypatch.setattr(game, "event", fail)
    with pytest.raises(RuntimeError):
        game.roll(PLAYER, "retry-actual-roll", action)
    assert state(game) == before and game.inspect(PLAYER, action)["receipt"] is None
    monkeypatch.setattr(game, "event", original)
    outcome = game.roll(PLAYER, "retry-actual-roll", action)
    assert game.roll(PLAYER, "retry-actual-roll", action) == outcome
    assert state(game).refusal_bonuses[0].action == action
    assert game.dice.calls == 2  # The failed transaction exposed no saved receipt.


def test_native_source_has_no_target_picker_and_play_preview_displays_actual_bonus(ledger):
    from girlframe.discord_adapter.m2_ui import open_play
    from girlframe.discord_adapter.m3_strain_effects import open_effect

    effects, game, identity = ready(ledger, apply=False)

    async def run():
        handler = current(1)
        await handler.response.defer(ephemeral=True)
        await open_effect(handler, effects, identity)
        form = handler.edit_original_response.call_args.kwargs["view"]
        assert {x.key for x in form.fields} == {"account"}
        assert not await form.interaction_check(current(2))
        form.values = {"account": "PRIVATE_NATIVE_CONTROL_ACCOUNT"}
        await form.confirm.callback(current(1, 19301))
        assert form.completed and state(game).refusal_bonuses[0].action is None
        owner = current(2)
        owner.channel_id = 900
        await owner.response.defer(ephemeral=True)
        await open_play(owner, game)
        wizard = owner.edit_original_response.call_args.kwargs["view"]
        assert "+2 from control slips" in wizard.text()
        assert "PRIVATE_NATIVE_CONTROL_ACCOUNT" not in wizard.text()
        assert game.dice.calls == 0

    asyncio.run(run())
    with ledger.engine.connect() as c:
        assert "PRIVATE_NATIVE_CONTROL_ACCOUNT" not in str(
            list(c.scalars(sa.select(t.events.c.payload_json)))
        )


def test_next_actual_girl_gets_the_bonus_and_the_following_refusal_gets_none(ledger):
    _, game, _ = ready(ledger)
    game.dice = Dice((4, 4))
    worker, gateway = GameWorker(game), Gateway()
    first = refusal(game, viewer=OTHER, key="other-girl-is-next")
    tick(worker, gateway)
    pass_tags(game)
    answer(game, OTHER, "actor_disobey", options=("tag_heat",), number=1, text="Her refusal")
    answer(game, ADMIN, "handler_disobey", flag=False)
    tick(worker, gateway, 5)
    source = state(game).refusal_bonuses[0]
    assert source.action == first and source.actor.entity == "3"
    second = refusal(game, key="later-girl-gets-no-reuse")
    tick(worker, gateway)
    receipt = game.inspect(PLAYER, second)["receipt"]
    assert receipt["pre_total"] == 8 and receipt.get("pre_modifiers", []) == []
    assert state(game).refusal_bonuses[0] == source and game.dice.calls == 2


def test_two_reserved_refusals_only_one_consumes_the_actual_global_next_roll_bonus(ledger):
    _, game, _ = ready(ledger)
    game.leave_scene(OTHER, "leave-first-scene", 900)
    game.bind_scene(ADMIN, "bind-second-scene", 901)
    game.join_scene(OTHER, "other-joins-second", 901)
    game.join_scene(ADMIN, "handler-joins-second", 901)
    first = refusal(game, key="first-reserved-refusal")
    second = refusal(game, viewer=OTHER, channel=901, key="second-reserved-refusal")
    worker, gateway = GameWorker(game), Gateway()
    for _ in range(2):
        job = worker.claim("m2_locks", ("acquiring",))
        asyncio.run(worker.acquire(job, gateway))

    def attempt(entry):
        viewer, identity = entry
        try:
            return game.roll(viewer, "race-roll:" + identity, identity)
        except WorkflowError as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, ((PLAYER, first), (OTHER, second))))
    assert sum(isinstance(x, dict) for x in outcomes) == 1
    assert sum(isinstance(x, str) and "STALE_CONTROL" in x for x in outcomes) == 1
    assert game.dice.calls == 1
    winning = next(x for x in outcomes if isinstance(x, dict))["action_id"]
    assert state(game).refusal_bonuses[0].action == winning


def test_applying_control_slip_with_an_invented_target_rolls_back_source_and_work(ledger):
    effects, game, identity = ready(ledger, apply=False)
    before = state(game)
    with pytest.raises(WorkflowError, match="unrelated choices"):
        effects.apply(
            ADMIN,
            "forged-recipient",
            identity,
            1,
            before.revision,
            Choice(
                rule_id="strain.rebellion.low.1.2", account="Cannot pick the next Girl", target="2"
            ),
        )
    assert state(game) == before and not state(game).refusal_bonuses
    assert effects.get(ADMIN, identity)["state"] == "pending"


def test_actual_source_failure_rolls_back_bonus_and_work_before_retry(ledger, monkeypatch):
    effects, game, identity = ready(ledger, apply=False)
    before = state(game)
    original = effects.strain._save

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic source-work save failure")

    monkeypatch.setattr(effects.strain, "_save", fail)
    choice = Choice(rule_id="strain.rebellion.low.1.2", account="Actual control slip")
    with pytest.raises(RuntimeError):
        effects.apply(ADMIN, "retry-control-source", identity, 1, before.revision, choice)
    assert state(game) == before and effects.get(ADMIN, identity)["state"] == "pending"
    monkeypatch.setattr(effects.strain, "_save", original)
    effects.apply(ADMIN, "retry-control-source", identity, 1, before.revision, choice)
    assert len(state(game).refusal_bonuses) == 1
