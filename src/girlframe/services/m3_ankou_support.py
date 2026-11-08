"""Finite actual Ankou resources, bodies and source-attributed effects."""

from typing import TYPE_CHECKING, Any

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_ankou as rules
from girlframe.engine.m2 import AssetState, GameState, IdentityState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.engine.m3_core import install
from girlframe.engine.m3_identity_slots import replacement_slot
from girlframe.engine.m3_leviathan_obsession import require_unlocked
from girlframe.engine.m3_mockingbird import actor_tags, give_tag
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def copy(state: GameState, other: GameState) -> None:
    for name in GameState.model_fields:
        setattr(state, name, getattr(other, name))


def text(account: str) -> str:
    if not account.strip() or len(account) > 1200:
        raise WorkflowError("Record the actual performed source in 1–1200 characters")
    return account.strip()


def cast_actor(
    game: "GameService", c: Connection, state: GameState, cast: SceneCast, actor: ActorRef
) -> None:
    view = resolve(state, actor, profiles(c, game.store.campaign_id))
    if (
        not view.alive
        or view.offstage_source
        or not any(x.actor == actor and x.controller == view.controller for x in cast.roles)
    ):
        raise WorkflowError("Use the actual living original source scene participant")


def range_people(
    game: "GameService", c: Connection, state: GameState, actor: ActorRef
) -> tuple[ActorRef, ...]:
    bound = profiles(c, game.store.campaign_id)
    own = resolve(state, actor, bound)
    if own.cell is None or own.offstage_source:
        raise WorkflowError("Establish the actual Ankou body and relay quadrant square")
    candidates = [current_ref(state, x.owner) for x in state.sheets.values() if x.character_id]
    from girlframe.engine.m3_handler_consequences import active_handler

    handler = active_handler(state)
    if handler is not None:
        candidates.append(handler)
    if state.world:
        candidates.extend(ActorRef(kind="npc", entity=x.id) for x in state.world.npcs if x.alive)
    result = []
    for ref in candidates:
        view = resolve(state, ref, bound, require_current_profile=False)
        if ref != actor and view.alive and not view.offstage_source and view.cell == own.cell:
            result.append(ref)
    return tuple(dict.fromkeys(result))


def processor_minds(
    game: "GameService",
    c: Connection,
    state: GameState,
    actor: ActorRef,
    exempt_cadre: bool,
    exempt: ActorRef | None,
) -> tuple[ActorRef, ...]:
    candidates = range_people(game, c, state, actor)
    if exempt is not None and exempt not in candidates:
        raise WorkflowError("Exempt only one actual additional person currently in range")
    bound = profiles(c, game.store.campaign_id)
    return tuple(
        x
        for x in candidates
        if x.kind != "handler"
        and resolve(state, x, bound).rules != "gorgon"
        and x != exempt
        and not (exempt_cadre and x.kind == "pilot")
    )


def erase_identity(state: GameState, actor: ActorRef, identity: str) -> IdentityState:
    if actor.kind != "pilot" or current_ref(state, int(actor.entity)) != actor:
        raise WorkflowError("Use this actual original Girl's Identity resources")
    sheet = state.sheets[actor.entity]
    value = next((x for x in sheet.identities if x.id == identity), None)
    if (
        value is None
        or value.protected
        or value.paired
        or value.am_limiter
        or value.id in sheet.sedation_locked
    ):
        raise WorkflowError(
            "SOURCE_IDENTITY_REQUIRED: preserve the actual protected/paired/locked slot"
        )
    require_unlocked(sheet.identities, (identity,))
    sheet.identities = [x for x in sheet.identities if x.id != identity]
    sheet.revision += 1
    return value


def write_identity(
    state: GameState, actor: ActorRef, identity: str, label: str, replace: str | None = None
) -> None:
    if actor.kind != "pilot" or current_ref(state, int(actor.entity)) != actor:
        raise WorkflowError("Write only on the actual original source person's Identity sheet")
    sheet = state.sheets[actor.entity]
    ordinary = [x for x in sheet.identities if not x.protected or x.paired or x.am_limiter]
    if len(ordinary) < 4 and replace is not None:
        raise WorkflowError("Do not erase a replacement Identity while an ordinary slot is free")
    slot = replacement_slot(sheet, replace)
    if replace:
        erase_identity(state, actor, replace)
    if any(x.id == identity or x.name.casefold() == label.casefold() for x in sheet.identities):
        raise WorkflowError("Use a distinct actual original Identity and label")
    sheet.identities.append(IdentityState(id=identity, name=text(label), slot=slot))
    sheet.revision += 1


