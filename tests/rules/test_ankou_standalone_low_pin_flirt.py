"""The original low-pinned Ankou owns her actual Flirt and later follow-through."""

from test_ankou_standalone_low_pin_keep import episode
from test_ledger import ledger as ledger


def test_standalone_accepted_feedback_low_pin_continues_actual_owned_flirt(
    ledger, tmp_path, monkeypatch
):
    episode(ledger, tmp_path, monkeypatch, recipe="flirt")
