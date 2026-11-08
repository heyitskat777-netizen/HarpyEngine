"""Real Prime-funded gifts retain ordinary private scenes, travel and endings."""

from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_disposable_psyche import real_period
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import answer, pass_tags, state, tick
from test_off_duty_cycle import activate, call, finish_routine, movement, roll_for
from test_repair_service import prepare_requests
from test_scene_requisition_service import agree_and_enter, propose
from test_strain import facts
from test_strain_service import D6
from test_vatgrown_plays import ready

from girlframe.database import tables as t
from girlframe.engine import m3_vatgrown_plays as rules
from girlframe.engine.m2 import PilotSheet, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_off_duty import RecoveryChoice
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_offered_girl_requisitions import (
    EVENT,
    accept_offer,
    offer_receipt,
    prove_receipt,
)
from girlframe.services.m3_retirement import RetirementService
from girlframe.services.m3_scene_requisitions import SceneRequisitionService, audience, guard
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def actual_offer(store, tmp_path, monkeypatch, kind):
    game, worker, gateway, controls = ready(store, tmp_path, monkeypatch)
    cycle, period = real_period(MissionService(store), game)
    roll_for(cycle, game, period, PLAYER, (5, 5))
    identity = rules.identity("investment", period, current_ref(state(game), 2).token)
    review = cycle.review(PLAYER, period)
    cycle.scene(
        PLAYER,
        str(uuid4()),
        period,
        review["revision"],
        state(game).revision,
        "prime_high",
        (2, 1),
        "The actual original Investor directs an endurance demonstration",
        investor=current_ref(state(game), 1),
    )
    for viewer in (PLAYER, ADMIN):
        call(cycle, game, viewer, period, "acknowledge", 2)
    controls.new_desire(
        ADMIN,
        str(uuid4()),
        identity,
        state(game).revision,
        "Complete my actual dangerous endurance demonstration",
        "I author a genuinely new desire as the original Investor",
    )
    game.dice.faces = (4, 4)
    action = game.begin(
        PLAYER,
        str(uuid4()),
        900,
        state(game).sheets["2"].revision,
        PlayInput(
            play="keep_your_head",
            source_work=identity,
            heat=0,
            context="I withstand the actual dangerous endurance demonstration",
            trigger_confirmed=True,
        ),
    )["action_id"]
    tick(worker, gateway, 3)
    pass_tags(game)
    answer(game, PLAYER, "actor_keep", options=("desperate", "tough"), denied=("sexy",))
    answer(game, ADMIN, "handler_keep", flag=True, text="The actual demonstration is sufficient")
    tick(worker, gateway, 6)
    assert game.inspect(PLAYER, action)["state"] == "complete"
    controls.fulfil(
        ADMIN,
        str(uuid4()),
        identity,
        state(game).revision,
        True,
        "The completed demonstration fulfilled my new desire; I offer this actual gift",
        kind=kind,
    )
    offer = rules.records(state(game), rules.RequisitionOffer)[-1]
    assert offer.kind == kind
    return game, cycle, period, offer


def following_period(cycle, game, period):
    call(cycle, game, PLAYER, period, "recover", RecoveryChoice())
    roll_for(cycle, game, period, OTHER, (4, 4))
    call(cycle, game, OTHER, period, "scene", None, (), "")
    call(cycle, game, OTHER, period, "recover", RecoveryChoice())
    finish_routine(cycle, game, period)
    call(cycle, game, ADMIN, period, "finish", movement(game))
    following = cycle.periods.begin(ADMIN, str(uuid4()))["id"]
    strain = StrainService(cycle.periods, dice=D6())
    strain.prepare(
        ADMIN,
        str(uuid4()),
        following,
        1,
        state(game).revision,
        facts(no_girl_void=True),
    )
    prepare_requests(EffectService(strain), game, following)
    activate(cycle, game, following)
    return following


def actual_receipt(game, offer, result, permissions):
    canon = state(game)
    receipt = next(x for x in canon.requisitions if x.id == result["id"])
    assert receipt.source_offer == offer.id and receipt.kind == offer.kind and receipt.price == 0
    with game.store.engine.connect() as c:
        assert offer_receipt(game, c, canon, offer.id) == receipt.id
        prove_receipt(game, c, canon, receipt)
        event = c.execute(sa.select(t.events).where(t.events.c.id == receipt.source_event)).one()
        assert event.kind == EVENT
        assert "PRIVATE_GIFT_ACCEPTANCE" not in event.payload_json
    assert result["charged"] == 0
    if "2" in canon.sheets:
        assert canon.sheets["2"].permissions == permissions
    return receipt


