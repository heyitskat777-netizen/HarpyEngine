"""Pause actual source-owned pending performances; rule choices stay in their services."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_bonded import Child, Source, records
from girlframe.services.m2_state import load_state
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


@dataclass(frozen=True)
class _Source:
    id: str
    kind: str
    channel: int
    scene: str
    event: str | None


def _sources(state: GameState) -> tuple[_Source, ...]:
    from girlframe.engine import m3_red_queen as royal

    bonded = tuple(
        _Source(x.id, "bonded", x.cast.channel, x.cast.id, x.effect_event)
        for x in records(state, Source)
        if x.action is None and x.phase in ("results", "child")
    )
    commands = tuple(
        _Source(x.id, "red_queen", x.cast.channel, x.cast.id, x.event)
        for x in royal.records(state, royal.Mark)
        if x.kind in ("flirt", "assault") and x.work and not x.completed_event
    )
    from girlframe.engine import m3_changeling as mental

    openings = tuple(
        _Source(x.id, "changeling_pause", x.cast.channel, x.cast.id, x.event)
        for x in mental.records(state, mental.PauseOpportunity)
        if not x.completed_event
    )
    from girlframe.engine import m3_ankou as ankou

    sequences = tuple(
        _Source(x.id, "ankou_sequence", x.venue.channel, x.venue.id, x.activated_event)
        for x in ankou.records(state, ankou.FeedbackSequence)
        if x.venue is not None
        and x.activated_event
        and not x.completed_event
        and not x.terminal_event
    )
    performances = tuple(
        _Source(x.id, "ankou_perform", x.cast.channel, x.cast.id, x.event)
        for x in ankou.records(state, ankou.Task)
        if x.kind == "perform" and not x.completed_event
    )
    from girlframe.engine import m3_bonded_am as borrowed_am

    am_encounters = tuple(
        _Source(x.id, "bonded_am", x.cast.channel, x.cast.id, x.event)
        for x in borrowed_am.sources(state)
        if x.phase in ("active", "effects") and not x.completed_event
    )
    return (*bonded, *commands, *openings, *sequences, *performances, *am_encounters)


def active(state: GameState, identity: str) -> bool:
    return any(x.id == identity for x in _sources(state))


def reserve(game: "GameService", c: Connection, state: GameState) -> None:
    from girlframe.services.p1_facilitator import require_scene_clear

    table = t.p1_source_pauses
    for source in _sources(state):
        existing = (
            c.execute(
                sa.select(table).where(
                    table.c.campaign_id == game.store.campaign_id,
                    table.c.id == source.id,
                )
            )
            .mappings()
            .first()
        )
        if existing is not None:
            continue
        scene = game.scene(c, source.channel)
        lock = game.lock(c, source.channel)
        require_scene_clear(game, c, source.channel)
        if scene["id"] != source.scene or (lock and lock["state"] != "released"):
            raise WorkflowError(
                "Finish the actual pending scene Play before activating this source"
            )
        other = c.scalar(
            sa.select(table.c.id).where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.channel_id == str(source.channel),
                table.c.state != "closed",
            )
        )
        if other is not None:
            raise WorkflowError("Finish or restore the previous actual source pause first")
        if source.event is None:
            raise WorkflowError("Activate the real source before reserving its scene pause")
        c.execute(
            table.insert().values(
                campaign_id=game.store.campaign_id,
                id=source.id,
                kind=source.kind,
                channel_id=str(source.channel),
                scene_id=source.scene,
                event_id=source.event,
                state="acquiring",
                snapshot_json="{}",
            )
        )


def projection(game: "GameService", c: Connection, identity: str) -> dict[str, Any]:
    table = t.p1_source_pauses
    row = (
        c.execute(
            sa.select(table).where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == identity,
            )
        )
        .mappings()
        .first()
    )
    return (
        dict(state=row["state"], error=row["last_error"], retry=row["state"] == "review")
        if row
        else dict(state="not_activated", error="", retry=False)
    )


def require_ready(game: "GameService", c: Connection, state: GameState, identity: str) -> None:
    if not active(state, identity) or projection(game, c, identity)["state"] != "held":
        raise WorkflowError(
            "SOURCE_PAUSE_NOT_ACKNOWLEDGED: wait for the actual scene pause; "
            "no choice effects applied"
        )


def _actual_child_chain(
    game: "GameService",
    c: Connection,
    root: str | None,
    prepared: PlayInput | None,
    action: dict[str, Any] | None,
) -> bool:
    """Only scope admission; normal Play services still require their exact owned choice."""
    identity = prepared.parent if prepared else (action or {}).get("id")
    seen: set[str] = set()
    table = t.m2["m2_actions"]
    while root and identity and identity not in seen:
        if identity == root:
            return True
        seen.add(identity)
        identity = c.scalar(
            sa.select(table.c.parent_id).where(
                table.c.campaign_id == game.store.campaign_id, table.c.id == identity
            )
        )
    return False


def require_clear(
    game: "GameService",
    c: Connection,
    channel: int,
    *,
    prepared: PlayInput | None = None,
    action: dict[str, Any] | None = None,
) -> None:
    table = t.p1_source_pauses
    rows = (
        c.execute(
            sa.select(table).where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.channel_id == str(channel),
                table.c.state != "closed",
            )
        )
        .mappings()
        .all()
    )
    if not rows:
        return
    state = load_state(c, game.store.campaign_id)
    for row in rows:
        if row["kind"] in ("ankou_sequence", "ankou_perform"):
            from girlframe.engine import m3_ankou as ankou

            source_id = (
                prepared.source_work
                if prepared
                else (action or {}).get("data", {}).get("ankou_effect_child", {}).get("id")
            )
            if prepared is not None:
                from girlframe.services.m3_required_plays import source_for_play

                linked_source = source_for_play(game, c, state, prepared)
                if linked_source is not None:
                    source_id = linked_source
            if source_id is None and action:
                source_id = action["data"].get("prepared", {}).get("source_work")
            if row["state"] != "held" or not active(state, row["id"]):
                raise WorkflowError("Wait for the actual original Ankou source pause")
            if row["kind"] == "ankou_perform":
                task = next(
                    (x for x in ankou.records(state, ankou.Task) if x.id == row["id"]), None
                )
                if task and (
                    source_id == task.id
                    or _actual_child_chain(game, c, task.child, prepared, action)
                ):
                    continue
            else:
                steps = [
                    x for x in ankou.records(state, ankou.FeedbackStep) if x.sequence == row["id"]
                ]
                if any(
                    source_id == x.id or _actual_child_chain(game, c, x.child, prepared, action)
                    for x in steps
                    if not x.completed_event
                ):
                    continue
                work = t.m3["m3_required_work"]
                loss = (
                    c.execute(
                        sa.select(work)
                        .where(work.c.campaign_id == game.store.campaign_id, work.c.id == source_id)
                        .order_by(work.c.revision.desc())
                        .limit(1)
                    )
                    .mappings()
                    .first()
                )
                known_loss_action = (
                    action is not None
                    and bool(action["data"].get("receipt"))
                    and action["data"].get("prepared", {}).get("source_work") == source_id
                )
                if loss is not None and (loss["state"] != "resolved" or known_loss_action):
                    import json

                    from girlframe.engine.m3_actor_state import ActorRef
                    from girlframe.services.m3_asset_loss import prove_loss_work

                    body = json.loads(loss["body_json"])
                    sequence = next(
                        x for x in ankou.records(state, ankou.FeedbackSequence) if x.id == row["id"]
                    )
                    own_unlink = body.get("reason") == "ankou_processor_unlink" and body.get(
                        "owner"
                    ) == sequence.actor.model_dump(mode="json")
                    if (
                        own_unlink
                        or body.get("reason") == "ankou_feedback_sequence"
                        and body.get("source_id") in {x.id for x in steps}
                    ):
                        original = ActorRef.model_validate(body["owner"])
                        prove_loss_work(game, c, dict(loss), body, original)
                        followup = (
                            prepared
                            if prepared is not None
                            else PlayInput.model_validate(action["data"]["prepared"])
                            if action is not None
                            else None
                        )
                        if followup is not None and followup.play in ("defeat", "keep_your_head"):
                            continue
            raise WorkflowError(
                "Resolve the actual original Ankou source and its required followups"
            )
        if row["kind"] == "changeling_pause":
            from girlframe.engine import m3_changeling as mental

            identity = (
                prepared.source_work
                if prepared
                else (action or {}).get("data", {}).get("changeling_child", {}).get("id")
            )
            opening = next(
                (x for x in mental.records(state, mental.PauseOpportunity) if x.id == row["id"]),
                None,
            )
            if (
                (
                    identity == row["id"]
                    or opening is not None
                    and _actual_child_chain(game, c, opening.action, prepared, action)
                )
                and opening is not None
                and active(state, opening.id)
                and row["state"] == "held"
                and (action is None or _actual_child_chain(game, c, opening.action, None, action))
            ):
                continue
            raise WorkflowError("SOURCE_SCENE_PAUSED: use the actual original psychic opening")
        if row["kind"] == "red_queen":
            from girlframe.engine import m3_red_queen as royal

            identity = (
                prepared.source_work
                if prepared
                else (action or {}).get("data", {}).get("red_queen_child", {}).get("id")
            )
            mark = next((x for x in royal.records(state, royal.Mark) if x.id == row["id"]), None)
            if (
                (
                    identity == row["id"]
                    or mark is not None
                    and _actual_child_chain(game, c, mark.child, prepared, action)
                )
                and mark is not None
                and active(state, mark.id)
                and row["state"] == "held"
                and (action is None or _actual_child_chain(game, c, mark.child, None, action))
            ):
                continue
            raise WorkflowError("SOURCE_SCENE_PAUSED: perform the actual original Court command")
        source_work = (
            prepared.source_work
            if prepared
            else (action or {}).get("data", {}).get("bonded_child", {}).get("child")
        )
        child = next(
            (x for x in records(state, Child) if x.id == source_work and x.source == row["id"]),
            None,
        )
        if child is None:
            child = next(
                (
                    x
                    for x in records(state, Child)
                    if x.source == row["id"]
                    and _actual_child_chain(game, c, x.child, prepared, action)
                ),
                None,
            )
        if child is None or row["state"] != "held" or not active(state, row["id"]):
            raise WorkflowError(
                "SOURCE_SCENE_PAUSED: resolve the original source or wait for restoration"
            )


def retry(game: "GameService", viewer: GuildViewer, key: str, identity: str) -> dict[str, Any]:
    def operation(c: Connection) -> dict[str, Any]:
        from girlframe.services.m3_access import Access
        from girlframe.services.m3_bonded import prove

        Access(game.store).authorize(c, viewer, "plays", director_response=True)
        state = load_state(c, game.store.campaign_id)
        current = projection(game, c, identity)
        if current["state"] == "not_activated":
            raise WorkflowError("Recover the actual original source pause")
        source_table = t.p1_source_pauses
        kind = c.scalar(
            sa.select(source_table.c.kind).where(
                source_table.c.campaign_id == game.store.campaign_id, source_table.c.id == identity
            )
        )
        if kind in ("ankou_sequence", "ankou_perform"):
            from girlframe.services.m3_ankou import prove_task
            from girlframe.services.m3_ankou_feedback_sequences import prove as prove_sequence

            if kind == "ankou_sequence":
                sequence = prove_sequence(game, c, state, identity)
                people = {int(sequence.actor.entity)}
            else:
                task = prove_task(game, c, state, identity)
                people = {task.controller}
        elif kind == "changeling_pause":
            from girlframe.services.m3_changeling import prove_fingers

            use = prove_fingers(game, c, state, identity)
            people = {use.controllers[use.actor.token], use.subject.controller}
        elif kind == "red_queen":
            from girlframe.services.m3_red_queen import prove_mark

            mark = prove_mark(game, c, state, identity)
            author = c.scalar(
                sa.select(t.events.c.actor_id).where(
                    t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == mark.event
                )
            )
            people = {x.controller for x in mark.cast.roles if x.actor == mark.target}
            if author is not None:
                people.add(int(author))
        else:
            source = prove(game, c, state, identity)
            people = set(source.controllers.values())
        if viewer.user_id not in people:
            raise WorkflowError("Only original source owners review its permission delivery")
        table = t.p1_source_pauses
        row = (
            c.execute(
                sa.select(table).where(
                    table.c.campaign_id == game.store.campaign_id,
                    table.c.id == identity,
                )
            )
            .mappings()
            .first()
        )
        if row is None or row["state"] != "review" or row["lease_until"] > int(game.store.clock()):
            raise WorkflowError("Reopen the actual source pause review first")
        c.execute(
            table.update()
            .where(
                table.c.campaign_id == game.store.campaign_id,
                table.c.id == identity,
            )
            .values(state="acquiring" if active(state, identity) else "restoring", last_error="")
        )
        game.event(c, viewer.user_id, key, "m3.source_pause_retry", source_id=identity)
        return projection(game, c, identity)

    return game.store._write(
        viewer, key, "m3.source_pause_retry", dict(source_id=identity), operation, auto_audit=False
    )
