"""One sustained normal session guards the integrated offline candidate in focused CI."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from p2_trial_runtime import Trial  # noqa: E402
from run_p2_session_trials import SCENARIOS, SceneTrial  # noqa: E402


def test_sustained_session_retains_memory_and_replays_native_outcomes(tmp_path):
    trial = Trial(tmp_path / "sustained", create=True)
    try:
        result = SceneTrial(trial).run(SCENARIOS[0])
        assert result["player_inputs"] == 100
        assert result["native_plays"] == result["dice_rolls"] == 2
        assert result["keep_enough"] is True
        assert result["pending_native_work"] == 0
        assert sum(result["handler_decisions"].values()) == 100
        assert result["raw_history_omitted"] > 0
    finally:
        trial.close()
