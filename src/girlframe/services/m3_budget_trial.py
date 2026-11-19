"""Private court testimony, a human finding and a real terminal consequence."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_budget_trial as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_civic_directive import director
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_budget_tags import _selection
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_strain import StrainService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

EVENT = "m3.budget_trial_statement"


def visible(state: GameState, viewer: GuildViewer) -> tuple[rules.Trial, ...]:
    result = []
    uid = str(viewer.user_id)
    girl = state.sheets.get(uid)
    for trial in rules.trials(state):
        if trial.controller == viewer.user_id:
            try:
                if director(state, trial.director).controller == viewer.user_id:
                    result.append(trial)
            except ValueError:
                continue
        elif trial.handler.entity == uid:
            if same_handler_body(state, trial.handler) or trial.executed:
                result.append(trial)
        elif (
            trial.charge_event
            and girl is not None
            and any(x.entity == uid and x.incarnation == girl.character_id for x in trial.cadre)
        ):
            result.append(trial)
    return tuple(result)


def options(trial: rules.Trial, user: int) -> tuple[tuple[str, str], ...]:
    if trial.phase == "charge" and user == trial.controller:
        return (("charge", "Serve the court's charge"),)
    if trial.phase != "hearing":
        return ()
    speakers = {x.actor.entity for x in trial.statements}
    if user == trial.controller and speakers == {x.entity for x in (*trial.cadre, trial.handler)}:
        condemn = (("condemn", "Find that the Cadre failed to save the Handler"),)
        if any(x.decision == "defend" for x in trial.statements):
            return (("save", "Confirm the Cadre saved the Handler"), *condemn)
        return condemn
    if str(user) in speakers:
        return ()
    if str(user) == trial.handler.entity:
        return (("answer", "Give your own answer"),)
    if any(x.entity == str(user) for x in trial.cadre):
        return (("defend", "Act to save your Handler"), ("pass", "Take no action"))
    return ()


def due(
    c: Connection, strain: StrainService, state: GameState, period: str
) -> tuple[dict[str, Any], rules.Trial] | None:
    trial = next(
        (x for x in rules.trials(state) if x.period == period and x.phase == "execution_due"), None
    )
    if trial is None:
        return None
    row, original = _selection(c, strain.game, trial.id, rule=rules.RULE)
    source = c.execute(
        sa.select(t.events.c.kind, t.events.c.actor_id, t.events.c.payload_json).where(
            t.events.c.campaign_id == strain.store.campaign_id,
            t.events.c.id == trial.verdict_event,
        )
    ).first()
    if (
        source is None
        or source.kind != EVENT
        or source.actor_id != str(trial.controller)
        or json.loads(source.payload_json).get("decision") != "condemn"
        or json.loads(source.payload_json).get("work_id") != trial.id
        or active_handler(original) != trial.handler
        or not same_handler_body(state, trial.handler)
        or row["off_duty_id"] != period
        or row["state"] != "pending"
    ):
        raise WorkflowError("Recover the original signed court sentence and Handler body")
    return row, trial


class TrialService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def _case(self, state: GameState, viewer: GuildViewer, identity: str) -> rules.Trial:
        case = next((x for x in visible(state, viewer) if x.id == identity), None)
        if case is None:
            raise WorkflowError("Only the original parties can open the private court record")
        return case

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            if not any(x.id == identity for x in rules.trials(state)):
                row, original = _selection(c, self.game, identity, rule=rules.RULE)
                handler = active_handler(original)
                if (
                    handler is None
                    or handler.entity != str(viewer.user_id)
                    or not same_handler_body(state, handler)
                ):
                    raise WorkflowError("Only the original Handler can open the trial")
                period = self.strain.periods._get(c, row["off_duty_id"])
                members = HandlerService(self.store)
                directors = []
                for actor in state.world.npcs if state.world else ():
                    try:
                        judge = director(state, actor.id)
                    except ValueError:
                        continue
                    if (
                        judge.revealed
                        and judge.controller not in period.pilots
                        and members._member(c, judge.controller)
                    ):
                        directors.append((judge.id, judge.name))
                return dict(revision=state.revision, phase="setup", directors=tuple(directors))
            case = self._case(state, viewer, identity)
            return dict(
                revision=state.revision,
                phase=case.phase,
                options=options(case, viewer.user_id),
                charge=case.charge,
                verdict=case.verdict,
                statements=tuple(
                    dict(
                        decision=x.decision,
                        account=x.account,
                    )
                    for x in case.statements
                    if viewer.user_id == case.controller or x.actor.entity == str(viewer.user_id)
                ),
            )

    def open(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, judge: str
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.strain._authorize(c, viewer)
            self.strain.missions.access.authorize(c, viewer, "world")
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            row, original = _selection(c, self.game, identity, rule=rules.RULE)
            state = self.strain._state(c, revision)
            handler = active_handler(original)
            period = self.strain.periods._get(c, row["off_duty_id"])
            court = director(state, judge)
            members = HandlerService(self.store)
            if (
                handler is None
                or handler.entity != str(viewer.user_id)
                or not same_handler_body(state, handler)
                or row["state"] != "pending"
                or period.phase != "preparing"
                or court.controller in period.pilots
                or not court.revealed
                or not members._member(c, court.controller)
                or any(x.id == identity for x in rules.trials(state))
            ):
                raise WorkflowError(
                    "Use the actual original Handler and an independent fictional Director"
                )
            cadre = tuple(
                current_ref(state, uid)
                for uid in period.pilots
                if str(uid) not in period.ended_characters and uid != viewer.user_id
            )
            if any(
                period.character_ids.get(x.entity) != x.incarnation
                or not members._member(c, int(x.entity))
                for x in cadre
            ):
                raise WorkflowError("Recover the actual original joined Cadre before the trial")
            _, appointment = MedicalService(self.store)._handler(c)
            rules.save(
                state,
                rules.Trial(
                    id=identity,
                    period=period.id,
                    source=row["event_id"],
                    handler=handler,
                    appointment=appointment,
                    director=court.id,
                    controller=court.controller,
                    cadre=cadre,
                ),
            )
            self.game.event(
                c, viewer.user_id, key, "m3.budget_trial_opened", state, work_id=identity
            )
            return dict(id=identity, phase="charge")

        return self.strain.missions._write(
            viewer,
            key,
            "m3.budget_trial_opened",
            dict(id=identity, revision=revision, judge=judge),
            operation,
            authorize,
        )

    def respond(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        decision: str,
        account: str,
    ) -> dict[str, Any]:
        account = account.strip()
        if not 0 < len(account) <= 1200:
            raise WorkflowError("Record your own actual court statement")

        def authorize(c: Connection) -> None:
            self.strain.missions.access.authorize(c, viewer, "strain")
            self.game.unpaused(c)
            self._case(load_state(c, self.store.campaign_id), viewer, identity)

        def operation(c: Connection) -> dict[str, Any]:
            state = self.strain._state(c, revision)
            trial = self._case(state, viewer, identity)
            row, original = _selection(c, self.game, identity, rule=rules.RULE)
            members = HandlerService(self.store)
            period = self.strain.periods._get(c, trial.period)
            _, appointment = MedicalService(self.store)._handler(c)
            if (
                row["state"] != "pending"
                or row["event_id"] != trial.source
                or row["off_duty_id"] != trial.period
                or active_handler(original) != trial.handler
                or not same_handler_body(state, trial.handler)
                or period.phase != "preparing"
                or appointment != trial.appointment
                or not members._member(c, trial.controller)
                or director(state, trial.director).controller != trial.controller
                or any(
                    x.entity in period.ended_characters
                    or current_ref(state, int(x.entity)) != x
                    or not members._member(c, int(x.entity))
                    for x in trial.cadre
                )
                or decision not in {x[0] for x in options(trial, viewer.user_id)}
            ):
                raise WorkflowError("Only the original speaker can make the current court choice")
            event = str(uuid4())
            if decision == "charge":
                updated = trial.model_copy(
                    update=dict(phase="hearing", charge=account, charge_event=event)
                )
            elif decision in ("save", "condemn"):
                updated = trial.model_copy(
                    update=dict(
                        phase="saved" if decision == "save" else "execution_due",
                        verdict=account,
                        verdict_event=event,
                    )
                )
            else:
                speaker = next(
                    x for x in (*trial.cadre, trial.handler) if x.entity == str(viewer.user_id)
                )
                statement = rules.Statement.model_validate(
                    dict(actor=speaker, decision=decision, event=event, account=account)
                )
                updated = trial.model_copy(update=dict(statements=(*trial.statements, statement)))
            rules.save(state, updated)
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
            if decision == "save":
                self.strain._save(c, row, event, json.loads(row["body_json"]), resolved=True)
            return dict(id=identity, phase=updated.phase)

        return self.strain.missions._write(
            viewer,
            key,
            EVENT,
            dict(id=identity, revision=revision, decision=decision, account=account),
            operation,
            authorize,
        )