def test_actual_prime_privacy_gift_waits_next_period_then_original_companion_owns_entry(
    ledger, tmp_path, monkeypatch
):
    game, cycle, period, offer = actual_offer(ledger, tmp_path, monkeypatch, "privacy")
    service = SceneRequisitionService(game)
    actor, companion = current_ref(state(game), 2), current_ref(state(game), 3)
    permissions = state(game).sheets["2"].permissions
    before = state(game)
    view = service.scene_purchase_view(PLAYER)
    with pytest.raises(WorkflowError, match="JUST_AN_EXPERIMENT"):
        service.buy_scene(
            PLAYER, str(uuid4()), actor, view["source_sha256"], "privacy", "No request", companion
        )
    assert state(game) == before
    payload = (
        game,
        PLAYER,
        "actual-privacy-gift",
        offer.id,
        before.revision,
        "PRIVATE_GIFT_ACCEPTANCE I choose this actual companion",
    )
    with pytest.raises(WorkflowError, match="PRIVACY_COMPANION_REQUIRED"):
        accept_offer(*payload)
    original_event = game.event

    def failed_event(*args, **kwargs):
        original_event(*args, **kwargs)
        raise RuntimeError("synthetic gift event rollback")

    monkeypatch.setattr(game, "event", failed_event)
    with pytest.raises(RuntimeError, match="gift event rollback"):
        accept_offer(*payload, companion=companion)
    assert state(game) == before
    monkeypatch.setattr(game, "event", original_event)
    accepted = accept_offer(*payload, companion=companion)
    assert accept_offer(*payload, companion=companion) == accepted
    receipt = actual_receipt(game, offer, accepted, permissions)
    assert receipt.companion == companion and not service.scene_tasks(PLAYER)
    following_period(cycle, game, period)
    identity = service.scene_tasks(PLAYER)[0]["id"]
    with pytest.raises(WorkflowError):
        service.scene_get(ADMIN, identity)
    propose(service, identity)
    data = service.scene_get(PLAYER, identity)
    with pytest.raises(WorkflowError):
        service.enter_scene(PLAYER, str(uuid4()), identity, data["revision"])
    assert not service.scene_get(PLAYER, identity)["active"]
    agree_and_enter(service, identity)
    active = service.scene_get(PLAYER, identity)
    assert active["active"] and active["benefit"]["purchase"] == receipt.id
    with ledger.engine.connect() as c:
        scene = active["benefit"]["scene"]["id"]
        assert audience(c, ledger, scene) == (2, 3)
        with pytest.raises(WorkflowError, match="PRIVACY_PROTECTED"):
            guard(c, ledger, scene, current_ref(state(game), 1))
    service.close_scene(OTHER, str(uuid4()), identity, active["revision"], "I end participation")
    assert not service.scene_get(PLAYER, identity)["active"]
    actual_receipt(game, offer, accepted, permissions)


def test_actual_prime_home_gift_qualifies_later_and_uses_real_supervised_round_trip(
    ledger, tmp_path, monkeypatch
):
    game, cycle, period, offer = actual_offer(ledger, tmp_path, monkeypatch, "visiting_home")
    permissions = state(game).sheets["2"].permissions
    payload = (
        game,
        PLAYER,
        "actual-home-gift",
        offer.id,
        state(game).revision,
        "PRIVATE_GIFT_ACCEPTANCE I accept this actual visit",
    )
    accepted = accept_offer(*payload)
    assert accept_offer(*payload) == accepted
    receipt = actual_receipt(game, offer, accepted, permissions)
    service = SceneRequisitionService(game)
    assert not service.scene_tasks(PLAYER)
    following = following_period(cycle, game, period)
    assert not service.scene_tasks(PLAYER)
    action = roll_for(cycle, game, following, PLAYER, (4, 4))
    identity = service.scene_tasks(PLAYER)[0]["id"]
    propose(service, identity, kind="visiting_home")
    data = service.scene_get(PLAYER, identity)
    with pytest.raises(WorkflowError):
        service.enter_scene(PLAYER, str(uuid4()), identity, data["revision"])
    agree_and_enter(service, identity)
    active = service.scene_get(PLAYER, identity)
    assert active["active"] and active["benefit"]["purchase"] == receipt.id
    assert active["benefit"]["action"] == action and active["benefit"]["period"] == following
    canon = state(game)
    buyer = next(x for x in canon.placements if x.actor == offer.actor)
    escort = next(x for x in canon.placements if x.actor == current_ref(canon, 3))
    assert buyer.custody == escort.actor and buyer.girl_cell is None and escort.girl_cell is None
    payload = (
        PLAYER,
        "actual-gift-return",
        identity,
        active["revision"],
        "Actual supervised return",
    )
    result = service.close_scene(*payload)
    assert service.close_scene(*payload) == result and result["done"]
    assert all(x.custody is None for x in state(game).placements)
    assert not any(x.active for x in state(game).escort_journeys)
    actual_receipt(game, offer, accepted, permissions)


def test_actual_prime_retirement_gift_requires_owner_confirmation_and_archives_original(
    ledger, tmp_path, monkeypatch
):
    game, _, _, offer = actual_offer(ledger, tmp_path, monkeypatch, "retirement")
    canon = state(game)
    permissions = canon.sheets["2"].permissions
    with ledger.engine.connect() as c:
        profile = c.scalar(sa.select(t.characters.c.id).where(t.characters.c.user_id == "2"))
    payload = (
        game,
        PLAYER,
        "actual-retirement-gift",
        offer.id,
        canon.revision,
        "PRIVATE_GIFT_ACCEPTANCE I explicitly choose my actual retirement",
    )
    with pytest.raises(WorkflowError, match="RETIREMENT_CONFIRMATION_REQUIRED"):
        accept_offer(*payload)
    assert state(game) == canon
    accepted = accept_offer(*payload, confirmed_retirement=True)
    assert accept_offer(*payload, confirmed_retirement=True) == accepted
    receipt = actual_receipt(game, offer, accepted, permissions)
    canon = state(game)
    assert "2" not in canon.sheets and 2 not in canon.order
    archive = next(x for x in canon.career_archives if x.id == receipt.archive_id)
    assert archive.actor == offer.actor and archive.ending == "retirement"
    assert PilotSheet.model_validate_json(archive.sheet_json).permissions == permissions
    assert any(x.get("kind") == "retirement_discharge" for x in canon.facts)
    service = RetirementService(game)
    assert service.receipt(PLAYER, receipt.id)["archive_id"] == archive.id
    with pytest.raises(WorkflowError):
        service.receipt(ADMIN, receipt.id)
    with ledger.engine.connect() as c:
        assert (
            c.scalar(sa.select(t.characters.c.id).where(t.characters.c.user_id == "2")) == profile
        )
