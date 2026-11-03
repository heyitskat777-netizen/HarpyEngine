"""Create a synthetic, status-only test fixture and trusted private-guild policy.

This is not a playable engine bootstrap. No credentials are read or written.
"""

import argparse
from pathlib import Path
from uuid import uuid4

from girlframe.discord_adapter.config import BotPolicy
from girlframe.engine_adapter.snapshot import SANDBOX_MARKER


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--application-id", type=int, required=True)
    parser.add_argument("--guild-id", type=int, required=True)
    parser.add_argument("--approve-admin-status", action="store_true")
    parser.add_argument("--dest", type=Path, default=Path("var/discord-dev"))
    args = parser.parse_args()
    destination = args.dest.resolve()
    sandbox = destination / "sandbox"
    policy = BotPolicy(
        application_id=args.application_id,
        guild_id=args.guild_id,
        campaign_id=uuid4(),
        sandbox=sandbox,
        allow_guild_administrators=True,
        status_audience_approved=args.approve_admin_status,
    )
    # Never replace an existing deployment or reset somebody's selected snapshot.
    destination.mkdir(parents=True, exist_ok=False)
    (sandbox / "scripts").mkdir(parents=True)
    (sandbox / "state").mkdir()
    (sandbox / "scripts/gm.py").write_text(
        "# Synthetic status-only fixture. Not a runnable game engine.\n"
    )
    (sandbox / SANDBOX_MARKER).write_text("Synthetic status-only test fixture; never canon.\n")
    (sandbox / "state/campaign.json").write_text('{"turn":0,"paused":true}\n')
    (destination / "policy.json").write_text(policy.model_dump_json(indent=2) + "\n")
    print(f"Created synthetic status fixture and local policy: {destination / 'policy.json'}")


if __name__ == "__main__":
    main()
