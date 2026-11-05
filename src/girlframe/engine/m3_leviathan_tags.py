"""Actual Leviathan Tag gifts and zero-modifier trigger marking across actual roles."""

from typing import Any
from uuid import NAMESPACE_URL, uuid5

from girlframe.engine.m2 import GameState, TagState
from girlframe.engine.m3_actor_state import ActorRef
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.engine.m3_leviathan_obsession import _harpy
from girlframe.engine.m3_world_state import WorldTag


def tags(state: GameState, actor: ActorRef) -> tuple[Any, ...]:
    if actor.kind == "pilot":
        sheet = state.sheets.get(actor.entity)
        if sheet is None or sheet.character_id != actor.incarnation:
            raise ValueError("Use the actual original Girl's Tags, never a replacement profile")
        return tuple(sheet.tags)
    if actor.kind == "handler":
        if not same_handler_body(state, actor):
            raise ValueError("Use the actual current Handler body, not its successor")
        return tuple(state.handler_tags)
    if _harpy(state, actor):
        from girlframe.engine.m3_harpy_defeat import harpy

        return harpy(state, actor).tags
    if state.world is None:
        raise ValueError("Recover the actual original world body and its Tags")
    collection = {"npc": "npcs", "gorgon": "gorgons", "external_pilot": "pilots"}[actor.kind]
    body = next(
        (x for x in getattr(state.world, collection) if x.id == actor.entity and x.alive), None
    )
    if body is None:
        raise ValueError("Use the actual living original body's Tag authority")
    return tuple(body.tags)


def _put(state: GameState, actor: ActorRef, values: tuple[Any, ...]) -> None:
    if actor.kind == "pilot":
        state.sheets[actor.entity].tags = list(values)
        state.sheets[actor.entity].revision += 1
    elif actor.kind == "handler":
        state.handler_tags = list(values)
    elif _harpy(state, actor):
        from girlframe.engine.m3_harpy_defeat import update

        changed = update(state, actor, tags=values)
        state.harpy_states, state.native_harpies, state.janus_cores = (
            changed.harpy_states,
            changed.native_harpies,
            changed.janus_cores,
        )
    else:
        assert state.world is not None
        collection = {"npc": "npcs", "gorgon": "gorgons", "external_pilot": "pilots"}[actor.kind]
        state.world = state.world.model_copy(
            update={
                collection: tuple(
                    x.model_copy(update={"tags": values}) if x.id == actor.entity else x
                    for x in getattr(state.world, collection)
                )
            }
        )


def controller(state: GameState, actor: ActorRef) -> int:
    if actor.kind == "pilot":
        tags(state, actor)
        return int(actor.entity)
    if actor.kind == "handler":
        tags(state, actor)
        return int(actor.entity)
    from girlframe.engine.m3_actors import resolve

    return resolve(state, actor, (), require_current_profile=False).controller


def _awake_type(state: GameState, source: ActorRef, event: str, rule: str) -> None:
    body = (
        next((x for x in state.world.gorgons if x.id == source.entity), None)
        if state.world
        else None
    )
    if (
        body is not None
        and body.gorgon_class == "dormant"
        and not any(
            x.get("kind") == "dormant_awakening" and x.get("gorgon") == source.entity
            for x in state.facts
        )
    ):
        state.facts.append(
            dict(
                kind="dormant_awakening",
                cause="own_type_play",
                gorgon=source.entity,
                actor=source.model_dump_json(),
                event=event,
                source_type=rule,
                source_action="",
                source_choice="",
            )
        )


def give_obsessed(original: GameState, source: ActorRef, target: ActorRef, event: str) -> GameState:
    body = (
        next(
            (
                x
                for x in original.world.gorgons
                if x.id == source.entity and x.alive and "leviathan" in x.types
            ),
            None,
        )
        if original.world
        else None
    )
    if source.kind != "gorgon" or body is None or source == target or not event.strip():
        raise ValueError("Give a real obsessed Tag from this actual Leviathan to another person")
    state = GameState.model_validate_json(original.model_dump_json())
    current = tags(state, target)
    identity = str(uuid5(NAMESPACE_URL, event + ":obsessed-tag:" + target.token))
    if any(x.id == identity for x in current):
        raise ValueError("This original source already gave its actual Tag")
    giver, owner = controller(state, source), controller(state, target)
    if target.kind in ("pilot", "handler"):
        tag: Any = TagState(
            id=identity,
            label="obsessed",
            giver=giver,
            giver_actor=source,
            observers=tuple(dict.fromkeys((giver, owner))),
        )
    elif _harpy(state, target):
        from girlframe.engine.m3_void_state import HarpyTag

        tag = HarpyTag(
            id=identity,
            label="obsessed",
            giver=giver,
            giver_ref=source,
            observers=tuple(dict.fromkeys((giver, owner))),
        )
    else:
        tag = WorldTag(id=identity, label="obsessed", giver_entity=source.model_dump_json())
    _put(state, target, (*current, tag))
    state.facts.append(
        dict(
            kind="leviathan_obsessed_tag",
            source=source.model_dump_json(),
            target=target.model_dump_json(),
            tag=identity,
            event=event,
        )
    )
    _awake_type(state, source, event, "gorgon-type.leviathan.leviathan-type")
    return GameState.model_validate_json(state.model_dump_json())


