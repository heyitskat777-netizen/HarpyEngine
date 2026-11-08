"""Printed scene purchases require actual original actors and owned participation."""

import pytest
from test_actors import bindings
from test_actors import canon as canon_fixture
from test_ledger import ledger as ledger_fixture

from girlframe.engine import m3_scene_requisitions as rules
from girlframe.engine.m3_actor_state import ActorRef, CastRole, SceneCast
from girlframe.engine.m3_actors import resolve

canon, ledger = canon_fixture, ledger_fixture


def ref(canon, uid=2):
    return ActorRef(kind="pilot", entity=str(uid), incarnation=canon.sheets[str(uid)].character_id)


def buy(canon, kind="privacy", **changes):
    actor = changes.pop("actor", ref(canon))
    return rules.purchase(
        canon,
        actor,
        bindings(canon),
        resolve(canon, actor, bindings(canon)).source_sha256,
        kind,
        changes.pop("companion", ref(canon, 3) if kind == "privacy" else None),
        changes.pop("account", "Actual paid scene request"),
        "actual-purchase",
        "actual-paid-event",
        **changes,
    )


def saved(canon, kind="privacy"):
    return rules.Benefit(
        purchase="actual-purchase",
        actor=ref(canon),
        kind=kind,
        companion=ref(canon, 3) if kind == "privacy" else None,
        period="actual-period",
        source_event="actual-qualifying-source",
        qualification_event="actual-qualified-event",
        action="actual-eight-plus-roll" if kind == "visiting_home" else None,
        total=8 if kind == "visiting_home" else None,
    )


def cast(canon, *, handler=False):
    roles = [CastRole(actor=ref(canon), controller=2, source_event="actual-join-2")]
    roles.append(
        CastRole(
            actor=ActorRef(kind="handler", entity="1") if handler else ref(canon, 3),
            controller=1 if handler else 3,
            source_event="actual-other-join",
        )
    )
    return SceneCast(
        id="actual-scene",
        channel=900,
        roles=tuple(roles),
        facilitator=1,
        facilitator_source="actual-ooc-facilitator",
    )


@pytest.mark.parametrize("kind,price", [("privacy", 1), ("visiting_home", 2)])
def test_actual_purchase_debits_printed_price_once_without_granting_a_scene(canon, kind, price):
    canon.sheets["2"].permissions = 5
    before = canon.model_dump_json()
    result = buy(canon, kind)
    assert canon.model_dump_json() == before
    assert result.sheets["2"].permissions == 5 - price
    assert result.requisitions[-1].actor == ref(canon)
    assert result.requisitions[-1].kind == kind
    assert result.scene_casts == canon.scene_casts and result.placements == canon.placements
    with pytest.raises(ValueError, match="already recorded"):
        buy(result, kind)


@pytest.mark.parametrize("kind", ["privacy", "visiting_home"])
def test_no_funds_is_rejected_without_changing_original_resources(canon, kind):
    before = canon.model_dump_json()
    with pytest.raises(ValueError, match="available Permissions"):
        buy(canon, kind)
    assert canon.model_dump_json() == before


def test_privacy_requires_two_original_girls_without_a_handler_role_or_fake_consent(canon):
    offer = saved(canon)
    with pytest.raises(ValueError, match="exactly the two"):
        rules.propose(offer, canon, bindings(canon), cast(canon, handler=True), "Actual room", 2)
    proposal = rules.propose(offer, canon, bindings(canon), cast(canon), "Actual private room", 2)
    assert proposal.scene.present == (2,) and not rules.active(proposal)
    with pytest.raises(ValueError):
        rules.attest(proposal, 1)
    agreed = rules.attest(proposal, 3)
    assert not rules.active(agreed)
    entered = rules.enter(agreed, 2, "actual-entry")
    assert rules.active(entered)
    ended = rules.close(entered, 3, "I end my own participation")
    assert not rules.active(ended) and ended.scene.closed_by == 3


def test_another_character_cannot_inherit_the_original_benefit(canon):
    offer = saved(canon)
    canon.sheets["2"].character_id = "another-character"
    with pytest.raises(ValueError, match="STALE_ACTOR"):
        rules.propose(offer, canon, bindings(canon), cast(canon), "Cannot inherit", 2)


def test_home_requires_actual_supervisor_owned_agreement_and_physical_origin(canon):
    offer = saved(canon, "visiting_home")
    supervisor = ActorRef(kind="handler", entity="1")
    proposed = rules.propose(
        offer,
        canon,
        bindings(canon),
        cast(canon, handler=True),
        "Actual supervised visit",
        2,
        supervisor=supervisor,
        home="My pre-Piloting home",
    )
    agreed = rules.attest(proposed, 1)
    with pytest.raises(ValueError, match="original physical placement"):
        rules.enter(agreed, 2, "actual-entry")
    entered = rules.enter(agreed, 2, "actual-entry", "actual-origin-snapshot")
    assert rules.active(entered)
    assert rules.close(entered, 2, "Actual visit completed").scene.closed_by == 2
    with pytest.raises(ValueError):
        rules.close(entered, 1, "Supervisor cannot forge the Girl's close")


def test_optional_decline_is_original_owner_only_and_preserves_paid_source(canon):
    offer = saved(canon)
    with pytest.raises(ValueError):
        rules.decline(offer, 3, "Not my paid choice")
    result = rules.decline(offer, 2, "I decline this optional scene without refund")
    assert result.declined and result.purchase == offer.purchase
