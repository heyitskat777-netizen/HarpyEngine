"""Normal Dive storage and optional actual Foundation removal after Go Off-Duty."""

import json
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_janus_storage as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_core import Followup
from girlframe.engine.m3_dive_state import Effect
from girlframe.engine.m3_janus_requisitions import STORAGE
from girlframe.engine.m3_off_duty import Period
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_janus_play import prove_link
from girlframe.services.m3_janus_requisitions import owned
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def available(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> bool:
    link = rules.live_link(state, actor)
    if link is None or owned(c, game, state, actor, STORAGE) is None:
        return False
    prove_link(game, c, state, link.id)
    return True


def gain(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    step: int,
    choice: str,
    actor: ActorRef,
    effect: Effect,
) -> tuple[Followup, ...]:
    if not available(game, c, state, actor) or effect.asset is None:
        raise WorkflowError("Actual Void Storage requires the owned rule and connected Harpy")
    receipt = owned(c, game, state, actor, STORAGE)
    assert receipt is not None
    from girlframe.engine.m3_actors import resolve
    from girlframe.services.m3_actors import profiles

    view = resolve(state, actor, profiles(c, game.store.campaign_id), require_current_profile=False)
    changed, followups = rules.alter(
        state,
        actor,
        effect.asset,
        effect.description,
        action["id"],
        action["data"]["response_event"],
        piloting=view.inside_frame is True and view.occupied_frame_instance == view.frame_instance,
        source=rules.GainSource(purchase=receipt.id, choice=choice, kind="dive_deep"),
        step=step,
    )
    state.sheets, state.facts = changed.sheets, changed.facts
    for entry in state.sheets[actor.entity].identities:
        if entry.id not in state.sheets[actor.entity].sedation_locked:
            entry.marked = False
    state.facts.append(
        dict(
            kind="dive_effect",
            action=action["id"],
            step=str(step),
            actor=actor.model_dump_json(),
            option="void_and_unmark_all",
            source_event=action["data"]["response_event"],
            account=effect.account,
            effect=effect.model_dump_json(),
        )
    )
    return followups


def prove(game: GameService, c: Connection, state: GameState, point: rules.StoredVoid) -> None:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == point.source_event,
        )
    )
    source = GameState.model_validate_json(raw) if raw else None
    original = next((x for x in rules.points(source) if x.id == point.id), None) if source else None
    action = game.action(c, point.action)
    response = c.scalar(
        sa.select(t.m2["m2_responses"].c.choice_id).where(
            t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_responses"].c.choice_id == point.choice,
        )
    )
    meta = action["data"].get("dive") or {}
    selected = meta.get("steps", [])[point.step] if len(meta.get("steps", [])) > point.step else {}
    if (
        original is None
        or source is None
        or original.removed_event
        or original != point.model_copy(update={"removed_event": None, "removed_period": None})
    ):
        raise WorkflowError("Recover this actual original Dive gain and its stored point")
    if point.source_kind == "dive_deep":
        if (
            action["data"]["play"] != "dive_deep"
            or not action["data"].get("receipt")
            or not response
            or selected.get("applied_event") != point.source_event
            or not selected.get("store_void")
            or ActorRef.model_validate(meta["actor"]) != point.actor
        ):
            raise WorkflowError("Recover this actual original stored Dive choice")
    else:
        prove_gain_source(game, c, source, point, action)
    from girlframe.engine.m3_janus_requisitions import held
    from girlframe.services.m3_privileges import purchase_proof

    receipt = held(source, point.actor, STORAGE)
    if receipt is None or receipt.id != point.purchase:
        raise WorkflowError("The stored point needs its actual paid original entitlement")
    purchase_proof(c, game.store, receipt)
    link = prove_link(game, c, source, point.link)
    if link.battery != point.core or link.connection != point.connection:
        raise WorkflowError("The stored point belongs to its actual original Harpy connection")


