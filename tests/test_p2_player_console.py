"""A human can reopen a held native Play and finish private GM/owner review offline."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from p2_trial_runtime import Trial  # noqa: E402
from playtest_director_session import Console  # noqa: E402

from girlframe.ai.gm_outcomes import KeepOutcome, OutcomeProposal  # noqa: E402
from girlframe.ai.gm_protocol import Assessment, TraitClaim  # noqa: E402
from girlframe.services.onboarding import WorkflowError  # noqa: E402


def test_console_reopens_held_play_retains_native_keys_and_finishes_gm_review(tmp_path):
    directory = tmp_path / "player-trial"
    trial = Trial(directory, create=True)
    try:
        console = Console(trial)
        first = console.execute("Handler, what is the established objective?")
        assert console.execute("/retry") == first
        declaration = console.execute(
            "GM, I choose Keep Your Head to hold the calibration needle steady."
        )
        review_id = declaration["conversation"]["gm"]["play_review_id"]
        action = console.execute(
            '/play {"play":"keep_your_head", "heat":0, "trigger_confirmed":true}'
        )["action_id"]
        assert trial.dice.calls == 1
        for role in ("lark", "kite", "gm"):
            console.execute("/as " + role)
            row = next(x for x in console.execute("/choices") if x["kind"] == "tag_window")
            committed = console.execute("/choice " + row["id"] + ' {"options":["pass"]}')
            assert console.execute("/retry") == committed
        trial.close()
        trial = Trial(directory)
        console = Console(trial)
        assert trial.dice.calls == 1
        console.execute("/as lark")
        row = next(x for x in console.execute("/choices") if x["kind"] == "actor_keep")
        console.execute(
            "/choice " + row["id"] + ' {"options":["in_control","tough"],"denied":["desperate"]}'
        )
        console.execute("/as gm")
        binding = console.execute("/bind " + review_id + " " + action)
        assert binding["mechanics_applied"] is False
        assert console.execute("/retry") == binding
        work = console.execute("/work")
        source = next(x for x in work["outcome_sources"] if x["operation"] == "keep")
        console.execute(
            '/frame {"stakes":"Hold the calibration needle steady",'
            '"demands":[{"id":"control","question":"Can the pilot maintain precision?"}]}'
        )
        request = console.execute("/propose choice " + source["source_id"])
        folder = Path(request["directory"])
        packet = json.loads((folder / "request.json").read_text())
        assert packet["native"]["action"]["id"] == action
        proposal = OutcomeProposal(
            request_id=packet["request_id"],
            decision=KeepOutcome(
                verdict="enough",
                narration="The needle stays steady.",
                assessments=(
                    Assessment(
                        demand_id="control",
                        sufficient=True,
                        evidence_ids=("traits", "source", "native"),
                        traits=(TraitClaim(trait="in_control", polarity="are"),),
                        private_reason="SYNTHETIC_ASSESSMENT_PRIVATE_CANARY",
                    ),
                ),
            ),
            cited_evidence=("source", "native"),
            private_reasoning="SYNTHETIC_PROPOSAL_PRIVATE_CANARY",
        )
        (folder / "proposal.json").write_text(proposal.model_dump_json())
        saved = console.execute("/load " + request["id"] + " " + str(folder / "proposal.json"))
        review = console.execute("/review " + saved["id"])
        assert "SYNTHETIC_ASSESSMENT_PRIVATE_CANARY" not in json.dumps(review)
        assert "SYNTHETIC_PROPOSAL_PRIVATE_CANARY" not in json.dumps(review)
        console.execute("/as lark")
        with pytest.raises(WorkflowError, match="NOT_OWNED"):
            console.execute("/confirm " + saved["id"])
        console.execute("/as gm")
        result = console.execute("/confirm " + saved["id"])
        assert console.execute("/retry") == result
        assert trial.game.inspect(trial.viewers()["lark"], action)["state"] == "complete"
        assert trial.dice.calls == 1
        assert not console.execute("/work")["native"]["choices"]
        assert console.execute("/work")["declarations"][0]["status"] == "native_complete"
        assert folder.stat().st_mode & 0o777 == 0o700
        assert (folder / "request.json").stat().st_mode & 0o777 == 0o600
    finally:
        trial.close()
