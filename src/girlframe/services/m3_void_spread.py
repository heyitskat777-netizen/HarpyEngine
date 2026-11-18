"""Freeze the original footprint occupants and perform each person's normal Void gain."""

import json
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_void_spread as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, ActorView
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_dive import _harpy_assets
from girlframe.engine.m3_handler_consequences import active_handler, same_handler_body
from girlframe.engine.m3_handler_void import require as require_handler_void
from girlframe.engine.m3_harpy_resources import assets as harpy_assets
from girlframe.engine.m3_janus_storage import alter, effective_assets
from girlframe.engine.m3_world import update
from girlframe.engine.m3_world_state import AdversaryPilot, WorldTag
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actor_history import snapshot_profiles
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_missions import MissionService
from girlframe.services.m3_off_duty import OffDutyService
from girlframe.services.m3_strain import StrainService
from girlframe.services.m3_strain_effects import EffectService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer

GAIN = "void_spread_gain"
HANDLER_GAIN = "void_spread_handler_void"
THRESHOLD_REASON = "void_spread"
MANIFESTATIONS = ("brain", "bones", "flesh", "abstract")


def _row(c: Connection, campaign: str, identity: str) -> dict[str, Any]:
    table = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(table)
            .where(
                table.c.campaign_id == campaign,
                table.c.id == identity,
            )
            .order_by(table.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None:
        raise WorkflowError("Recover the original area Void work")
    return dict(row)


def _scope(c: Connection, campaign: str, row: dict[str, Any]) -> tuple[rules.Spread, GameState]:
    body = json.loads(row["body_json"])
    if body["rule_id"] != rules.RULE or row["kind"] != "strain_event" or not body.get("spread"):
        raise WorkflowError("Save the original Strain footprint first")
    spread = rules.Spread.model_validate_json(json.dumps(body["spread"]))
    history = t.m2["m2_state_history"]
    raw = c.scalar(
        sa.select(history.c.body_json)
        .join(
            t.events,
            (history.c.campaign_id == t.events.c.campaign_id)
            & (history.c.event_id == t.events.c.id),
        )
        .where(
            history.c.campaign_id == campaign,
            history.c.event_id == spread.scope_event,
            t.events.c.kind == "m3.void_spread_scoped",
        )
    )
    if raw is None or spread.scope_event is None:
        raise WorkflowError("Choose the actual saved connected footprint first")
    work = t.m3["m3_required_work"]
    saved = c.scalar(
        sa.select(work.c.body_json).where(
            work.c.campaign_id == campaign,
            work.c.id == row["id"],
            work.c.event_id == spread.scope_event,
            work.c.kind == "strain_event",
        )
    )
    if saved is None or json.loads(saved).get("spread") != body["spread"]:
        raise WorkflowError("Recover the original unsuperseded scope and dice")
    return spread, GameState.model_validate_json(raw)


def _people(c: Connection, campaign: str, original: GameState) -> tuple[ActorView, ...]:
    assert original.world is not None
    refs = [current_ref(original, x) for x in original.order]
    handler = active_handler(original)
    if handler:
        context = next((x for x in original.director_contexts if x.active), None)
        refs.append(handler.model_copy(update={"incarnation": context.id}) if context else handler)
    refs += [ActorRef(kind="npc", entity=x.id) for x in original.world.npcs if x.alive]
    refs += [
        ActorRef(kind="external_pilot", entity=x.id)
        for group in (
            original.world.pilots,
            original.harpy_states,
            original.janus_cores,
        )
        for x in group
        if x.alive
    ]
    bound = snapshot_profiles(c, campaign, original)
    return tuple(
        resolve(original, ref, bound, require_current_profile=False) for ref in dict.fromkeys(refs)
    )


def _application(state: GameState, identity: str) -> rules.Application:
    result = next((x for x in rules.applications(state) if x.id == identity), None)
    if result is None:
        raise WorkflowError("Recover the original footprint application")
    return result


def _external_girl(state: GameState, ref: ActorRef) -> AdversaryPilot | None:
    if state.world is None or ref.kind != "external_pilot":
        return None
    return next(
        (
            pilot
            for pilot in state.world.pilots
            if pilot.id == ref.entity and pilot.alive and pilot.kind in ("rebel", "foundation")
        ),
        None,
    )


def _verify(
    c: Connection,
    campaign: str,
    state: GameState,
    row: dict[str, Any],
) -> tuple[rules.Application, rules.Occupant]:
    body = json.loads(row["body_json"])
    record = _application(state, body["spread_work"])
    person = next((x for x in record.occupants if x.work == row["id"]), None)
    parent = _row(c, campaign, record.id)
    parent_body = json.loads(parent["body_json"])
    history = t.m2["m2_state_history"]
    source = c.scalar(
        sa.select(history.c.body_json)
        .join(
            t.events,
            (history.c.campaign_id == t.events.c.campaign_id)
            & (history.c.event_id == t.events.c.id),
        )
        .where(
            history.c.campaign_id == campaign,
            history.c.event_id == record.event,
            t.events.c.kind == "m3.void_spread_applied",
        )
    )
    if (
        person is None
        or parent_body.get("spread_started") != record.event
        or body["spread_event"] != record.event
        or parent_body["spread"]["scope_event"] != record.scope
        or parent["off_duty_id"] != row["off_duty_id"]
        or body["owner"] != person.actor.model_dump(mode="json")
        or body["label"] != person.label
        or row["owner_id"] != str(person.controller)
        or source is None
        or record not in rules.applications(GameState.model_validate_json(source))
    ):
        raise WorkflowError("Recover the original occupant and its area-gain source")
    return record, person


def finish(
    c: Connection, strain: StrainService, identity: str, event: str, *, resolved: bool
) -> None:
    row = _row(c, strain.store.campaign_id, identity)
    if resolved and row["state"] == "pending":
        strain._save(c, row, event, json.loads(row["body_json"]), resolved=True)


def settle(
    c: Connection, strain: StrainService, state: GameState, identity: str, event: str
) -> None:
    record = _application(state, identity)
    finish(
        c,
        strain,
        identity,
        event,
        resolved=all(
            _row(c, strain.store.campaign_id, x.work)["state"] == "resolved"
            for x in record.occupants
        ),
    )


def handler_source(c: Connection, store: OnboardingStore, row: dict[str, Any]) -> None:
    _, person = _verify(c, store.campaign_id, load_state(c, store.campaign_id), row)
    if person.role != "handler":
        raise WorkflowError("Recover this original Handler-style exposure")


def complete_handler(
    c: Connection, store: OnboardingStore, row: dict[str, Any], event: str
) -> None:
    strain = StrainService(OffDutyService(MissionService(store)))
    state = load_state(c, store.campaign_id)
    record, _ = _verify(c, store.campaign_id, state, row)
    settle(c, strain, state, record.id, event)


def prove_threshold(
    c: Connection,
    store: OnboardingStore,
    first: dict[str, Any],
    body: dict[str, Any],
    actor: ActorRef,
) -> None:
    source = _row(c, store.campaign_id, body["source_work"])
    _, person = _verify(c, store.campaign_id, load_state(c, store.campaign_id), source)
    gain = json.loads(source["body_json"])
    if (
        source["kind"] != GAIN
        or person.actor != actor
        or person.role != "girl"
        or gain.get("gain") != first["event_id"]
        or first["id"] not in gain.get("thresholds", ())
        or first["off_duty_id"] != source["off_duty_id"]
        or first["id"] != f"{source['id']}:{body['details']['family']}"
    ):
        raise ValueError("Recover the actual footprint's original Void alteration")


def complete_threshold(c: Connection, store: OnboardingStore, work: str, event: str) -> None:
    strain = StrainService(OffDutyService(MissionService(store)))
    row = _row(c, store.campaign_id, work)
    state = load_state(c, store.campaign_id)
    record, _ = _verify(c, store.campaign_id, state, row)
    finish(
        c,
        strain,
        work,
        event,
        resolved=all(
            _row(c, store.campaign_id, x)["state"] == "resolved"
            for x in json.loads(row["body_json"])["thresholds"]
        ),
    )
    settle(c, strain, state, record.id, event)


class SpreadService:
    def __init__(self, strain: StrainService):
        self.strain, self.store, self.game = strain, strain.store, strain.game

    def area(self, viewer: GuildViewer, identity: str) -> tuple[tuple[str, str], ...]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            self.strain.missions._handler(c, viewer)
            row = EffectService(self.strain)._row(c, identity)
            if row["owner_id"] != str(viewer.user_id):
                raise WorkflowError("Only the original Handler can review this footprint")
            _, original = _scope(c, self.store.campaign_id, row)
            return tuple(
                (x.ref.token, x.label)
                for x in _people(c, self.store.campaign_id, original)
                if x.cell is None and x.offstage_source is None
            )

    def start(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        work_revision: int,
        outside: tuple[str, ...],
        account: str,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            self.strain._authorize(c, viewer)
            self.strain.missions.access.authorize(c, viewer, "world")
            self.strain.missions.access.authorize(c, viewer, "plays")
            self.game.unpaused(c)

        def operation(c: Connection) -> dict[str, Any]:
            state = self.strain._state(c, expected)
            row = EffectService(self.strain)._row(c, identity)
            self.strain._check(c, viewer, row, work_revision)
            spread, original = _scope(c, self.store.campaign_id, row)
            body = json.loads(row["body_json"])
            handler = active_handler(original)
            if (
                body.get("spread_started")
                or handler is None
                or not same_handler_body(state, handler)
                or not spread.scope_event
            ):
                raise WorkflowError("Reopen the original unapplied footprint")
            people = _people(c, self.store.campaign_id, original)
            unknown = tuple(x.ref for x in people if x.cell is None and x.offstage_source is None)
            if (
                len(outside) != len(set(outside))
                or set(outside) != {x.token for x in unknown}
                or (unknown and not 0 < len(account.strip()) <= 1200)
            ):
                raise WorkflowError(
                    "Review the actual unknown positions. Attest only documented absence "
                    "from the footprint, or recover the original scope before applying it."
                )
            event = str(uuid4())
            occupants = []
            for person in people:
                if person.cell is None or person.cell not in spread.cells:
                    continue
                role: rules.Role
                if person.rules in ("handler", "director"):
                    role = "handler"
                elif person.rules == "npc":
                    role = "npc"
                elif person.ref.kind == "pilot" and person.rules == "girl_frame":
                    role = "girl"
                elif person.ref.kind == "external_pilot" and person.girl == "harpy":
                    role = "harpy"
                elif _external_girl(original, person.ref) is not None:
                    role = "external_girl"
                else:
                    role = "unsupported"
                occupants.append(
                    rules.Occupant(
                        actor=person.ref,
                        label=person.label,
                        cell=person.cell,
                        role=role,
                        controller=viewer.user_id if role == "npc" else person.controller,
                        work=str(
                            uuid5(
                                NAMESPACE_URL,
                                f"girlframe:void-spread:{identity}:{person.ref.token}",
                            )
                        ),
                    )
                )
            record = rules.Application(
                id=identity,
                scope=spread.scope_event,
                event=event,
                handler=handler,
                occupants=tuple(occupants),
                reviewed_outside=unknown,
            )
            for record_person in record.occupants:
                if record_person.role == "handler":
                    state, _ = require_handler_void(
                        state,
                        record_person.actor,
                        work=record_person.work,
                        source_event=event,
                        appointment=MedicalService(self.store)._handler(c)[1],
                    )
            state.facts.append(dict(kind=rules.KIND, id=identity, body=record.model_dump_json()))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.void_spread_applied",
                state,
                event_id=event,
                work_id=identity,
                scope=spread.scope_event,
            )
            for item in record.occupants:
                related(
                    c,
                    self.store,
                    row,
                    item.work,
                    item.controller,
                    item.controller,
                    HANDLER_GAIN if item.role == "handler" else GAIN,
                    dict(
                        spread_work=identity,
                        spread_event=event,
                        owner=item.actor.model_dump(mode="json"),
                        label=item.label,
                    ),
                    event,
                )
            self.strain._save(
                c,
                row,
                event,
                body | dict(spread_started=event, outside_review=account.strip()),
                resolved=not record.occupants,
            )
            return dict(id=identity, required=len(record.occupants))

        return self.strain.missions._write(
            viewer,
            key,
            "m3.void_spread_applied",
            dict(
                id=identity,
                expected=expected,
                work_revision=work_revision,
                outside=outside,
                account=account,
            ),
            operation,
            authorize,
        )

    def _owned(
        self,
        c: Connection,
        viewer: GuildViewer,
        state: GameState,
        identity: str,
    ) -> tuple[dict[str, Any], rules.Application, rules.Occupant]:
        row = _row(c, self.store.campaign_id, identity)
        if row["kind"] != GAIN or row["owner_id"] != str(viewer.user_id):
            raise WorkflowError("Only this original occupant's controller can review the gain")
        record, person = _verify(c, self.store.campaign_id, state, row)
        return row, record, person

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            row, _, person = self._owned(c, viewer, state, identity)
            body = json.loads(row["body_json"])
            asset_choices: tuple[tuple[str, str], ...] = ()
            if (
                row["state"] == "pending"
                and not body.get("gain")
                and person.role in ("girl", "harpy", "external_girl")
            ):
                current = resolve(
                    state,
                    person.actor,
                    profiles(c, self.store.campaign_id),
                    require_current_profile=False,
                )
                if current.controller != viewer.user_id:
                    raise WorkflowError("Recover the original occupant's authority")
                if person.role == "girl":
                    asset_choices = tuple(
                        (x.id, x.name) for x in effective_assets(state, person.actor) if not x.void
                    )
                elif person.role == "harpy":
                    asset_choices = tuple(
                        (x.id, x.name) for x in harpy_assets(state, person.actor) if not x.void
                    )
                else:
                    external = _external_girl(state, person.actor)
                    if external is None:
                        raise WorkflowError("Recover this original external Girl body")
                    asset_choices = tuple((x.id, x.name) for x in external.assets if not x.void)
            return dict(
                role=person.role,
                revision=state.revision,
                state=row["state"],
                gain=body.get("gain"),
                external_followup=body.get("external_followup"),
                assets=asset_choices,
                actor=person.label,
            )

    def gain(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        pick: str,
        account: str,
    ) -> dict[str, Any]:
        if not 0 < len(account.strip()) <= 1200:
            raise WorkflowError("Describe the actual original corruption")

        def authorize(c: Connection) -> None:
            self.strain.missions.access.authorize(c, viewer, "strain")
            self.strain.missions.access.authorize(c, viewer, "plays")
            self.game.unpaused(c)
            self._owned(c, viewer, load_state(c, self.store.campaign_id), identity)

        def operation(c: Connection) -> dict[str, Any]:
            state = self.strain._state(c, expected)
            row, record, person = self._owned(c, viewer, state, identity)
            body = json.loads(row["body_json"])
            if row["state"] != "pending" or body.get("gain"):
                raise WorkflowError("Recover the original pending Void gain")
            current = resolve(
                state,
                person.actor,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
            event = str(uuid4())
            families: tuple[str, ...] = ()
            external_followup: str | None = None
            if person.role == "npc":
                if (
                    pick not in MANIFESTATIONS
                    or current.rules != "npc"
                    or state.world is None
                    or not same_handler_body(state, record.handler)
                ):
                    raise WorkflowError(
                        "The original Handler chooses this NPC's actual manifestation"
                    )
                tag = WorldTag(
                    id=identity,
                    label="Void of the " + pick,
                    giver_entity=record.handler.model_dump_json(),
                )
                state.world = update(
                    state.world,
                    npcs=tuple(
                        x.model_copy(update=dict(tags=(*x.tags, tag)))
                        if x.id == person.actor.entity
                        else x
                        for x in state.world.npcs
                    ),
                )
            elif person.role == "girl":
                if (
                    current.controller != viewer.user_id
                    or current.piloting is None
                    or current.rules != "girl_frame"
                ):
                    raise WorkflowError("Recover this original Girl's current owned Frame context")
                state, followups = alter(
                    state,
                    person.actor,
                    pick,
                    account.strip(),
                    identity,
                    event,
                    piloting=current.piloting,
                )
                families = tuple(
                    "girl" if x.kind == "girl_void_threshold" else "frame" for x in followups
                )
            elif person.role == "harpy":
                if current.controller != viewer.user_id or current.girl != "harpy":
                    raise WorkflowError("Recover this original Harpy body and authority")
                assets = harpy_assets(state, person.actor)
                if not any(x.id == pick and not x.void for x in assets):
                    raise WorkflowError("Choose one actual uncorrupted Harpy Asset")
                state = _harpy_assets(
                    state,
                    person.actor,
                    tuple(
                        x.model_copy(update=dict(void=True, description=account.strip()))
                        if x.id == pick
                        else x
                        for x in assets
                    ),
                    event=event,
                )
            elif person.role == "external_girl":
                external = _external_girl(state, person.actor)
                if current.controller != viewer.user_id or external is None or state.world is None:
                    raise WorkflowError("Recover this original external Girl body and authority")
                selected = next((x for x in external.assets if x.id == pick and not x.void), None)
                if selected is None:
                    raise WorkflowError("Choose one actual uncorrupted external Girl Asset")
                altered = tuple(
                    x.model_copy(update=dict(void=True, description=account.strip()))
                    if x.id == selected.id
                    else x
                    for x in external.assets
                )
                if all(x.void for x in altered if x.family == selected.family):
                    external_followup = selected.family
                updated = external.model_copy(update=dict(assets=altered))
                state.world = update(
                    state.world,
                    pilots=tuple(updated if x.id == external.id else x for x in state.world.pilots),
                )
            else:
                raise WorkflowError("Recover this original role's specific Void gain workflow")
            thresholds = tuple(f"{identity}:{x}" for x in families)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.void_spread_gained",
                state,
                event_id=event,
                work_id=identity,
            )
            for family, work in zip(families, thresholds, strict=True):
                related(
                    c,
                    self.store,
                    row,
                    work,
                    viewer.user_id,
                    viewer.user_id,
                    "void_threshold",
                    dict(
                        owner=person.actor.model_dump(mode="json"),
                        character=person.actor.incarnation,
                        details=dict(family=family),
                        source_action=None,
                        source_pdf=19,
                        reason=THRESHOLD_REASON,
                        source_work=identity,
                    ),
                    event,
                )
            if external_followup:
                body["external_followup"] = external_followup
            pending = bool(thresholds or external_followup)
            self.strain._save(
                c,
                row,
                event,
                body | dict(gain=event, pick=pick, account=account.strip(), thresholds=thresholds),
                resolved=not pending,
            )
            settle(c, self.strain, state, record.id, event)
            return dict(id=identity, state="pending" if pending else "resolved")

        return self.strain.missions._write(
            viewer,
            key,
            "m3.void_spread_gained",
            dict(id=identity, expected=expected, pick=pick, account=account),
            operation,
            authorize,
        )
