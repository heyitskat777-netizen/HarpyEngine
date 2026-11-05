"""Next actual Off-Duty Core care, printed Pet outing and real physical return."""

import json
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from pydantic import Field
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_janus as cores
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_actors import frame_position, resolve
from girlframe.engine.m3_janus_requisitions import PET
from girlframe.engine.m3_janus_state import BASELINE
from girlframe.engine.m3_off_duty import Period
from girlframe.engine.m3_void_state import HarpyTag
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_janus import prove_core
from girlframe.services.m3_janus_play import prove_link
from girlframe.services.m3_janus_requisitions import owned
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_scene_requisitions import _activation
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KIND = "janus_pet_outing"


class Outing(Model):
    id: str
    period: str
    actor: ActorRef
    core: ActorRef
    frame: str
    link: str
    purchase: str
    source_event: str
    opportunity_event: str
    phase: Literal["choice", "carried", "surgery", "returned"] = "choice"
    decision_event: str | None = None
    return_event: str | None = None
    account: str = Field(default="", max_length=1200)
    leash: str | None = None


def outings(state: GameState) -> tuple[Outing, ...]:
    return tuple(
        Outing.model_validate_json(x["body"])
        for x in state.facts
        if x.get("kind") == "janus_pet_outing"
    )


def put(state: GameState, value: Outing) -> None:
    body = dict(kind="janus_pet_outing", body=value.model_dump_json())
    if any(x.id == value.id for x in outings(state)):
        state.facts = [
            body
            if x.get("kind") == "janus_pet_outing"
            and Outing.model_validate_json(x["body"]).id == value.id
            else x
            for x in state.facts
        ]
    else:
        state.facts.append(body)


def treatment(
    state: GameState, actor: ActorRef, judge: int, appointment: str, event: str, period: str
) -> GameState:
    """Actual Foundation treatment replaces four control Tags, without moving bodies."""
    core = cores.core(state, actor)
    prior = {core.control_tags.get(role, core.baseline_tags[role]) for role, _ in BASELINE}
    mapping = {role: core.id + ":treatment:" + period + ":" + role for role, _ in BASELINE}
    tags = tuple(
        HarpyTag(
            id=mapping[role],
            label=label,
            giver=judge,
            gm_setter_appointment=appointment,
            gm_setter_event=event,
            observers=tuple(sorted({judge, core.controller, int(core.frame_owner.entity)})),
        )
        for role, label in BASELINE
    )
    return cores.update(
        state,
        actor,
        tags=(*tuple(x for x in core.tags if x.id not in prior), *tags),
        control_tags=mapping,
        takeover_event=None,
        state_event=event,
    )


