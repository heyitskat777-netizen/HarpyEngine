"""A saved GM proposal survives another process without weakening policy freshness."""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROGRAM = r"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "tools"))
from p2_trial_runtime import Trial
from girlframe.ai.observation import AppendSceneInput
from girlframe.ai.knowledge import Acquisition, KnowledgeProposal
from girlframe.services.onboarding import WorkflowError

directory, phase = Path(sys.argv[1]), sys.argv[2]
trial = Trial(directory, create=phase == "prepare")
gm, pilot = trial.viewers()["gm"], trial.viewers()["lark"]
try:
    if phase == "prepare":
        source = trial.observer.append_scene_input(pilot, trial.scene, AppendSceneInput(
            command_key="sighting",
            expected_scene_revision=trial.observer.status(pilot, trial.scene).scene_revision,
            speaker="pilot", text="A synthetic light flashes.", fictional_channel="private"))
        opened = trial.session.knowledge.open(gm, "request", trial.scene, source.source_id)
        packet = trial.session.knowledge.packet(gm, trial.scene, opened["id"])
        proposal = KnowledgeProposal(request_id=packet.request_id, updates=(Acquisition(
            basis="perception", quote="A synthetic light flashes.",
            recipients=(packet.source.actor,)),))
        saved = trial.session.knowledge.propose(gm, "proposal", trial.scene, opened["id"], proposal)
        (directory / "saved-proposal.json").write_text(json.dumps(saved))
        print(json.dumps({"saved": True}))
    else:
        saved = json.loads((directory / "saved-proposal.json").read_text())
        policy = trial.store.policy
        trial.store.policy = policy.model_copy(update={"owner_table_outcomes": None})
        rejected = False
        try:
            trial.session.knowledge.confirm(gm, "wrong-policy", trial.scene, saved["id"])
        except WorkflowError as error:
            assert "STALE_KNOWLEDGE_PROPOSAL" in str(error)
            rejected = True
        finally:
            trial.store.policy = policy
        assert rejected
        result = trial.session.knowledge.confirm(gm, "confirm", trial.scene, saved["id"])
        assert trial.session.knowledge.confirm(gm, "confirm", trial.scene, saved["id"]) == result
        with trial.store.engine.connect() as c:
            actor = trial.observer._authorize_input(c, pilot, trial.scene, "pilot")[2]
        known = trial.context.build(pilot, trial.scene, actor=actor).model_dump_json()
        assert "A synthetic light flashes." in known
        print(json.dumps({"confirmed": len(result["references"]),
                          "changed_policy_rejected": rejected}))
finally:
    trial.close()
"""


def test_saved_proposal_crosses_process_hash_seeds_but_rejects_changed_policy(tmp_path):
    outputs = []
    for phase, seed in (("prepare", "1"), ("confirm", "2")):
        completed = subprocess.run(
            [sys.executable, "-c", PROGRAM, str(tmp_path / "trial"), phase],
            cwd=ROOT,
            env=os.environ | {"PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        outputs.append(json.loads(completed.stdout.strip().splitlines()[-1]))
    assert outputs == [{"saved": True}, {"confirmed": 1, "changed_policy_rejected": True}]
