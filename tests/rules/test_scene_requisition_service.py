"""Actual paid sources, final rolls, protected rooms and supervised round trips."""

import asyncio
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_comfort_service import ready
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_ui import current
from test_off_duty_cycle import activate, roll_for

from girlframe.database import tables as t
from girlframe.discord_adapter.m3_scene_requisitions import open_purchase, open_scene
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.services.m3_scene_requisitions import (
    SceneRequisitionService,
    audience,
    guard,
    synchronize,
)
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def setup(store):
    _, cycle, game, period = ready(store)
    return SceneRequisitionService(game), cycle, game, period


def pay(service, kind="privacy", key=None):
    data = service.scene_purchase_view(PLAYER)
    return service.buy_scene(
        PLAYER,
        key or str(uuid4()),
        ActorRef.model_validate(data["actor"]),
        data["source_sha256"],
        kind,
        "PRIVATE_ORIGINAL_PURCHASE_REQUEST",
        ActorRef.model_validate(data["companions"][0]["ref"]) if kind == "privacy" else None,
    )


def sync(service, period):
    with service.store.transaction() as c:
        actual = service.periods._get(c, period)
        history = t.m3["m3_off_duty_history"]
        source = c.scalar(
            sa.select(history.c.event_id)
            .where(
                history.c.campaign_id == service.store.campaign_id,
                history.c.id == period,
            )
            .order_by(history.c.revision.desc())
            .limit(1)
        )
        synchronize(c, service.store, actual, source)


def propose(service, identity, *, kind="privacy"):
    data = service.scene_get(PLAYER, identity, 900)
    target = next(x for x in data["roles"] if x["ref"]["entity"] == "3")
    return service.propose_scene(
        PLAYER,
        str(uuid4()),
        identity,
        data["revision"],
        900,
        data["cast_revision"],
        "PRIVATE_ACTUAL_SCENE",
        supervisor=ActorRef.model_validate(target["ref"]) if kind == "visiting_home" else None,
        home="PRIVATE_PRE_PILOT_HOME" if kind == "visiting_home" else "",
    )


def agree_and_enter(service, identity):
    data = service.scene_get(OTHER, identity)
    service.attest_scene(OTHER, str(uuid4()), identity, data["revision"])
    data = service.scene_get(PLAYER, identity)
    return service.enter_scene(PLAYER, str(uuid4()), identity, data["revision"])


def test_privacy_qualifies_on_actual_next_activation_not_a_later_purchase_and_is_source_private(
    ledger,
):
    service, cycle, game, period = setup(ledger)
    first = pay(service)
    assert not service.scene_tasks(PLAYER)
    activate(cycle, game, period)
    sync(service, period)
    tasks = service.scene_tasks(PLAYER)
    assert len(tasks) == 1 and state(game).sheets["2"].permissions == 3
    later = pay(service)
    sync(service, period)
    assert len(service.scene_tasks(PLAYER)) == 1
    assert len(service.scene_receipts(PLAYER)) == 2
    identity = tasks[0]["id"]
    data = service.scene_get(OTHER, identity)
    assert "PRIVATE_ORIGINAL_PURCHASE" not in str(data)
    assert data["benefit"]["purchase"] == first["id"] != later["id"]
    with pytest.raises(WorkflowError):
        service.scene_get(ADMIN, identity)


