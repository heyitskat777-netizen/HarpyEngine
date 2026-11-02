import ast
import asyncio
import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from girlframe.__main__ import main
from girlframe.config import Settings, load_settings
from girlframe.discord_adapter.fake import FakeDiscordTransport
from girlframe.engine.identity import RequestContext, RequestPrincipal
from girlframe.services.health import respond_health


def test_help_without_configuration(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as result:
        main(["--help"])
    assert result.value.code == 0
    assert "health" in capsys.readouterr().out


def test_health_creates_local_database_without_secrets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "new" / "health.db"
    monkeypatch.setenv("GIRLFRAME_DATABASE_URL", f"sqlite:///{db}")
    assert main(["health"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result == {
        "milestone": "M0",
        "status": "foundation_ok",
        "database_checked": True,
        "discord_connected": False,
        "rules_implemented": False,
    }
    assert db.is_file()


def test_failed_health_does_not_expose_config(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "synthetic-private-value"
    monkeypatch.setenv("GIRLFRAME_DATABASE_URL", f"postgresql://user:{secret}@example.invalid/db")
    assert main(["health"]) == 1
    output = capsys.readouterr()
    assert not output.out
    assert secret not in output.err
    assert "failed" in output.err


def test_unwritable_database_reports_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    blocker = tmp_path / "file-not-directory"
    blocker.write_text("synthetic")
    monkeypatch.setenv("GIRLFRAME_DATABASE_URL", f"sqlite:///{blocker}/db.sqlite")
    assert main(["health"]) == 1
    assert "failed" in capsys.readouterr().err


def test_start_does_not_claim_bot_is_running(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["start"]) == 2
    assert "no Discord runtime" in capsys.readouterr().err


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://example.invalid/db",
        "sqlite://",
        "sqlite:///x?uri=true",
        "sqlite+pysqlite:///x",
    ],
)
def test_configuration_rejects_unsupported_backends(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(database_url=url)


def test_configuration_is_explicit_and_immutable() -> None:
    settings = load_settings({})
    assert settings.database_url == "sqlite:///./var/girlframe.db"
    with pytest.raises(ValidationError):
        settings.database_url = "sqlite:///:memory:"


@pytest.mark.parametrize("bad_id", [0, -1, 2**64, True, "123", 1.5])
def test_identity_rejects_invalid_or_coerced_snowflakes(bad_id: object) -> None:
    with pytest.raises(ValidationError):
        RequestPrincipal.model_validate({"user_id": bad_id, "guild_id": 123})


def test_identity_does_not_accept_claimed_authority() -> None:
    with pytest.raises(ValidationError):
        RequestPrincipal.model_validate({"user_id": 123, "guild_id": 456, "role": "owner"})


def test_offline_service_responds_only_to_addressed_interaction() -> None:
    fake = FakeDiscordTransport()
    context = RequestContext(
        principal=RequestPrincipal(user_id=123456789012345678, guild_id=234567890123456789),
        campaign_id=UUID("00000000-0000-4000-8000-000000000001"),
        interaction_id=345678901234567890,
    )
    asyncio.run(respond_health(context, fake))
    assert len(fake.responses) == 1
    response = fake.responses[0]
    assert response.principal == context.principal
    assert response.interaction_id == context.interaction_id
    assert "not implemented" in response.content


def test_engine_import_boundaries() -> None:
    root = Path(__file__).resolve().parents[1] / "src/girlframe/engine"
    forbidden = {"discord", "openai", "sqlalchemy", "alembic"}
    forbidden_internal = {
        "database",
        "discord_adapter",
        "engine_adapter",
        "_vendor",
        "services",
        "ai",
        "delivery",
        "gm",
        "handler",
    }
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            imports = []
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0, f"Review relative domain import: {path}"
                imports = [node.module or ""]
                if node.module == "girlframe":
                    imports += [f"girlframe.{alias.name}" for alias in node.names]
            for name in imports:
                parts = name.split(".")
                assert parts[0] not in forbidden, (path, name)
                assert not (
                    len(parts) > 1 and parts[0] == "girlframe" and parts[1] in forbidden_internal
                ), (path, name)
