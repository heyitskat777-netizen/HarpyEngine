from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_mission_service import service

from girlframe.engine.m2 import Obligation
from girlframe.engine.m3_observation import order
from girlframe.engine.m3_off_duty import Period, Progress
from girlframe.engine.m3_scientific_observation import Demand, materialize, require_orders

ledger = ledger_fixture


@pytest.fixture
def context(ledger):
    _, game = service(ledger)
    canon = state(game)
    period = Period(
        id=str(uuid4()),
        handler=1,
        pilots=canon.order,
        character_ids={uid: x.character_id for uid, x in canon.sheets.items()},
    )
    return period, canon


@pytest.mark.parametrize(
    "subjects,hiding",
    [
        ((), {}),
        ((2, 2), {"2": False}),
        ((2, 3, 4), {"2": False, "3": False, "4": False}),
        ((2,), {}),
        ((2,), {"02": False}),
        ((2,), {"2": "no"}),
    ],
)
def test_demand_requires_distinct_actual_ids_and_an_explicit_boolean_for_each(subjects, hiding):
    with pytest.raises(ValidationError):
        Demand(subjects=subjects, hiding=hiding)


def test_two_required_orders_materialize_distinct_causes_without_early_status_or_sheet_effects(
    context,
):
    period, canon = context
    sheets, status = canon.model_dump()["sheets"], canon.order
    require_orders(
        canon, Demand(subjects=(2, 3), hiding={"2": False, "3": True}), "science", "Actual demand"
    )
    assert len(canon.obligations) == 2 and all(
        x.kind == "scientific_observation_order" for x in canon.obligations
    )
    assert not period.progress
    for uid in (2, 3):
        period, canon = materialize(
            period,
            canon,
            1,
            uid,
            "science",
            "order-" + str(uid),
            canon.sheets[str(uid)].character_id,
        )
    assert canon.order == status and canon.model_dump()["sheets"] == sheets
    assert all(
        x.state == "fulfilled"
        for x in canon.obligations
        if x.kind == "scientific_observation_order"
    )
    debts = [x for x in canon.obligations if x.kind == "void_observation"]
    assert len(debts) == len({x.id for x in debts}) == 2 and all(
        x.state == "pending" for x in debts
    )
    assert all(x.details["source_pdf"] == "150" for x in debts)
    assert period.progress["2"].observation.source_event == "order-2"
    assert period.progress["3"].observation.suspects_hiding is True


def test_existing_observation_keeps_original_context_and_adds_one_distinct_scientific_cause(
    context,
):
    period, canon = context
    period, canon = order(
        period, period.revision, 1, 2, canon, True, "Original suspicion", "original-order"
    )
    original = period.progress["2"].observation
    require_orders(
        canon, Demand(subjects=(2,), hiding={"2": False}), "science", "Actual scientific demand"
    )
    updated, changed = materialize(
        period, canon, 1, 2, "science", "science-order", canon.sheets["2"].character_id
    )
    observation = updated.progress["2"].observation
    assert observation.source_event == original.source_event == "original-order"
    assert observation.obligations[:1] == original.obligations and len(observation.obligations) == 2
    assert not observation.suspects_hiding and observation.hiding_review_event == "science-order"
    assert changed.order == canon.order and all(
        x.state == "pending" for x in changed.obligations if x.kind == "void_observation"
    )


def test_unbound_existing_cause_is_retained_alongside_the_actual_new_scientific_cause(context):
    period, canon = context
    canon.obligations.append(
        Obligation(id="prior-void", kind="void_observation", owner=2, action="prior-event")
    )
    require_orders(canon, Demand(subjects=(2,), hiding={"2": False}), "science", "Actual demand")
    updated, changed = materialize(
        period, canon, 1, 2, "science", "science-order", canon.sheets["2"].character_id
    )
    assert "prior-void" in updated.progress["2"].observation.obligations
    assert len(updated.progress["2"].observation.obligations) == 2
    assert len([x for x in changed.obligations if x.kind == "void_observation"]) == 2


def test_foreign_targets_wrong_character_owner_or_reserved_play_cannot_be_overwritten(context):
    period, canon = context
    with pytest.raises(ValueError):
        require_orders(canon, Demand(subjects=(4,), hiding={"4": False}), "science", "No such Girl")
    require_orders(canon, Demand(subjects=(2,), hiding={"2": False}), "science", "Actual demand")
    for owner, character in ((3, canon.sheets["2"].character_id), (1, "other-character")):
        with pytest.raises(ValueError):
            materialize(period, canon, owner, 2, "science", "event", character)
    period.progress["2"] = Progress(action_id="already-reserved")
    with pytest.raises(ValueError, match="committed"):
        materialize(period, canon, 1, 2, "science", "event", canon.sheets["2"].character_id)