def synchronize(c: Connection, store: OnboardingStore, period: Period, event: str) -> None:
    if period.phase != "active":
        return
    state = load_state(c, store.campaign_id)
    if not state.janus_cores:
        return
    if not any(getattr(x, "rule_id", None) == PET for x in state.requisitions):
        history = t.m3["m3_off_duty_history"]
        real_activation = c.scalar(
            sa.select(history.c.event_id)
            .join(t.events, history.c.event_id == t.events.c.id)
            .where(
                history.c.campaign_id == store.campaign_id,
                history.c.id == period.id,
                t.events.c.kind == "m3.off_duty_activated",
            )
            .limit(1)
        )
        if real_activation is None:
            return  # No Pet opportunity or actual Foundation-care trigger exists.
    activation = _activation(c, store, period)
    if activation is None:
        return
    initial, activation_event = activation
    game = GameService(store)
    judge, appointment = MedicalService(store)._handler(c)
    for core in initial.janus_cores:
        if (
            not core.alive
            or not core.attached
            or int(core.frame_owner.entity) not in period.pilots
            or core.frame_owner.entity in period.ended_characters
        ):
            continue
        actor = core.frame_owner
        identity = str(uuid5(NAMESPACE_URL, "girlframe:janus-pet:" + period.id + ":" + core.id))
        if any(x.id == identity for x in outings(state)) or any(
            x.get("kind") == "janus_foundation_treatment"
            and x.get("period") == period.id
            and x.get("core") == cores.ref(core).model_dump_json()
            for x in state.facts
        ):
            continue
        links = []
        for link in initial.battery_links:
            if (
                link.caster != actor
                or link.battery != cores.ref(core)
                or link.tier not in ("mid", "high")
                or not link.effects_event
                or any(x.link == link.id for x in outings(state))
            ):
                continue
            raw = c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json).where(
                    t.m2["m2_state_history"].c.campaign_id == store.campaign_id,
                    t.m2["m2_state_history"].c.event_id == link.source_event,
                )
            )
            source = GameState.model_validate_json(raw) if raw else None
            receipt = owned(c, game, source, actor, PET) if source else None
            if receipt is not None and owned(c, game, state, actor, PET) is not None:
                links.append((link, receipt))
        if links:
            link, receipt = links[-1]
            opportunity_event = str(uuid4())
            value = Outing(
                id=identity,
                period=period.id,
                actor=actor,
                core=cores.ref(core),
                frame=core.frame_instance,
                link=link.id,
                purchase=receipt.id,
                source_event=activation_event,
                opportunity_event=opportunity_event,
            )
            put(state, value)
            saved = game.event(
                c,
                period.handler,
                str(uuid4()),
                "m3.janus_pet_opportunity",
                state,
                event_id=opportunity_event,
                period_id=period.id,
                source_event=activation_event,
                outing=identity,
            )
            related(
                c,
                store,
                dict(campaign_id=store.campaign_id, off_duty_id=period.id),
                identity,
                int(actor.entity),
                int(actor.entity),
                KIND,
                dict(outing=identity, character=actor.incarnation, source_pdf=70, immediate=False),
                saved,
            )
        else:
            treatment_event = str(uuid4())
            state = treatment(
                state, cores.ref(core), judge, appointment, treatment_event, period.id
            )
            state.facts.append(
                dict(
                    kind="janus_foundation_treatment",
                    core=cores.ref(core).model_dump_json(),
                    period=period.id,
                    event=treatment_event,
                    activation=activation_event,
                )
            )
            game.event(
                c,
                judge,
                str(uuid4()),
                "m3.janus_foundation_core_treated",
                state,
                event_id=treatment_event,
                core=cores.ref(core).model_dump(mode="json"),
                period_id=period.id,
                source_event=activation_event,
            )


