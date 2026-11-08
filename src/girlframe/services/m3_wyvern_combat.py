"""Actual source-owned Wyvern combat grants, restraints and protected resources."""

import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_battle as battle
from girlframe.engine import m3_wyvern as rules
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_state import ActorRef, Model, SceneCast
from girlframe.engine.m3_actors import fingerprint, frame_position, resolve
from girlframe.engine.m3_world import kill_gorgon, update
from girlframe.services.m2_game import GameService
from girlframe.services.m2_state import load_state
from girlframe.services.m3_access import Access
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_dose_up import _cast, _roll_source
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.m3_wyvern import prove_shield, prove_use, require_rule, validate_pending_use
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

KINDS: dict[type[Model], str] = {
    battle.WyvernDeflection: "wyvern_deflection",
    battle.WyvernPinResponse: "wyvern_pin_response",
    battle.WyvernEncirclement: "wyvern_encirclement",
    battle.WyvernCrush: "wyvern_crush",
}


def records[T: Model](state: GameState, model: type[T]) -> tuple[T, ...]:
    return tuple(
        model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == KINDS[model]
    )


def put(state: GameState, value: Model) -> None:
    kind, identity = KINDS[type(value)], str(value.model_dump()["id"])
    state.facts = [
        x for x in state.facts if not (x.get("kind") == kind and x.get("id") == identity)
    ]
    state.facts.append(dict(kind=kind, id=identity, body=value.model_dump_json()))


def _copy(state: GameState, other: GameState) -> None:
    for name in GameState.model_fields:
        setattr(state, name, getattr(other, name))


def _ref(action: dict[str, Any]) -> ActorRef:
    context = action["data"].get("tag_context", {})
    if context.get("actor"):
        return ActorRef.model_validate(context["actor"])
    actual = action["data"].get("actor_basic", {}).get("actor")
    if actual:
        return ActorRef.model_validate(actual)
    original = action["data"].get("character_ids", {}).get(str(action["actor_id"]))
    if original is None:
        raise WorkflowError("Recover the actual original source actor, never its account alias")
    return ActorRef(kind="pilot", entity=str(action["actor_id"]), incarnation=original)


def _target(action: dict[str, Any]) -> ActorRef | None:
    data = action["data"]
    prepared = data.get("prepared", {})
    if prepared.get("target_actor"):
        return ActorRef.model_validate(prepared["target_actor"])
    for name in (
        "battle",
        "engage",
        "snoop",
        "actor_basic",
        "alpha",
        "alpha_sex",
        "princess_sex",
        "stim_sex",
        "oldgen_sex",
        "casualty_sex",
        "vatgrown_sex",
        "bonded",
        "prince",
    ):
        raw = data.get(name, {}).get("target")
        if raw:
            return ActorRef.model_validate(raw)
    if prepared.get("target") is not None:
        owner = str(prepared["target"])
        original = data.get("character_ids", {}).get(owner)
        if original:
            return ActorRef(kind="pilot", entity=owner, incarnation=original)
    return None


def _live_frame(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, frame: str
) -> Any:
    view = resolve(state, actor, profiles(c, game.store.campaign_id), require_current_profile=False)
    if (
        not view.alive
        or rules.frame(state, actor) != frame
        or not view.piloting
        or view.frame_instance != frame
        or view.offstage_source
    ):
        raise WorkflowError("Use the actual original living Wyvern Frame while genuinely piloting")
    return view


