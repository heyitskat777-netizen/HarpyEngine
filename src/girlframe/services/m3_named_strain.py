"""Resume the exact new-track die and its original Handler's owned choice."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_custom_strain as custom
from girlframe.engine import m3_director_strain as calls
from girlframe.engine import m3_named_strain as rules
from girlframe.engine import m3_void_rift as rift
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.services.m2_state import load_state
from girlframe.services.m3_director_strain import _proof as phone_source
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KIND = "named_strain_roll"
DIE = "m3.named_strain_die_saved"
CHOSEN = "m3.named_strain_effect_applied"


class NamedStrainService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def _scope(
        self, c: Connection, viewer: GuildViewer, identity: str, state: GameState
    ) -> tuple[dict[str, Any], rules.Table, rules.SavedRoll | None]:
        table = t.m3["m3_required_work"]
        found = (
            c.execute(
                sa.select(table)
                .where(table.c.campaign_id == self.store.campaign_id, table.c.id == identity)
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if found is None or found["kind"] != KIND or found["owner_id"] != str(viewer.user_id):
            raise WorkflowError("Only the original Handler owns this new track work")
        row = dict(found)
        body = json.loads(row["body_json"])
        track = next((x for x in rules.tables(state) if x.id == body.get("track")), None)
        if track is None:
            raise WorkflowError("Recover the original Director-authored track")
        born = phone_source(c, self.strain, track.id, track.controller)
        owner = next((x for x in calls.calls(born) if x.id == track.id), None)
        if (
            owner is None
            or owner.command.mode != "create_track"
            or owner.command.new_track != track.design
            or owner.sender != track.director
            or track not in rules.tables(born)
        ):
            raise WorkflowError("Recover the exact original table and signed phone call")
        saved = next((x for x in rules.rolls(state) if x.id == identity), None)
        if saved is None:
            if body.get("stage") != "die" or row["off_duty_id"] is None:
                raise WorkflowError("Recover the original unrolled named track request")
        else:
            original = saved.model_copy(update={"column": None, "applied": None})
            source: GameState | None
            if saved.source == track.id:
                source = born
            else:
                history = t.m2["m2_state_history"]
                raw = c.scalar(
                    sa.select(history.c.body_json)
                    .join(
                        t.events,
                        (t.events.c.campaign_id == history.c.campaign_id)
                        & (t.events.c.id == history.c.event_id),
                    )
                    .where(
                        history.c.campaign_id == self.store.campaign_id,
                        history.c.event_id == saved.source,
                        t.events.c.kind == DIE,
                        t.events.c.actor_id == saved.handler.entity,
                    )
                )
                source = GameState.model_validate_json(raw) if raw else None
            if (
                source is None
                or original not in rules.rolls(source)
                or saved.track != track.id
                or saved.handler.entity != row["owner_id"]
                or saved.period_id != row["off_duty_id"]
                or body.get("face") != saved.face
                or bool(saved.applied) != (row["state"] == "resolved")
            ):
                raise WorkflowError("Recover the original saved die and its progress")
        return row, track, saved

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            row, track, roll = self._scope(c, viewer, identity, state)
            return dict(
                revision=state.revision,
                work_revision=row["revision"],
                status=row["state"],
                track=track.design.name,
                face=roll.face if roll else None,
                options=track.design.faces[roll.face - 1] if roll else (),
                column=roll.column if roll else None,
            )

    def advance(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        work_revision: int,
        column: int | None,
    ) -> dict[str, Any]:
        kind = CHOSEN if column is not None else DIE

        def authorize(c: Connection) -> None:
            self.strain._authorize(c, viewer)
            self.strain.missions.access.authorize(c, viewer, "world")
            registry = self.strain.missions.access.registry
            assert registry is not None
            registry.require_available(custom.RULE)
            registry.require_available(calls.RULE)

        def operation(c: Connection) -> dict[str, Any]:
            state = self.strain._state(c, expected)
            row, track, saved = self._scope(c, viewer, identity, state)
            if row["state"] != "pending" or row["revision"] != work_revision:
                raise WorkflowError("STALE_NAMED_STRAIN: reopen the original work")
            if row["off_duty_id"] is not None:
                self.strain._check(c, viewer, row, work_revision)
            handler = active_handler(state)
            if handler is None or saved is not None and not same_handler_body(state, saved.handler):
                raise WorkflowError("The original Handler owns this actual saved track result")
            event = str(uuid4())
            body = json.loads(row["body_json"])
            arrivals: tuple[tuple[str, rift.Arrival], ...] = ()
            if saved is None and column is None:
                period = row["off_duty_id"]
                assert period is not None
                saved = rules.SavedRoll(
                    id=identity,
                    period_id=period,
                    track=track.id,
                    handler=handler,
                    source=event,
                    rng_source=self.strain.rng_source,
                    face=self.strain.dice.roll_d6(),
                )
                body |= dict(stage="column", face=saved.face)
                arrivals = rift.upcoming(state, identity, period, event)
            elif saved is not None and type(column) is int and column in (1, 2):
                choice = track.design.faces[saved.face - 1][column - 1]
                custom.apply(
                    state,
                    custom.Occurrence(
                        id=event,
                        mode="named_track",
                        actor=handler,
                        controller=viewer.user_id,
                        period=saved.period_id,
                        source_work=identity,
                        target_controller=track.target_controller,
                        design=custom.Design(
                            title=choice.title.strip(),
                            tag=choice.tag.strip(),
                            npc=track.design.npc,
                            account=track.account,
                        ),
                    ),
                )
                saved = saved.model_copy(update=dict(column=column, applied=event))
                body |= dict(column=column, applied=event)
            else:
                raise WorkflowError("Resume the saved die by choosing one actual column")
            rules.save_roll(state, saved)
            self.game.event(
                c,
                viewer.user_id,
                key,
                kind,
                state,
                event_id=event,
                work_id=identity,
                rng_source=saved.rng_source,
            )
            self.strain._save(c, row, event, body, resolved=saved.applied is not None)
            self.strain._rift_work(c, row, viewer.user_id, arrivals, event)
            return dict(id=identity, face=saved.face, column=saved.column)

        return self.strain.missions._write(
            viewer,
            key,
            kind,
            dict(id=identity, expected=expected, work_revision=work_revision, column=column),
            operation,
            authorize,
        )