def test_privacy_agreement_protection_and_delayed_audience(
    ledger,
):
    service, cycle, game, period = setup(ledger)
    pay(service)
    activate(cycle, game, period)
    sync(service, period)
    identity = service.scene_tasks(PLAYER)[0]["id"]
    propose(service, identity)
    ledger.safety(OTHER, "pause-room", ledger.status(OTHER)["revision"], pause=True)
    data = service.scene_get(OTHER, identity)
    service.attest_scene(OTHER, "my-owned-room-agreement", identity, data["revision"])
    assert not service.scene_get(PLAYER, identity)["active"]
    data = service.scene_get(PLAYER, identity)
    with pytest.raises(WorkflowError, match="SAFETY_PAUSED"):
        service.enter_scene(PLAYER, "paused-entry", identity, data["revision"])
    ledger.safety(OTHER, "resume-room", ledger.status(OTHER)["revision"], pause=False)
    service.enter_scene(PLAYER, "actual-entry", identity, data["revision"])
    active = service.scene_get(OTHER, identity)
    assert active["active"]
    scene = active["benefit"]["scene"]["id"]
    with ledger.engine.connect() as c:
        assert audience(c, ledger, scene) == (2, 3)
        with pytest.raises(WorkflowError, match="PRIVACY_PROTECTED"):
            guard(c, ledger, scene, ActorRef(kind="handler", entity="1"))
    ledger.safety(OTHER, "pause-before-withdraw", ledger.status(OTHER)["revision"], pause=True)
    service.close_scene(
        OTHER, "my-owned-withdrawal", identity, active["revision"], "I end my participation"
    )
    with ledger.engine.connect() as c:
        assert audience(c, ledger, scene) == (2, 3)
        with pytest.raises(WorkflowError, match="PRIVACY_CLOSED"):
            guard(c, ledger, scene, ActorRef.model_validate(active["benefit"]["actor"]))
        guard(
            c, ledger, scene, ActorRef.model_validate(active["benefit"]["actor"]), continuation=True
        )
    assert not service.scene_get(PLAYER, identity)["active"]


def test_home_actual_final_eight_roll_supervision_and_physical_round_trip_are_owned(ledger):
    service, cycle, game, period = setup(ledger)
    paid = pay(service, "visiting_home")
    activate(cycle, game, period)
    assert not service.scene_tasks(PLAYER)
    roll_for(cycle, game, period, PLAYER, (2, 2))
    sync(service, period)
    identity = service.scene_tasks(PLAYER)[0]["id"]
    propose(service, identity, kind="visiting_home")
    with pytest.raises(WorkflowError):
        data = service.scene_get(PLAYER, identity)
        service.enter_scene(PLAYER, "not-yet-supervised", identity, data["revision"])
    agree_and_enter(service, identity)
    active = service.scene_get(PLAYER, identity)
    assert active["active"] and active["benefit"]["purchase"] == paid["id"]
    canon = state(game)
    buyer = next(x for x in canon.placements if x.actor.entity == "2")
    escort = next(x for x in canon.placements if x.actor.entity == "3")
    assert buyer.custody.entity == "3" and buyer.girl_cell is None and escort.girl_cell is None
    with ledger.transaction() as c:
        canon = state(game)
        canon.sheets["2"].assets[0].damaged = True
        game.event(c, 1, "actual-damage-during-visit", "synthetic.state", canon)
    result = service.close_scene(
        PLAYER, "actual-return-once", identity, active["revision"], "Actual supervised return"
    )
    assert result["done"]
    assert (
        service.close_scene(
            PLAYER, "actual-return-once", identity, active["revision"], "Actual supervised return"
        )
        == result
    )
    canon = state(game)
    assert all(x.custody is None for x in canon.placements)
    assert canon.sheets["2"].assets[0].damaged and canon.sheets["2"].permissions == 2
    assert not any(x.active for x in canon.escort_journeys)


def test_home_low_roll_retains_paid_source_and_cannot_be_claimed_retroactively(ledger):
    service, cycle, game, period = setup(ledger)
    pay(service, "visiting_home")
    activate(cycle, game, period)
    roll_for(cycle, game, period, PLAYER, (1, 1))
    sync(service, period)
    assert not service.scene_tasks(PLAYER)
    assert state(game).sheets["2"].permissions == 2


