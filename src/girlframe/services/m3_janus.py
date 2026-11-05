"""Original JANUS Core admission: owner request, real controller facts, Foundation review."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_janus as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_janus_state import CoreFacts, CoreSetup, JanusCore
from girlframe.services.handler_setup import HandlerService
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_medical import MedicalService
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KIND = "janus_core_setup"


def _history(c: Connection, game: GameService, event: str) -> GameState:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == event,
        )
    )
    if raw is None:
        raise WorkflowError("SOURCE_JANUS_MISSING: recover the actual original canonical event")
    return GameState.model_validate_json(raw)


def _row(c: Connection, game: GameService, identity: str) -> dict[str, Any]:
    table = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(table)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == identity)
            .order_by(table.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None or row["kind"] != KIND:
        raise WorkflowError("This actual JANUS Core setup is unavailable")
    return dict(row)


def _value(row: dict[str, Any]) -> CoreSetup:
    return CoreSetup.model_validate_json(json.dumps(json.loads(row["body_json"])["setup"]))


def _event(
    c: Connection, game: GameService, event: str, kind: str, actor: int, identity: str
) -> None:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        .mappings()
        .first()
    )
    if (
        row is None
        or row["kind"] != kind
        or row["actor_id"] != str(actor)
        or json.loads(row["payload_json"]).get("setup") != identity
    ):
        raise WorkflowError("SOURCE_JANUS_MISSING: recover the actual original human response")


def prove_core(c: Connection, game: GameService, state: GameState, actor: ActorRef) -> JanusCore:
    value = rules.core(state, actor)
    initial = rules.core(_history(c, game, value.source_event), actor)
    stable = (
        "id",
        "controller",
        "frame_owner",
        "frame_instance",
        "source_setup",
        "proposed_event",
        "source_event",
        "judge",
        "appointment",
        "source_facts",
        "body_vessel",
        "baseline_tags",
    )
    if any(getattr(value, key) != getattr(initial, key) for key in stable):
        raise WorkflowError("SOURCE_JANUS_CHANGED: preserve original Core/controller/Frame facts")
    row = _row(c, game, value.source_setup)
    setup = _value(row)
    if (
        setup.phase != "admitted"
        or setup.core != actor
        or setup.owner != value.frame_owner
        or setup.frame != value.frame_instance
        or setup.controller != value.controller
        or setup.facts != value.source_facts
        or setup.review_event != value.source_event
        or setup.proposed_event != value.proposed_event
        or setup.judge != value.judge
        or setup.appointment != value.appointment
    ):
        raise WorkflowError("SOURCE_JANUS_SETUP_MISSING: recover actual original setup review")
    _event(
        c, game, setup.source_event, "m3.janus_core_requested", int(setup.owner.entity), setup.id
    )
    _event(
        c, game, value.proposed_event, "m3.janus_core_facts_proposed", value.controller, setup.id
    )
    _event(c, game, value.source_event, "m3.janus_core_admitted", value.judge, setup.id)
    return value


class JanusService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _access(self, c: Connection, viewer: GuildViewer) -> None:
        access = Access(self.store)
        access.authorize(c, viewer, "playbooks")
        assert access.registry is not None
        access.registry.require_available(rules.CORE)
        self.game.unpaused(c)

    def _unchanged(self, c: Connection, setup: CoreSetup) -> GameState:
        state = load_state(c, self.store.campaign_id)
        actual = resolve(
            state, setup.owner, profiles(c, self.store.campaign_id), require_current_profile=False
        )
        if (
            actual.frame_instance != setup.frame
            or actual.frame not in ("JANUS", "JANUS-B")
            or actual.frame_scrapped
        ):
            raise WorkflowError("STALE_JANUS_FRAME: recover the actual original JANUS and owner")
        if MedicalService(self.store)._handler(c) != (setup.judge, setup.appointment):
            raise WorkflowError("Recover the actual original Foundation source-review appointment")
        if not HandlerService(self.store)._member(c, setup.controller):
            raise WorkflowError("The original Core controller must still belong to this campaign")
        return state

    def request(self, viewer: GuildViewer, key: str, controller: int) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            actual = resolve(
                state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
            )
            if (
                actual.rules != "girl_frame"
                or actual.frame not in ("JANUS", "JANUS-B")
                or not actual.frame_instance
                or actual.frame_scrapped
                or rules.bound(state, actor, actual.frame_instance)
            ):
                raise WorkflowError("Set up one actual original Core for your existing JANUS-B")
            if self.game.pending_actions(c):
                raise WorkflowError("Finish the actual pending Play before admitting a Core")
            if not HandlerService(self.store)._member(c, controller):
                raise WorkflowError("Choose an actual current campaign member as Core controller")
            table = t.m3["m3_required_work"]
            rows = c.execute(
                sa.select(table)
                .where(table.c.campaign_id == self.store.campaign_id, table.c.kind == KIND)
                .order_by(table.c.revision)
            ).mappings()
            latest = {x["id"]: dict(x) for x in rows}
            if any(
                x["state"] != "resolved"
                and _value(x).owner == actor
                and _value(x).frame == actual.frame_instance
                for x in latest.values()
            ):
                raise WorkflowError("Resume this original JANUS's pending owned Core setup")
            judge, appointment = MedicalService(self.store)._handler(c)
            identity, event = str(uuid4()), str(uuid4())
            value = CoreSetup(
                id=identity,
                owner=actor,
                frame=actual.frame_instance,
                controller=controller,
                judge=judge,
                appointment=appointment,
                source_event=event,
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.janus_core_requested",
                state,
                setup=identity,
                event_id=event,
            )
            related(
                c,
                self.store,
                dict(campaign_id=self.store.campaign_id, campaign_context=True),
                identity,
                controller,
                viewer.user_id,
                KIND,
                dict(setup=value.model_dump(mode="json")),
                event,
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.janus_core_requested",
            dict(controller=controller),
            operation,
            authorize=lambda c: self._access(c, viewer),
            auto_audit=False,
        )

    def _save(self, c: Connection, row: dict[str, Any], value: CoreSetup, event: str) -> None:
        c.execute(
            t.m3["m3_required_work"]
            .insert()
            .values(
                **{
                    key: item
                    for key, item in row.items()
                    if key not in ("revision", "owner_id", "state", "body_json", "event_id")
                },
                revision=row["revision"] + 1,
                owner_id=str(value.controller if value.phase == "controller" else value.judge),
                state="resolved"
                if value.phase in ("admitted", "declined", "withdrawn")
                else "pending",
                body_json=json.dumps(dict(setup=value.model_dump(mode="json"))),
                event_id=event,
            )
        )

    def change(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        revision: int,
        game_revision: int,
        *,
        facts: CoreFacts | None = None,
        approve: bool | None = None,
        account: str = "",
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            row = _row(c, self.game, identity)
            value = _value(row)
            state = self._unchanged(c, value)
            if (
                row["revision"] != revision
                or state.revision != game_revision
                or row["state"] == "resolved"
            ):
                raise WorkflowError("STALE_JANUS_SETUP: reopen the original current setup")
            if (facts is None) == (approve is None):
                raise WorkflowError(
                    "Supply one actual controller proposal or source-review response"
                )
            event = str(uuid4())
            if facts is not None:
                if viewer.user_id != value.controller or value.phase != "controller":
                    raise WorkflowError(
                        "Only the original actual Core controller supplies her facts"
                    )
                normalized = CoreFacts.model_validate_json(
                    facts.model_copy(
                        update=dict(
                            identities=tuple(
                                x.model_copy(update={"id": identity + ":identity:" + str(n)})
                                for n, x in enumerate(facts.identities)
                            ),
                            girl_assets=tuple(
                                x.model_copy(update={"id": identity + ":girl:" + str(n)})
                                for n, x in enumerate(facts.girl_assets)
                            ),
                        )
                    ).model_dump_json()
                )
                value = value.model_copy(
                    update=dict(facts=normalized, proposed_event=event, phase="review")
                )
                kind = "facts_proposed"
            else:
                if viewer.user_id != value.judge or value.phase != "review" or not account.strip():
                    raise WorkflowError(
                        "The actual Foundation source judge reviews real proposed facts"
                    )
                if approve:
                    assert value.facts is not None and value.proposed_event is not None
                    original = "janus-core:" + identity
                    state = rules.admit(
                        state,
                        value.owner,
                        value.frame,
                        value.controller,
                        value.facts,
                        identity=original,
                        setup=identity,
                        proposed_event=value.proposed_event,
                        event=event,
                        judge=value.judge,
                        appointment=value.appointment,
                    )
                    value = value.model_copy(
                        update=dict(
                            core=ActorRef(kind="external_pilot", entity=original),
                            review_event=event,
                            review=account.strip(),
                            phase="admitted",
                        )
                    )
                    kind = "admitted"
                else:
                    value = value.model_copy(
                        update=dict(review_event=event, review=account.strip(), phase="declined")
                    )
                    kind = "declined"
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.janus_core_" + kind,
                state,
                setup=identity,
                event_id=event,
            )
            self._save(c, row, value, event)
            return dict(id=identity, phase=value.phase)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.janus_core_setup_changed",
                dict(
                    id=identity,
                    revision=revision,
                    game_revision=game_revision,
                    facts=facts.model_dump(mode="json") if facts else None,
                    approve=approve,
                    account=account,
                ),
                operation,
                authorize=lambda c: self._access(c, viewer),
                auto_audit=False,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            row = _row(c, self.game, identity)
            value = _value(row)
            if viewer.user_id not in (int(value.owner.entity), value.controller, value.judge):
                raise WorkflowError("Only the original setup participants view these private facts")
            state = load_state(c, self.store.campaign_id)
            data = value.model_dump(mode="json")
            if viewer.user_id not in (value.controller, value.judge):
                data["facts"] = None
                data["review"] = ""
            return dict(
                id=identity,
                revision=row["revision"],
                game_revision=state.revision,
                setup=data,
                controller=viewer.user_id == value.controller,
                judge=viewer.user_id == value.judge,
            )

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        table = t.m3["m3_required_work"]
        rows = c.execute(
            sa.select(table)
            .where(table.c.campaign_id == self.store.campaign_id, table.c.kind == KIND)
            .order_by(table.c.revision)
        ).mappings()
        latest = {x["id"]: dict(x) for x in rows}
        result = []
        for row in latest.values():
            value = _value(row)
            if viewer.user_id in (int(value.owner.entity), value.controller, value.judge):
                result.append(
                    dict(
                        id=value.id,
                        revision=row["revision"],
                        phase=value.phase,
                        actionable=row["state"] != "resolved"
                        and viewer.user_id == int(row["owner_id"]),
                    )
                )
        return result

    def candidates(self, viewer: GuildViewer) -> list[tuple[str, str]]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            return [
                (str(uid), "Campaign member " + str(uid))
                for uid in c.scalars(
                    sa.select(t.members.c.user_id).where(
                        t.members.c.campaign_id == self.store.campaign_id,
                        t.members.c.active.is_(True),
                    )
                )
            ]

    def menu(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            tasks = self._tasks(c, viewer)
            sheet = state.sheets.get(str(viewer.user_id))
            can_request = False
            if (
                sheet is not None
                and sheet.frame in ("JANUS", "JANUS-B")
                and not sheet.frame_scrapped
            ):
                actor = current_ref(state, viewer.user_id)
                frame = (
                    sheet.frame_runtime.id
                    if sheet.frame_runtime
                    else "initial:" + str(actor.incarnation)
                )
                can_request = rules.bound(state, actor, frame) is None and not any(
                    x["phase"] in ("controller", "review") for x in tasks
                )
            available = False
            try:
                registry = Access(self.store).registry
                if registry is not None:
                    registry.require_available(rules.CORE)
                    available = True
            except (ValueError, WorkflowError):
                pass
            return dict(
                tasks=tasks,
                source_available=available,
                can_request=can_request and available,
                cores=[
                    dict(
                        actor=rules.ref(x).model_dump(mode="json"),
                        label="Harpy Core",
                        frame=x.frame_instance,
                        alive=x.alive,
                        tags=[
                            tag.label
                            for tag in x.tags
                            if viewer.user_id == x.controller or viewer.user_id in tag.observers
                        ],
                    )
                    for x in state.janus_cores
                    if x.controller == viewer.user_id or int(x.frame_owner.entity) == viewer.user_id
                ],
            )

    def withdraw(
        self, viewer: GuildViewer, key: str, identity: str, revision: int
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            row = _row(c, self.game, identity)
            value = _value(row)
            if viewer.user_id not in (int(value.owner.entity), value.controller):
                raise WorkflowError("Only this original requester/controller withdraws this setup")
            if row["revision"] != revision or row["state"] == "resolved":
                raise WorkflowError("Reopen the actual current pending setup")
            state = load_state(c, self.store.campaign_id)
            event = self.game.event(
                c, viewer.user_id, key, "m3.janus_core_setup_withdrawn", state, setup=identity
            )
            updated = value.model_copy(
                update=dict(
                    phase="withdrawn",
                    review_event=event,
                    review="The original requester/controller withdrew this source admission.",
                )
            )
            self._save(c, row, updated, event)
            return dict(id=identity, phase="withdrawn")

        return self.store._write(
            viewer,
            key,
            "m3.janus_core_setup_withdrawn",
            dict(id=identity, revision=revision),
            operation,
            authorize=lambda c: self.game.authorize(c, viewer, game=False),
            auto_audit=False,
        )
