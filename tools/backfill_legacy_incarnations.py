"""Offline source-aware identity backfill; dry-run by default and no Discord/token access."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import URL
from sqlalchemy.exc import SQLAlchemyError

from girlframe.config import Settings
from girlframe.database.connection import create_database_engine
from girlframe.discord_adapter.config import load_bot_policy
from girlframe.services.m3_incarnations import backfill
from girlframe.services.onboarding import OnboardingStore, WorkflowError


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--operator", default="offline-maintenance")
    parser.add_argument("--key", default=str(uuid4()))
    args = parser.parse_args()
    if not args.database.is_file() or not args.operator.strip() or len(args.operator) > 100:
        parser.error("Use an existing local SQLite database and a bounded operator label.")
    engine = create_database_engine(
        Settings(database_url=str(URL.create("sqlite", database=str(args.database.resolve()))))
    )
    try:
        store = OnboardingStore(engine, load_bot_policy(args.policy))
        print(json.dumps(backfill(store, apply=args.apply, key=args.key, operator=args.operator)))
    except (WorkflowError, ValueError, SQLAlchemyError):
        parser.exit(1, "Identity backfill did not commit; recover the original source or policy.\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
