"""Real AM body adjustments, never invented damage or an empty-set Void threshold."""

import json
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_am_body as bodies
from girlframe.engine import m3_am_jailbroken as occupancy
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_janus_storage import effective_assets
from girlframe.services.m2_game import GameService
from girlframe.services.m3_asset_loss import snapshots
from girlframe.services.m3_work import related
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer


class Adjustment(Model):
    operation: Literal["code", "return", "jailbroken"]
    source_id: str
    event: str
    actor: ActorRef
    previous: str
    vessel: str
    before_components: tuple[str, ...]
    after_components: tuple[str, ...]
    source_action: str | None

    @property
    def work(self) -> str:
        return str(
            uuid5(NAMESPACE_URL, "girlframe:am-body-void:" + self.event + ":" + self.source_id)
        )


def adjustment(
    game: GameService,
    c: Connection,
    event: str,
    operation: Literal["code", "return", "jailbroken"],
    identity: str,
) -> tuple[GameState, GameState, Adjustment]:
    before, after = snapshots(game, c, event)
    if operation == "jailbroken":
        from girlframe.services.m3_am_jailbroken import prove

        value = prove(game, c, after, identity)
        if value.event != event:
            raise WorkflowError("Use the actual same-mind Occupancy birth")
        actor, previous, vessel = value.actor, value.previous, value.vessel
        action = None
    else:
        from girlframe.services.m3_am_body import prove as prove_swap
        from girlframe.services.m3_dose_up import _roll_source

        swap = prove_swap(game, c, after, identity)
        _roll_source(game, c, game.action(c, swap.action))
        expected = swap.event if operation == "code" else swap.returned_event
        if expected != event:
            raise WorkflowError("Use only the actual Code Swap or its genuine hooked return")
        actor = swap.actor
        previous = swap.original_vessel if operation == "code" else swap.new_vessel
        vessel = swap.new_vessel if operation == "code" else swap.original_vessel
        action = swap.action if operation == "code" else None
    old, new = before.sheets.get(actor.entity), after.sheets.get(actor.entity)
    if (
        actor.kind != "pilot"
        or old is None
        or new is None
        or old.character_id != actor.incarnation
        or new.character_id != actor.incarnation
        or old.girl != "AM"
        or new.girl != "AM"
        or bodies._pose(before, actor).vessel_id != previous
        or bodies._pose(after, actor).vessel_id != vessel
        or previous == vessel
        or [x for x in old.assets if x.family == "frame"]
        != [x for x in new.assets if x.family == "frame"]
        or old.frame_runtime != new.frame_runtime
    ):
        raise WorkflowError("Preserve the actual same living AM, changed body and unchanged Frame")
    source = Adjustment(
        operation=operation,
        source_id=identity,
        event=event,
        actor=actor,
        previous=previous,
        vessel=vessel,
        before_components=tuple(
            x.id for x in effective_assets(before, actor) if x.family == "girl"
        ),
        after_components=tuple(x.id for x in effective_assets(after, actor) if x.family == "girl"),
        source_action=action,
    )
    return before, after, source


def _threshold(before: GameState, after: GameState, actor: ActorRef) -> bool:
    old = tuple(x for x in effective_assets(before, actor) if x.family == "girl")
    new = tuple(x for x in effective_assets(after, actor) if x.family == "girl")
    return bool(new and all(x.void for x in new) and not (old and all(x.void for x in old)))


def _body(value: Adjustment) -> dict[str, Any]:
    return dict(
        reason="am_body_adjustment",
        operation=value.operation,
        source_id=value.source_id,
        adjustment_event=value.event,
        previous=value.previous,
        vessel=value.vessel,
        before_components=list(value.before_components),
        after_components=list(value.after_components),
        owner=value.actor.model_dump(mode="json"),
        character=value.actor.incarnation,
        source_action=value.source_action,
        source_pdf=19,
        details=dict(family="girl"),
        immediate=True,
    )


def prove_void_source(
    game: GameService,
    c: Connection,
    row: dict[str, Any],
    body: dict[str, Any],
    actor: ActorRef,
) -> None:
    operation = body.get("operation")
    if operation not in ("code", "return", "jailbroken"):
        raise WorkflowError("Use a genuine AM body operation, not generic asset damage")
    before, after, value = adjustment(
        game, c, body.get("adjustment_event", ""), operation, body.get("source_id", "")
    )
    expected = _body(value)
    if (
        value.actor != actor
        or row["id"] != value.work
        or row["revision"] != 1
        or row["event_id"] != value.event
        or row["kind"] != "void_threshold"
        or row["owner_id"] != actor.entity
        or row["subject_id"] != actor.entity
        or any(body.get(k) != v for k, v in expected.items())
        or not _threshold(before, after, actor)
    ):
        raise WorkflowError("Prove the exact nonempty all-Void AM adjustment and original work")


