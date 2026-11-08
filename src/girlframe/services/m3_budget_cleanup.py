"""Owned cleanup scene and actual original recipient Void, using shared consequences."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_budget_cleanup as rules
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_core import Followup
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_plays import _ordinary_scene_idle
from girlframe.services.m3_work import related
from girlframe.services.onboarding import OnboardingStore, WorkflowError
from girlframe.services.read_only_bot import GuildViewer


def source(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Cleanup:
    value = rules.get(state, identity)
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == value.source_event,
            )
        )
        .mappings()
        .first()
    )
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == value.source_event,
        )
    )
    original = rules.get(GameState.model_validate_json(raw), identity) if raw else None
    immutable = (
        "id",
        "source_work",
        "source_event",
        "period",
        "mission",
        "location",
        "handler",
        "people",
        "mode",
        "account",
        "selected",
        "rng_source",
    )
    if (
        event is None
        or original is None
        or event["kind"] != "m3.strain_effect_applied"
        or event["actor_id"] != value.handler.entity
        or json.loads(event["payload_json"]).get("rule_id") != "strain.budget.low.4.1"
        or json.loads(event["payload_json"]).get("work_id") != value.source_work
        or any(getattr(original, k) != getattr(value, k) for k in immutable)
    ):
        raise WorkflowError(
            "Recover the original mission-site cleanup and its single exposure draw"
        )
    return value


def current(game: GameService, c: Connection, state: GameState, value: rules.Cleanup) -> None:
    if not same_handler_body(state, value.handler) or any(
        current_ref(state, int(x.entity)) != x for x in value.people
    ):
        raise WorkflowError("Recover this cleanup's actual original participants")
    if state.world is None or not any(x.id == value.location for x in state.world.locations):
        raise WorkflowError("Recover the cleanup's actual past-mission site")


def at_site(
    game: GameService, c: Connection, state: GameState, value: rules.Cleanup, actor: ActorRef
) -> None:
    assert state.world is not None
    site = next(x for x in state.world.locations if x.id == value.location)
    actual = resolve(
        state, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if actual.cell is not None and actual.cell != site.cell:
        raise WorkflowError(
            "Complete actual travel to this cleanup site before reporting attendance"
        )
    if (
        actual.offstage_source
        or actual.custody
        or actual.vitals_active is False
        or actual.subsumed
        or any(x.actor == actor and x.incapacitated for x in state.placements)
    ):
        raise WorkflowError("Recover this person's actual presence and freedom before cleanup")


def work(c: Connection, game: GameService, identity: str) -> dict[str, Any]:
    table = t.m3["m3_required_work"]
    row = (
        c.execute(
            sa.select(table)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == identity,
            )
            .order_by(table.c.revision.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    if row is None or row["kind"] != "budget_cleanup":
        raise WorkflowError("Recover the actual required cleanup work")
    return dict(row)


def finish(c: Connection, game: GameService, identity: str, event: str) -> None:
    row = work(c, game, identity)
    if row["state"] == "pending":
        c.execute(
            t.m3["m3_required_work"]
            .insert()
            .values(
                **(
                    row
                    | dict(
                        revision=row["revision"] + 1,
                        state="resolved",
                        event_id=event,
                    )
                )
            )
        )


class CleanupService:
    def __init__(self, store: OnboardingStore):
        self.store, self.game = store, GameService(store)

    def available(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        result = []
        for value in rules.cases(load_state(c, self.store.campaign_id)):
            if value.phase == "complete" or viewer.user_id not in {
                int(value.handler.entity),
                *(int(p.entity) for p in value.people),
            }:
                continue
            actionable = bool(
                value.phase == "scene"
                and value.scene
                and (
                    viewer.user_id not in value.scene.acknowledgements
                    or viewer.user_id == int(value.handler.entity)
                    and set(value.scene.participants) == set(value.scene.acknowledgements)
                )
                or value.phase == "rewrite"
                and value.selected is not None
                and value.people[value.selected].entity == str(viewer.user_id)
            )
            result.append(dict(id=value.id, mode=value.mode, actionable=actionable))
        return result

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            Access(self.store).authorize(c, viewer, "strain")
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            if viewer.user_id not in {
                int(value.handler.entity),
                *(int(p.entity) for p in value.people),
            }:
                raise WorkflowError("Only this cleanup's original humans may review it")
            target = value.people[value.selected] if value.selected is not None else None
            own = target is not None and target.entity == str(viewer.user_id)
            assets = []
            storage = False
            sup = None
            if own and value.phase == "rewrite":
                assert target is not None
                current(self.game, c, state, value)
                from girlframe.engine.m3_janus_storage import effective_assets
                from girlframe.services.m3_janus_storage import available

                assets = [
                    dict(id=x.id, label=x.name, family=x.family)
                    for x in effective_assets(state, target)
                    if not x.void
                ]
                storage = available(self.game, c, state, target)
                from girlframe.services.m3_sup import offer

                sup = offer(self.game, c, state, target)
            return dict(
                id=identity,
                revision=state.revision,
                phase=value.phase,
                mode=value.mode,
                handler=viewer.user_id == int(value.handler.entity),
                own=own,
                attended=bool(value.scene and viewer.user_id in value.scene.acknowledgements),
                all_attended=bool(
                    value.scene
                    and set(value.scene.participants) == set(value.scene.acknowledgements)
                ),
                summary=value.account,
                assets=assets,
                storage=storage,
                sup=sup,
                thresholds=value.thresholds,
            )

    def act(
        self,
        viewer: GuildViewer,
        key: str,
        identity: str,
        expected: int,
        action: str,
        account: str,
        asset: str | None = None,
        storage: bool = False,
        growth_fields: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if not account.strip() or len(account) > 1200:
            raise WorkflowError("Describe your actual cleanup attendance or owned Void alteration")

        def authorize(c: Connection) -> None:
            Access(self.store).authorize(c, viewer, "strain")
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            if viewer.user_id not in {
                int(value.handler.entity),
                *(int(p.entity) for p in value.people),
            }:
                raise WorkflowError("Only an original cleanup participant may respond")

        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            _ordinary_scene_idle(c, self.game)
            state = load_state(c, self.store.campaign_id)
            value = source(self.game, c, state, identity)
            current(self.game, c, state, value)
            if state.revision != expected or value.phase == "complete":
                raise WorkflowError("STALE_CLEANUP: reopen the original source")
            event = str(uuid4())
            followups: tuple[Followup, ...] = ()
            if value.phase == "scene" and value.scene is not None:
                if asset is not None or storage or growth_fields:
                    raise WorkflowError("This cleanup scene grants no Asset or automatic Void")
                scene = value.scene.model_copy(deep=True)
                if action == "attend" and viewer.user_id not in scene.acknowledgements:
                    actor = (
                        value.handler
                        if value.handler.entity == str(viewer.user_id)
                        else current_ref(state, viewer.user_id)
                    )
                    at_site(self.game, c, state, value, actor)
                    scene.acknowledgements += (viewer.user_id,)
                    value = value.model_copy(update=dict(scene=scene))
                elif (
                    action == "end"
                    and viewer.user_id == int(value.handler.entity)
                    and set(scene.participants) == set(scene.acknowledgements)
                ):
                    value = value.model_copy(update=dict(phase="complete", ended_event=event))
                else:
                    raise WorkflowError(
                        "Record your own attendance, then the actual Handler ends the scene"
                    )
            elif value.phase == "rewrite" and action == "rewrite" and value.selected is not None:
                actor = value.people[value.selected]
                from girlframe.services.m3_sup import parse

                growth = parse(self.game, c, state, actor, growth_fields or {})
                if actor.entity != str(viewer.user_id) or (asset is None and growth is None):
                    raise WorkflowError(
                        "Only the randomly selected original Girl chooses its Void alteration"
                    )
                if growth and (asset is not None or storage):
                    raise WorkflowError("Sup growth replaces the existing-Asset/Storage choice")
                from girlframe.engine.m3_janus_storage import alter
                from girlframe.services.m3_janus_storage import gain_source

                gain = gain_source(self.game, c, state, actor, identity, "budget_cleanup", storage)
                actual = resolve(
                    state, actor, profiles(c, self.store.campaign_id), require_current_profile=False
                )
                if actual.piloting is None:
                    raise WorkflowError(
                        "Review your body and Frame mode in /mission position first"
                    )
                state, followups = alter(
                    state,
                    actor,
                    asset or "",
                    account.strip(),
                    identity,
                    event,
                    piloting=actual.piloting,
                    source=gain,
                    growth=growth,
                )
                actual_asset: str | None
                if growth:
                    from girlframe.engine.m3_sup import growths

                    actual_asset = next(
                        x.asset for x in growths(state) if x.actor == actor and x.event == event
                    )
                else:
                    actual_asset = asset
                thresholds = tuple(identity + ":void:" + x.kind for x in followups)
                value = value.model_copy(
                    update=dict(
                        phase="threshold" if thresholds else "complete",
                        asset=actual_asset,
                        description=account.strip(),
                        storage=storage,
                        gain_event=event,
                        thresholds=thresholds,
                        ended_event=None if thresholds else event,
                    )
                )
            else:
                raise WorkflowError(
                    "Resume the original cleanup scene, owned alteration or Void consequence"
                )
            value = rules.Cleanup.model_validate_json(value.model_dump_json())
            rules.put(state, value)
            state.facts.append(
                dict(
                    kind="budget_cleanup_action",
                    cleanup=identity,
                    action=action,
                    account=account.strip(),
                    event=event,
                )
            )
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.budget_cleanup_changed",
                state,
                event_id=event,
                cleanup=identity,
                action=action,
            )
            if value.phase == "complete":
                finish(c, self.game, identity, event)
            for item, threshold in zip(followups, value.thresholds, strict=True):
                family = "girl" if item.kind == "girl_void_threshold" else "frame"
                assert value.selected is not None
                actor = value.people[value.selected]
                related(
                    c,
                    self.store,
                    work(c, self.game, identity),
                    threshold,
                    int(actor.entity),
                    int(actor.entity),
                    "void_threshold",
                    dict(
                        owner=actor.model_dump(mode="json"),
                        character=actor.incarnation,
                        details=dict(family=family),
                        source_action=None,
                        source_pdf=19,
                        reason="budget_cleanup",
                        cleanup=identity,
                    ),
                    event,
                )
            return dict(id=identity, phase=value.phase)

        try:
            return self.store._write(
                viewer,
                key,
                "m3.budget_cleanup_changed",
                dict(
                    id=identity,
                    expected=expected,
                    action=action,
                    account=account,
                    asset=asset,
                    storage=storage,
                )
                | (dict(growth_fields=growth_fields) if growth_fields is not None else {}),
                operation,
                auto_audit=False,
                authorize=authorize,
            )
        except ValueError as error:
            raise WorkflowError(str(error)) from None


def prove_gain(
    game: GameService,
    c: Connection,
    state: GameState,
    identity: str,
) -> rules.Cleanup:
    value = source(game, c, state, identity)
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == value.gain_event,
            )
        )
        .mappings()
        .first()
    )
    if (
        value.mode != "exposure"
        or value.selected is None
        or value.asset is None
        or value.description is None
        or value.gain_event is None
        or event is None
        or event["kind"] != "m3.budget_cleanup_changed"
        or event["actor_id"] != value.people[value.selected].entity
        or json.loads(event["payload_json"]).get("cleanup") != identity
        or json.loads(event["payload_json"]).get("action") != "rewrite"
    ):
        raise WorkflowError(
            "Recover the single original exposure and the selected Girl's actual alteration"
        )
    return value


def prove_void_source(
    game: GameService,
    c: Connection,
    first: dict[str, Any],
    body: dict[str, Any],
    actor: ActorRef,
) -> None:
    raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.event_id == first["event_id"],
        )
    )
    if raw is None:
        raise WorkflowError("Recover the actual cleanup Void gain history")
    value = prove_gain(game, c, GameState.model_validate_json(raw), body.get("cleanup", ""))
    if (
        value.selected is None
        or actor != value.people[value.selected]
        or first["id"] not in value.thresholds
        or first["event_id"] != value.gain_event
        or first["off_duty_id"] != value.period
        or body.get("source_action") is not None
    ):
        raise WorkflowError("Recover the original cleanup's source-bound Void consequence")


def complete_void(
    game: GameService,
    c: Connection,
    work_id: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    table = t.m3["m3_required_work"]
    body = c.scalar(
        sa.select(table.c.body_json).where(
            table.c.campaign_id == game.store.campaign_id,
            table.c.id == work_id,
            table.c.revision == 1,
        )
    )
    if body is None:
        raise WorkflowError("Recover the actual cleanup Void continuation")
    identity = json.loads(body).get("cleanup", "")
    state = load_state(c, game.store.campaign_id)
    value = source(game, c, state, identity)
    if value.phase == "complete":
        return
    if work_id not in value.thresholds or value.phase != "threshold":
        raise WorkflowError("Resume the exact original cleanup Void continuation")
    for required in value.thresholds:
        status = c.scalar(
            sa.select(table.c.state)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == required,
            )
            .order_by(table.c.revision.desc())
            .limit(1)
        )
        if status != "resolved":
            return
    rules.put(state, value.model_copy(update=dict(phase="complete", ended_event=event)))
    prior_index = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.command_key == key,
        )
    )
    from girlframe.services.m3_janus_storage import continuation_actor

    completed = game.event(
        c,
        continuation_actor(game, c, event, viewer),
        key,
        "m3.budget_cleanup_completed",
        state,
        cleanup=identity,
        event_index=1 if prior_index is None else prior_index + 1,
    )
    finish(c, game, identity, completed)
