"""M1 Discord startup, local checks and trusted database maintenance."""

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.exc import ArgumentError, SQLAlchemyError

from girlframe import __version__
from girlframe.config import load_settings
from girlframe.database.connection import check_database
from girlframe.discord_adapter.config import load_bot_policy, load_bot_token, policy_summary
from girlframe.discord_adapter.runtime import connection_failure_message, serve
from girlframe.engine_adapter.snapshot import SandboxStatusSource
from girlframe.services.engine_status import EngineStatusUnavailable, get_engine_status
from girlframe.services.health import foundation_health


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="HarpyEngine M1 drafts, raw dice ledger and local maintenance"
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("health", help="Check local SQLite access without tokens or network")
    start = commands.add_parser("start", help="Run the guild-scoped Discord bot")
    start.add_argument(
        "--config", type=Path, help="Trusted local JSON policy (never a player input)"
    )
    start.add_argument(
        "--check", action="store_true", help="Validate local policy/sandbox without login"
    )
    commands.add_parser(
        "engine-status", help="Read turn/paused from an explicitly configured sandbox"
    )
    database = commands.add_parser("db", help="Trusted local backup, restore, export or rebuild")
    actions = database.add_subparsers(dest="action", required=True)
    backup = actions.add_parser("backup", help="WAL-consistent private backup to a new file")
    backup.add_argument("--dest", type=Path, required=True)
    restore = actions.add_parser(
        "restore", help="Restore to a new offline file; never replace data"
    )
    restore.add_argument("--source", type=Path, required=True)
    restore.add_argument("--dest", type=Path, required=True)
    export = actions.add_parser("export", help="Export public sheets and published receipts only")
    export.add_argument("--config", type=Path, required=True)
    export.add_argument("--dest", type=Path, required=True)
    rebuild = actions.add_parser("rebuild", help="Rebuild character views from private snapshots")
    rebuild.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "db":
        from girlframe.database.connection import create_database_engine
        from girlframe.database.maintenance import copy_database, database_path, write_export
        from girlframe.services.ledger import CampaignLedger
        from girlframe.services.onboarding import OnboardingStore

        try:
            settings = load_settings()
            if args.action in {"backup", "restore"}:
                source = args.source if args.action == "restore" else database_path(settings)
                copy_database(source, args.dest)
            else:
                policy = load_bot_policy(args.config)
                engine = create_database_engine(settings)
                try:
                    ledger = CampaignLedger(OnboardingStore(engine, policy))
                    if args.action == "export":
                        write_export(args.dest, ledger.public_export())
                    else:
                        ledger.rebuild_projections()
                finally:
                    engine.dispose()
        except Exception:
            print(
                "Database maintenance failed. Check inputs, migrations and new destination; "
                "existing files are never replaced.",
                file=sys.stderr,
            )
            return 1
        print(json.dumps({"operation": args.action, "ok": True}))
        return 0
    if args.command == "start":
        configured_path = args.config or os.environ.get("GIRLFRAME_DISCORD_CONFIG")
        if not configured_path:
            print("Use start --config PATH or set GIRLFRAME_DISCORD_CONFIG.", file=sys.stderr)
            return 2
        try:
            policy = load_bot_policy(Path(configured_path))
            get_engine_status(SandboxStatusSource(policy.sandbox))
        except (OSError, ValueError, EngineStatusUnavailable):
            print("Bot policy or disposable sandbox is invalid; startup refused.", file=sys.stderr)
            return 1
        if args.check:
            print(policy_summary(policy))
            return 0
        try:
            token = load_bot_token()
        except ValueError:
            print(
                "DiscordBot is not available; configure it securely in this environment.",
                file=sys.stderr,
            )
            return 1
        try:
            asyncio.run(serve(policy, token, os.environ.get("HTTPS_PROXY")))
        except KeyboardInterrupt:
            print("Discord bot stopped.")
        except Exception as error:
            print(connection_failure_message(error), file=sys.stderr)
            return 1
        return 0
    if args.command == "engine-status":
        try:
            settings = load_settings()
            if settings.engine_sandbox is None:
                raise EngineStatusUnavailable("Sandbox is not configured")
            status = get_engine_status(SandboxStatusSource(settings.engine_sandbox))
        except (ValidationError, ArgumentError, EngineStatusUnavailable):
            print(
                "Engine status unavailable; configure GIRLFRAME_ENGINE_SANDBOX "
                "with an isolated development runtime.",
                file=sys.stderr,
            )
            return 1
        print(status.model_dump_json())
        return 0
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
