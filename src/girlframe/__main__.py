"""Offline CLI and explicit no-token startup boundary."""

import argparse
import json
import sys
from collections.abc import Sequence

from pydantic import ValidationError
from sqlalchemy.exc import ArgumentError, SQLAlchemyError

from girlframe import __version__
from girlframe.config import load_settings
from girlframe.database.connection import check_database
from girlframe.services.health import foundation_health


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GIRL FRAME M0 offline foundation")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("health", help="Check local SQLite access without tokens or network")
    commands.add_parser("start", help="Report the unimplemented Discord runtime (exit 2)")
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "start":
        print(
            "M0 has no Discord runtime. Use 'health' for the offline startup check.",
            file=sys.stderr,
        )
        return 2
    try:
        settings = load_settings()
        check_database(settings)
    except (ValidationError, ArgumentError, SQLAlchemyError, OSError):
        # Never print raw configuration, database errors, or possible credentials.
        print(
            "Local database check failed; verify GIRLFRAME_DATABASE_URL and file access.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(foundation_health(database_checked=True), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
