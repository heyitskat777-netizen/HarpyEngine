import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "repository_check", Path(__file__).resolve().parents[1] / "tools/check_repository.py"
)
assert spec is not None and spec.loader is not None
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


@pytest.mark.parametrize("prefix", ["sk-", "mfa.", "ghp_"])
def test_scanner_detects_synthetic_credentials_without_echoing_them(prefix: str) -> None:
    value = prefix + "x" * 40
    findings = checker.inspect_file(Path("example.py"), value.encode())
    assert len(findings) == 1
    assert value not in findings[0]


@pytest.mark.parametrize("name", ["rules.pdf", ".env", "campaign.json", "state.db", "archive.zip"])
def test_scanner_rejects_private_publishable_paths(name: str) -> None:
    assert checker.inspect_file(Path(name), b"synthetic")


def test_scanner_allows_placeholder_example() -> None:
    assert not checker.inspect_file(
        Path(".env.example"), b"GIRLFRAME_DATABASE_URL=sqlite:///./var/x"
    )
