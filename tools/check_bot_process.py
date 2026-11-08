"""Read-only local bot process count; never print command arguments or credentials."""

import argparse
import json
from pathlib import Path


# The supported launcher uses Python's -m girlframe start, optionally with -u.
def is_bot(arguments: list[bytes]) -> bool:
    if not arguments or b"python" not in Path(arguments[0].decode(errors="replace")).name.encode():
        return False
    index = 1
    flags = {b"-u", b"-B", b"-b", b"-bb", b"-E", b"-I", b"-s", b"-S", b"-q", b"-O", b"-OO", b"-v"}
    while index < len(arguments):
        current = arguments[index]
        if current == b"-m":
            return arguments[index + 1 : index + 3] == [b"girlframe", b"start"]
        if current in flags:
            index += 1
        elif current in (b"-X", b"-W"):
            index += 2
        elif current.startswith((b"-X", b"-W")):
            index += 1
        else:
            return False  # A script/-c/-- is not the supported module launcher.
    return False


def running(proc: Path = Path("/proc")) -> list[int]:
    result = []
    for entry in proc.glob("[0-9]*/cmdline"):
        try:
            arguments = entry.read_bytes().rstrip(b"\0").split(b"\0")
            if is_bot(arguments):
                result.append(int(entry.parent.name))
        except (OSError, ValueError):
            continue  # A process may exit between directory and command-line reads.
    return sorted(result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-one", action="store_true")
    args = parser.parse_args()
    processes = running()
    print(json.dumps({"running_discord_bot_processes": len(processes), "pids": processes}))
    return int(args.expect_one and len(processes) != 1)


if __name__ == "__main__":
    raise SystemExit(main())
