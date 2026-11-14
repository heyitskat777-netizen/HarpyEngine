"""Friendly early rejection; SQL triggers are the authoritative persistence barrier."""

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.services.onboarding import WorkflowError


def require_canonical_writable(connection: Connection, campaign: str) -> None:
    """Do not infer selective safety from owner labels or the current incarnation.

    Any draining history conservatively blocks this campaign's whole canonical
    state. It does not block every side table or external worker, and cannot be
    used as evidence that a source has been parked or that a freeze is complete.
    """
    if (
        connection.scalar(
            sa.select(t.actor_availability.c.generation)
            .where(
                t.actor_availability.c.campaign_id == campaign,
                t.actor_availability.c.phase == "draining",
            )
            .limit(1)
        )
        is not None
    ):
        raise WorkflowError(
            "CANONICAL_DRAINING: canonical gameplay changes are unavailable. "
            "No completed freeze or safe rejoin is established."
        )
