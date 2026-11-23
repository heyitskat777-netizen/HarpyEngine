"""Original Handler leave followed by the actual players' private preferences."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_void_leave as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import depth
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_budget_tags import _selection
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

APPROVED = "m3.void_leave_approved"
VOTED = "m3.void_leave_preference_recorded"
DECIDED = "m3.void_leave_story_decided"


def require_story(state: GameState) -> None:
    for leave in rules.leaves(state):
        if leave.returned and leave.decision is None:
            raise WorkflowError(
                "Record the original players' choices about continuing the campaign"
            )
        if leave.decision == "close":
            raise WorkflowError("The table drew this campaign to a close")


class LeaveService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _source(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[dict[str, Any], GameState, ActorRef]:
        Access(self.store).authorize(c, viewer, "strain")
        row, original = _selection(c, self.game, identity, rule=rules.RULE)
        handler = active_handler(original)
        if (
            handler is None
            or row["owner_id"] != str(viewer.user_id)
            or handler.entity != row["owner_id"]
        ):
            raise WorkflowError("Only the original Endgame Handler owns this leave")
        return row, load_state(c, self.store.campaign_id), handler

    @staticmethod
    def _bonds(state: GameState, handler: ActorRef) -> tuple[tuple[str, str], ...]:
        return (
            tuple(
                (x.id, x.name)
                for x in state.world.npcs
                if x.alive and depth(state, handler, ActorRef(kind="npc", entity=x.id)) > 0
            )
            if state.world
            else ()
        )

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            row, state, handler = self._source(c, viewer, identity)
            return dict(
                revision=row["revision"],
                game_revision=state.revision,
                bonds=self._bonds(state, handler),
                leave=next((x for x in rules.leaves(state) if x.id == identity), None),
            )

    def approve(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        expected: int,
        home: str,
        quadrant: int,
        account: str,
        *,
        bond: str | None = None,
    ) -> dict[str, Any]:
        if (
            type(quadrant) is not int
            or quadrant <= 0
            or quadrant == 12
            or not 0 < len(home.strip()) <= 300
            or not 0 < len(account.strip()) <= 900
        ):
            raise WorkflowError(
                "Record the original home outside Quadrant 12 and the leave account"
            )

        def authorize(c: Connection) -> None:
            self.game.unpaused(c)
            self._source(c, viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            row, state, handler = self._source(c, viewer, identity)
            if (
                row["revision"] != revision
                or row["state"] != "pending"
                or state.revision != expected
                or not same_handler_body(state, handler)
                or self.game.pending_actions(c)
            ):
                raise WorkflowError("STALE_VOID_LEAVE: reopen the original Endgame")
            if bond is not None and bond not in dict(self._bonds(state, handler)):
                raise WorkflowError("Choose an actual NPC Bond of this original Handler")
            period = OffDutyService(MissionService(self.store))._get(c, row["off_duty_id"])
            if period.phase != "preparing" or str(period.handler) != handler.entity:
                raise WorkflowError("Bind leave to the original preparing Off-Duty period")
            _, appointment = MedicalService(self.store)._handler(c)
            event = str(uuid4())
            rules.save(
                state,
                rules.Leave(
                    id=identity,
                    selection=row["event_id"],
                    approved=event,
                    period=period.id,
                    handler=handler,
                    appointment=appointment,
                    voters=tuple(
                        ActorRef(
                            kind="pilot",
                            entity=str(uid),
                            incarnation=period.character_ids[str(uid)],
                        )
                        for uid in period.pilots
                    ),
                    home=home.strip(),
                    quadrant=quadrant,
                    account=account.strip(),
                    bond=ActorRef(kind="npc", entity=bond) if bond else None,
                ),
            )
            self.game.event(
                c, viewer.user_id, key, APPROVED, state, event_id=event, work_id=identity
            )
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{k: v for k, v in row.items() if k not in ("revision", "state", "event_id")},
                    revision=revision + 1,
                    state="resolved",
                    event_id=event,
                )
            )
            return dict(id=identity, state="reserved")

        return self.store._write(
            viewer,
            key,
            APPROVED,
            dict(
                id=identity,
                revision=revision,
                expected=expected,
                home=home,
                quadrant=quadrant,
                account=account,
                bond=bond,
            ),
            operation,
            auto_audit=False,
            authorize=authorize,
        )

    def _table(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[GameState, rules.Leave, ActorRef | None]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        record = next((x for x in rules.leaves(state) if x.id == identity and x.returned), None)
        voter = (
            next((x for x in record.voters if x.entity == str(viewer.user_id)), None)
            if record
            else None
        )
        if record is None or voter is None and record.handler.entity != str(viewer.user_id):
            raise WorkflowError("The leave follow-up belongs to its original table")
        assert record.returned is not None
        ended, metadata = self._event(c, record.returned, "m3.off_duty_end", record.handler.entity)
        original = record.model_copy(update={"votes": (), "decision": None, "decided": None})
        if (
            original not in rules.leaves(ended)
            or metadata.get("period_id") != record.period
            or metadata.get("completed") is not True
        ):
            raise WorkflowError("Recover the actual completed leave before asking for preferences")
        return state, record, voter

    def _event(
        self, c: Connection, event: str, kind: str, actor: str
    ) -> tuple[GameState, dict[str, Any]]:
        history = t.m2["m2_state_history"]
        proof = c.execute(
            sa.select(history.c.body_json, t.events.c.payload_json)
            .join(
                t.events,
                (t.events.c.campaign_id == history.c.campaign_id)
                & (t.events.c.id == history.c.event_id),
            )
            .where(
                history.c.campaign_id == self.store.campaign_id,
                history.c.event_id == event,
                t.events.c.kind == kind,
                t.events.c.actor_id == actor,
            )
        ).first()
        if proof is None:
            raise WorkflowError("Recover the actual original leave or preference receipt")
        return GameState.model_validate_json(proof.body_json), json.loads(proof.payload_json)

    def followup(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state, record, voter = self._table(c, viewer, identity)
            return dict(
                revision=state.revision,
                decision=record.decision,
                voters=len(record.voters),
                votes=tuple(x for x in record.votes if voter is None or x.voter == voter),
                decision_owner=voter is None,
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        preference: rules.Response,
    ) -> dict[str, Any]:
        if preference not in ("continue", "close"):
            raise WorkflowError("Choose your actual preference about the campaign")

        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "strain", director_response=True)
            self.game.unpaused(c)
            self._table(c, viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            state, record, voter = self._table(c, viewer, identity)
            if state.revision != expected or record.decided or self.game.pending_actions(c):
                raise WorkflowError("STALE_VOID_LEAVE: reopen the original follow-up")
            event = str(uuid4())
            if voter is not None:
                if any(x.voter == voter for x in record.votes):
                    raise WorkflowError("Only one preference belongs to each original player")
                record = record.model_copy(
                    update=dict(
                        votes=(
                            *record.votes,
                            rules.Vote(voter=voter, preference=preference, event=event),
                        )
                    )
                )
                kind = VOTED
            else:
                _, appointment = MedicalService(self.store)._handler(c)
                if (
                    len(record.votes) != len(record.voters)
                    or record.appointment != appointment
                    or not same_handler_body(state, record.handler)
                ):
                    raise WorkflowError("Wait for every original player's choice before deciding")
                for vote in record.votes:
                    original, metadata = self._event(c, vote.event, VOTED, vote.voter.entity)
                    if metadata.get("work_id") != record.id or not any(
                        x.id == record.id and vote in x.votes for x in rules.leaves(original)
                    ):
                        raise WorkflowError("Recover each original player's actual preference")
                record = record.model_copy(update=dict(decision=preference, decided=event))
                kind = DECIDED
            rules.save(state, record)
            self.game.event(c, viewer.user_id, key, kind, state, event_id=event, work_id=identity)
            return dict(id=identity, decision=record.decision)

        return self.store._write(
            viewer,
            key,
            "m3.void_leave_followup",
            dict(id=identity, expected=expected, preference=preference),
            operation,
            auto_audit=False,
            authorize=authorize,
        )