def count(state: GameState, actor: ActorRef) -> int:
    return len(tags(state, actor))


def mark_modifier(
    original: GameState, target: ActorRef, tag_id: str, scene: str, event: str
) -> tuple[GameState, bool]:
    """Mark one actual Girl Tag for the ordinary modifier, without a Type cost/wake."""
    if not scene.strip() or not event.strip():
        raise ValueError("Use the actual scene and ordinary Tag-mark event")
    values = tags(original, target)
    chosen = next((x for x in values if x.id == tag_id), None)
    if chosen is None or chosen.rejection_pending:
        raise ValueError("Choose an actual available Girl Tag")
    girl = target.kind in ("pilot", "external_pilot") or (
        target.kind == "handler"
        and any(x.active and x.id == target.incarnation for x in original.director_contexts)
    )
    if not girl:
        raise ValueError("This mark operation is only for an actual Girl Tag")
    field = "trigger_scene" if isinstance(chosen, WorldTag) else "scene_used"
    if getattr(chosen, field) == scene:
        raise ValueError("This actual Tag was already used in this scene")
    state = GameState.model_validate_json(original.model_dump_json())
    _put(
        state,
        target,
        tuple(
            x.model_copy(update={"marked": True, field: scene}) if x.id == tag_id else x
            for x in values
        ),
    )
    state.facts.append(
        dict(
            kind="leviathan_ordinary_tag_marked",
            actor=target.model_dump_json(),
            tag=tag_id,
            scene=scene,
            event=event,
        )
    )
    return GameState.model_validate_json(state.model_dump_json()), bool(chosen.marked)


def mark_cost(
    original: GameState,
    source: ActorRef,
    target: ActorRef,
    tag_id: str,
    scene: str,
    event: str,
) -> tuple[GameState, bool]:
    if source.kind != "gorgon" or source == target or not scene.strip() or not event.strip():
        raise ValueError("The trigger needs the actual distinct source, subject and scene")
    if original.world is None or not any(
        x.id == source.entity and x.alive and "leviathan" in x.types for x in original.world.gorgons
    ):
        raise ValueError("Use the actual living original Leviathan")
    state = GameState.model_validate_json(original.model_dump_json())
    values = tags(state, target)
    tag = next((x for x in values if x.id == tag_id and x.label.casefold() == "obsessed"), None)
    if tag is None or tag.rejection_pending:
        raise ValueError("Mark an actual available obsessed Tag; owed rejection remains real")
    world = isinstance(tag, WorldTag)
    if (tag.trigger_scene if world else tag.scene_used) == scene:
        raise ValueError("This actual obsessed Tag already paid a mark in this scene")
    update = {"marked": True, "trigger_scene" if world else "scene_used": scene}
    _put(state, target, tuple(x.model_copy(update=update) if x.id == tag.id else x for x in values))
    girl = (
        target.kind == "pilot"
        or target.kind == "external_pilot"
        or (
            target.kind == "handler"
            and any(x.active and x.id == target.incarnation for x in state.director_contexts)
        )
    )
    state.facts.append(
        dict(
            kind="leviathan_obsession_cost",
            source=source.model_dump_json(),
            target=target.model_dump_json(),
            tag=tag_id,
            scene=scene,
            event=event,
            modifier="0",
        )
    )
    _awake_type(state, source, event, "gorgon-type.leviathan.succumb-to-obsession")
    return GameState.model_validate_json(state.model_dump_json()), bool(tag.marked and girl)


def defer_rejection(original: GameState, actor: ActorRef, tag_id: str, event: str) -> GameState:
    state = GameState.model_validate_json(original.model_dump_json())
    values = tags(state, actor)
    chosen = next((x for x in values if x.id == tag_id and x.marked), None)
    if chosen is None:
        raise ValueError("Keep the real marked trigger Tag and its actual owned rejection debt")
    if not _reject_legal(state, actor, chosen):
        raise ValueError("The actual Mentor/locker source must permit choosing rejection")
    _put(
        state,
        actor,
        tuple(
            x.model_copy(update={"rejection_pending": True}) if x.id == tag_id else x
            for x in values
        ),
    )
    state.facts.append(
        dict(
            kind="leviathan_trigger_rejection_owed",
            actor=actor.model_dump_json(),
            tag=tag_id,
            event=event,
        )
    )
    return GameState.model_validate_json(state.model_dump_json())


