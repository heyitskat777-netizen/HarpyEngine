"""Bind the original sentence and the exact, independently approved successor draft."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_rebel_assimilation as assimilation
from girlframe.engine import m3_rebel_succession as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actors import fingerprint
from girlframe.engine.m3_civic_directive import director
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_handler_state import SavedDraft
from girlframe.engine.m3_world_state import Npc
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_budget_tags import _selection
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m3_handler_creation import HandlerCreationService

EVENT = "m3.new_foundation_court"


def _court(state: GameState, identity: str, group: str) -> Npc:
    authority = director(state, identity)
    if authority.faction != group or not authority.revealed:
        raise ValueError("Choose the actual visible fictional Director of this Foundation group")
    return authority


def _proof(c: Connection, strain: StrainService, event: str | None) -> Any:
    events = t.events
    return c.execute(
        sa.select(events.c.kind, events.c.actor_id, events.c.payload_json, events.c.seq).where(
            events.c.campaign_id == strain.store.campaign_id,
            events.c.id == event,
        )
    ).first()


def due(
    c: Connection, strain: StrainService, state: GameState, period: str
) -> rules.Succession | None:
    case = next(
        (
            x
            for x in rules.successions(state)
            if x.period == period and x.sentenced and not x.executed
        ),
        None,
    )
    if case is None:
        return None
    row, original = _selection(c, strain.game, case.id, rule=rules.RULE)
    proof = _proof(c, strain, case.sentenced)
    if (
        proof is None
        or proof.kind != EVENT
        or proof.actor_id != str(case.controller)
        or json.loads(proof.payload_json).get("work_id") != case.id
        or json.loads(proof.payload_json).get("decision") != "sentence"
        or active_handler(original) != case.old_handler
        or not same_handler_body(state, case.old_handler)
        or row["off_duty_id"] != period
        or row["state"] != "pending"
    ):
        raise WorkflowError("Recover the actual original Foundation sentence and Handler")
    return case


def visible(state: GameState, viewer: GuildViewer) -> tuple[rules.Succession, ...]:
    return (
        tuple(
            x
            for x in rules.successions(state)
            if (
                x.old_handler.entity == str(viewer.user_id)
                or x.controller == viewer.user_id
                and any(
                    npc.id == x.court and npc.alive and npc.controller == viewer.user_id
                    for npc in state.world.npcs
                )
            )
        )
        if state.world
        else ()
    )


def prepare_successor(
    c: Connection,
    creation: HandlerCreationService,
    state: GameState,
    viewer: GuildViewer,
    saved: SavedDraft,
) -> rules.Succession | None:
    from girlframe.services.m3_missions import MissionService
    from girlframe.services.m3_off_duty import OffDutyService

    case = next(
        (
            x
            for x in rules.successions(state)
            if x.executed and not x.completed and x.old_handler.entity == str(viewer.user_id)
        ),
        None,
    )
    if case is None:
        return None
    if (
        not case.approved
        or case.refused
        or case.draft_fingerprint != fingerprint(saved)
        or saved.generation != case.executed
    ):
        raise WorkflowError(
            "Obtain the original court's agreement to this exact successor draft first"
        )
    if (
        _court(state, case.court, case.group).controller != case.controller
        or not HandlerService(creation.store)._member(c, case.controller)
        or state.world is None
        or not any(
            x.id == case.group and x.active and x.kind == "foundation" for x in state.world.factions
        )
    ):
        raise WorkflowError("Recover the original court's current authority over succession")
    strain = StrainService(OffDutyService(MissionService(creation.store)))
    approval = _proof(c, strain, case.approved)
    pledge = _proof(c, strain, case.pledged)
    if (
        approval is None
        or pledge is None
        or approval.kind != EVENT
        or pledge.kind != EVENT
        or approval.actor_id != str(case.controller)
        or pledge.actor_id != str(viewer.user_id)
        or approval.seq <= pledge.seq
        or json.loads(approval.payload_json).get("work_id") != case.id
        or json.loads(approval.payload_json).get("decision") != "approve"
        or json.loads(pledge.payload_json).get("work_id") != case.id
        or json.loads(pledge.payload_json).get("decision") != "pledge"
    ):
        raise WorkflowError("Recover original court approval and owned successor pledge")
    return case


class SuccessionService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def _draft(self, c: Connection, case: rules.Succession) -> SavedDraft | None:
        from girlframe.services.m3_handler_creation import HandlerCreationService

        service = HandlerCreationService(self.store)
        row = service._draft_row(c, int(case.old_handler.entity), case.appointment)
        return service._draft(c, row) if row and row["state"] == "pending" else None

    def _source(self, c: Connection, identity: str) -> tuple[dict[str, Any], GameState, str]:
        row, original = _selection(c, self.game, identity, rule=rules.RULE)
        selection_id = json.loads(row["body_json"])["source_work"]
        group = (
            next((x.faction for x in original.strain.endgames if x.id == selection_id), None)
            if original.strain
            else None
        )
        if group is None:
            raise WorkflowError("Recover the selected original group")
        return row, original, group

    def _choices(
        self, c: Connection, viewer: GuildViewer, case: rules.Succession
    ) -> tuple[tuple[str, str], ...]:
        if case.completed:
            return ()
        if not case.sentenced and viewer.user_id == case.controller:
            return (("sentence", "State the ideals and sentence"),)
        if not case.executed:
            return ()
        saved = self._draft(c, case)
        if saved is None or saved.draft.missing or saved.generation != case.executed:
            return ()
        if case.old_handler.entity == str(viewer.user_id) and (
            case.refused or not case.pledged or case.draft_fingerprint != fingerprint(saved)
        ):
            return (("pledge", "Submit your original successor's pledge"),)
        if (
            viewer.user_id == case.controller
            and case.pledged
            and not case.approved
            and not case.refused
            and case.draft_fingerprint == fingerprint(saved)
        ):
            return (
                ("approve", "Approve the exact successor pledge"),
                ("refuse", "Request a different pledge"),
            )
        return ()

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            case = next((x for x in rules.successions(state) if x.id == identity), None)
            if case is None:
                _, original, group = self._source(c, identity)
                handler = active_handler(original)
                if (
                    handler is None
                    or handler.entity != str(viewer.user_id)
                    or not same_handler_body(state, handler)
                ):
                    raise WorkflowError("Only the actual original Handler can open the succession")
                judges = []
                for npc in state.world.npcs if state.world else ():
                    try:
                        court = _court(state, npc.id, group)
                    except ValueError:
                        continue
                    if HandlerService(self.store)._member(c, court.controller):
                        judges.append((court.id, court.name))
                return dict(revision=state.revision, setup=True, courts=tuple(judges))
            if case not in visible(state, viewer):
                raise WorkflowError(
                    "The Foundation succession belongs to its original participants"
                )
            actual_draft = self._draft(c, case) if case.executed and not case.completed else None
            return dict(
                revision=state.revision,
                setup=False,
                ideals=case.ideals,
                sentence=case.sentence,
                pledge=case.pledge,
                sentenced=bool(case.sentenced),
                executed=bool(case.executed),
                complete=bool(case.completed),
                approved=bool(
                    case.approved
                    and (
                        case.completed
                        or actual_draft
                        and fingerprint(actual_draft) == case.draft_fingerprint
                    )
                ),
                choices=self._choices(c, viewer, case),
            )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        decision: str,
        *,
        judge: str | None = None,
        ideals: str = "",
        account: str = "",
    ) -> dict[str, Any]:
        account, ideals = account.strip(), ideals.strip()
        if (
            (decision == "open") != (judge is not None)
            or (decision in ("sentence", "pledge") and not 0 < len(account) <= 1200)
            or (decision == "sentence" and not 0 < len(ideals) <= 1200)
        ):
            raise WorkflowError("Record the original court decision or your own actual pledge")

        def authorize(c: Connection) -> None:
            for scope in ("strain", "world"):
                self.strain.missions.access.authorize(c, viewer, scope)
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            state = self.strain._state(c, revision)
            row, original, group = self._source(c, identity)
            case = next((x for x in rules.successions(state) if x.id == identity), None)
            period = self.strain.periods._get(c, row["off_duty_id"])
            handler = active_handler(original)
            if handler is None or row["state"] != "pending":
                raise WorkflowError("Recover the original pending Foundation succession")
            event = str(uuid4())
            if decision == "open":
                assert judge is not None
                court = _court(state, judge, group)
                actual = (
                    next((x for x in state.world.factions if x.id == group), None)
                    if state.world
                    else None
                )
                if (
                    case is not None
                    or handler.entity != str(viewer.user_id)
                    or not same_handler_body(state, handler)
                    or period.phase != "preparing"
                    or actual is None
                    or not HandlerService(self.store)._member(c, court.controller)
                ):
                    raise WorkflowError("Only the original Handler can open the actual court")
                _, appointment = MedicalService(self.store)._handler(c)
                state = assimilation.assimilate(
                    state,
                    assimilation.Assimilation(
                        id=identity,
                        original=actual,
                        handler=handler,
                        source=row["event_id"],
                        rule=rules.RULE,
                        event=event,
                    ),
                )
                changed = rules.Succession(
                    id=identity,
                    source=row["event_id"],
                    period=period.id,
                    group=group,
                    old_handler=handler,
                    appointment=appointment,
                    court=court.id,
                    controller=court.controller,
                    assimilation=event,
                )
            else:
                if (
                    case is None
                    or case not in visible(state, viewer)
                    or decision not in {x[0] for x in self._choices(c, viewer, case)}
                    or _court(state, case.court, case.group).controller != case.controller
                    or not HandlerService(self.store)._member(c, case.controller)
                ):
                    raise WorkflowError("Only the actual original owner can make this court choice")
                if decision == "sentence":
                    if period.phase != "preparing" or not same_handler_body(
                        state, case.old_handler
                    ):
                        raise WorkflowError(
                            "Recover the original living Handler and preparing period"
                        )
                    changed = case.model_copy(
                        update=dict(ideals=ideals, sentence=account, sentenced=event)
                    )
                elif decision == "pledge":
                    draft = self._draft(c, case)
                    assert draft is not None
                    changed = case.model_copy(
                        update=dict(
                            pledge=account,
                            pledged=event,
                            draft_fingerprint=fingerprint(draft),
                            approved=None,
                            refused=None,
                        )
                    )
                else:
                    changed = case.model_copy(
                        update={"approved" if decision == "approve" else "refused": event}
                    )
            rules.save(state, changed)
            self.game.event(
                c,
                viewer.user_id,
                key,
                EVENT,
                state,
                event_id=event,
                work_id=identity,
                decision=decision,
            )
            return dict(id=identity, decision=decision)

        return self.strain.missions._write(
            viewer,
            key,
            EVENT,
            dict(
                id=identity,
                revision=revision,
                decision=decision,
                judge=judge,
                ideals=ideals,
                account=account,
            ),
            operation,
            authorize,
        )