def synchronize(game: GameService, c: Connection, event: str) -> tuple[str, ...]:
    """After canonical operation (and Code SQL response), append genuine owed work once."""
    from girlframe.services.m2_state import load_state

    state = load_state(c, game.store.campaign_id)
    operations: list[tuple[Literal["code", "return", "jailbroken"], str]] = []
    for swap in bodies.swaps(state):
        if swap.event == event:
            operations.append(("code", swap.id))
        if swap.returned_event == event:
            operations.append(("return", swap.id))
    operations.extend(("jailbroken", x.id) for x in occupancy.history(state) if x.event == event)
    result = []
    table = t.m3["m3_required_work"]
    for operation, identity in operations:
        before, after, value = adjustment(game, c, event, operation, identity)
        if not _threshold(before, after, value.actor):
            continue
        if not c.scalar(
            sa.select(table.c.id)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == value.work,
            )
            .limit(1)
        ):
            scope: dict[str, Any] = dict(campaign_id=game.store.campaign_id)
            if value.source_action:
                scope["scene_id"] = game.action(c, value.source_action)["scene_id"]
            else:
                scenes = [
                    x
                    for x in after.scene_casts
                    if x.open and any(r.actor == value.actor for r in x.roles)
                ]
                if len(scenes) == 1:
                    scope["scene_id"] = scenes[0].id
                else:
                    scope["campaign_context"] = True
            related(
                c,
                game.store,
                scope,
                value.work,
                int(value.actor.entity),
                int(value.actor.entity),
                "void_threshold",
                _body(value),
                event,
            )
        result.append(value.work)
    return tuple(result)


def intercept_finish(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    event: str,
) -> bool:
    """Hold the real Code source before finish; no fictitious choice or premature work birth."""
    from girlframe.engine import m3_am_code as code
    from girlframe.services.m2_state import load_state

    meta = action["data"].get("am_body_void")
    if meta is not None:
        table = t.m3["m3_required_work"]
        row = (
            c.execute(
                sa.select(table)
                .where(
                    table.c.campaign_id == game.store.campaign_id,
                    table.c.id == meta["work"],
                )
                .order_by(table.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if meta.get("completed_event"):
            if row is None or row["state"] != "resolved":
                raise WorkflowError("Finish the actual body adjustment threshold before Code")
            return False
        action["state"] = "awaiting_choices"
        return True
    value = code.session(state, action["data"]["am_code"]["maintenance"])
    if not value.body_swap:
        return False
    swap = bodies.swap(state, value.body_swap)
    if swap.event != event or not _threshold(
        load_state(c, game.store.campaign_id), state, swap.actor
    ):
        return False
    # Only a prediction while this real response is applying. synchronize later proves the
    # canonical Swap + SQL response before creating any actual required work.
    work = str(uuid5(NAMESPACE_URL, "girlframe:am-body-void:" + event + ":" + swap.id))
    action["data"]["am_body_void"] = dict(work=work, source=swap.id, source_event=event)
    action["state"] = "awaiting_choices"
    return True


def complete_void_continuation(
    game: GameService,
    c: Connection,
    work_id: str,
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    from uuid import uuid4

    from girlframe.engine.m3_void import FINAL
    from girlframe.services.m2_state import load_state
    from girlframe.services.m3_am_code import finish
    from girlframe.services.m3_janus_storage import continuation_actor

    table = t.m3["m3_required_work"]
    rows = list(
        c.execute(
            sa.select(table)
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == work_id,
            )
            .order_by(table.c.revision)
        ).mappings()
    )
    if not rows or rows[-1]["state"] != "resolved":
        raise WorkflowError("Resolve this actual AM body threshold before source completion")
    body = json.loads(rows[0]["body_json"])
    actor = ActorRef.model_validate(body["owner"])
    prove_void_source(game, c, dict(rows[0]), body, actor)
    if body["source_action"] is None:
        return  # A true unrolled return/occupancy has no invented parent Action.
    state = load_state(c, game.store.campaign_id)
    threshold = next(
        (
            x
            for x in state.void_thresholds
            if work_id in x.source_works and x.actor == actor and x.stage in FINAL
        ),
        None,
    )
    action = game.action(c, body["source_action"])
    meta = action["data"].get("am_body_void")
    if (
        threshold is None
        or meta is None
        or meta.get("work") != work_id
        or meta.get("source") != body["source_id"]
        or meta.get("source_event") != body["adjustment_event"]
    ):
        raise WorkflowError("Recover the original Code source's actual completed body threshold")
    if meta.get("completed_event"):
        return
    completed = str(uuid4())
    meta["completed_event"] = completed
    meta["threshold_event"] = event
    if action["state"] not in ("complete", "aborted"):
        finish(game, c, state, action, completed)
    game.save_action(c, action)
    prior = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.command_key == key,
        )
    )
    game.event(
        c,
        continuation_actor(game, c, event, viewer),
        key,
        "m3.am_body_void_completed",
        state,
        event_id=completed,
        event_index=1 if prior is None else prior + 1,
        action_id=action["id"],
        work_id=work_id,
        threshold_event=event,
    )