def test_native_privacy_purchase_and_agreements_use_actual_owned_forms(ledger):
    service, cycle, game, period = setup(ledger)

    async def purchase():
        caller = current(2, 21001)
        caller.channel_id = 900
        await caller.response.defer(ephemeral=True)
        await open_purchase(caller, service, "privacy")
        form = caller.edit_original_response.call_args.kwargs["view"]
        option = form.fields[0].options[0][0]
        form.values.update(
            companion=(option,), account="Actual private room purchase", payment=("yes",)
        )
        await form.confirm.callback(current(2, 21002))
        assert form.completed

    asyncio.run(purchase())
    activate(cycle, game, period)
    sync(service, period)
    identity = service.scene_tasks(PLAYER)[0]["id"]

    async def decide(uid, number, operation, **values):
        caller = current(uid, number)
        caller.channel_id = 900
        await caller.response.defer(ephemeral=True)
        await open_scene(caller, service, identity)
        form = caller.edit_original_response.call_args.kwargs["view"]
        assert not await form.interaction_check(current(1))
        form.values.update(operation=(operation,), **values)
        submitter = current(uid, number + 1)
        submitter.channel_id = 900
        await form.confirm.callback(submitter)
        assert form.completed

    asyncio.run(decide(2, 21003, "propose", account="Actual private room"))
    asyncio.run(decide(3, 21005, "attest"))
    asyncio.run(decide(2, 21007, "enter"))
    assert service.scene_get(PLAYER, identity)["active"]
    asyncio.run(decide(3, 21009, "close", account="My own withdrawal"))
    assert service.scene_get(PLAYER, identity)["state"] == "resolved"


def test_ended_purchaser_receipt_does_not_offer_a_new_scene_or_block_survivor_saves(ledger):
    from girlframe.services.m3_careers import end_in_transaction, synchronize_end

    service, cycle, game, period = setup(ledger)
    paid = pay(service, "visiting_home")
    activate(cycle, game, period)
    with ledger.transaction() as c:
        canon = state(game)
        actor = ActorRef(kind="pilot", entity="2", incarnation=canon.sheets["2"].character_id)
        source = str(uuid4())
        ended = end_in_transaction(
            c,
            game,
            canon,
            actor,
            reason="death",
            source_event=source,
            account="Actual ending before qualification",
            archive_id=str(uuid4()),
        )
        game.event(c, 1, "actual-ended-purchaser", "m3.synthetic_ending", ended, event_id=source)
        synchronize_end(c, game, ended.career_archives[-1])
    from test_m2_game import Dice, Gateway, answer, tick

    from girlframe.delivery.m2_worker import GameWorker
    from girlframe.engine.m2 import PlayInput

    game.dice = Dice((4, 5))
    game.begin(
        OTHER,
        str(uuid4()),
        900,
        state(game).sheets["3"].revision,
        PlayInput(
            play="go_off_duty",
            off_duty_id=period,
            heat=0,
            context="Actual surviving Girl's off duty",
            trigger_confirmed=True,
        ),
    )
    worker, gateway = GameWorker(game), Gateway()
    tick(worker, gateway)
    for viewer in (OTHER, ADMIN):
        if any(x["kind"] == "tag_window" for x in game.choices(viewer)):
            answer(game, viewer, "tag_window", options=("pass",))
    tick(worker, gateway, 8)
    sync(service, period)
    assert not service.scene_tasks(OTHER)
    assert any(x.id == paid["id"] for x in state(game).requisitions)


def test_owner_can_decline_unused_privacy_when_original_companion_ended(ledger):
    from girlframe.services.m3_careers import end_in_transaction, synchronize_end

    service, cycle, game, period = setup(ledger)
    pay(service)
    activate(cycle, game, period)
    sync(service, period)
    identity = service.scene_tasks(PLAYER)[0]["id"]
    with ledger.transaction() as c:
        canon = state(game)
        actor = ActorRef(kind="pilot", entity="3", incarnation=canon.sheets["3"].character_id)
        source = str(uuid4())
        ended = end_in_transaction(
            c,
            game,
            canon,
            actor,
            reason="death",
            source_event=source,
            account="Actual companion ending",
            archive_id=str(uuid4()),
        )
        game.event(c, 1, "actual-companion-ended", "m3.synthetic_ending", ended, event_id=source)
        synchronize_end(c, game, ended.career_archives[-1])
    data = service.scene_get(PLAYER, identity)
    service.decline_scene(
        PLAYER,
        "actual-unused-privacy-decline",
        identity,
        data["revision"],
        "I decline the scene; no replacement inherits the original invitation",
    )
    assert service.scene_get(PLAYER, identity)["state"] == "resolved"
