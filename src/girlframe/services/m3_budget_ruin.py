"""Actual selected Budget Endgame destroys two existing locations once."""

import json
from typing import Any
from uuid import uuid4

from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_collateral import stage_loss
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_strain_state import Trigger
from girlframe.engine.m3_world import Followup, destroy
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_budget_tags import _selection
from girlframe.services.m3_medical import MedicalService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

RULE = "strain.budget.endgame.3"


class RuinService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _source(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[dict[str, Any], GameState]:
        Access(self.store).authorize(c, viewer, "strain")
        Access(self.store).authorize(c, viewer, "world")
        row, original = _selection(c, self.game, identity, rule=RULE)
        state = load_state(c, self.store.campaign_id)
        handler = active_handler(original)
        if (
            handler is None
            or int(handler.entity) != viewer.user_id
            or row["owner_id"] != str(viewer.user_id)
            or not same_handler_body(state, handler)
        ):
            raise WorkflowError("Only the original Endgame Handler chooses these two locations")
        return row, state

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row, state = self._source(c, viewer, identity)
            return dict(
                id=identity,
                revision=row["revision"],
                game_revision=state.revision,
                state=row["state"],
                locations=[
                    dict(id=x.id, label=x.name, kind=x.kind)
                    for x in state.world.locations
                    if x.condition != "destroyed"
                ]
                if state.world
                else [],
            )

    def apply(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        expected: int,
        locations: tuple[str, ...],
        account: str,
    ) -> dict[str, Any]:
        if (
            len(locations) != 2
            or len(set(locations)) != 2
            or not account.strip()
            or len(account) > 1200
        ):
            raise WorkflowError("Choose two distinct surviving locations and describe their ruin")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            row, state = self._source(c, viewer, identity)
            if (
                row["state"] != "pending"
                or row["revision"] != revision
                or state.revision != expected
            ):
                raise WorkflowError("STALE_RUIN: reopen the original Endgame request")
            if state.world is None or state.strain is None:
                raise WorkflowError("Initialize the actual map and Strain before this consequence")
            from girlframe.services.m3_handler_plays import _ordinary_scene_idle

            _ordinary_scene_idle(c, self.game)
            changed = GameState.model_validate_json(state.model_dump_json())
            assert changed.world is not None
            followups: list[Followup] = []
            for location in locations:
                result = destroy(changed.world, location, gorgon_cause=False)
                changed.world = result.world
                followups.extend(result.followups)
            event = str(uuid4())
            judge, appointment = MedicalService(self.store)._handler(c)
            loss = stage_loss(
                state,
                changed,
                source="budget-ruin:" + identity,
                event=event,
                judge=judge,
                appointment=appointment,
                handler=active_handler(state),
            )
            additions = tuple(
                Trigger(
                    id=identity + ":structure:" + x.entity,
                    kind="structure_destroyed",
                    entity=x.entity,
                    source_event=event,
                )
                for x in followups
                if x.kind == "budget_structure_destroyed"
            )
            assert changed.strain is not None
            changed.strain = changed.strain.model_copy(
                update={"triggers": changed.strain.triggers + additions}
            )
            changed.facts.append(
                dict(
                    kind="budget_endgame_ruin",
                    event=event,
                    work=identity,
                    locations=json.dumps(locations),
                    account=account,
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.budget_locations_ruined",
                changed,
                event_id=event,
                work_id=identity,
                locations=locations,
                quadrant_loss=loss.id if loss else None,
            )
            if loss is not None:
                from girlframe.services.m3_quadrant_loss import materialize_loss

                materialize_loss(self.game, c, loss, event, period=row["off_duty_id"])
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{k: v for k, v in row.items() if k not in ("revision", "state", "event_id")},
                    revision=row["revision"] + 1,
                    state="resolved",
                    event_id=event,
                )
            )
            return dict(
                id=identity,
                state="resolved",
                locations=list(locations),
                quadrant_loss=loss.id if loss else None,
            )

        def authorize(c: Connection) -> None:
            self._source(c, viewer, identity)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.budget_locations_ruined",
                dict(
                    id=identity,
                    revision=revision,
                    expected=expected,
                    locations=locations,
                    account=account,
                ),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
