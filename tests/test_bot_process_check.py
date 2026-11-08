"""Prevent a false 'offline' report from launching a duplicate bot worker."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "check_bot_process", Path(__file__).resolve().parents[1] / "tools/check_bot_process.py"
)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


@pytest.mark.parametrize(
    "arguments,expected",
    [
        ([b"python", b"-u", b"-m", b"girlframe", b"start", b"--config", b"private-policy"], True),
        ([b"/venv/python3", b"-m", b"girlframe", b"start"], True),
        ([b"python", b"-X", b"dev", b"-Wignore", b"-u", b"-m", b"girlframe", b"start"], True),
        ([b"python", b"script.py", b"-m", b"girlframe", b"start"], False),
        ([b"python", b"-c", b"script text", b"-m", b"girlframe", b"start"], False),
        ([b"bash", b"-m", b"girlframe", b"start"], False),
        ([b"python", b"-m", b"girlframe", b"health"], False),
        ([b"python", b"-m", b"girlframe"], False),
    ],
)
def test_supported_bot_launcher_recognizes_python_flags_and_excludes_nonbots(arguments, expected):
    assert checker.is_bot(arguments) is expected


def test_count_reports_only_actual_modules_without_printing_arguments(tmp_path, capsys):
    for pid, arguments in (
        (1, [b"python", b"-u", b"-m", b"girlframe", b"start"]),
        (2, [b"python", b"sensitive-other-script", b"PRIVATE_VALUE"]),
    ):
        folder = tmp_path / str(pid)
        folder.mkdir()
        (folder / "cmdline").write_bytes(b"\0".join(arguments) + b"\0")
    assert checker.running(tmp_path) == [1]
    assert "PRIVATE_VALUE" not in capsys.readouterr().out