def gain_source(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    choice: str,
    kind: Any,
    selected: bool,
) -> rules.GainSource | None:
    if not selected:
        return None
    if not available(game, c, state, actor):
        raise WorkflowError("Use only your actual owned Void Storage and connected Harpy")
    receipt = owned(c, game, state, actor, STORAGE)
    assert receipt is not None
    return rules.GainSource(purchase=receipt.id, choice=choice, kind=kind)


def prove_gain_source(
    game: GameService,
    c: Connection,
    source: GameState,
    point: rules.StoredVoid,
    action: dict[str, Any],
) -> None:
    events = t.events
    event = (
        c.execute(
            sa.select(events.c.kind, events.c.actor_id).where(
                events.c.campaign_id == game.store.campaign_id,
                events.c.id == point.source_event,
            )
        )
        .mappings()
        .first()
    )
    if event is None:
        raise WorkflowError("Recover the actual stored-gain source event")
    if point.source_kind == "dormant_void":
        proof = next(
            (
                x
                for x in source.facts
                if x.get("kind") == "dormant_void_paid"
                and x.get("event") == point.source_event
                and x.get("work") == point.choice
            ),
            None,
        )
        if proof is None or event["kind"] != "m3.dormant_void_taken":
            raise WorkflowError("Recover the actual Dormant gain and original owned response")
    elif point.source_kind == "call_guest":
        value = next((x for x in source.mockingbird.calls if x.id == point.choice), None)
        if (
            value is None
            or value.guest != point.actor
            or value.choice_event != point.source_event
            or event["kind"] != "m3.call_response"
        ):
            raise WorkflowError("Recover the actual guest's owned Void gain")
    else:
        row = c.execute(
            sa.select(t.m2["m2_choices"].c.kind).where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.id == point.choice,
                t.m2["m2_choices"].c.action_id == point.action,
            )
        ).first()
        expected = {
            "mockingbird_risk": ("mockingbird_risk",),
            "mockingbird_sex": ("mockingbird_sex_rewrite", "mockingbird_sex_self"),
        }.get(point.source_kind, ())
        response = (
            c.execute(
                sa.select(t.m2["m2_responses"]).where(
                    t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_responses"].c.choice_id == point.choice,
                )
            )
            .mappings()
            .first()
        )
        if (
            row is None
            or row[0] not in expected
            or response is None
            or response["event_id"] != point.source_event
            or response["actor_id"] != point.actor.entity
            or json.loads(response["answer_json"]).get("fields", {}).get("storage") != "yes"
            or not action["data"].get("receipt")
        ):
            raise WorkflowError("Recover the real original stored gain receipt and owned answer")


def allow_pending_unplug(
    game: GameService, c: Connection, state: GameState, connection: str, actor: ActorRef
) -> bool:
    from girlframe.engine.m3_frame_control import unplug
    from girlframe.engine.m3_void import FINAL
    from girlframe.services.m3_recovery import pending as pending_recovery
    from girlframe.services.m3_void import prepare_threshold

    if pending_recovery(game, c):
        return False
    table = t.m2["m2_actions"]
    actions = list(
        c.execute(
            sa.select(table.c.id).where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.state.not_in(("complete", "aborted")),
            )
        ).mappings()
    )
    for action in actions:
        for row in game.pending(c, action["id"]):
            if row["actor_id"] == actor.entity and row["kind"].endswith("void_threshold"):
                work = json.loads(row["body_json"]).get("work_id")
                if work:
                    prepared, _ = prepare_threshold(c, game, work, state)
                    for field in GameState.model_fields:
                        setattr(state, field, getattr(prepared, field))

    candidates = [
        x
        for x in state.void_thresholds
        if x.actor == actor and x.storage_points and x.stage not in FINAL
    ]
    if not candidates:
        return False
    after = unplug(
        state, connection, actor, "source-unplug-preview", "Actual source unplug preview"
    )
    stoppable = {
        w
        for x in candidates
        if not rules.full_family(after, actor, x.family)
        for w in x.source_works
    }
    for action in actions:
        pending = game.pending(c, action["id"])
        if not pending or any(
            row["actor_id"] != actor.entity
            or not row["kind"].endswith("void_threshold")
            or json.loads(row["body_json"]).get("work_id") not in stoppable
            for row in pending
        ):
            return False
    return bool(stoppable)


