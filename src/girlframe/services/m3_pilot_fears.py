"""Original actors make, answer and adjudicate one printed Directors' demand."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_pilot_fears as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_civic_directive import director
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_intracadre_marriage import allocation_fields
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import ActorService
from girlframe.services.m3_cast import CastService
from girlframe.services.m3_intracadre_marriage import allocate_punishment
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

Action = Literal["demand", "respond", "addressed", "discipline"]
EVENT = "m3.strain_pilot_fears"


def stage(
    c: Connection,
    strain: StrainService,
    state: GameState,
    row: dict[str, Any],
    actor: str | None,
    event: str,
) -> None:
    npc = director(state, actor)
    period = strain.periods._get(c, row["off_duty_id"])
    handler = active_handler(state)
    cadre = tuple(current_ref(state, uid) for uid in period.pilots)
    if (
        handler is None
        or not cadre
        or any(period.character_ids.get(x.entity) != x.incarnation for x in cadre)
        or not HandlerService(strain.store)._member(c, npc.controller)
        or any(x.id == row["id"] for x in rules.cases(state))
    ):
        raise WorkflowError("Recover the original Director, Handler and preparing Cadre")
    rules.save(
        state,
        rules.Fears(
            id=row["id"],
            source=event,
            period=period.id,
            director=npc.id,
            controller=npc.controller,
            handler=handler,
            cadre=cadre,
        ),
    )


def access(case: rules.Fears, user: int) -> tuple[bool, bool, bool]:
    """Visibility and action options for the original Director, Cadre and Handler."""
    is_director = user == case.controller
    member = str(user) in {x.entity for x in case.cadre}
    is_handler = str(user) == case.handler.entity
    return is_director, member, is_handler


def proof(c: Connection, campaign: str, row: dict[str, Any]) -> None:
    """Only the committed call naming an original participant can require this severity."""
    body = json.loads(row["body_json"])
    history = t.m2["m2_state_history"]
    works = t.m3["m3_required_work"]
    initial = c.execute(
        sa.select(works.c.event_id).where(
            works.c.campaign_id == campaign,
            works.c.id == row["id"],
            works.c.revision == 1,
        )
    ).scalar_one_or_none()
    raw = c.scalar(
        sa.select(history.c.body_json)
        .join(
            t.events,
            (t.events.c.campaign_id == history.c.campaign_id)
            & (t.events.c.id == history.c.event_id),
        )
        .where(
            history.c.campaign_id == campaign,
            history.c.event_id == initial,
            t.events.c.kind == EVENT,
        ),
    )
    case = (
        next(
            (
                x
                for x in rules.cases(GameState.model_validate_json(raw))
                if x.id == body["fear_case"]
            ),
            None,
        )
        if raw
        else None
    )
    if (
        case is None
        or case.result != "discipline"
        or case.result_event != initial
        or case.period != row["off_duty_id"]
        or case.handler.entity != row["owner_id"]
        or not any(
            x.token == body.get("original") and row["id"] == f"{case.id}:severe:{x.entity}"
            for x in case.cadre
        )
        or body.get("required_severity") != "severe"
    ):
        raise WorkflowError("Recover the Directors' actual original call for collective discipline")


class FearsService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def _case(self, state: GameState, viewer: GuildViewer, identity: str) -> rules.Fears:
        case = next((x for x in rules.cases(state) if x.id == identity), None)
        if case is None or not any(access(case, viewer.user_id)):
            raise WorkflowError("This demand belongs to the original Directors and Cadre")
        if not case.demand_event and viewer.user_id != case.controller:
            raise WorkflowError("The original Directors have not issued the demand")
        return case

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            case = self._case(state, viewer, identity)
            is_director, member, _ = access(case, viewer.user_id)
            return dict(
                revision=state.revision,
                demand=case.demand,
                result=case.result,
                issue=is_director and not case.demand_event,
                review=is_director and bool(case.demand_event) and not case.result,
                respond=member and bool(case.demand_event) and not case.result,
                responses=tuple(
                    (x.event, x.account)
                    for x in case.responses
                    if is_director or x.actor.entity == str(viewer.user_id)
                ),
            )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        action: Action,
        account: str,
        *,
        channel: int | None = None,
        evidence: str | None = None,
    ) -> dict[str, Any]:
        if (
            action not in ("demand", "respond", "addressed", "discipline")
            or not 0 < len(account.strip()) <= 1200
            or (channel is not None) != (action == "respond")
            or (evidence is not None) != (action == "addressed")
        ):
            raise WorkflowError("Record the actual demand, performed action or adjudication")

        def authorize(c: Connection) -> None:
            self.strain.missions.access.authorize(c, viewer, "strain")
            self.strain.missions.access.authorize(c, viewer, "world")
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            case = self._case(state, viewer, identity)
            is_director, member, _ = access(case, viewer.user_id)
            if action == "respond":
                if not member or current_ref(state, viewer.user_id) not in case.cadre:
                    raise WorkflowError("Only the original Girl can record her own Cadre action")
            elif not is_director or director(state, case.director).controller != viewer.user_id:
                raise WorkflowError(
                    "Only the original fictional Director's controller can adjudicate"
                )

        def operation(c: Connection) -> dict[str, Any]:
            state = self.strain._state(c, expected)
            case = self._case(state, viewer, identity)
            row = EffectService(self.strain)._row(c, identity)
            body = json.loads(row["body_json"])
            period = self.strain.periods._get(c, case.period)
            if (
                row["state"] != "pending"
                or row["off_duty_id"] != case.period
                or body.get("fear_requested") != case.source
                or body["rule_id"] != rules.RULE
                or case.result
                or period.phase != "preparing"
                or not same_handler_body(state, case.handler)
                or (case.demand_event is None) != (action == "demand")
            ):
                raise WorkflowError("Reopen the original pending public-fear demand")
            event = str(uuid4())
            disciplines = []
            if action == "demand":
                case = case.model_copy(update=dict(demand=account.strip(), demand_event=event))
            elif action == "respond":
                actor = current_ref(state, viewer.user_id)
                assert channel is not None
                cast, _ = CastService(ActorService(self.strain.missions))._current(
                    c, state, channel
                )
                if not any(x.actor == actor and x.controller == viewer.user_id for x in cast.roles):
                    raise WorkflowError("Record the action from the Girl's actual joined scene")
                response = rules.Response(
                    actor=actor, scene=cast.id, event=event, account=account.strip()
                )
                case = case.model_copy(update=dict(responses=case.responses + (response,)))
            else:
                if action == "addressed" and not any(x.event == evidence for x in case.responses):
                    raise WorkflowError("Choose an actual performed action from the original Cadre")
                case = case.model_copy(
                    update=dict(
                        result=action,
                        result_event=event,
                        decision=account.strip(),
                        evidence=evidence,
                    )
                )
                if action == "discipline":
                    self.strain.missions.access.authorize(c, viewer, "discipline")
                    for original in case.cadre:
                        if current_ref(state, int(original.entity)) != original:
                            raise WorkflowError("Recover the original collective discipline roster")
                        work = f"{identity}:severe:{original.entity}"
                        allocation = allocate_punishment(
                            self.game,
                            c,
                            state,
                            original,
                            source_event=event,
                            source_id=work,
                            work_id=work,
                        )
                        recipient = allocation.subject if allocation else original
                        disciplines.append(
                            (
                                work,
                                int(recipient.entity),
                                dict(
                                    reason=rules.KIND,
                                    fear_case=identity,
                                    original=original.token,
                                    source_pdf=145,
                                    character=recipient.incarnation,
                                    required_severity="severe",
                                    **allocation_fields(state, work),
                                ),
                            )
                        )
            rules.save(state, case)
            self.game.event(c, viewer.user_id, key, EVENT, state, event_id=event, work_id=identity)
            for work, subject, discipline in disciplines:
                related(
                    c,
                    self.store,
                    row,
                    work,
                    int(case.handler.entity),
                    subject,
                    "punishment",
                    discipline,
                    event,
                )
            if case.result:
                # The original roll's consequence is now real. Discipline itself
                # remains mandatory work in the same preparation until performed.
                self.strain._save(c, row, event, body | {"fear_result": event}, resolved=True)
            return dict(id=identity, state=case.result or "pending")

        return self.strain.missions._write(
            viewer,
            key,
            EVENT,
            dict(
                id=identity,
                expected=expected,
                action=action,
                account=account,
                channel=channel,
                evidence=evidence,
            ),
            operation,
            authorize,
        )
