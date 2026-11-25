"""The Activity installs an owned Frame Asset using the engine's payment ledger."""

import mission_lab

# isort: split
import pytest
from frame_purchases import FramePurchases
from test_enforcer_requisitions import approved
from test_ledger import OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_requisition_service import ready

from girlframe.engine.m3_enforcer_requisitions import MASTER
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


@pytest.fixture(autouse=True)
def source_registry(monkeypatch):
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(mission_lab.ENGINE / "rules/registry.json"))


def test_owned_installment_cost_and_receipt_survive_reopen(ledger):
    _, game = ready(ledger)
    purchases = FramePurchases(game)
    data = purchases.view(PLAYER)
    assert data["permissions"] == 3 and data["asset_installment_price"] == 1
    request = {
        "actor": data["actor"],
        "expected": data["source_sha256"],
        "choice": {
            "name": "Relay antenna",
            "description": "A shielded comms assembly.",
            "account": "Install the assembly in the original Frame.",
            "trigger_confirmed": True,
        },
    }
    with pytest.raises(WorkflowError, match="owned"):
        purchases.perform(OTHER, "not-my-frame", request)
    receipt = purchases.perform(PLAYER, "paid-frame-asset", request)
    reopened = FramePurchases(GameService(ledger))
    assert reopened.perform(PLAYER, "paid-frame-asset", request) == receipt
    assert reopened.view(PLAYER)["permissions"] == 2
    assert [x["name"] for x in reopened.view(PLAYER)["receipts"]] == ["Relay antenna"]
    assert not reopened.view(OTHER)["receipts"]
    assert len(state(game).requisitions) == 1
    policy = ledger.policy
    ledger.policy = policy.model_copy(update={"m3_approval": None})
    assert "M3_REVIEW_PENDING" in reopened.view(PLAYER)["reason"]


@pytest.mark.parametrize(
    "frame,kind,price", [("THE ENFORCER", "ability_unlock", 2), ("JANUS", "frame_grafting", 3)]
)
def test_frame_acquisition_is_reviewed_owned_and_idempotent(
    ledger, tmp_path, monkeypatch, frame, kind, price
):
    _, game = ready(ledger, frame=frame)
    purchases = FramePurchases(game)
    assert MASTER not in {rule["id"] for rule in purchases.view(PLAYER)["abilities"]["rules"]}
    approved(ledger, game, tmp_path, monkeypatch)
    offer = purchases.view(PLAYER)["abilities"]
    assert (offer["kind"], offer["price"]) == (kind, price)
    assert MASTER in {rule["id"] for rule in offer["rules"]}
    request = {
        "actor": offer["actor"],
        "expected": offer["source_sha256"],
        "kind": kind,
        "rule": MASTER,
        "account": "Record this paid acquisition.",
        "confirmed": True,
    }
    with pytest.raises(ValueError, match="confirm"):
        purchases.acquire(PLAYER, "unconfirmed", {**request, "confirmed": False})
    with pytest.raises(WorkflowError, match="original Girl"):
        purchases.acquire(OTHER, "not-my-ability", request)
    receipt = purchases.acquire(PLAYER, "new-ability", request)
    reopened = FramePurchases(GameService(ledger))
    assert reopened.acquire(PLAYER, "new-ability", request) == receipt
    view = reopened.view(PLAYER)
    assert view["permissions"] == 3 - price
    assert [rule["rule"] for rule in view["abilities"]["enforcer_rules"] if rule["active"]] == [
        MASTER
    ]
    assert MASTER not in {rule["id"] for rule in view["abilities"]["rules"]}
    assert not reopened.view(OTHER)["abilities"]["enforcer_rules"]
