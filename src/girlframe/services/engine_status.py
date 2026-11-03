"""Local read-only service. Discord authorization is required before network exposure."""

from typing import Protocol

from girlframe.engine.status import PublicCampaignStatus


class EngineStatusUnavailable(RuntimeError):
    """A sanitized failure; no paths, raw state, or underlying exceptions for users."""


class EngineStatusSource(Protocol):
    def read_status(self) -> PublicCampaignStatus:
        """Return only the approved status projection, without side effects."""
        ...


def get_engine_status(source: EngineStatusSource) -> PublicCampaignStatus:
    return source.read_status()
