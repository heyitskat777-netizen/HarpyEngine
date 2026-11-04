"""Owned original physical facts, facilitator review and no placement reset command."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_physical as rules
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_physical_state import InitialPlacement, Review
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KIND = "physical_initial"
Decision = Literal["accept", "decline", "withdraw"]


class PhysicalService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        Access(self.store).authorize(c, viewer, "world", director_response=True)

    def _handler(self, c: Connection, viewer: GuildViewer) -> None:
        HandlerService(self.store).authorize(c, viewer)
        if load_state(c, self.store.campaign_id).handler != viewer.user_id:
            raise WorkflowError("Recover the actual Handler appointment before physical review.")

    def _rows(self, c: Connection) -> list[dict[str, Any]]:
        table = t.m3["m3_required_work"]
        return list(
            {
                row["id"]: dict(row)
                for row in c.execute(
                    sa.select(table)
                    .where(table.c.campaign_id == self.store.campaign_id, table.c.kind == KIND)
                    .order_by(table.c.revision)
                ).mappings()
            }.values()
        )

    def _row(self, c: Connection, identity: str) -> dict[str, Any]:
        row = next((x for x in self._rows(c) if x["id"] == identity), None)
        if row is None:
            raise WorkflowError("Unknown physical setup request.")
        return row

    def _review(self, c: Connection, row: dict[str, Any]) -> Review:
        body = Review.model_validate_json(row["body_json"])
        source = (
            c.execute(
                sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
                    t.events.c.campaign_id == self.store.campaign_id,
                    t.events.c.id == body.proposed_event,
                )
            )
            .mappings()
            .first()
        )
        if (
            source is None
            or row["campaign_id"] != self.store.campaign_id
            or row["state"] not in ("pending", "resolved")
            or (row["state"] == "pending") != (body.decision == "pending")
            or source["kind"] != "m3.initial_placement_proposed"
            or source["actor_id"] != body.proposal.actor.entity
            or json.loads(source["payload_json"]).get("work_id") != row["id"]
            or row["owner_id"] != str(body.handler)
            or row["subject_id"] != body.proposal.actor.entity
            or not row["campaign_context"]
            or any(row[x] is not None for x in ("mission_id", "off_duty_id", "scene_id"))
        ):
            raise WorkflowError("SOURCE_PLACEMENT_MISSING: recover the original factual proposal.")
        return body

    def _party(self, c: Connection, viewer: GuildViewer, body: Review) -> bool:
        return viewer.user_id == int(body.proposal.actor.entity) or (
            viewer.user_id == body.handler
            and HandlerService(self.store).current(c)[1].handler_id == body.handler
            and load_state(c, self.store.campaign_id).handler == body.handler
        )

    def _idle(self, c: Connection) -> None:
        locks = t.m2["m2_locks"]
        if self.game.pending_actions(c) or c.scalar(
            sa.select(locks.c.channel_id)
            .where(
                locks.c.campaign_id == self.store.campaign_id,
                locks.c.state != "released",
            )
            .limit(1)
        ):
            raise WorkflowError(
                "Finish pending Plays and restore chat before confirming physical facts."
            )

    def preview(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self._access(c, viewer)
            state = load_state(c, self.store.campaign_id)
            ref = ActorRef(
                kind="pilot",
                entity=str(viewer.user_id),
                incarnation=self.game.character_binding(
                    c, state, viewer.user_id, require_current_profile=False
                ),
            )
            actor = resolve(
                state, ref, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            placement = next((x for x in state.placements if x.actor == ref), None)
            return dict(
                game_revision=state.revision,
                pending_id=next(
                    (
                        row["id"]
                        for row in self._rows(c)
                        if row["state"] == "pending" and self._review(c, row).proposal.actor == ref
                    ),
                    None,
                ),
                actor=ref.model_dump(mode="json"),
                label=actor.label,
                frame_instance=actor.frame_instance,
                placement=placement.model_dump(mode="json") if placement else None,
                locations=[
                    dict(id=x.id, name=x.name, cell=list(x.cell)) for x in state.world.locations
                ]
                if state.world
                else [],
            )

    def propose(
        self, viewer: GuildViewer, key: str, expected: int, proposal: InitialPlacement
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self._access(c, viewer)
            if proposal.actor.kind != "pilot" or proposal.actor.entity != str(viewer.user_id):
                raise WorkflowError("Propose only your own original Girl's actual physical facts.")

        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            if type(expected) is not int or state.revision != expected:
                raise WorkflowError("STALE_PLACEMENT: refresh the current original physical facts.")
            self.game.character_binding(c, state, viewer.user_id, require_current_profile=False)
            actor = rules.validate(state, profiles(c, self.store.campaign_id), proposal)
            handler = HandlerService(self.store).current(c)[1].handler_id
            if (
                handler is None
                or state.handler != handler
                or not HandlerService(self.store)._member(c, handler)
            ):
                raise WorkflowError("Recover the actual Handler appointment before physical setup.")
            if any(
                self._review(c, row).proposal.actor == proposal.actor
                for row in self._rows(c)
                if row["state"] != "resolved"
            ):
                raise WorkflowError("Resume or withdraw your existing original physical proposal.")
            identity, source = str(uuid4()), str(uuid4())
            body = Review(
                proposal=proposal, label=actor.label, handler=handler, proposed_event=source
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.initial_placement_proposed",
                event_id=source,
                work_id=identity,
            )
            related(
                c,
                self.store,
                dict(campaign_id=self.store.campaign_id, campaign_context=True),
                identity,
                handler,
                viewer.user_id,
                KIND,
                body.model_dump(mode="json"),
                source,
            )
            return {"id": identity, "revision": 1}

        try:
            proposal = InitialPlacement.model_validate_json(proposal.model_dump_json())
            return self.store._write(
                viewer,
                key,
                "m3.initial_placement_proposed",
                dict(expected=expected, proposal=proposal.model_dump(mode="json")),
                operation,
                auto_audit=False,
                authorize=access,
            )
        except ValidationError:
            raise WorkflowError("Invalid physical facts; reopen your original review.") from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def tasks(self, viewer: GuildViewer) -> list[dict[str, Any]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            return self._tasks(c, viewer)

    def _tasks(
        self, c: Connection, viewer: GuildViewer, *, history: bool = False
    ) -> list[dict[str, Any]]:
        return [
            dict(
                id=row["id"],
                revision=row["revision"],
                label=body.label,
                incoming=viewer.user_id == body.handler,
                state=row["state"],
            )
            for row in self._rows(c)
            if (history or row["state"] != "resolved")
            and str(viewer.user_id) in (row["owner_id"], row["subject_id"])
            and self._party(c, viewer, body := self._review(c, row))
        ]

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            row = self._row(c, identity)
            body = self._review(c, row)
            if not self._party(c, viewer, body):
                raise WorkflowError("These physical facts belong to their actual participants.")
            return dict(
                id=identity,
                revision=row["revision"],
                state=row["state"],
                review=body.model_dump(mode="json"),
                own=viewer.user_id == int(body.proposal.actor.entity),
                can_review=viewer.user_id == body.handler,
            )

    def decide(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        decision: Decision,
        account: str,
    ) -> dict[str, Any]:
        def access(c: Connection) -> None:
            self._access(c, viewer)
            body = self._review(c, self._row(c, identity))
            if decision == "withdraw":
                if viewer.user_id != int(body.proposal.actor.entity):
                    raise WorkflowError("Only the actual proposing human can withdraw these facts.")
            elif decision in ("accept", "decline"):
                self._handler(c, viewer)
                if body.handler != viewer.user_id:
                    raise WorkflowError("Recover the original physical review's changed Handler.")
            else:
                raise WorkflowError("Choose an available physical review action.")

        def operation(c: Connection) -> dict[str, Any]:
            row = self._row(c, identity)
            body = self._review(c, row)
            if (
                type(expected) is not int
                or row["state"] != "pending"
                or row["revision"] != expected
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "STALE_PLACEMENT: reopen the pending actual review and respond."
                )
            event, vessel = str(uuid4()), None
            state = None
            if decision == "accept":
                self.game.unpaused(c)
                self._idle(c)
                if not HandlerService(self.store)._member(c, int(body.proposal.actor.entity)):
                    raise WorkflowError(
                        "The original proposing human must still be a campaign member."
                    )
                state = load_state(c, self.store.campaign_id)
                vessel = "vessel:" + identity
                state = rules.initial(
                    state,
                    profiles(c, self.store.campaign_id),
                    body.proposal,
                    vessel,
                    body.proposed_event,
                    event,
                )
            status = {"accept": "accepted", "decline": "declined", "withdraw": "withdrawn"}[
                decision
            ]
            body = Review.model_validate_json(
                body.model_copy(
                    update=dict(
                        decision=status, vessel_id=vessel, review_event=event, response=account
                    )
                ).model_dump_json()
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.initial_placement_reviewed",
                state,
                event_id=event,
                work_id=identity,
                decision=status,
            )
            c.execute(
                t.m3["m3_required_work"]
                .insert()
                .values(
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("revision", "state", "body_json", "event_id")
                    },
                    revision=expected + 1,
                    state="resolved",
                    body_json=body.model_dump_json(),
                    event_id=event,
                )
            )
            return {"id": identity, "revision": expected + 1, "decision": status}

        try:
            return self.store._write(
                viewer,
                key,
                "m3.initial_placement_reviewed",
                dict(id=identity, expected=expected, decision=decision, account=account),
                operation,
                auto_audit=False,
                authorize=access,
            )
        except ValidationError:
            raise WorkflowError(
                "Invalid actual physical review; reopen the saved request."
            ) from None
        except ValueError as error:
            raise WorkflowError(str(error)) from None
