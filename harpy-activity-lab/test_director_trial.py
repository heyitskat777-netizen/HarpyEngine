"""The Activity boundary retains the native owner and source of a GM proposal."""

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("girlframe.services.director_session")

from girlframe.services.onboarding import WorkflowError
from test_director_adjudication import prepare
from test_director_conversation import routed as routed_fixture
from test_director_observation import observed as observed_fixture
from test_ledger import ADMIN, OTHER, PLAYER
from test_ledger import ledger as ledger_fixture
from test_m2_game import tick

from director_trial import DirectorTrial, open_trial
from discord_session import DiscordConfig

ledger = ledger_fixture
observed = observed_fixture
routed = routed_fixture


def test_discord_trial_cannot_reassign_existing_persona_receipts(tmp_path, monkeypatch):
    expected = DiscordConfig(
        "111111111111111111",
        "fixture",
        "222222222222222222",
        "333333333333333333",
        other_user_id="444444444444444444",
        handler_user_id="555555555555555555",
    )
    trial = tmp_path / "p2-discord-trials" / "rehearsal"
    trial.mkdir(parents=True)
    (trial / "activity-discord-binding.json").write_text(
        json.dumps(
            {
                "application": expected.client_id,
                "guild": expected.guild_id,
                "accounts": {
                    "invited": expected.invited_user_id,
                    "other": expected.other_user_id,
                    "handler": "666666666666666666",
                },
            }
        ),
        encoding="utf-8",
    )
    with monkeypatch.context() as local:
        local.delenv("GIRLFRAME_RULES_REGISTRY", raising=False)
        with pytest.raises(WorkflowError, match="original Discord roster"):
            open_trial(
                tmp_path,
                tmp_path / "p2-activity-trials",
                "rehearsal",
                discord_config=expected,
            )


def test_activity_proposal_uses_native_choice_and_retains_confirmed_outcome(routed):
    observer, context, scene, game, dice = routed
    _, _, action, worker, gateway = prepare(
        routed, "Keep the needle steady.", "trial-prepare"
    )
    trial = SimpleNamespace(
        scene=scene,
        viewers=lambda: {"handler": ADMIN, "lark": PLAYER, "kite": OTHER},
        store=game.store,
        observer=observer,
        context=context,
    )
    adapter = DirectorTrial(trial)
    gm = adapter.perform(ADMIN, "work", {"operation": "gm-work"})
    source = next(item for item in gm["outcome_sources"] if item["operation"] == "keep")
    opened = adapter.perform(
        ADMIN,
        "open-work",
        {
            "operation": "open",
            "kind": "choice",
            "source": source["source_id"],
            "frame": {
                "stakes": "Hold the mark",
                "demands": [
                    {
                        "id": "steady",
                        "question": "Can the pilot hold the needle steady?",
                    }
                ],
            },
        },
    )
    proposed = adapter.perform(
        ADMIN,
        "propose-work",
        {
            "operation": "propose",
            "request": opened["request"],
            "proposal": {
                "request_id": opened["packet"]["request_id"],
                "decision": {
                    "kind": "keep",
                    "verdict": "enough",
                    "narration": "The needle holds.",
                    "assessments": [
                        {
                            "demand_id": "steady",
                            "sufficient": True,
                            "evidence_ids": ["source", "native", "traits"],
                            "traits": [{"trait": "in_control", "polarity": "are"}],
                            "private_reason": "PRIVATE_ASSESSMENT_CANARY",
                        }
                    ],
                },
                "cited_evidence": ["source", "native"],
                "private_reasoning": "PRIVATE_GM_CANARY",
            },
        },
    )
    review = {"operation": "review", "proposal": proposed["id"]}
    with pytest.raises(WorkflowError, match="GM_OUTCOME_NOT_OWNED"):
        adapter.perform(OTHER, "wrong-owner", review)
    assert "PRIVATE_" not in json.dumps(adapter.perform(ADMIN, "review-work", review))
    confirm = {"operation": "confirm", "proposal": proposed["id"], "approved": True}
    saved = adapter.perform(ADMIN, "confirm-work", confirm)
    with pytest.raises(WorkflowError):
        adapter.perform(OTHER, "wrong-confirm", confirm)
    tick(worker, gateway, 5)
    reopened = DirectorTrial(trial)
    assert reopened.perform(ADMIN, "confirm-work", confirm) == saved
    assert reopened.view(ADMIN)["work"]["proposals"][0]["status"] == "confirmed"
    assert game.inspect(PLAYER, action)["state"] == "complete" and dice.calls == 1
