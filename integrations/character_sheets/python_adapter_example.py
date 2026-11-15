"""Offline codec example; no Discord connection, database write or activation."""

import argparse
from pathlib import Path

from girlframe.engine.character_documents import parse_draft


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path)
    args = parser.parse_args()
    document = parse_draft(args.document.read_bytes())
    print("Valid creation document:", document.profile.callsign)
    print("Girl:", document.profile.girl_playbook, "| Frame:", document.profile.frame_playbook)
    print("Saved/activated: no — use an authorized engine preview and confirmation.")


if __name__ == "__main__":
    main()
