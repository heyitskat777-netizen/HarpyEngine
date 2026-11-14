"""Rejected session Plays identify the actual registry blocker without opening it."""

import json
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_consume import ready
from test_ledger import PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import state
from test_registry import data

from girlframe.database import tables as t
from girlframe.engine.m2 import PlayInput
from girlframe.engine.rules_registry import Registry
from girlframe.services.m3_access import digest, load_registry
from girlframe.services.onboarding import WorkflowError

ledger = ledger_fixture


def test_unavailable_rule_reports_canonical_public_metadata_only():
    registry = Registry.model_validate_json(json.dumps(data()))
    entry = next(x for x in registry.entries if x.aliases)
    with pytest.raises(ValueError) as raised:
        registry.require_available(entry.aliases[0])
    message = str(raised.value)
    assert message.startswith("UNSUPPORTED_RULE: implementation and review are incomplete")
    assert f"rule={entry.id};" in message
    assert "implementation=subset" in message
    assert "source_audit=inventoried" in message
    assert "independent_review=pending" in message
    assert entry.aliases[0] not in message
    assert not entry.verified and registry.coverage == "RULES_SUBSET"
    with pytest.raises(ValueError, match="^UNSUPPORTED_RULE: unknown registry entry$"):
        registry.require_available("PRIVATE_UNKNOWN_RULE_INPUT")


def test_consume_keep_rejection_identifies_starvation_without_roll_or_state_change(
    ledger, tmp_path, monkeypatch
):
    game, worker, gateway, controls = ready(ledger, tmp_path, monkeypatch)
    temporary = load_registry().model_dump(mode="json")
    original = next(x for x in data()["entries"] if x["id"] == "frame.consume.starvation")
    temporary["entries"] = [
        original if x["id"] == original["id"] else x for x in temporary["entries"]
    ]
    registry = Registry.model_validate_json(json.dumps(temporary))
    path = tmp_path / "synthetic-approved-except-real-starvation-gate.json"
    path.write_text(registry.model_dump_json())
    monkeypatch.setenv("GIRLFRAME_RULES_REGISTRY", str(path))
    ledger.policy = ledger.policy.model_copy(
        update={
            "m3_approval": ledger.policy.m3_approval.model_copy(
                update={"registry_sha256": digest(registry)}
            )
        }
    )
    before = state(game).model_dump_json()
    before_rolls = game.dice.calls
    with ledger.engine.connect() as c:
        before_actions = c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_actions"]))
    with pytest.raises(WorkflowError) as raised:
        game.begin(
            PLAYER,
            str(uuid4()),
            900,
            state(game).sheets["2"].revision,
            PlayInput(
                play="keep_your_head",
                heat=0,
                context="PRIVATE_DIAGNOSTIC_SESSION_CONTEXT",
                trigger_confirmed=True,
            ),
        )
    message = str(raised.value)
    assert "rule=frame.consume.starvation;" in message
    assert "implementation=subset" in message
    assert "independent_review=pending" in message
    assert "PRIVATE_DIAGNOSTIC_SESSION_CONTEXT" not in message
    assert state(game).model_dump_json() == before
    assert game.dice.calls == before_rolls
    with ledger.engine.connect() as c:
        assert (
            c.scalar(sa.select(sa.func.count()).select_from(t.m2["m2_actions"])) == before_actions
        )
