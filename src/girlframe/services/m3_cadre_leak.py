"""Private proof of the leaked incident, with actual elimination or public apology."""

import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_cadre_leak as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_careers import archive_for
from girlframe.engine.m3_civic_directive import director
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

Action = Literal["demand", "apologize", "verify_elimination"]


def stage(
    c: Connection,
    strain: StrainService,
    state: GameState,
    work: str,
    event: str,
    speaker: str,
    parties: tuple[ActorRef, ...],
    report: str,
) -> None:
    npc = director(state, speaker)
    handler = active_handler(state)
    if (
        handler is None
        or not HandlerService(strain.store)._member(c, npc.controller)
        or not parties
        or len(set(parties)) != len(parties)
        or any(
            x.kind not in ("pilot", "npc") or x.entity == npc.id and x.kind == "npc"
            for x in parties
        )
        or any(x.id == work for x in rules.leaks(state))
    ):
        raise WorkflowError("Recover the actual leak's original parties and a separate Director")
    bound = profiles(c, strain.store.campaign_id)
    for ref in parties:
        resolve(state, ref, bound, require_current_profile=False)
    rules.put(
        state,
        rules.Leak(
            id=work,
            source=event,
            handler=handler,
            director=npc.id,
            controller=npc.controller,
            parties=parties,
            report=report,
        ),
    )


def _died(state: GameState, actor: ActorRef) -> bool:
    if actor.kind == "pilot":
        archive = archive_for(state, actor)
        return archive is not None and archive.ending in ("death", "execution")
    return bool(state.world and any(x.id == actor.entity and not x.alive for x in state.world.npcs))


def _deaths(
    c: Connection,
    campaign: str,
    record: rules.Leak,
    state: GameState,
) -> tuple[str, ...]:
    """Prove actual deaths after this source, including original Pilot incarnations."""
    if not all(_died(state, x) for x in record.parties):
        return ()
    events, history = t.events, t.m2["m2_state_history"]
    source = c.scalar(
        sa.select(events.c.seq).where(
            events.c.campaign_id == campaign,
            events.c.id == record.source,
            events.c.kind == "m3.strain_effect_applied",
        )
    )
    if source is None:
        raise WorkflowError("Recover the actual original leak")
    pending = set(record.parties)
    proved: dict[ActorRef, str] = {}
    for event, body in c.execute(
        sa.select(events.c.id, history.c.body_json)
        .join(
            history,
            (events.c.id == history.c.event_id) & (events.c.campaign_id == history.c.campaign_id),
        )
        .where(events.c.campaign_id == campaign, events.c.seq > source)
        .order_by(events.c.seq)
    ):
        snapshot = GameState.model_validate_json(body)
        for ref in tuple(pending):
            if _died(snapshot, ref):
                proved[ref] = event
                pending.remove(ref)
        if not pending:
            return tuple(proved[x] for x in record.parties)
    return ()


class LeakService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def _case(self, state: GameState, viewer: GuildViewer, identity: str) -> rules.Leak:
        record = next((x for x in rules.leaks(state) if x.id == identity), None)
        if record is None or viewer.user_id not in (record.controller, int(record.handler.entity)):
            raise WorkflowError("Only the original Handler and Director review this leak")
        return record

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            record = self._case(state, viewer, identity)
            is_handler = str(viewer.user_id) == record.handler.entity
            options = []
            if not record.outcome_event:
                if not is_handler and not record.demand_event:
                    options.append(("demand", "Demand an actual public apology"))
                if is_handler and record.demand_event:
                    options.append(("apologize", "Publish the Handler's actual apology"))
                if (
                    is_handler
                    and not record.demand_event
                    and all(_died(state, x) for x in record.parties)
                ):
                    options.append(("verify_elimination", "Verify the actual deaths"))
            return dict(
                revision=state.revision,
                demand=record.demand,
                apology=record.apology,
                options=tuple(options),
                complete=bool(record.outcome_event),
            )

    def bulletin(self, viewer: GuildViewer, identity: str, *, apology: bool) -> str:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            record = next(
                (x for x in rules.leaks(load_state(c, self.store.campaign_id)) if x.id == identity),
                None,
            )
            if record is None:
                raise WorkflowError("There is no published bulletin for this incident")
            if not apology:
                return record.report
            if record.outcome_event is None or record.apology is None:
                raise WorkflowError("There is no published apology for this incident")
            return record.apology

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        action: Action,
        account: str,
    ) -> dict[str, str]:
        if (
            action not in ("demand", "apologize", "verify_elimination")
            or not 0 < len(account.strip()) <= 1200
        ):
            raise WorkflowError("Record the actual demand, public apology or reviewed outcome")

        def authorize(c: Connection) -> None:
            self.strain.missions.access.authorize(c, viewer, "strain")
            self.strain.missions.access.authorize(c, viewer, "world")
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            case = self._case(state, viewer, identity)
            if action == "demand":
                if (
                    viewer.user_id != case.controller
                    or director(state, case.director).controller != viewer.user_id
                ):
                    raise WorkflowError(
                        "Only the original fictional Director's controller demands an apology"
                    )
            else:
                if str(viewer.user_id) != case.handler.entity:
                    raise WorkflowError("Only the original Handler answers this leak")
                HandlerService(self.store).authorize(c, viewer)

        def operation(c: Connection) -> dict[str, str]:
            state = self.strain._state(c, expected)
            case = self._case(state, viewer, identity)
            row = EffectService(self.strain)._row(c, identity)
            body = json.loads(row["body_json"])
            if (
                case.outcome_event
                or row["state"] != "pending"
                or body["rule_id"] != rules.RULE
                or body.get("leak_requested") != case.source
                or not same_handler_body(state, case.handler)
                or self.strain.periods._get(c, row["off_duty_id"]).phase != "preparing"
                or (case.demand_event is not None) != (action == "apologize")
            ):
                raise WorkflowError("Recover the pending original leak and its actual demand")
            event = str(uuid4())
            if action == "apologize":
                case = case.model_copy(update=dict(apology=account.strip(), outcome_event=event))
            else:
                deaths = _deaths(c, self.store.campaign_id, case, state)
                if bool(deaths) != (action == "verify_elimination"):
                    raise WorkflowError(
                        "Follow the actual status of every original party in this leak"
                    )
                if action == "demand":
                    case = case.model_copy(update=dict(demand=account.strip(), demand_event=event))
                else:
                    case = case.model_copy(update=dict(death_events=deaths, outcome_event=event))
            rules.put(state, case)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.strain_leak_answered",
                state,
                event_id=event,
                work_id=identity,
                resolution=action,
            )
            self.strain._save(c, row, event, body, resolved=bool(case.outcome_event))
            return dict(id=identity, state="resolved" if case.outcome_event else "pending")

        return self.strain.missions._write(
            viewer,
            key,
            "m3.strain_leak_answered",
            dict(id=identity, expected=expected, action=action, account=account),
            operation,
            authorize,
        )