class PetService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _source(
        self, c: Connection, viewer: GuildViewer, identity: str
    ) -> tuple[GameState, Outing]:
        self.game.authorize(c, viewer, game=False)
        state = load_state(c, self.store.campaign_id)
        value = next((x for x in outings(state) if x.id == identity), None)
        if value is None or viewer.user_id not in (
            int(value.actor.entity),
            cores.core(state, value.core).controller,
        ):
            raise WorkflowError("This actual Pet outing belongs only to its original participants")
        raw = c.scalar(
            sa.select(t.m2["m2_state_history"].c.body_json).where(
                t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                t.m2["m2_state_history"].c.event_id == value.opportunity_event,
            )
        )
        source = GameState.model_validate_json(raw) if raw else None
        original = next((x for x in outings(source) if x.id == value.id), None) if source else None
        stable = (
            "id",
            "period",
            "actor",
            "core",
            "frame",
            "link",
            "purchase",
            "source_event",
            "opportunity_event",
        )
        if original is None or any(getattr(original, k) != getattr(value, k) for k in stable):
            raise WorkflowError("Preserve this actual original qualifying Pet outing source")
        prove_core(c, self.game, state, value.core)
        prove_link(self.game, c, state, value.link)
        return state, value

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            state, value = self._source(c, viewer, identity)
            return dict(
                id=value.id,
                revision=state.revision,
                outing=value.model_dump(mode="json"),
                can_act=viewer.user_id == int(value.actor.entity),
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(
                id=x.id,
                revision=state.revision,
                phase=x.phase,
                actionable=viewer.user_id == int(x.actor.entity),
            )
            for x in outings(state)
            if x.phase in ("choice", "carried")
            and viewer.user_id in (int(x.actor.entity), cores.core(state, x.core).controller)
        ]

    def decide(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, carry: bool, account: str
    ) -> dict[str, Any]:
        return self._change(
            viewer, key, identity, revision, "carry" if carry else "surgery", account
        )

    def return_core(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        return self._change(viewer, key, identity, revision, "return", account)

    def _change(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        operation: str,
        account: str,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "playbooks")
            self._source(c, viewer, identity)

        def change(c: Connection) -> dict[str, Any]:
            from girlframe.services.m3_missions import MissionService
            from girlframe.services.m3_off_duty import OffDutyService

            self.game.unpaused(c)
            state, value = self._source(c, viewer, identity)
            if (
                viewer.user_id != int(value.actor.entity)
                or state.revision != revision
                or not account.strip()
                or self.game.pending_actions(c)
            ):
                raise WorkflowError("Refresh your actual owned outing and finish pending Plays")
            if current_ref(state, viewer.user_id) != value.actor:
                raise WorkflowError("No successor inherits the original Core outing")
            period = OffDutyService(MissionService(self.store))._get(c, value.period)
            if period.phase != "active":
                raise WorkflowError("Use this actual active Off-Duty outing")
            core = cores.core(state, value.core)
            if not core.alive:
                raise WorkflowError("This original Core has ended; no living outing is fabricated")
            if operation not in ("carry", "surgery", "return") or (operation == "return") != (
                value.phase == "carried"
            ):
                raise WorkflowError("Use the actual current outing operation")
            event = str(uuid4())
            if operation == "carry":
                if owned(c, self.game, state, value.actor, PET) is None:
                    raise WorkflowError(
                        "Restore the actual original Pet entitlement before using it"
                    )
                if any(
                    x.phase == "connected" and value.core in (x.caster, x.battery)
                    for x in state.neural_connections
                ):
                    raise WorkflowError(
                        "Physically unplug the actual wire before carrying the Core"
                    )
                own = resolve(state, value.actor, profiles(c, self.store.campaign_id))
                cell = cores.position(state, core)
                if own.cell is not None and cell is not None and own.cell != cell:
                    raise WorkflowError(
                        "Actual separated bodies do not prove taking the Core along"
                    )
                state = cores.update(
                    state,
                    value.core,
                    attached=False,
                    linked=False,
                    cell=cell,
                    custody="captured",
                    custodian=value.actor,
                    custody_event=event,
                    physical_source_event=event,
                    state_event=event,
                )
                value = value.model_copy(
                    update=dict(
                        phase="carried",
                        decision_event=event,
                        account=account,
                        leash="pet-leash:" + value.id,
                    )
                )
                assert value.leash is not None
                state.facts.append(
                    dict(
                        kind="janus_pet_leash_and_collar",
                        item=value.leash,
                        holder=value.core.model_dump_json(),
                        custodian=value.actor.model_dump_json(),
                        event=event,
                        outing=value.id,
                        name="Leash and Collar",
                    )
                )
            else:
                if operation == "return":
                    cell = frame_position(state, value.actor, value.frame)
                    if core.cell is not None and cell is not None and core.cell != cell:
                        raise WorkflowError(
                            "Return the actual Core to her real original Frame before attachment"
                        )
                    state = cores.update(
                        state,
                        value.core,
                        attached=True,
                        linked=True,
                        cell=None,
                        custody="core",
                        custodian=value.actor,
                        custody_event=event,
                        physical_source_event=event,
                        state_event=event,
                    )
                value = value.model_copy(
                    update=dict(
                        phase="returned" if operation == "return" else "surgery",
                        return_event=event if operation == "return" else None,
                        decision_event=value.decision_event or event,
                        account=account,
                    )
                )
            put(state, value)
            saved = self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.janus_pet_" + operation,
                state,
                event_id=event,
                outing=value.id,
                period_id=value.period,
                core=value.core.model_dump(mode="json"),
            )
            if operation != "carry":
                judge, appointment = MedicalService(self.store)._handler(c)
                routine = str(uuid4())
                state = treatment(state, value.core, judge, appointment, routine, value.period)
                state.facts.append(
                    dict(
                        kind="janus_foundation_treatment",
                        core=value.core.model_dump_json(),
                        period=value.period,
                        event=routine,
                        activation=value.source_event,
                    )
                )
                self.game.event(
                    c,
                    judge,
                    str(uuid4()),
                    "m3.janus_foundation_core_treated",
                    state,
                    event_id=routine,
                    source_event=saved,
                    core=value.core.model_dump(mode="json"),
                    period_id=value.period,
                )
                work = t.m3["m3_required_work"]
                row = (
                    c.execute(
                        sa.select(work)
                        .where(work.c.campaign_id == self.store.campaign_id, work.c.id == identity)
                        .order_by(work.c.revision.desc())
                        .limit(1)
                    )
                    .mappings()
                    .one()
                )
                c.execute(
                    work.insert().values(
                        **{
                            k: v
                            for k, v in row.items()
                            if k not in ("revision", "state", "body_json", "event_id")
                        },
                        revision=row["revision"] + 1,
                        state="resolved",
                        event_id=saved,
                        body_json=json.dumps(
                            json.loads(row["body_json"]) | dict(resolution=value.phase)
                        ),
                    )
                )
            return dict(id=value.id, phase=value.phase)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.janus_pet_changed",
                dict(outing=identity, operation=operation, account=account),
                change,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None
