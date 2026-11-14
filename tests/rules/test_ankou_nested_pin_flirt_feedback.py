"""An actual pinned Ankou Flirt must resolve its own final-Identity Feedback."""

import pytest
from test_ankou_nested_pin_feedback import episode
from test_ledger import ledger as ledger


@pytest.mark.parametrize("given", [True, False])
def test_native_nested_pin_flirt_feedback_preserves_owned_results(
    ledger, tmp_path, monkeypatch, given
):
    episode(ledger, tmp_path, monkeypatch, given, recipe="flirt")
