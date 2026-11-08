"""Consumed-String opportunities, original eye observations and real incoming child work."""

from typing import TYPE_CHECKING, Any, Literal, cast
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_changeling as rules
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_bonds import current_ref, make_helpless
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _cast, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def _use(
    game: "GameService", c: Connection, state: GameState, value: rules.Fingers, event: str
) -> None:
    from girlframe.services.m3_changeling import prove_fingers, validate_pending_fingers

    if value.event == event:
        validate_pending_fingers(game, c, state, value, event)
    elif prove_fingers(game, c, state, value.id) != value:
        raise WorkflowError("Preserve the actual source-owned consumed String")


def _actor(state: GameState, action: dict[str, Any]) -> ActorRef:
    for name in ("actor_context", "actor_basic", "battle", "engage", "tag_context"):
        meta = action["data"].get(name, {})
        if meta.get("actor"):
            return ActorRef.model_validate(meta["actor"])
    return current_ref(state, int(action["actor_id"]))


def _target(action: dict[str, Any]) -> ActorRef | None:
    for name in ("actor_context", "actor_basic", "battle", "engage", "tag_context"):
        meta = action["data"].get(name, {})
        if isinstance(meta.get("target"), dict):
            return ActorRef.model_validate(meta["target"])
    prepared = PlayInput.model_validate(action["data"]["prepared"])
    return prepared.target_actor


