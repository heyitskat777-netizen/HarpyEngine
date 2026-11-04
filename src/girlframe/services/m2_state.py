"""M2 private-state persistence and explicit public projection helpers."""

from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState, PilotSheet


def load_state(connection: Connection, campaign: str) -> GameState:
    table = t.m2["m2_state"]
    value = connection.scalar(sa.select(table.c.body_json).where(table.c.campaign_id == campaign))
    return GameState.model_validate_json(value) if value else GameState()


def active(connection: Connection, campaign: str, owner: int) -> bool:
    return str(owner) in load_state(connection, campaign).sheets


def public_sheet(sheet: PilotSheet, state: GameState) -> dict[str, Any]:
    result: dict[str, Any] = {
        "callsign": sheet.callsign,
        "girl_playbook": sheet.girl,
        "frame_playbook": sheet.frame,
        "status": "active_m2_subset",
        "game_revision": sheet.revision,
    }
    draft = sheet.review.creation
    for field in ("frame_name", "frame_appearance"):
        if field in sheet.public_fields:
            result[field] = (
                getattr(sheet.frame_runtime, field)
                if sheet.frame_runtime
                else getattr(draft, field)
            )
    if "appearance" in sheet.public_fields:
        result["appearance"] = draft.girl_appearance
    if "identities" in sheet.public_fields:
        result["identities"] = [x.name for x in sheet.identities]
    if "assets" in sheet.public_fields:
        result["assets"] = [
            {
                "name": x.name,
                "family": x.family,
                "damaged": x.damaged,
                **(
                    {"description": x.description}
                    if "asset_descriptions" in sheet.public_fields
                    else {}
                ),
            }
            for x in sheet.assets
        ]
    if sheet.owner in state.order:
        i = state.order.index(sheet.owner)
        result["rank"] = "Ace" if i == 0 else "Dog" if i == len(state.order) - 1 else "Wings"
    return result