def gain_heat(state: GameState, actor: ActorRef, amount: int, event: str, reason: str) -> None:
    if actor.kind != "pilot" or current_ref(state, int(actor.entity)) != actor:
        raise WorkflowError("Gain Heat only on this actual original source person")
    from girlframe.engine.m3_leviathan_obsession import allowed_gain

    state.sheets[actor.entity].heat += allowed_gain(state, actor, amount, reason, event)
    state.sheets[actor.entity].revision += 1


def add_tag(
    game: "GameService",
    c: Connection,
    state: GameState,
    source: str,
    actor: ActorRef,
    target: ActorRef,
    label: str,
    scene: str,
    event: str,
    kind: str,
) -> str:
    bound = profiles(c, game.store.campaign_id)
    observers = tuple(sorted({resolve(state, ref, bound).controller for ref in (actor, target)}))
    tag = rules.identity("tag", source, target.token, kind, event)
    copy(state, give_tag(state, bound, target, actor, text(label), tag, event, observers))
    use = rules.TagUse.model_validate(
        dict(
            id=tag,
            source=source,
            actor=actor,
            target=target,
            tag=tag,
            scene=scene,
            event=event,
            kind=kind,
        )
    )
    rules.put(state, use)
    return tag


def remove_tag(state: GameState, actor: ActorRef, tag: str) -> None:
    if actor.kind == "pilot" and current_ref(state, int(actor.entity)) == actor:
        sheet = state.sheets[actor.entity]
        if not any(x.id == tag for x in sheet.tags):
            raise WorkflowError("Choose an actual current source-owned Tag")
        sheet.tags = [x for x in sheet.tags if x.id != tag]
        sheet.revision += 1
    elif actor.kind == "handler":
        if not any(x.id == tag for x in state.handler_tags):
            raise WorkflowError("Recover the actual original Handler Tag")
        state.handler_tags = [x for x in state.handler_tags if x.id != tag]
    elif actor.kind == "npc" and state.world:
        npc = next((x for x in state.world.npcs if x.id == actor.entity), None)
        if npc is None or not any(x.id == tag for x in npc.tags):
            raise WorkflowError("Recover the actual original NPC Tag")
        state.world = state.world.model_copy(
            update={
                "npcs": tuple(
                    x.model_copy(update={"tags": tuple(y for y in x.tags if y.id != tag)})
                    if x.id == actor.entity
                    else x
                    for x in state.world.npcs
                )
            }
        )
    else:
        raise WorkflowError("SOURCE_TAG_ADAPTER_REQUIRED: do not mutate a different body's Tags")


def move_tag(state: GameState, actor: ActorRef, target: ActorRef, tag: str) -> None:
    if actor.kind != "pilot" or target.kind != "pilot":
        raise WorkflowError("SOURCE_TAG_MOVE_REQUIRED: use actual native source and recipient")
    if (
        current_ref(state, int(actor.entity)) != actor
        or current_ref(state, int(target.entity)) != target
    ):
        raise WorkflowError("Never move a Tag onto an account replacement")
    original = next((x for x in state.sheets[actor.entity].tags if x.id == tag), None)
    if original is None or any(x.id == tag for x in state.sheets[target.entity].tags):
        raise WorkflowError("Move one actual current Tag without duplicating it")
    remove_tag(state, actor, tag)
    state.sheets[target.entity].tags.append(original.model_copy(deep=True))
    state.sheets[target.entity].revision += 1


def temporary_asset(
    state: GameState, actor: ActorRef, source: str, kind: str, event: str, replace: str | None
) -> str:
    label = "Eyes Everywhere" if kind == "eyes" else "Will of the Many"
    key = rules.identity("asset", source, kind)
    from girlframe.engine.m3_janus_storage import ids

    result = install(
        state.sheets[actor.entity],
        AssetState(
            id=key,
            family="frame",
            name=label,
            description="Actual linked Ankou Processor Core benefit",
        ),
        replace=replace,
        effective_void=ids(state, actor),
        state=state,
    )
    state.sheets[actor.entity] = result.sheet
    return key


def unlink(
    game: "GameService", c: Connection, state: GameState, value: rules.Processor, event: str
) -> None:
    if value.unlinked_event:
        raise WorkflowError("This original processor link is already ended")
    sheet = state.sheets.get(value.actor.entity)
    if sheet is None or sheet.character_id != value.actor.incarnation:
        raise WorkflowError("SOURCE_BODY_REQUIRED: preserve the ended original link and resources")
    sheet.assets = [x for x in sheet.assets if x.id not in current_assets(state, value)]
    for use in rules.records(state, rules.TagUse):
        if use.source == value.id and use.kind == "champion" and not use.ended_event:
            if any(x.id == use.tag for x in actor_tags(state, use.target)):
                remove_tag(state, use.target, use.tag)
            rules.put(state, use.model_copy(update={"ended_event": event}))
    sheet.revision += 1
    rules.put(state, value.model_copy(update={"unlinked_event": event}))