def fingers_effect(
    game: "GameService",
    c: Connection,
    state: GameState,
    use: rules.Fingers,
    event: str,
) -> tuple[GameState, tuple[str, ...]]:
    _use(game, c, state, use, event)
    changed = GameState.model_validate_json(state.model_dump_json())
    if use.kind == "pause":
        rules.put(
            changed,
            rules.PauseOpportunity(
                id=use.id,
                use=use.id,
                actor=use.actor,
                subject=use.subject,
                cast=use.cast,
                event=event,
            ),
        )
    elif use.kind == "sight":
        scenes = [
            item
            for item in state.scene_casts
            if item.open
            and any(
                role.actor == use.target and role.controller == use.subject.controller
                for role in item.roles
            )
            and (use.subject_scene is None or item.id == use.subject_scene)
        ]
        if len(scenes) != 1:
            raise WorkflowError("Choose the actual original eyes' real current scene")
        actual = resolve(
            state, use.target, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        if actual.cell is None:
            raise WorkflowError("SOURCE_EYE_POSITION_REQUIRED: establish the actual eyes' location")
        rules.put(
            changed,
            rules.EyeView(
                id=use.id,
                use=use.id,
                actor=use.actor,
                subject=use.subject,
                cast=scenes[0],
                event=event,
            ),
        )
    elif use.kind == "interrupt":
        original = game.action(c, use.incoming or "")
        if original["state"] in ("complete", "aborted") or _actor(state, original) != use.target:
            raise WorkflowError("Interrupt the real original person's genuinely pending Play")
        scene = _cast(game, c, state, int(original["channel_id"]))
        if not any(role.actor == use.target for role in scene.roles):
            raise WorkflowError("Keep the actual incoming role and its original source scene")
        pending = game.pending(c, original["id"])
        if any(
            row["kind"] not in ("tag_window", "tag_resolution", "tag_marker_agreement")
            for row in pending
        ):
            raise WorkflowError(
                "SOURCE_COMMITTED_EFFECT_INTERRUPT_REQUIRED: preserve already owed consequences"
            )
        game.request(c, original, use.subject.controller, "changeling_interrupt")
        row = next(
            row for row in game.pending(c, original["id"]) if row["kind"] == "changeling_interrupt"
        )
        rules.put(
            changed,
            rules.Interruption(
                id=use.id,
                use=use.id,
                incoming=original["id"],
                actor=use.target,
                original_play=original["data"]["play"],
                receipt=(original["data"].get("receipt") or {}).get("id"),
                cast=scene,
                choice=row["id"],
                event=event,
            ),
        )
    elif use.kind == "sex":
        # The original target separately confirms/declines; no performed Sex is inferred here.
        rules.put(changed, use.model_copy(update=dict(phase="sex")))
    else:
        raise WorkflowError("Use this port only for the actual finite source effect")
    return changed, ()


def _born[T: Model](
    game: "GameService",
    c: Connection,
    state: GameState,
    model: type[T],
    identity: str,
    mutable: set[str],
) -> T:
    value = rules.record(state, model, identity)
    data = value.model_dump()
    born = rules.record(_history(c, game, str(data["event"])), model, identity)
    if value.model_dump(exclude=mutable) != born.model_dump(exclude=mutable):
        raise WorkflowError("Keep the actual immutable original mental effect source")
    from girlframe.services.m3_changeling import prove_fingers

    prove_fingers(game, c, state, str(data["use"]))
    return value


def effect_complete(
    game: "GameService", c: Connection, state: GameState, use: rules.Fingers
) -> bool:
    if use.kind == "pause":
        value = rules.record(state, rules.PauseOpportunity, use.id)
        return value.completed_event is not None
    if use.kind == "sight":
        view = rules.record(state, rules.EyeView, use.id)
        return view.ended_event is not None or any(
            x.view == view.id for x in rules.records(state, rules.EyeObservation)
        )
    if use.kind == "interrupt":
        return rules.record(state, rules.Interruption, use.id).completed_event is not None
    return True


def effect_detail(
    game: "GameService",
    c: Connection,
    state: GameState,
    use: rules.Fingers,
) -> dict[str, Any]:
    from girlframe.services.m3_changeling import prove_fingers

    prove_fingers(game, c, state, use.id)
    if use.kind == "sight":
        value = _born(game, c, state, rules.EyeView, use.id, {"ended_event"})
        return dict(
            kind="sight",
            body=value.model_dump(mode="json"),
            observations=[
                x.model_dump(mode="json")
                for x in rules.records(state, rules.EyeObservation)
                if x.view == use.id
            ],
        )
    if use.kind == "pause":
        opening = _born(
            game,
            c,
            state,
            rules.PauseOpportunity,
            use.id,
            {"action", "bound_event", "completed_event"},
        )
        from girlframe.services.p1_source_pause import projection as pause_projection

        return dict(
            kind="pause",
            pause=pause_projection(game, c, use.id),
            body=opening.model_dump(mode="json"),
            child=dict(source_work=use.id, parent=None)
            if opening.action is None and not opening.completed_event
            else None,
        )
    if use.kind == "interrupt":
        interruption = _interruption(game, c, state, use.id)
        return dict(
            kind="interrupt",
            body=interruption.model_dump(mode="json"),
            child=dict(source_work=use.id, parent=interruption.incoming)
            if not interruption.child and not interruption.completed_event
            else None,
        )
    if use.kind == "sex":
        return dict(
            kind="sex",
            accepted=use.consent_event is not None,
            outcome=use.sex_outcome,
            action=use.action,
        )
    return {}


def _interruption(
    game: "GameService", c: Connection, state: GameState, identity: str
) -> rules.Interruption:
    value = _born(
        game, c, state, rules.Interruption, identity, {"child", "bound_event", "completed_event"}
    )
    original = game.action(c, value.incoming)
    if (
        _actor(state, original) != value.actor
        or original["data"]["play"] != value.original_play
        or (original["data"].get("receipt") or {}).get("id") != value.receipt
    ):
        raise WorkflowError("Preserve the original incoming receipt, paid resources and actor")
    return value


def prepare_child(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    use = next(
        (
            item
            for item in rules.records(state, rules.Fingers)
            if item.id == prepared.source_work and item.kind in ("pause", "interrupt")
        ),
        None,
    )
    if use is None:
        return None
    scene = _cast(game, c, state, channel)
    if use.kind == "pause":
        from girlframe.services.p1_source_pause import require_ready

        require_ready(game, c, state, use.id)
        grant = _born(
            game,
            c,
            state,
            rules.PauseOpportunity,
            use.id,
            {"action", "bound_event", "completed_event"},
        )
        actor, parent, choice = grant.actor, None, None
        if grant.action or grant.completed_event or prepared.parent:
            raise WorkflowError("Use the actual paused opening once, without a fake parent")
        if fingerprint(scene) != fingerprint(grant.cast):
            raise WorkflowError("Use the actual source opening before its original scene changes")
    else:
        interrupt = _interruption(game, c, state, use.id)
        actor, parent, choice = interrupt.actor, interrupt.incoming, interrupt.choice
        if (
            interrupt.child
            or interrupt.completed_event
            or prepared.parent not in (None, parent)
            or prepared.play == interrupt.original_play
        ):
            raise WorkflowError("Choose an actual different legally triggered Play/course")
        if fingerprint(scene) != fingerprint(interrupt.cast):
            raise WorkflowError("Keep the actual incoming scene and original roles")
    actual = resolve(
        state, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if (
        actual.controller != viewer.user_id
        or not prepared.trigger_confirmed
        or not prepared.context.strip()
    ):
        raise WorkflowError(
            "The actual original actor authors the real legally triggered performance"
        )
    return dict(
        id=use.id,
        kind=use.kind,
        actor=actor.model_dump(mode="json"),
        actor_controller=actual.controller,
        cast=scene.model_dump(mode="json"),
        cast_sha256=fingerprint(scene),
        table=sorted({x.controller for x in scene.roles}),
        parent=parent,
        choice=choice,
    )


def bind_child(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    meta = action["data"]["changeling_child"]
    if meta["kind"] == "pause":
        grant = _born(
            game,
            c,
            state,
            rules.PauseOpportunity,
            meta["id"],
            {"action", "bound_event", "completed_event"},
        )
        if grant.action or grant.completed_event:
            raise WorkflowError("Reserve the actual opening once")
        rules.put(state, grant.model_copy(update=dict(action=action["id"], bound_event=event)))
    else:
        value = _interruption(game, c, state, meta["id"])
        if value.child or value.completed_event:
            raise WorkflowError("Bind the actual different course once")
        rules.put(state, value.model_copy(update=dict(child=action["id"], bound_event=event)))


def pre_roll_child(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    action: dict[str, Any],
) -> None:
    meta = action["data"]["changeling_child"]
    from girlframe.services.m3_changeling import _live

    use = rules.get(state, meta["id"])
    _live(game, c, state, use.brain)
    _live(game, c, state, use.subject)
    if meta["kind"] == "pause":
        grant = _born(
            game,
            c,
            state,
            rules.PauseOpportunity,
            meta["id"],
            {"action", "bound_event", "completed_event"},
        )
        bound, ended = grant.action, grant.completed_event
    else:
        value = _interruption(game, c, state, meta["id"])
        bound, ended = value.child, value.completed_event
    if (
        bound != action["id"]
        or ended
        or viewer.user_id != meta["actor_controller"]
        or fingerprint(_cast(game, c, state, int(action["channel_id"]))) != meta["cast_sha256"]
    ):
        raise WorkflowError("Roll only the actual unchanged bound source performance")


def complete_child(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    from girlframe.services.m2_choices import ChoiceEngine
    from girlframe.services.m3_changeling import settle_fingers

    cause = event
    canonical = (
        c.scalar(
            sa.select(t.events.c.id).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        is not None
    )
    if canonical:
        event = str(uuid4())
    meta = action["data"]["changeling_child"]
    if action["state"] != "complete":
        raise WorkflowError("Complete the genuine child and its actual effects first")
    _roll_source(game, c, action)
    if meta["kind"] == "pause":
        grant = _born(
            game,
            c,
            state,
            rules.PauseOpportunity,
            meta["id"],
            {"action", "bound_event", "completed_event"},
        )
        if grant.action != action["id"]:
            raise WorkflowError("Use the bound actual opening performance")
        rules.put(state, grant.model_copy(update=dict(completed_event=event)))
    else:
        value = _interruption(game, c, state, meta["id"])
        if value.child != action["id"]:
            raise WorkflowError("Use the bound actual different course")
        original = game.action(c, value.incoming)
        rows = game.pending(c, original["id"])
        if any(
            row["kind"]
            not in ("tag_window", "tag_resolution", "tag_marker_agreement", "changeling_interrupt")
            for row in rows
        ):
            raise WorkflowError("Do not cancel already owed source consequences")
        for row in rows:
            c.execute(
                t.m2["m2_choices"]
                .update()
                .where(
                    t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_choices"].c.id == row["id"],
                    t.m2["m2_choices"].c.state == "pending",
                )
                .values(state="completed_by_work", revision=row["revision"] + 1)
            )
        original["data"].setdefault("result", {}).update(
            changeling_interrupted=value.id, replacement=action["id"], not_performed=True
        )
        original["state"] = "complete"
        game.save_action(c, original)
        rules.put(state, value.model_copy(update=dict(completed_event=event)))
        game.queue(
            c,
            original,
            "outcome",
            dict(
                play=original["data"]["play"],
                callsign=ChoiceEngine(game).original_callsign(state, original),
                receipt=original["data"].get("receipt"),
                total=original["data"].get("result", {}).get("total"),
                tier=original["data"].get("result", {}).get("tier"),
                changeling_interrupted=True,
                replacement=action["id"],
                not_affected=True,
            ),
        )
    settle_fingers(game, c, state, meta["id"], event)

    if canonical:
        _publish(
            game,
            c,
            state,
            cause,
            event,
            "m3.changeling_child_completed",
            action_id=action["id"],
            use=meta["id"],
        )


def release_child(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    if action["data"].get("receipt"):
        raise WorkflowError("Known source receipts remain committed")
    meta = action["data"]["changeling_child"]
    if meta["kind"] == "pause":
        value = _born(
            game,
            c,
            state,
            rules.PauseOpportunity,
            meta["id"],
            {"action", "bound_event", "completed_event"},
        )
        if value.action != action["id"] or value.completed_event:
            raise WorkflowError("Release only this genuine unrolled reservation")
        rules.put(state, value.model_copy(update=dict(action=None, bound_event=None)))
    else:
        interruption = _interruption(game, c, state, meta["id"])
        if interruption.child != action["id"] or interruption.completed_event:
            raise WorkflowError("Release only this genuine unrolled replacement")
        rules.put(state, interruption.model_copy(update=dict(child=None, bound_event=None)))


def recent_loss(
    game: "GameService",
    c: Connection,
    state: GameState,
    session: rules.Session,
    start_event: str,
    account: str,
    event: str,
) -> tuple[GameState, tuple[str, ...]]:
    if session.total >= 8 or session.recent_event or not account.strip():
        raise WorkflowError(
            "The original Handler adjudicates only this real low recent-memory loss"
        )
    start, through = _history(c, game, start_event), _history(c, game, session.event)
    if start.revision > through.revision:
        raise WorkflowError("Use an actual chronological fictional-time window")
    history = t.m2["m2_state_history"]
    events = tuple(
        c.scalars(
            sa.select(history.c.event_id)
            .where(
                history.c.campaign_id == game.store.campaign_id,
                history.c.revision >= start.revision,
                history.c.revision <= through.revision,
            )
            .order_by(history.c.revision)
        )
    )
    if start_event not in events or session.event not in events:
        raise WorkflowError("Recover the actual finite canonical memory window")
    changed = GameState.model_validate_json(state.model_dump_json())
    rules.put(
        changed,
        rules.RecentLoss(
            id=rules.identity("recent", session.id),
            session=session.id,
            actor=session.actor,
            brain=session.brain,
            start_event=start_event,
            through_event=session.event,
            start_revision=start.revision,
            through_revision=through.revision,
            events=events,
            handler=session.handler,
            controller=session.handler_controller,
            account=account,
            event=event,
        ),
    )
    return changed, ()


def can_recall(state: GameState, actor: ActorRef, knowledge_event: str) -> bool:
    """Only typed in-fiction knowledge consumers use this; OOC history/owed work stay intact."""
    return not any(
        value.actor == actor and knowledge_event in value.events
        for value in rules.records(state, rules.RecentLoss)
    )


def force_damage(
    game: "GameService",
    c: Connection,
    state: GameState,
    use: rules.Fingers,
    asset: str,
    event: str,
) -> tuple[GameState, tuple[str, ...]]:
    from girlframe.services.m3_battle import damage_actor

    _use(game, c, state, use, event)
    if use.kind != "damage" or use.main_event:
        raise WorkflowError("Use the actual pending forced self-damage source")
    actual = resolve(
        state, use.target, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if not any(item.id == asset and not item.damaged for item in actual.assets):
        raise WorkflowError("The actual affected person chooses one real undamaged owned Asset")
    changed = GameState.model_validate_json(state.model_dump_json())
    value = rules.ForcedDamage(
        id=use.id,
        use=use.id,
        target=use.target,
        asset=asset,
        controller=use.subject.controller,
        event=event,
    )
    rules.put(changed, value)
    changed, work = damage_actor(
        game,
        c,
        changed,
        target=use.target,
        asset_id=asset,
        source_action=None,
        source_work=use.id,
        event=event,
        actor=use.actor,
        opponent=use.actor,
        chooser_controller=use.subject.controller,
        occurrence="changeling_forced_self_damage",
        physical_blow=False,
    )
    rules.put(changed, value.model_copy(update=dict(work=tuple(work))))
    return changed, tuple(work)


def prove_damage_source(
    game: "GameService",
    c: Connection,
    state: GameState,
    identity: str,
    target: ActorRef,
    asset: str | None,
    event: str,
    actor: ActorRef | None,
    chooser: int | None,
) -> rules.Fingers:
    from girlframe.services.m3_changeling import prove_fingers

    use = prove_fingers(game, c, state, identity)
    value = rules.record(state, rules.ForcedDamage, identity)
    if value.event != event:
        born = rules.record(_history(c, game, value.event), rules.ForcedDamage, identity)
        if born != value:
            raise WorkflowError("Preserve the actual selected damage source and owed work")
    if (
        use.kind != "damage"
        or value.target != target
        or value.asset != asset
        or actor != use.actor
        or chooser != use.subject.controller
        or value.controller != chooser
    ):
        raise WorkflowError(
            "Use only the affected human's actual chosen Asset and original String source"
        )
    return use


def fry(
    game: "GameService",
    c: Connection,
    state: GameState,
    use: rules.Fingers,
    outcome: str,
    event: str,
) -> tuple[GameState, tuple[str, ...]]:
    _use(game, c, state, use, event)
    if (
        use.kind != "fry"
        or use.subject.kind != "human_npc"
        or use.target.kind != "npc"
        or outcome not in ("helpless", "dead")
        or use.main_event
    ):
        raise WorkflowError(
            "The original Handler chooses the actual proved human NPC's printed outcome"
        )
    changed = GameState.model_validate_json(state.model_dump_json())
    if outcome == "helpless":
        changed = make_helpless(changed, use.target, use.actor, event)
    else:
        if changed.world is None:
            raise WorkflowError("Recover the actual original human NPC")
        target = next(
            (item for item in changed.world.npcs if item.id == use.target.entity and item.alive),
            None,
        )
        if target is None:
            raise WorkflowError("Use the actual living original human NPC")
        changed.world = changed.world.model_copy(
            update=dict(
                npcs=tuple(
                    item.model_copy(update=dict(alive=False)) if item.id == target.id else item
                    for item in changed.world.npcs
                )
            )
        )
    rules.put(
        changed,
        rules.FryOutcome(
            id=use.id,
            use=use.id,
            subject=use.subject,
            handler=use.handler,
            controller=use.handler_controller,
            outcome=cast(Literal["helpless", "dead"], outcome),
            event=event,
        ),
    )
    return changed, ()


def sex_complete(game: "GameService", c: Connection, state: GameState, use: rules.Fingers) -> bool:
    from girlframe.engine.m3_changeling_sex import records as links

    if any(value.use == use.id for value in links(state)):
        from girlframe.services.m3_changeling_sex import sex_complete as linked_complete

        return linked_complete(game, c, state, use)
    if use.sex_outcome == "declined":
        return use.sex_event is not None and use.consent_event is None and use.action is None
    if (
        use.sex_outcome != "performed"
        or not use.action
        or not use.sex_event
        or not use.consent_event
    ):
        return False
    action = game.action(c, use.action)
    if (
        action["state"] != "complete"
        or action["data"].get("changeling_remote", {}).get("id") != use.id
    ):
        return False
    _roll_source(game, c, action)
    return True


def bind_remote_sex(
    game: "GameService",
    c: Connection,
    state: GameState,
    identity: str,
    action: dict[str, Any],
    event: str,
) -> None:
    from girlframe.services.m3_changeling import prove_fingers

    if action["data"].get("changeling_remote", {}).get("id") != identity:
        raise WorkflowError("Bind only exact source-specific remote metadata")
    use = prove_fingers(game, c, state, identity)
    if (
        use.kind != "sex"
        or use.consent_event is None
        or use.sex_outcome
        or use.action
        or _actor(state, action) != use.actor
    ):
        raise WorkflowError("Bind only the original actually accepted remote Sex source")
    rules.put(state, use.model_copy(update=dict(action=action["id"])))


def complete_remote_sex(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    from girlframe.services.m3_changeling import prove_fingers, settle_fingers

    cause = event
    canonical = (
        c.scalar(
            sa.select(t.events.c.id).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
            )
        )
        is not None
    )
    if canonical:
        event = str(uuid4())
    identity = action["data"]["changeling_remote"]["id"]
    use = prove_fingers(game, c, state, identity)
    if use.action != action["id"] or not use.consent_event or action["state"] != "complete":
        raise WorkflowError("Complete the actual bound consensual Sex source and all its effects")
    _roll_source(game, c, action)
    rules.put(state, use.model_copy(update=dict(sex_outcome="performed", sex_event=event)))
    settle_fingers(game, c, state, identity, event)

    if canonical:
        _publish(
            game,
            c,
            state,
            cause,
            event,
            "m3.changeling_remote_sex_completed",
            action_id=action["id"],
            use=identity,
        )


def synchronize(game: "GameService", c: Connection, event: str) -> None:
    from girlframe.services.m3_battle import synchronize_damage
    from girlframe.services.m3_changeling import synchronize_brains

    synchronize_damage(game, c, event)
    synchronize_brains(game, c, event)


def _publish(
    game: "GameService",
    c: Connection,
    state: GameState,
    cause: str,
    event: str,
    kind: str,
    **data: Any,
) -> None:
    row = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == cause
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise WorkflowError("Publish the genuine cause before its dependent effect completion")
    index = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.command_key == row["command_key"],
        )
    )
    game.event(
        c,
        row["actor_id"],
        row["command_key"],
        kind,
        state,
        event_id=event,
        event_index=0 if index is None else index + 1,
        source_event=cause,
        **data,
    )
