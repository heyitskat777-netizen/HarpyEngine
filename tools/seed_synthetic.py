"""Create a NEW offline M1 pilot database; never seed a configured live database."""

import argparse
import os
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config

from girlframe.config import Settings
from girlframe.database.connection import create_database_engine
from girlframe.discord_adapter.config import BotPolicy
from girlframe.engine.drafts import DraftInput
from girlframe.services.ledger import CampaignLedger
from girlframe.services.onboarding import OnboardingStore
from girlframe.services.read_only_bot import GuildViewer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dest", type=Path, required=True)
    args = parser.parse_args()
    destination = args.dest.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    url = f"sqlite:///{destination}"
    previous = os.environ.get("GIRLFRAME_DATABASE_URL")
    try:
        os.environ["GIRLFRAME_DATABASE_URL"] = url
        command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    finally:
        if previous is None:
            os.environ.pop("GIRLFRAME_DATABASE_URL", None)
        else:
            os.environ["GIRLFRAME_DATABASE_URL"] = previous
    engine = create_database_engine(Settings(database_url=url))
    try:
        policy = BotPolicy(
            application_id=100,
            guild_id=200,
            campaign_id=uuid4(),
            sandbox=destination.parent,
            allow_guild_administrators=True,
        )
        ledger = CampaignLedger(OnboardingStore(engine, policy))
        operator = GuildViewer(1, 200, True, True)
        ledger.create_campaign(operator, "synthetic-create", 0, "Offline Synthetic Pilot")
        ledger.join(operator, "synthetic-join")
        ledger.save_draft(
            operator,
            "synthetic-draft",
            0,
            DraftInput(callsign="SYNTH_A", girl_playbook="OLDGEN", frame_playbook="JANUS-B"),
        )
        ledger.roll_basic(operator, "synthetic-roll", ledger.status(operator)["revision"])
        # Offline metadata only: not a usable Discord policy or executable engine.
        print("Created offline synthetic campaign, draft and OS-backed raw dice receipt.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
