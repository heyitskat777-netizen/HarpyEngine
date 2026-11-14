"""Reversed counter pin permits its original owner to Flirt with the real pinner."""

from test_ankou_low_pin_keep import episode
from test_ledger import ledger as ledger


def test_native_beneath_counter_feedback_low_pin_continues_actual_owned_flirt(
    ledger, tmp_path, monkeypatch
):
    episode(ledger, tmp_path, monkeypatch, recipe="flirt")
