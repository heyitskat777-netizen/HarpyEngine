"""Profile bindings for a caller-verified canonical state, without present-day aliases."""

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ProfileBinding
from girlframe.engine.m3_careers import profile_character
from girlframe.services.onboarding import WorkflowError


def snapshot_profiles(c: Connection, campaign: str, state: GameState) -> tuple[ProfileBinding, ...]:
    """Caller proves the event/state; these bindings do not grant current authority."""
    bindings = []
    for sheet in state.sheets.values():
        profile = c.scalar(
            sa.select(t.snapshots.c.character_id).where(
                t.snapshots.c.campaign_id == campaign,
                t.snapshots.c.user_id == str(sheet.owner),
                t.snapshots.c.revision == sheet.source_profile_revision,
            )
        )
        if profile is None:
            raise WorkflowError("Recover the original state's actual profile snapshot")
        bindings.append(
            ProfileBinding(
                owner=sheet.owner,
                character_id=profile_character(
                    state, sheet.owner, profile, sheet.source_profile_revision
                ),
                profile_revision=sheet.source_profile_revision,
                source_character_id=profile,
                source_profile_revision=sheet.source_profile_revision,
            )
        )
    return tuple(bindings)