def complete_stopped(
    game: GameService,
    c: Connection,
    state: GameState,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    from girlframe.services.m3_void import complete

    for fact in state.facts:
        if fact.get("kind") == "janus_storage_cause_ended" and fact.get("event") == event:
            value = next(x for x in state.void_thresholds if x.id == fact["threshold"])
            complete(c, game, value, event, viewer, key)


def continuation_actor(
    game: GameService, c: Connection, event: str, viewer: GuildViewer | None
) -> int | str:
    if viewer is not None:
        return viewer.user_id
    actor = c.scalar(
        sa.select(t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.id == event,
        )
    )
    if actor is None:
        raise WorkflowError("A system continuation needs its actual persisted source event")
    return str(actor)


def intercept_replug(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    meta = action["data"]["janus"]
    if meta.get("storage_replug"):
        return bool(game.pending(c, action["id"]))
    link = next((x for x in state.battery_links if x.id == meta.get("link")), None)
    if link is None or link.phase != "connected" or not link.effects_event:
        return False
    activation = link.answer_event or link.effects_event
    works = []
    for family in ("girl", "frame"):
        points = [x for x in rules.for_family(state, link.caster, family) if x.link != link.id]
        if not points or not rules.full_family(state, link.caster, family):
            continue
        identity = str(uuid5(NAMESPACE_URL, "girlframe:storage-replug:" + link.id + ":" + family))
        body = dict(
            id=identity,
            reason="janus_storage_replug",
            source_action=action["id"],
            source_pdf=19,
            storage_pdf=70,
            source_event=activation,
            owner=link.caster.model_dump(mode="json"),
            character=link.caster.incarnation,
            details=dict(family=family),
            link=link.id,
            points=[x.id for x in points],
            immediate=True,
        )
        works.append(body)
        game.request(
            c, action, link.caster_controller, "janus_void_threshold", dict(work_id=identity)
        )
    meta["storage_replug"] = works
    return bool(works)


def synchronize_replug(
    game: GameService, c: Connection, action: dict[str, Any], event: str
) -> None:
    from girlframe.services.m3_work import related

    for work in action["data"]["janus"].get("storage_replug", ()):
        if c.scalar(
            sa.select(t.m3["m3_required_work"].c.id).where(
                t.m3["m3_required_work"].c.campaign_id == game.store.campaign_id,
                t.m3["m3_required_work"].c.id == work["id"],
            )
        ):
            continue
        related(
            c,
            game.store,
            dict(campaign_id=game.store.campaign_id, scene_id=action["scene_id"]),
            work["id"],
            int(work["owner"]["entity"]),
            int(work["owner"]["entity"]),
            "void_threshold",
            work,
            work["source_event"],
        )


def prove_replug(
    game: GameService, c: Connection, first: dict[str, Any], body: dict[str, Any], actor: ActorRef
) -> None:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == first["event_id"],
        )
    )
    source = GameState.model_validate_json(raw) if raw else None
    if source is None:
        raise WorkflowError("Recover the actual completed reconnect source")
    link = prove_link(game, c, source, body["link"])
    action = game.action(c, body["source_action"])
    original = next(
        (
            x
            for x in action["data"].get("janus", {}).get("storage_replug", ())
            if x["id"] == first["id"]
        ),
        None,
    )
    if (
        link.caster != actor
        or link.source_action != action["id"]
        or (link.answer_event or link.effects_event) != first["event_id"]
        or original != body
        or not body["points"]
        or not set(body["points"]) <= {x.id for x in rules.active(source, actor)}
    ):
        raise WorkflowError(
            "Use the actual completed new Battery connection, not another Void gain"
        )