def _reject_legal(state: GameState, actor: ActorRef, tag: Any) -> bool:
    if _harpy(state, actor) or actor.kind == "handler":
        from girlframe.engine.m3_tag_permissions import can_reject

        if not can_reject(state, actor, tag.id):
            return False
    if actor.kind == "pilot":
        from girlframe.engine.m3_beneath import rejection_blocked
        from girlframe.engine.m3_girl_runtime_state import mentor_tag

        if mentor_tag(state.sheets[actor.entity], tag, state) or rejection_blocked(
            state, int(actor.entity), tag.id
        ):
            return False
    if actor.kind == "external_pilot" and not _harpy(state, actor):
        from girlframe.engine.m3_leviathan_obsession import authority

        body = next(x for x in state.world.pilots if x.id == actor.entity) if state.world else None
        if body is not None and body.girl.upper() == "NEWGIRL":
            known = authority(state, actor)
            if known is None or known.mentor is None:
                raise ValueError(
                    "FACTUAL_IDENTITIES_REQUIRED: establish the actual existing Mentor"
                )
            if tag.giver_entity in (known.mentor.entity, known.mentor.model_dump_json()):
                return False
    return True


def trigger_options(state: GameState, actor: ActorRef, tag_id: str) -> dict[str, Any]:
    """Source driver checks these before a voluntary cost, and again at the owned decision."""
    from girlframe.engine.m3_leviathan_obsession import ordinary, pool, require_unlocked

    tag = next((x for x in tags(state, actor) if x.id == tag_id), None)
    if tag is None or tag.rejection_pending:
        raise ValueError("Resolve the actual current marked Tag first")
    girl = actor.kind in ("pilot", "external_pilot") or (
        actor.kind == "handler"
        and any(x.active and x.id == actor.incarnation for x in state.director_contexts)
    )
    if not tag.marked or not girl:
        return dict(
            requires_resolution=False,
            reject=False,
            embrace=False,
            replacements=[],
            needs_factual_identities=False,
        )
    reject = _reject_legal(state, actor, tag)
    try:
        values, eligible = pool(state, actor), ordinary(state, actor)
    except ValueError as error:
        if "FACTUAL_IDENTITIES_REQUIRED" not in str(error):
            raise
        return dict(
            requires_resolution=True,
            reject=reject,
            embrace=False,
            replacements=[],
            needs_factual_identities=True,
        )
    replacements = []
    for identity in values:
        if identity.id not in eligible:
            continue
        try:
            require_unlocked(values, (identity.id,))
        except ValueError:
            continue
        replacements.append(identity.id)
    cap = len(eligible) + sum(x.paired for x in values)
    return dict(
        requires_resolution=True,
        reject=reject,
        embrace=cap < 4 or bool(replacements),
        replacements=replacements if cap >= 4 else [],
        needs_factual_identities=False,
    )


def embrace_trigger(
    original: GameState,
    actor: ActorRef,
    tag_id: str,
    event: str,
    *,
    replace: str | None = None,
    judge: int | None = None,
) -> GameState:
    from girlframe.engine.m3_leviathan_obsession import _put as put_identities
    from girlframe.engine.m3_leviathan_obsession import ordinary, pool, require_identity_change
    from girlframe.engine.m3_leviathan_obsession_state import GrantedIdentity

    state = GameState.model_validate_json(original.model_dump_json())
    options = trigger_options(state, actor, tag_id)
    tag = next(x for x in tags(state, actor) if x.id == tag_id)
    if not options["embrace"] or not tag.marked or not event.strip():
        raise ValueError("A real owned repeated-Tag decision needs its eligible current identities")
    values, eligible = pool(state, actor), ordinary(state, actor)
    if options["replacements"]:
        if replace not in options["replacements"]:
            raise ValueError("Choose one actual eligible ordinary Identity at the cap")
        assert replace is not None
        require_identity_change(state, actor, (replace,))
        selected = next(x for x in values if x.id == replace)
        slot = selected.slot
    else:
        if replace is not None:
            raise ValueError("Do not manufacture an ordinary replacement below the cap")
        slot = next((i for i in range(4) if i not in {x.slot for x in values}), None)
    identity = GrantedIdentity(
        id=str(uuid5(NAMESPACE_URL, event + ":trigger-embrace:" + tag_id)),
        name=tag.label,
        slot=slot if actor.kind in ("pilot", "handler") else None,
    )
    sedation = actor.kind == "pilot" and replace in state.sheets[actor.entity].sedation_locked
    if sedation:
        identity = identity.model_copy(update={"marked": True})
    changed = tuple(identity if x.id == replace else x for x in values)
    new_ordinary = tuple(identity.id if x == replace else x for x in eligible)
    if replace is None:
        changed = (*changed, identity)
        new_ordinary = (*new_ordinary, identity.id)
    put_identities(state, actor, changed, new_ordinary, None, event, judge)
    if sedation:
        sheet = state.sheets[actor.entity]
        sheet.sedation_locked = tuple(x for x in sheet.sedation_locked if x != replace) + (
            identity.id,
        )
    _put(state, actor, tuple(x for x in tags(state, actor) if x.id != tag_id))
    state.facts.append(
        dict(
            kind="leviathan_trigger_tag_embraced",
            actor=actor.model_dump_json(),
            tag=tag_id,
            identity=identity.id,
            event=event,
        )
    )
    return GameState.model_validate_json(state.model_dump_json())
