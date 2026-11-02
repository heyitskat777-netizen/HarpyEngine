"""Read an explicitly selected disposable runtime, never discover canonical state."""

from dataclasses import dataclass
from pathlib import Path

from girlframe._vendor.harpyframe.read_only_bridge import load_public_status
from girlframe.engine.status import PublicCampaignStatus
from girlframe.services.engine_status import EngineStatusUnavailable

SANDBOX_MARKER = "SANDBOX_NONCANONICAL_DO_NOT_SYNC.md"


@dataclass(frozen=True)
class SandboxStatusSource:
    sandbox: Path

    def read_status(self) -> PublicCampaignStatus:
        try:
            if not self.sandbox.is_absolute() or self.sandbox.is_symlink():
                raise ValueError("Invalid sandbox")
            root = self.sandbox.resolve(strict=True)
            paths = [
                root / SANDBOX_MARKER,
                root / "scripts",
                root / "scripts/gm.py",
                root / "state",
                root / "state/campaign.json",
            ]
            if any(path.is_symlink() for path in paths):
                raise ValueError("Symlinked sandbox files are unsupported")
            if not all(path.is_file() for path in (paths[0], paths[2], paths[-1])):
                raise ValueError("Not a bootstrapped sandbox")
            return PublicCampaignStatus.model_validate(load_public_status(paths[-1]))
        except (OSError, ValueError, RecursionError):
            raise EngineStatusUnavailable("Engine sandbox status is unavailable.") from None
