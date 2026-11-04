"""Source-bound Strain effects; selection/description never substitutes for mechanics."""

import json
from typing import Any

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_strain_effects as rules
from girlframe.services.m2_state import load_state
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class EffectService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def _row(self, c: Connection, identity: str) -> dict[str, Any]:
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table)
                .where(table.c.campaign_id == self.store.campaign_id, table.c.id == identity)
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is None or row["kind"] != "strain_event":
            raise WorkflowError("Unknown Strain event effect.")
        return dict(row)

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            self.strain.missions._handler(c, viewer)
            row = self._row(c, identity)
            if row["owner_id"] != str(viewer.user_id):
                raise WorkflowError("This effect belongs to its assigned Handler.")
            body = json.loads(row["body_json"])
            return {
                **{k: row[k] for k in ("id", "revision", "state", "off_duty_id")},
                "rule_id": body["rule_id"],
                "supported": body["rule_id"] in rules.SUPPORTED,
                "game_revision": load_state(c, self.store.campaign_id).revision,
            }

    def apply(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        choice: rules.Choice,
    ) -> dict[str, Any]:
        choice = rules.Choice.model_validate_json(choice.model_dump_json())

        def authorize(c: Connection) -> None:
            self.strain._authorize(c, viewer)
            self.strain.missions.access.authorize(c, viewer, "world")
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            self.strain._check(c, viewer, row, revision)
            state = self.strain._state(c, game_revision)
            if json.loads(row["body_json"])["rule_id"] != choice.rule_id:
                raise WorkflowError(
                    "The selected effect does not match this actual saved Strain event."
                )
            updated = rules.apply(state, choice, identity, period_id=row["off_duty_id"])
            event = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.strain_effect_applied",
                updated,
                work_id=identity,
                rule_id=choice.rule_id,
            )
            self.strain._save(
                c,
                row,
                event,
                json.loads(row["body_json"]) | {"choice": choice.model_dump(mode="json")},
                resolved=True,
            )
            return {"id": identity, "state": "resolved", "game_revision": updated.revision}

        try:
            return self.strain.missions._write(
                viewer,
                key,
                "m3.strain_effect_applied",
                {
                    "id": identity,
                    "revision": revision,
                    "game_revision": game_revision,
                    "choice": choice.model_dump(mode="json"),
                },
                operation,
                authorize,
            )
        except ValidationError:
            raise WorkflowError(
                "Invalid Strain effect choices; reopen the current world review."
            ) from None