def actual_action_actor(action: dict[str, Any]) -> ActorRef:
    data = action["data"]
    raw = data.get("tag_context", {}).get("actor") or data.get("actor_basic", {}).get("ref")
    if raw:
        return ActorRef.model_validate(raw)
    incarnation = data.get("character_ids", {}).get(str(action["actor_id"]))
    if not incarnation:
        raise WorkflowError("Recover the original actual source actor, never its account alias")
    return ActorRef(kind="pilot", entity=str(action["actor_id"]), incarnation=incarnation)


def prove_birth(game: "GameService", c: Connection, event: str, kind: str, actor: int) -> GameState:
    row = c.execute(
        sa.select(t.events.c.actor_id, t.events.c.kind).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    ).first()
    if row is None or row.actor_id != str(actor) or row.kind != kind:
        raise WorkflowError("Recover the exact canonical original human-authored source event")
    return _history(c, game, event)


def current_assets(state: GameState, value: rules.Processor) -> tuple[str, ...]:
    result = []
    for original in value.assets:
        asset = original
        seen = {asset}
        while True:
            following = {
                x["new"]
                for x in state.facts
                if x.get("kind") == "modular_repair"
                and x.get("actor") == value.actor.model_dump_json()
                and x.get("old") == asset
            }
            if not following:
                break
            if len(following) != 1 or next(iter(following)) in seen:
                raise WorkflowError(
                    "Preserve the actual original temporary Asset's real Modular lineage"
                )
            asset = next(iter(following))
            seen.add(asset)
        result.append(asset)
    return tuple(result)


def prove_unlink_loss(
    game: "GameService",
    c: Connection,
    after: GameState,
    event: str,
    source_id: str,
    actor: ActorRef,
) -> dict[str, Any]:
    from girlframe.services.m3_ankou import prove_source
    from girlframe.services.m3_asset_loss import snapshots

    before, saved = snapshots(game, c, event)
    value = prove_source(game, c, saved, source_id)
    old, new = before.sheets.get(actor.entity), saved.sheets.get(actor.entity)
    removed = current_assets(before, value)
    if (
        value.actor != actor
        or value.unlinked_event != event
        or old is None
        or new is None
        or old.character_id != actor.incarnation
        or new.character_id != actor.incarnation
        or [x for x in old.assets if x.id not in removed] != new.assets
    ):
        raise WorkflowError(
            "Prove the canonical exact original Processor temporary Assets removed on actual unlink"
        )
    actual = resolve(
        before, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    return dict(piloting=actual.piloting, in_battle=value.unlink_in_battle, source_action=None)


def materialize_unlinks(game: "GameService", c: Connection, event: str) -> None:
    from uuid import uuid4

    from girlframe.services.m2_state import load_state
    from girlframe.services.m3_asset_loss import create_loss_work, snapshots

    state = load_state(c, game.store.campaign_id)
    for value in rules.records(state, rules.Processor):
        if not value.unlinked_event or any(
            x.get("kind") == "ankou_unlink_materialized" and x.get("id") == value.id
            for x in state.facts
        ):
            continue
        before, after = snapshots(game, c, value.unlinked_event)
        source = prove_unlink_loss(game, c, after, value.unlinked_event, value.id, value.actor)
        venue = next(
            (
                x
                for x in state.scene_casts
                if x.open and any(r.actor == value.actor for r in x.roles)
            ),
            None,
        )
        scope: dict[str, Any] = dict(campaign_id=game.store.campaign_id)
        if venue:
            scope["scene_id"] = venue.id
        else:
            scope["campaign_context"] = True
        work = create_loss_work(
            game,
            c,
            before,
            after,
            scope=scope,
            actor=value.actor,
            event=value.unlinked_event,
            reason="ankou_processor_unlink",
            source_id=value.id,
            in_battle=source["in_battle"],
        )
        state = load_state(c, game.store.campaign_id)
        state.facts.append(
            dict(kind="ankou_unlink_materialized", id=value.id, event=value.unlinked_event)
        )
        rules.put(
            state,
            rules.get(state, rules.Processor, value.id).model_copy(update={"work": tuple(work)}),
        )
        completion = str(uuid4())
        game.event(
            c,
            int(value.actor.entity),
            completion,
            "m3.ankou_unlink_work",
            state,
            event_id=completion,
            source=value.id,
        )


def clear_unqualified_helpless(state: GameState, actor: ActorRef, event: str) -> bool:
    return rules.clear_unqualified_helpless(state, actor, event)