def complete_replug(
    game: GameService,
    c: Connection,
    identity: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    from girlframe.engine.m3_void import FINAL
    from girlframe.services.m2_choices import ChoiceEngine
    from girlframe.services.m3_void import source

    row, body, actor = source(game, c, identity)
    state = load_state(c, game.store.campaign_id)
    if row["state"] != "resolved" or not any(
        identity in x.source_works and x.stage in FINAL for x in state.void_thresholds
    ):
        raise WorkflowError("Finish this original stored reconnect consequence")
    action = game.action(c, body["source_action"])
    choices = t.m2["m2_choices"]
    for pending in game.pending(c, action["id"]):
        if (
            pending["kind"] == "janus_void_threshold"
            and json.loads(pending["body_json"]).get("work_id") == identity
        ):
            c.execute(
                choices.update()
                .where(
                    choices.c.campaign_id == game.store.campaign_id, choices.c.id == pending["id"]
                )
                .values(state="completed_by_work", revision=choices.c.revision + 1)
            )
    if not game.pending(c, action["id"]):
        ChoiceEngine(game).finish(c, state, action)
    game.save_action(c, action)


class StorageService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def view(self, viewer: GuildViewer) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            values = [x for x in rules.points(state) if x.actor == actor and not x.removed_event]
            for point in values:
                prove(self.game, c, state, point)
            active = {x.id for x in rules.active(state, actor)}
            period_rows = c.scalars(
                sa.select(t.m3["m3_off_duty"].c.body_json).where(
                    t.m3["m3_off_duty"].c.campaign_id == self.store.campaign_id,
                    t.m3["m3_off_duty"].c.phase == "active",
                )
            )
            periods = []
            for raw in period_rows:
                period = Period.model_validate_json(raw)
                progress = period.progress.get(actor.entity)
                if (
                    period.character_ids.get(actor.entity) == actor.incarnation
                    and progress
                    and progress.roll
                    and progress.roll.source == "status"
                    and progress.roll.stage == "choices"
                    and progress.action_id
                    and not any(
                        x.actor == actor and x.removed_period == period.id
                        for x in rules.points(state)
                    )
                ):
                    periods.append(period.id)
            return dict(
                revision=state.revision,
                periods=periods,
                points=[x.model_dump(mode="json") | dict(active=x.id in active) for x in values],
            )

    def request(
        self,
        viewer: GuildViewer,
        key: str,
        revision: int,
        point_id: str,
        period_id: str,
        account: str,
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "playbooks")

        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            actor = current_ref(state, viewer.user_id)
            point = next((x for x in rules.points(state) if x.id == point_id), None)
            period = self._period(c, period_id)
            progress = period.progress.get(actor.entity)
            if (
                state.revision != revision
                or point is None
                or point.actor != actor
                or point.removed_event
                or not account.strip()
                or self.game.pending_actions(c)
                or period.phase != "active"
                or period.character_ids.get(actor.entity) != actor.incarnation
                or progress is None
                or progress.roll is None
                or progress.roll.source != "status"
                or progress.roll.stage != "choices"
                or progress.action_id is None
            ):
                raise WorkflowError(
                    "Request surgery after your own actual current Go Off-Duty roll"
                )
            source = self.game.action(c, progress.action_id)
            if source["data"]["play"] != "go_off_duty" or source["state"] != "complete":
                raise WorkflowError("Finish your actual Go Off-Duty roll before Foundation surgery")
            prove(self.game, c, state, point)
            if any(x.actor == actor and x.removed_period == period.id for x in rules.points(state)):
                raise WorkflowError("The Foundation removes at most one stored Void per period")
            if any(
                x.get("kind") == "janus_void_surgery"
                and x.get("period") == period.id
                and x.get("actor") == actor.model_dump_json()
                for x in state.facts
            ):
                raise WorkflowError("Use your existing actual surgical request")
            identity = str(uuid4())
            event = str(uuid4())
            state.facts.append(
                dict(
                    kind="janus_void_surgery",
                    id=identity,
                    point=point.id,
                    actor=actor.model_dump_json(),
                    period=period.id,
                    judge=str(period.handler_recipient or period.handler),
                    source_action=progress.action_id,
                    source_event=event,
                    account=account,
                    phase="pending",
                )
            )
            self.game.event(
                c, viewer.user_id, key, "m3.janus_storage_surgery_requested", state, event_id=event
            )
            return dict(id=identity)

        return self.store._write(
            viewer,
            key,
            "m3.janus_storage.request",
            dict(point=point_id, period=period_id, revision=revision, account=account),
            change,
            auto_audit=False,
            authorize=authorize,
        )

    def _period(self, c: Connection, identity: str) -> Period:
        raw = c.scalar(
            sa.select(t.m3["m3_off_duty"].c.body_json).where(
                t.m3["m3_off_duty"].c.campaign_id == self.store.campaign_id,
                t.m3["m3_off_duty"].c.id == identity,
            )
        )
        if not raw:
            raise WorkflowError("Use an actual existing Off-Duty period")
        return Period.model_validate_json(raw)

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        return [
            dict(id=x["id"], revision=state.revision, actionable=str(viewer.user_id) == x["judge"])
            for x in state.facts
            if x.get("kind") == "janus_void_surgery"
            and x.get("phase") == "pending"
            and str(viewer.user_id) in (x["judge"], ActorRef.model_validate_json(x["actor"]).entity)
        ]

    def get(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            self.game.authorize(c, viewer, game=False)
            state = load_state(c, self.store.campaign_id)
            work = next(
                (
                    x
                    for x in state.facts
                    if x.get("kind") == "janus_void_surgery" and x["id"] == identity
                ),
                None,
            )
            if work is None or str(viewer.user_id) not in (
                work["judge"],
                ActorRef.model_validate_json(work["actor"]).entity,
            ):
                raise WorkflowError(
                    "This actual surgical request is private to its patient/reviewer"
                )
            return dict(
                id=identity,
                revision=state.revision,
                work=work,
                can_act=work["phase"] == "pending" and work["judge"] == str(viewer.user_id),
            )

    def confirm(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "playbooks", director_response=True)

        def change(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            work = next(
                (
                    x
                    for x in state.facts
                    if x.get("kind") == "janus_void_surgery" and x["id"] == identity
                ),
                None,
            )
            if (
                work is None
                or work["judge"] != str(viewer.user_id)
                or work["phase"] != "pending"
                or state.revision != revision
                or not account.strip()
                or self.game.pending_actions(c)
            ):
                raise WorkflowError("Only the original Foundation reviewer records actual surgery")
            period = self._period(c, work["period"])
            if period.phase != "active":
                raise WorkflowError("Perform actual surgery during the original Off-Duty period")
            point = next(x for x in rules.points(state) if x.id == work["point"])
            patient = state.sheets.get(point.actor.entity)
            source = c.scalar(
                sa.select(t.m2["m2_state_history"].c.body_json).where(
                    t.m2["m2_state_history"].c.campaign_id == self.store.campaign_id,
                    t.m2["m2_state_history"].c.event_id == work["source_event"],
                )
            )
            original = GameState.model_validate_json(source) if source else None
            if (
                patient is None
                or patient.character_id != point.actor.incarnation
                or (original is None or work not in original.facts)
            ):
                raise WorkflowError("Surgery needs the actual original patient and owned request")
            prove(self.game, c, state, point)
            if point.removed_event:
                raise WorkflowError("This actual stored Void was already removed")
            event = str(uuid4())
            rules.put(
                state,
                point.model_copy(update={"removed_event": event, "removed_period": period.id}),
            )
            work.update(phase="completed", completion_event=event, surgery_account=account)
            rules.end_inactive_causes(state, event)
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.janus_storage_surgically_removed",
                state,
                event_id=event,
                point=point.id,
                period_id=period.id,
            )
            complete_stopped(self.game, c, state, event, viewer, key)
            return dict(id=identity, point=point.id)

        return self.store._write(
            viewer,
            key,
            "m3.janus_storage.confirm",
            dict(id=identity, revision=revision, account=account),
            change,
            auto_audit=False,
            authorize=authorize,
        )
