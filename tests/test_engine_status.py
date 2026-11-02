import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from girlframe.__main__ import main
from girlframe._vendor.harpyframe import read_only_bridge
from girlframe.config import Settings, load_settings
from girlframe.engine.status import PublicCampaignStatus
from girlframe.engine_adapter.snapshot import SANDBOX_MARKER, SandboxStatusSource
from girlframe.services.engine_status import EngineStatusUnavailable, get_engine_status


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    root = tmp_path / "disposable"
    (root / "state").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "scripts/gm.py").write_text("# Synthetic placeholder; never executed.\n")
    (root / SANDBOX_MARKER).write_text("Synthetic disposable runtime\n")
    (root / "state/campaign.json").write_text(
        json.dumps({"turn": 7, "paused": True, "gm_only": {"secret": "SYNTHETIC_CANARY"}})
    )
    return root


def test_read_only_service_projects_exact_fields_without_mutation(sandbox: Path) -> None:
    before = {
        str(p.relative_to(sandbox)): p.read_bytes() for p in sandbox.rglob("*") if p.is_file()
    }
    result = get_engine_status(SandboxStatusSource(sandbox))
    assert result.model_dump() == {"turn": 7, "paused": True}
    assert "SYNTHETIC_CANARY" not in result.model_dump_json()
    assert before == {
        str(p.relative_to(sandbox)): p.read_bytes() for p in sandbox.rglob("*") if p.is_file()
    }


def test_status_cli_uses_no_database_or_private_output(
    sandbox: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIRLFRAME_ENGINE_SANDBOX", str(sandbox))
    assert main(["engine-status"]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == {"turn": 7, "paused": True}
    assert not output.err
    assert not (tmp_path / "var").exists()


def test_engine_config_is_opt_in_and_absolute(sandbox: Path) -> None:
    assert load_settings({}).engine_sandbox is None
    assert load_settings({"GIRLFRAME_ENGINE_SANDBOX": str(sandbox)}).engine_sandbox == sandbox
    with pytest.raises(ValidationError):
        Settings(engine_sandbox=Path("runtime/dev"))


def test_unconfigured_status_fails_closed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GIRLFRAME_ENGINE_SANDBOX", raising=False)
    assert main(["engine-status"]) == 1
    output = capsys.readouterr()
    assert not output.out
    assert "GIRLFRAME_ENGINE_SANDBOX" in output.err


@pytest.mark.parametrize(
    "payload",
    [
        [],
        None,
        {"turn": True, "paused": True},
        {"turn": -1, "paused": True},
        {"turn": "7", "paused": True},
        {"turn": 7, "paused": "true"},
        {"turn": 7},
        {"paused": True},
    ],
)
def test_invalid_status_types_rejected(sandbox: Path, payload: object) -> None:
    (sandbox / "state/campaign.json").write_text(json.dumps(payload))
    with pytest.raises(EngineStatusUnavailable, match="^Engine sandbox status is unavailable.$"):
        get_engine_status(SandboxStatusSource(sandbox))


@pytest.mark.parametrize("data", [b'{"secret": "SYNTHETIC_CANARY",', b"\xff\xfeinvalid"])
def test_parse_failures_hide_raw_input_and_paths(
    sandbox: Path, data: bytes, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (sandbox / "state/campaign.json").write_bytes(data)
    monkeypatch.setenv("GIRLFRAME_ENGINE_SANDBOX", str(sandbox))
    assert main(["engine-status"]) == 1
    output = capsys.readouterr()
    assert not output.out
    assert "SYNTHETIC_CANARY" not in output.err
    assert str(sandbox) not in output.err
    assert "Traceback" not in output.err


@pytest.mark.parametrize("missing", [SANDBOX_MARKER, "scripts/gm.py", "state/campaign.json"])
def test_incomplete_or_canonical_template_is_not_accepted(sandbox: Path, missing: str) -> None:
    (sandbox / missing).unlink()
    with pytest.raises(EngineStatusUnavailable):
        get_engine_status(SandboxStatusSource(sandbox))


def test_symlinked_snapshot_is_rejected(sandbox: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text('{"turn": 100, "paused": false}')
    state = sandbox / "state/campaign.json"
    state.unlink()
    state.symlink_to(outside)
    with pytest.raises(EngineStatusUnavailable):
        get_engine_status(SandboxStatusSource(sandbox))


def test_symlinked_sandbox_is_rejected(sandbox: Path, tmp_path: Path) -> None:
    link = tmp_path / "link"
    link.symlink_to(sandbox, target_is_directory=True)
    with pytest.raises(EngineStatusUnavailable):
        get_engine_status(SandboxStatusSource(link))


def test_oversize_snapshot_fails_closed(sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(read_only_bridge, "MAX_SNAPSHOT_BYTES", 16)
    with pytest.raises(EngineStatusUnavailable):
        get_engine_status(SandboxStatusSource(sandbox))


def test_public_projection_rejects_extra_private_fields() -> None:
    with pytest.raises(ValidationError):
        PublicCampaignStatus.model_validate({"turn": 7, "paused": True, "secret": "canary"})