def _use(
    game: GameService, c: Connection, state: GameState, use: rules.RousedUse, event: str
) -> None:
    validate_pending_use(game, c, state, use, event)
    _live_frame(game, c, state, use.actor, use.frame)
    cast = _cast(game, c, state, use.cast.channel)
    if fingerprint(cast) != fingerprint(use.cast) or not all(
        any(x.actor == ref for x in cast.roles) for ref in (use.actor, use.target)
    ):
        raise WorkflowError("Use the current actual encounter, not the old Rouse scene")
    target = resolve(
        state, use.target, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if not target.alive or target.offstage_source:
        raise WorkflowError("Choose the actual living present original foe")


def prove_damage_source(
    game: GameService,
    c: Connection,
    state: GameState,
    source_id: str,
    target: ActorRef,
    asset: str | None,
    event: str,
    actor: ActorRef | None,
    chooser: int | None,
) -> rules.RousedUse:
    value = next((x for x in rules.records(state, rules.RousedUse) if x.id == source_id), None)
    if value is None:
        raise WorkflowError("Recover the real original Roused damage grant")
    if value.event == event:
        validate_pending_use(game, c, state, value, event)
    else:
        value = prove_use(game, c, state, source_id)
    controller = next((x.controller for x in value.cast.roles if x.actor == value.actor), None)
    if (
        value.kind != "strike"
        or value.target != target
        or value.asset != asset
        or actor != value.actor
        or chooser != controller
    ):
        raise WorkflowError("Use only the exact actual original Roused strike and selected Asset")
    return value


def roused_effect(
    game: GameService, c: Connection, state: GameState, use: rules.RousedUse, event: str
) -> tuple[GameState, tuple[str, ...]]:
    _use(game, c, state, use, event)
    if use.kind == "strike":
        from girlframe.services.m3_battle import damage_actor

        actual = resolve(
            state, use.actor, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        if use.target_frame is not None:
            from girlframe.services.m3_battle import damage_frame_at_scene

            if use.asset is None:
                raise WorkflowError("Choose an actual parked Frame Asset")
            return damage_frame_at_scene(
                game,
                c,
                state,
                target=use.target,
                frame_instance=use.target_frame,
                asset_id=use.asset,
                source_action=None,
                source_work=use.id,
                event=event,
                actor=use.actor,
                chooser_controller=actual.controller,
                occurrence="wyvern_roused_parked_strike",
            )
        return damage_actor(
            game,
            c,
            state,
            target=use.target,
            asset_id=use.asset,
            source_action=None,
            source_work=use.id,
            event=event,
            actor=use.actor,
            opponent=use.actor,
            chooser_controller=actual.controller,
            occurrence="wyvern_roused_strike",
            physical_blow=True,
        )
    changed = GameState.model_validate_json(state.model_dump_json())
    if use.kind == "pin":
        if rules.pinned(changed, use.target) is not None:
            raise WorkflowError(
                "The actual original target is already pinned; preserve that source"
            )
        rules.put(
            changed,
            rules.Pin(
                id=rules.identity("pin", use.id),
                use=use.id,
                actor=use.actor,
                target=use.target,
                frame=use.frame,
                event=event,
            ),
        )
        return changed, ()
    if use.kind != "too_big" or not use.incoming:
        raise WorkflowError("Choose an actual printed Roused use")
    incoming = game.action(c, use.incoming)
    if (
        incoming["state"] in ("complete", "aborted")
        or incoming["scene_id"] != use.cast.id
        or _ref(incoming) != use.target
        or _target(incoming) != use.actor
        or any(x.incoming == incoming["id"] for x in records(state, battle.WyvernDeflection))
    ):
        raise WorkflowError("Proclaim too big against this actual unresolved incoming Play")
    if incoming["state"] not in ("awaiting_lock", "ready_to_roll", "tag_window"):
        raise WorkflowError(
            "Resolve already committed effects; they cannot be retroactively erased"
        )
    receipt = incoming["data"].get("receipt")
    value = battle.WyvernDeflection(
        id=rules.identity("deflection", use.id),
        use=use.id,
        actor=use.target,
        defender=use.actor,
        frame=use.frame,
        incoming=incoming["id"],
        original_play=incoming["data"]["play"],
        choice=game.request(
            c,
            incoming,
            resolve(
                state,
                use.target,
                profiles(c, game.store.campaign_id),
                require_current_profile=False,
            ).controller,
            "wyvern_replacement",
            dict(
                id=rules.identity("deflection", use.id),
                source_work=rules.identity("deflection", use.id),
            ),
        ),
        receipt=receipt["id"] if receipt else None,
        cast=use.cast,
        event=event,
    )
    put(changed, value)
    incoming["data"]["wyvern_deflected"] = value.id
    incoming["state"] = "awaiting_choices"
    game.save_action(c, incoming)
    return changed, ()


def require_damage_allowed(
    game: GameService, c: Connection, state: GameState, target: ActorRef
) -> None:
    shield = rules.shielded(state, target)
    if shield is None:
        return
    prove_shield(game, c, state, shield.id)
    raise WorkflowError("This actual recipient is Shielded; their Assets cannot be damaged")


def require_targetable(
    game: GameService, c: Connection, state: GameState, target: ActorRef
) -> None:
    shield = rules.shielded(state, target)
    if shield is None:
        return
    prove_shield(game, c, state, shield.id)
    raise WorkflowError("This actual recipient is Shielded; nobody can make Plays against them")


def observe(
    game: GameService, c: Connection, before: GameState, after: GameState, event: str
) -> None:
    """Existing source-only condition endings after genuine physical changes; no event writes."""
    for prior in rules.records(before, rules.Shield):
        if prior.ended_event:
            continue
        value = next((x for x in rules.records(after, rules.Shield) if x.id == prior.id), None)
        if value is None or value.ended_event:
            continue
        prove_shield(game, c, before, prior.id)
        if not rules.shield_active(after, value):
            rules.put(after, value.model_copy(update=dict(ended_event=event)))
    for prior_pin in rules.records(before, rules.Pin):
        if prior_pin.ended_event:
            continue
        pin_value = next((x for x in rules.records(after, rules.Pin) if x.id == prior_pin.id), None)
        if pin_value is None or pin_value.ended_event:
            continue
        source = prove_use(game, c, before, pin_value.use)
        old_frame = frame_position(before, pin_value.actor, pin_value.frame)
        new_frame = frame_position(after, pin_value.actor, pin_value.frame)
        moved = old_frame is not None and new_frame is not None and old_frame != new_frame
        sheet = after.sheets.get(pin_value.actor.entity)
        frame_ended = (
            sheet is not None
            and sheet.character_id == pin_value.actor.incarnation
            and (
                sheet.frame_scrapped
                or (sheet.frame_runtime is not None and sheet.frame_runtime.id != pin_value.frame)
            )
        )
        if (
            moved
            or frame_ended
            or battle.original_ended(after, pin_value.actor)
            or battle.original_ended(after, pin_value.target)
        ):
            rules.put(after, pin_value.model_copy(update=dict(ended_event=event)))
        if source.frame != pin_value.frame:
            raise WorkflowError("Preserve the actual original pinning Frame")


def complete_damage_work(
    game: GameService,
    c: Connection,
    row: dict[str, Any],
    event: str,
    viewer: GuildViewer | None,
    key: str,
) -> None:
    body = json.loads(row["body_json"])
    source_id = body.get("source_work")
    state = load_state(c, game.store.campaign_id)
    value = next((x for x in rules.records(state, rules.RousedUse) if x.id == source_id), None)
    if value is None or value.completed_event:
        return
    prove_use(game, c, state, value.id)
    born = next(
        x
        for x in rules.records(_history(c, game, value.event), rules.RousedUse)
        if x.id == value.id
    )
    if born.work != value.work:
        raise WorkflowError("Preserve the actual original strike's immutable required work")
    work = t.m3["m3_required_work"]
    for identity in born.work:
        latest = (
            c.execute(
                sa.select(work)
                .where(work.c.campaign_id == game.store.campaign_id, work.c.id == identity)
                .order_by(work.c.revision.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if latest is None or latest["state"] != "resolved":
            return
    final = str(uuid4())
    rules.put(state, value.model_copy(update=dict(completed_event=final)))
    actor_id = (
        viewer.user_id
        if viewer
        else next(x.controller for x in value.cast.roles if x.actor == value.actor)
    )
    index = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.command_key == key
        )
    )
    game.event(
        c,
        actor_id,
        key,
        "m3.wyvern_roused_completed",
        state,
        event_id=final,
        event_index=index + 1 if index is not None else 0,
        use=value.id,
        source_event=event,
    )


def shield(
    game: GameService, c: Connection, state: GameState, value: rules.Shield, event: str
) -> tuple[GameState, tuple[str, ...]]:
    from girlframe.services.m3_wyvern import prove_source

    source = prove_source(game, c, state, value.session)
    action = game.action(c, source.id)
    if (
        source.play != "wyvern_protector"
        or source.total < 8
        or source.actor != value.actor
        or source.target != value.target
        or source.frame != value.frame
        or source.event != event
        or value.event != event
        or value.id != rules.identity("shield", source.id)
        or value.high != (source.total >= 11)
        or value not in rules.records(state, rules.Shield)
        or action["data"]["wyvern"]["sourcefacts"].get("target_vessel") != value.target_vessel
    ):
        raise WorkflowError("Stage only the exact actual successful original Protector effect")
    _live_frame(game, c, state, value.actor, value.frame)
    actual = resolve(
        state, value.target, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if not actual.alive or actual.vessel_id != value.target_vessel:
        raise WorkflowError("Protect only the actual original living recipient/body")
    return state, ()


def _pin(game: GameService, c: Connection, state: GameState, identity: str) -> rules.Pin:
    value = next((x for x in rules.records(state, rules.Pin) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual original pin")
    use = prove_use(game, c, state, value.use)
    born = next(
        (x for x in rules.records(_history(c, game, value.event), rules.Pin) if x.id == identity),
        None,
    )
    if (
        use.kind != "pin"
        or use.actor != value.actor
        or use.target != value.target
        or use.frame != value.frame
        or value.event != use.event
        or born is None
        or any(
            getattr(born, k) != getattr(value, k)
            for k in ("id", "use", "actor", "target", "frame", "event")
        )
    ):
        raise WorkflowError("Preserve the real original physical pin and consumed Roused source")
    return value


def _deflection(
    game: GameService, c: Connection, state: GameState, identity: str
) -> battle.WyvernDeflection:
    value = next((x for x in records(state, battle.WyvernDeflection) if x.id == identity), None)
    if value is None:
        raise WorkflowError("Recover the actual original incoming replacement source")
    use = prove_use(game, c, state, value.use)
    born = next(
        (
            x
            for x in records(_history(c, game, value.event), battle.WyvernDeflection)
            if x.id == identity
        ),
        None,
    )
    if (
        born is None
        or use.kind != "too_big"
        or use.incoming != value.incoming
        or (use.actor, use.target, use.frame) != (value.defender, value.actor, value.frame)
        or any(
            getattr(born, k) != getattr(value, k)
            for k in (
                "id",
                "use",
                "actor",
                "defender",
                "frame",
                "incoming",
                "original_play",
                "receipt",
                "choice",
                "cast",
                "event",
            )
        )
    ):
        raise WorkflowError(
            "Preserve the actual incoming Play, opponent and original too-big source"
        )
    row = (
        c.execute(
            sa.select(t.m2["m2_choices"]).where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.id == value.choice,
            )
        )
        .mappings()
        .first()
    )
    original = game.action(c, value.incoming)
    if (
        row is None
        or row["kind"] != "wyvern_replacement"
        or row["action_id"] != value.incoming
        or _ref(original) != value.actor
        or _target(original) != value.defender
        or (original["data"].get("receipt") or {}).get("id") != value.receipt
    ):
        raise WorkflowError("Never clear or rewrite the actual incoming receipt/source row")
    if value.child:
        child = game.action(c, value.child)
        bound = next(
            (
                x
                for x in records(
                    _history(c, game, value.bound_event or ""), battle.WyvernDeflection
                )
                if x.id == identity
            ),
            None,
        )
        if (
            bound is None
            or bound.child != value.child
            or _ref(child) != value.actor
            or child["data"].get("wyvern_replacement", {}).get("id") != identity
            or child.get("parent_id") != value.incoming
            or child["data"].get("play") == value.original_play
        ):
            raise WorkflowError("Preserve the actual opponent's genuinely different replacement")
    return value


def _meta(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    identity: str,
    cast: SceneCast,
    *,
    parent: str | None,
    choice: str | None,
) -> dict[str, Any]:
    from girlframe.engine.m3_handler_consequences import active_handler

    handler = active_handler(state)
    if handler is None or state.handler is None:
        raise WorkflowError("Recover the original source Handler and actual table")
    return dict(
        id=identity,
        actor=actor.model_dump(mode="json"),
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        table=sorted(
            {x.controller for x in cast.roles}
            | ({cast.facilitator} if cast.facilitator is not None else set())
        ),
        handler=handler.model_dump(mode="json"),
        handler_controller=state.handler,
        parent=parent,
        choice=choice,
    )


def prepare_pin_response(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    from girlframe.engine.m3_actor_bonds import current_ref

    actor = current_ref(state, viewer.user_id) if str(viewer.user_id) in state.sheets else None
    active = rules.pinned(state, actor) if actor is not None else None
    selected = next(
        (x for x in rules.records(state, rules.Pin) if x.id == prepared.source_work), None
    )
    if active is None and selected is None:
        return None
    candidate = selected or active
    assert candidate is not None
    value = _pin(game, c, state, candidate.id)
    if selected is not None and active is not None and selected.id != active.id:
        raise WorkflowError("Deal only with this actual body's original pin")
    if prepared.source_work not in (None, value.id):
        raise WorkflowError("This pinned body must use its actual own pin response source")
    scene = _cast(game, c, state, channel)
    actual = resolve(
        state, value.target, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    target = prepared.target_actor
    if target is None and prepared.target == int(value.actor.entity):
        target = value.actor
    if (
        value.ended_event
        or actual.controller != viewer.user_id
        or target != value.actor
        or prepared.parent is not None
        or not prepared.trigger_confirmed
        or not prepared.context.strip()
        or not all(any(x.actor == ref for x in scene.roles) for ref in (value.actor, value.target))
    ):
        raise WorkflowError(
            "Deal with the actual original pinner through your own real triggered Play"
        )
    if value.child and game.action(c, value.child)["state"] not in ("complete", "aborted"):
        raise WorkflowError("Resume the actual already bound pin response")
    result = _meta(game, c, state, value.target, value.id, scene, parent=None, choice=None)
    result.update(
        pin=value.id, use=value.use, target=value.actor.model_dump(mode="json"), frame=value.frame
    )
    return result


def bind_pin_response(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    meta = action["data"]["wyvern_pin_response"]
    value = _pin(game, c, state, meta["id"])
    if value.ended_event or _ref(action) != value.target:
        raise WorkflowError("Bind only the actual pinned original actor's response")
    scene = SceneCast.model_validate_json(json.dumps(meta["cast"]))
    rules.put(state, value.model_copy(update=dict(child=action["id"])))
    put(
        state,
        battle.WyvernPinResponse(
            id=value.id + ":" + action["id"],
            pin=value.id,
            actor=value.target,
            pinner=value.actor,
            action=action["id"],
            cast=scene,
            event=event,
        ),
    )


def pre_roll_pin_response(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    meta = action["data"]["wyvern_pin_response"]
    pin = _pin(game, c, state, meta["id"])
    value = next(
        (x for x in records(state, battle.WyvernPinResponse) if x.action == action["id"]), None
    )
    actual = resolve(
        state, pin.target, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if (
        pin.ended_event
        or pin.child != action["id"]
        or value is None
        or value.actor != _ref(action)
        or actual.controller != viewer.user_id
        or fingerprint(_cast(game, c, state, int(action["channel_id"]))) != fingerprint(value.cast)
    ):
        raise WorkflowError("Resume the original bound physical pin response before RNG")
    born = next(
        (
            x
            for x in records(_history(c, game, value.event), battle.WyvernPinResponse)
            if x.id == value.id
        ),
        None,
    )
    if born != value:
        raise WorkflowError("Preserve the original pin response binding")


def complete_pin_response(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    value = next(
        (x for x in records(state, battle.WyvernPinResponse) if x.action == action["id"]), None
    )
    if value is None or value.completed_event:
        return
    _pin(game, c, state, value.pin)
    if action["state"] != "complete" or _ref(action) != value.actor:
        raise WorkflowError("Resolve the actual pin counter's effects before completion")
    _roll_source(game, c, action)
    final = str(uuid4())
    put(state, value.model_copy(update=dict(completed_event=final)))
    _saved_transition(
        game,
        c,
        state,
        event,
        "m3.wyvern_pin_response_completed",
        final,
        action_id=action["id"],
        pin=value.pin,
    )
    # A response is not itself release. Real maneuver/physical producers or pinner release do that.


def prepare_replacement(
    game: GameService,
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    if not any(x.id == prepared.source_work for x in records(state, battle.WyvernDeflection)):
        return None
    value = _deflection(game, c, state, prepared.source_work or "")
    original = game.action(c, value.incoming)
    scene = _cast(game, c, state, channel)
    actual = resolve(
        state, value.actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    row = next((x for x in game.pending(c, value.incoming) if x["id"] == value.choice), None)
    if (
        value.completed_event
        or value.child
        or actual.controller != viewer.user_id
        or row is None
        or prepared.play == value.original_play
        or prepared.parent not in (None, value.incoming)
        or not prepared.trigger_confirmed
        or not prepared.context.strip()
        or original["scene_id"] != scene.id
        or fingerprint(scene) != fingerprint(value.cast)
    ):
        raise WorkflowError(
            "The actual opponent must make a genuinely different legal Play instead"
        )
    result = _meta(
        game, c, state, value.actor, value.id, scene, parent=value.incoming, choice=value.choice
    )
    result.update(
        incoming=value.incoming, defender=value.defender.model_dump(mode="json"), frame=value.frame
    )
    return result


def bind_replacement(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    value = _deflection(game, c, state, action["data"]["wyvern_replacement"]["id"])
    if value.child or _ref(action) != value.actor or action["data"]["play"] == value.original_play:
        raise WorkflowError("Bind the original opponent's different replacement once")
    put(state, value.model_copy(update=dict(child=action["id"], bound_event=event)))


def pre_roll_replacement(
    game: GameService, c: Connection, viewer: GuildViewer, state: GameState, action: dict[str, Any]
) -> None:
    value = _deflection(game, c, state, action["data"]["wyvern_replacement"]["id"])
    actual = resolve(
        state, value.actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if (
        value.child != action["id"]
        or value.completed_event
        or actual.controller != viewer.user_id
        or fingerprint(_cast(game, c, state, int(action["channel_id"]))) != fingerprint(value.cast)
    ):
        raise WorkflowError("Roll only the actual already bound replacement source")


def complete_replacement(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    from girlframe.services.m2_choices import ChoiceEngine

    value = _deflection(game, c, state, action["data"]["wyvern_replacement"]["id"])
    if value.completed_event:
        return
    if value.child != action["id"] or action["state"] != "complete":
        raise WorkflowError("Complete the real replacement and all its actual effects")
    _roll_source(game, c, action)
    original = game.action(c, value.incoming)
    # Close unperformed windows; preserve every existing response and receipt.
    rows = game.pending(c, original["id"])
    if any(
        x["kind"]
        not in ("tag_window", "tag_resolution", "tag_marker_agreement", "wyvern_replacement")
        for x in rows
    ):
        raise WorkflowError(
            "Actual already-committed mandatory consequences must be completed first"
        )
    choices = t.m2["m2_choices"]
    for row in rows:
        c.execute(
            choices.update()
            .where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.id == row["id"],
                choices.c.state == "pending",
            )
            .values(state="completed_by_work", revision=choices.c.revision + 1)
        )
    final = str(uuid4())
    put(state, value.model_copy(update=dict(completed_event=final)))
    original["data"].setdefault("result", {}).update(
        wyvern_deflected=value.id, replacement=action["id"], not_affected=True
    )
    original["state"] = "complete"
    game.save_action(c, original)
    _saved_transition(
        game,
        c,
        state,
        event,
        "m3.wyvern_replacement_completed",
        final,
        action_id=action["id"],
        incoming=original["id"],
    )
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
            wyvern_replaced=True,
            replacement=action["id"],
            not_affected=True,
        ),
    )


def require_free(game: GameService, c: Connection, state: GameState, actor: ActorRef) -> None:
    value = rules.pinned(state, actor)
    if value is not None:
        _pin(game, c, state, value.id)
        raise WorkflowError("The actual pinned body must deal with its original pinner first")


def require_incoming_response(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], kind: str
) -> None:
    identity = action["data"].get("wyvern_deflected")
    if identity:
        value = _deflection(game, c, state, identity)
        if not value.completed_event:
            raise WorkflowError("Make the actual source-owned replacement Play before continuing")


class WyvernCombatService:
    def __init__(self, game: GameService):
        self.game, self.store = game, game.store

    def _tasks(self, c: Connection, viewer: GuildViewer) -> list[dict[str, Any]]:
        state = load_state(c, self.store.campaign_id)
        result = []
        sources: tuple[rules.Pin | battle.WyvernDeflection, ...] = (
            *rules.records(state, rules.Pin),
            *records(state, battle.WyvernDeflection),
        )
        for value in sources:
            use = prove_use(self.game, c, state, value.use)
            people = {x.controller for x in use.cast.roles if x.actor in (use.actor, use.target)}
            if viewer.user_id not in people:
                continue
            actor = value.target if isinstance(value, rules.Pin) else value.actor
            controller = next((x.controller for x in use.cast.roles if x.actor == actor), None)
            done = bool(
                value.ended_event if isinstance(value, rules.Pin) else value.completed_event
            )
            result.append(
                dict(
                    id=value.id,
                    revision=state.revision,
                    label="Actual Wyvern pin"
                    if isinstance(value, rules.Pin)
                    else "Actual replacement Play owed",
                    phase="complete" if done else "pending",
                    pending=not done and controller == viewer.user_id,
                )
            )
        return result

    def menu(self, viewer: GuildViewer, channel: int | None = None) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            return dict(revision=state.revision, tasks=self._tasks(c, viewer))

    def view(self, viewer: GuildViewer, identity: str) -> dict[str, Any]:
        with self.store.engine.connect() as c:
            _access(self.game, c, viewer)
            state = load_state(c, self.store.campaign_id)
            pin = next((x for x in rules.records(state, rules.Pin) if x.id == identity), None)
            value = (
                _pin(self.game, c, state, identity)
                if pin
                else _deflection(self.game, c, state, identity)
            )
            use = prove_use(self.game, c, state, value.use)
            controllers = {x.actor: x.controller for x in use.cast.roles}
            if viewer.user_id not in (controllers.get(use.actor), controllers.get(use.target)):
                raise WorkflowError(
                    "Only the original actual people reopen this private combat source"
                )
            done = bool(
                value.ended_event if isinstance(value, rules.Pin) else value.completed_event
            )
            actor = value.target if isinstance(value, rules.Pin) else value.actor
            is_pin = isinstance(value, rules.Pin)
            counter = dict(
                kind="wyvern_pin_response" if is_pin else "wyvern_replacement",
                parent=None if isinstance(value, rules.Pin) else value.incoming,
                channel=use.cast.channel,
                body=dict(source_work=value.id),
                actor=actor.model_dump(mode="json"),
            )
            child_action = self.game.action(c, value.child) if value.child else None
            active_child = bool(
                child_action and child_action["state"] not in ("complete", "aborted")
            )
            supported = (
                actor.kind == "pilot"
                and state.sheets.get(actor.entity) is not None
                and state.sheets[actor.entity].character_id == actor.incarnation
            )
            return dict(
                id=value.id,
                revision=state.revision,
                kind="pin" if is_pin else "replacement",
                label="Actual physical pin" if is_pin else "Actual different Play required",
                summary="The actual Frame pins the target until a real counter or release."
                if is_pin and not done
                else "The actual incoming Play must be replaced, preserving known dice and costs."
                if not done
                else "The original source and its genuine completion are saved.",
                can_counter=not done
                and not active_child
                and supported
                and viewer.user_id == controllers.get(actor),
                can_resume=not done
                and active_child
                and supported
                and viewer.user_id == controllers.get(actor),
                child=value.child,
                can_release=is_pin and not done and viewer.user_id == controllers.get(use.actor),
                counter=counter if not done else None,
            )

    def release_pin(
        self, viewer: GuildViewer, key: str, identity: str, revision: int, account: str
    ) -> dict[str, Any]:
        def operation(c: Connection) -> dict[str, Any]:
            self.game.unpaused(c)
            state = load_state(c, self.store.campaign_id)
            value = _pin(self.game, c, state, identity)
            actual = resolve(
                state,
                value.actor,
                profiles(c, self.store.campaign_id),
                require_current_profile=False,
            )
            if (
                state.revision != revision
                or value.ended_event
                or actual.controller != viewer.user_id
                or not account.strip()
                or len(account) > 1200
            ):
                raise WorkflowError(
                    "Only the actual original pinner records a genuine performed release"
                )
            event = str(uuid4())
            rules.put(state, value.model_copy(update=dict(ended_event=event)))
            self.game.event(
                c,
                viewer.user_id,
                key,
                "m3.wyvern_pin_released",
                state,
                event_id=event,
                pin=value.id,
            )
            return dict(id=value.id, revision=state.revision)

        return self.store._write(
            viewer,
            key,
            "m3.wyvern_pin_released",
            dict(id=identity, revision=revision, account=account),
            operation,
            auto_audit=False,
            authorize=lambda c: _access(self.game, c, viewer),
        )


def _access(game: GameService, c: Connection, viewer: GuildViewer) -> None:
    gate = Access(game.store)
    gate.authorize(c, viewer, "plays", director_response=True)
    assert gate.registry is not None
    gate.registry.require_available(rules.BURDEN)


def parked_strike_options(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, scene: SceneCast
) -> list[dict[str, Any]]:
    from girlframe.engine.m3_physical import occupied_frame

    source = resolve(
        state, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if source.cell is None or not source.piloting:
        return []
    result = []
    for role in scene.roles:
        target = role.actor
        if target == actor or target.kind != "pilot":
            continue
        sheet = state.sheets.get(target.entity)
        if (
            sheet is None
            or sheet.character_id != target.incarnation
            or "assets" not in sheet.public_fields
        ):
            continue
        view = resolve(
            state, target, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        pose = next((x for x in state.placements if x.actor == target), None)
        if (
            not view.alive
            or pose is None
            or pose.mode != "outside_frame"
            or view.frame_instance is None
            or frame_position(state, target, view.frame_instance) != source.cell
            or any(occupied_frame(x) == (target, view.frame_instance) for x in state.placements)
        ):
            continue
        runtime = sheet.frame_runtime
        if runtime and runtime.core_id or runtime is None and sheet.frame in ("JANUS", "JANUS-B"):
            continue
        for asset in sheet.assets:
            if asset.family == "frame" and not asset.damaged:
                result.append(
                    dict(
                        id=rules.identity("parked-strike", target.token, asset.id),
                        target=target.model_dump(mode="json"),
                        target_frame=view.frame_instance,
                        asset=asset.id,
                        kind="strike",
                        label="Strike " + view.label + "'s parked Frame: " + asset.name,
                    )
                )
    return result


def _saved_transition(
    game: GameService,
    c: Connection,
    state: GameState,
    source_event: str,
    kind: str,
    identity: str,
    **metadata: Any,
) -> str:
    origin = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == source_event
            )
        )
        .mappings()
        .first()
    )
    if origin is None:
        raise WorkflowError("Save the real source completion before its dependent transition")
    index = c.scalar(
        sa.select(sa.func.max(t.events.c.event_index)).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.command_key == origin["command_key"],
        )
    )
    return game.event(
        c,
        origin["actor_id"],
        origin["command_key"],
        kind,
        state,
        event_id=identity,
        event_index=index + 1 if index is not None else 0,
        source_event=source_event,
        **metadata,
    )


def release_unrolled(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> bool:
    if not action["data"].get("wyvern_pin_response") and not action["data"].get(
        "wyvern_replacement"
    ):
        return False
    if action["data"].get("receipt") or c.scalar(
        sa.select(t.m2["m2_receipts"].c.id).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == action["id"],
        )
    ):
        raise WorkflowError("A known actual counter roll cannot become an unrolled cancellation")
    if action["data"].get("wyvern_pin_response"):
        value = _pin(game, c, state, action["data"]["wyvern_pin_response"]["id"])
        if value.child != action["id"]:
            raise WorkflowError("Release only the actual unrolled bound counter")
        rules.put(state, value.model_copy(update=dict(child=None)))
    else:
        value_replacement = _deflection(game, c, state, action["data"]["wyvern_replacement"]["id"])
        if value_replacement.child != action["id"]:
            raise WorkflowError("Release only this actual unrolled replacement")
        put(state, value_replacement.model_copy(update=dict(child=None, bound_event=None)))
    return True


def crushing_options(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, cast: SceneCast
) -> dict[str, Any]:
    """Only the actual piloted, paid Crushing Bulk source supplies extra maneuvers."""
    if actor.kind != "pilot" or actor.entity not in state.sheets:
        return dict(maneuvers=[], vehicles=[])
    sheet = state.sheets[actor.entity]
    if sheet.character_id != actor.incarnation or sheet.frame != rules.FRAME:
        return dict(maneuvers=[], vehicles=[])
    if not rules.held(state, actor, rules.CRUSH):
        return dict(maneuvers=[], vehicles=[])
    require_rule(game, c, state, actor, rules.CRUSH)
    _live_frame(game, c, state, actor, rules.frame(state, actor))
    from girlframe.services.m3_vehicles import vehicle_options

    return dict(
        maneuvers=["encircle", "crush_small"], vehicles=vehicle_options(game, c, state, cast, actor)
    )


def apply_maneuver(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    row: dict[str, Any],
    kind: str,
    asset: str,
    vehicle: str | None,
) -> tuple[str, ...]:
    meta = action["data"]["engage"]
    actor, target = ActorRef.model_validate(meta["actor"]), ActorRef.model_validate(meta["target"])
    cast = SceneCast.model_validate_json(json.dumps(meta["cast"]))
    options = crushing_options(game, c, state, actor, cast)
    if kind not in options["maneuvers"]:
        raise WorkflowError("Use only the actual paid piloted Crushing Bulk maneuver")
    _roll_source(game, c, action)
    event = action["data"]["response_event"]
    frame = rules.frame(state, actor)
    if kind == "encircle":
        put(
            state,
            battle.WyvernEncirclement(
                id=rules.identity("encircle", action["id"], row["id"]),
                actor=actor,
                target=target,
                frame=frame,
                action=action["id"],
                choice=row["id"],
                asset=asset,
                event=event,
            ),
        )
        return ()
    if vehicle is not None and vehicle not in {x["id"] for x in options["vehicles"]}:
        raise WorkflowError("Choose a real assessed empty regular vehicle in the actual scene")
    if vehicle is None:
        target_gorgon = (
            next((x for x in state.world.gorgons if x.id == target.entity), None)
            if state.world
            else None
        )
        if (
            target.kind != "gorgon"
            or target_gorgon is None
            or target_gorgon.gorgon_class != "sprite"
            or not target_gorgon.alive
        ):
            raise WorkflowError(
                "Crush an actual opposing Sprite Gorgon or assessed empty regular vehicle"
            )
        require_targetable(game, c, state, target)
    crush = battle.WyvernCrush(
        id=rules.identity("crush", action["id"], row["id"]),
        actor=actor,
        frame=frame,
        action=action["id"],
        choice=row["id"],
        asset=asset,
        target=target if vehicle is None else None,
        vehicle=vehicle,
        event=event,
    )
    put(state, crush)
    meta["wyvern_crush"] = crush.id
    return resolve_crush(game, c, state, action, crush.id, event)


def _crush_source(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    identity: str,
) -> battle.WyvernCrush:
    value = next((x for x in records(state, battle.WyvernCrush) if x.id == identity), None)
    if (
        value is None
        or value.action != action["id"]
        or action["data"].get("engage", {}).get("wyvern_crush") != identity
    ):
        raise WorkflowError("Recover the exact actual Crushing Bulk maneuver source")
    _roll_source(game, c, action)
    meta = action["data"]["engage"]
    if ActorRef.model_validate(meta["actor"]) != value.actor or value.id != rules.identity(
        "crush", value.action, value.choice
    ):
        raise WorkflowError("Preserve the original actual Crushing Bulk actor and choice")
    birth_saved = (
        c.scalar(
            sa.select(t.events.c.id).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == value.event,
            )
        )
        is not None
    )
    if not birth_saved:
        pending = next((x for x in game.pending(c, action["id"]) if x["id"] == value.choice), None)
        if (
            pending is None
            or pending["kind"] != "engage_maneuvers"
            or int(pending["actor_id"]) != int(action["actor_id"])
            or action["data"].get("response_event") != value.event
        ):
            raise WorkflowError(
                "Stage crushing only inside its actual owned pending Engage response"
            )
        require_rule(game, c, state, value.actor, rules.CRUSH)
        _live_frame(game, c, state, value.actor, value.frame)
    else:
        born = _history(c, game, value.event)
        require_rule(game, c, born, value.actor, rules.CRUSH)
        if rules.frame(born, value.actor) != value.frame:
            raise WorkflowError("Preserve the original actual Crushing Bulk Frame")
        original = next((x for x in records(born, battle.WyvernCrush) if x.id == identity), None)
        if original is None or original.model_dump(
            exclude={"work", "completed_event", "outcome"}
        ) != value.model_dump(exclude={"work", "completed_event", "outcome"}):
            raise WorkflowError("Preserve the immutable actual Crushing Bulk birth")
        response = (
            c.execute(
                sa.select(t.m2["m2_responses"]).where(
                    t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_responses"].c.choice_id == value.choice,
                )
            )
            .mappings()
            .first()
        )
        if response is None:
            raise WorkflowError("Recover the actual canonical Engage maneuver response")
        answer = json.loads(response["answer_json"])
        if (
            "crush_small" not in answer.get("options", [])
            or answer.get("fields", {}).get("crush_small") != value.asset
            or answer.get("fields", {}).get("wyvern_vehicle") != value.vehicle
        ):
            raise WorkflowError("Preserve the real selected crush target and used Asset")
    return value


def resolve_crush(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    identity: str,
    event: str,
    *,
    allow_sprite: bool = True,
) -> tuple[str, ...]:
    """Apply the real whole-object effect; Sprite interception remains a genuine work chain."""
    value = _crush_source(game, c, state, action, identity)
    if value.completed_event:
        return ()
    if value.vehicle is not None:
        from girlframe.services.m3_vehicles import destroy_vehicle

        changed, work = destroy_vehicle(
            game, c, state, value.vehicle, value.actor, action["id"], event
        )
        _copy(state, changed)
        put(
            state,
            value.model_copy(
                update=dict(
                    work=tuple(work),
                    completed_event=event if not work else None,
                    outcome="crushed" if not work else "pending",
                )
            ),
        )
        return tuple(work)
    assert value.target is not None
    require_targetable(game, c, state, value.target)
    if allow_sprite:
        from girlframe.services.m3_sprite import defer

        changed, work = defer(
            game,
            c,
            state,
            target=value.target,
            asset=None,
            source_action=action["id"],
            source_work=None,
            event=event,
            opponent=value.actor,
            chooser=int(action["actor_id"]),
            occurrence="wyvern_crush",
            effect="fatal",
        )
        if work:
            _copy(state, changed)
            put(state, value.model_copy(update=dict(work=tuple(work))))
            return tuple(work)
    if state.world is None:
        raise WorkflowError("Recover the real Sprite body before crushing it")
    original = next(
        (x for x in state.world.gorgons if x.id == value.target.entity and x.alive), None
    )
    if original is None or original.gorgon_class != "sprite":
        raise WorkflowError("Crush only the actual original living Sprite body")
    crushed = original.model_copy(
        update=dict(
            assets=(), destroyed_assets=(*original.destroyed_assets, *original.assets), exposed=True
        )
    )
    state.world = update(
        state.world,
        gorgons=tuple(crushed if x.id == original.id else x for x in state.world.gorgons),
    )
    state.world = kill_gorgon(state.world, original.id)
    from girlframe.engine.m3_leviathan_obsession import release_dead_sources
    from girlframe.engine.m3_physical import interrupt_journeys

    _copy(
        state,
        battle.end_actor_casts(
            interrupt_journeys(state, value.target, event, "Actual Crushing Bulk destruction"),
            value.target,
            event,
        ),
    )
    _copy(state, release_dead_sources(state, event))
    put(state, value.model_copy(update=dict(completed_event=event, outcome="crushed")))
    return ()


def intercepted_crush(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    identity: str,
    event: str,
) -> None:
    """Called only after an actual Sprite has taken the original fatal physical blow."""
    value = _crush_source(game, c, state, action, identity)
    if value.completed_event:
        return
    if not value.work or not any(
        x.get("kind") == "sprite_blow_resolved"
        and x.get("id") in value.work
        and x.get("intercepted")
        for x in state.facts
    ):
        raise WorkflowError("The original Sprite must actually intercept before ending the crush")
    put(state, value.model_copy(update=dict(completed_event=event, outcome="intercepted")))


def release_counter_pin(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    maneuvers: dict[str, str],
    event: str,
) -> None:
    meta = action["data"].get("wyvern_pin_response")
    if not meta or not ({"drive_back", "reposition"} & set(maneuvers)):
        return
    value = _pin(game, c, state, meta["id"])
    if (
        value.child != action["id"]
        or _ref(action) != value.target
        or _target(action) != value.actor
    ):
        raise WorkflowError("Only the actual bound counter displaces the real original pinner")
    rules.put(state, value.model_copy(update=dict(ended_event=event)))
