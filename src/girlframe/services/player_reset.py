"""Owner-confirmed reset of an active sheet through HarpyEngine's career archive."""

from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_career_state import CareerArchive
from girlframe.engine.m3_careers import archive_for, binding
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_careers import (
    CareerService,
    end_in_transaction,
    synchronize_end,
)
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def awaiting_replacement(state: GameState, owner: int) -> CareerArchive | None:
    current = binding(state, owner)
    if not current or current.active or str(owner) in state.sheets:
        return None
    archive = next(
        (
            x
            for x in reversed(state.career_archives)
            if x.actor.entity == str(owner) and x.actor.incarnation == current.character
        ),
        None,
    )
    return (
        archive
        if archive
        and archive.ending == "player_reset"
        and archive_for(state, archive.actor) == archive
        else None
    )


def purge_sheet(
    game: GameService, viewer: GuildViewer, key: str, data: dict[str, Any]
) -> dict[str, Any]:
    if (
        data.keys() != {"callsign", "confirmed", "character", "revision"}
        or type(data["revision"]) is not int
        or not isinstance(data["callsign"], str)
        or not isinstance(data["character"], str)
        or data["confirmed"] is not True
    ):
        raise ValueError("Approve the reset and type the current callsign.")

    def perform(c: Connection) -> dict[str, Any]:
        game.unpaused(c)
        CareerService(game.store)._idle(c)
        state = load_state(c, game.store.campaign_id)
        sheet = state.sheets.get(str(viewer.user_id))
        if (
            not sheet
            or sheet.character_id != data["character"]
            or sheet.revision != data["revision"]
            or sheet.callsign != data["callsign"].strip()
        ):
            raise WorkflowError(
                "The callsign or character revision does not match your active sheet."
            )
        actor = current_ref(state, viewer.user_id)
        event, archive = str(uuid4()), str(uuid4())
        account = "The owner confirmed the callsign and restarted their enrollment."
        changed = end_in_transaction(
            c,
            game,
            state,
            actor,
            reason="player_reset",
            source_event=event,
            account=account,
            archive_id=archive,
        )
        game.event(
            c,
            viewer.user_id,
            key,
            "m3.player_sheet_reset",
            changed,
            event_id=event,
            archive_id=archive,
        )
        synchronize_end(c, game, changed.career_archives[-1])
        return {"archive_id": archive, "state": "new_enrollment"}

    try:
        return game.store._write(
            viewer,
            key,
            "m3.player_sheet_reset",
            data,
            perform,
            authorize=lambda c: Access(game.store).authorize(c, viewer, "playbooks"),
            auto_audit=False,
        )
    except ValueError as error:
        raise WorkflowError(str(error)) from None
