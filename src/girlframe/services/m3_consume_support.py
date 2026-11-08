"""Actual body, damage, custody and knowledge effects of proved CONSUME sources."""

import json
from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_consume as rules
from girlframe.engine.m2 import AssetState, GameState
from girlframe.engine.m3_actor_bonds import is_helpless
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import frame_position, resolve
from girlframe.engine.m3_assets import can_replace_at_limit, counts_toward_limit, frame_capacity
from girlframe.engine.m3_battle import end_actor_casts
from girlframe.engine.m3_budget_removal import blocked
from girlframe.engine.m3_frame_state import SuppliedAsset
from girlframe.engine.m3_handler_consequences import same_handler_body
from girlframe.engine.m3_physical import interrupt_journeys
from girlframe.engine.m3_physical_state import Placement
from girlframe.services.m2_game import GameService
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError


def prove_session(game: GameService, c: Connection, state: GameState, action: str) -> rules.Session:
    source = rules.session(state, action)
    actual = game.action(c, action)
    receipt = c.scalar(
        sa.select(t.m2["m2_receipts"].c.body_json).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == action,
        )
    )
    meta = actual["data"].get("consume", {})
    if (
        receipt is None
        or json.loads(receipt) != actual["data"].get("receipt")
        or actual["data"].get("play") != source.play
        or meta.get("play") != source.play
        or meta.get("actor") != source.actor.model_dump(mode="json")
        or meta.get("target") != (source.target.model_dump(mode="json") if source.target else None)
        or source.frame != meta.get("frame")
        or source.total != actual["data"].get("result", {}).get("total")
    ):
        raise WorkflowError(
            "Recover the actual original CONSUME session and immutable rolled source"
        )
    return source


def prove_kill(
    game: GameService, c: Connection, state: GameState, target: ActorRef, action: str, event: str
) -> rules.Consumption:
    source = prove_session(game, c, state, action)
    consumed = next(
        (
            x
            for x in rules.records(state, rules.Consumption)
            if x.session == action and x.event == event and x.option == "kill"
        ),
        None,
    )
    choice = (
        c.execute(
            sa.select(t.m2["m2_choices"]).where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.id == (consumed.choice if consumed else ""),
            )
        )
        .mappings()
        .first()
    )
    if (
        source.play != "consume_eat"
        or source.target != target
        or not source.vulnerable
        or not source.killable
        or source.total < 8
        or consumed is None
        or consumed.target != target
        or consumed.actor != source.actor
        or choice is None
        or choice["action_id"] != action
        or choice["kind"] != "consume_eat"
        or choice["actor_id"] != source.actor.entity
    ):
        raise WorkflowError(
            "A compulsory actual Eat death needs its genuine original killing choice"
        )
    return consumed


def custody_of(state: GameState, target: ActorRef) -> rules.InternalCustody | None:
    values = [
        x
        for x in rules.records(state, rules.InternalCustody)
        if x.target == target and x.escaped_event is None
    ]
    if len(values) > 1:
        raise WorkflowError("Recover one actual original swallowed-body custody source")
    return values[0] if values else None


def require_free(state: GameState, target: ActorRef) -> None:
    if custody_of(state, target):
        raise WorkflowError("CONSUME_INTERNAL_CUSTODY: use a genuine escape or rescue source")


def context(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    target: ActorRef,
    scene: SceneCast,
) -> dict[str, Any]:
    bound = profiles(c, game.store.campaign_id)
    original = rules.frame(state, actor)
    own, other = (
        resolve(state, ref, bound, require_current_profile=False) for ref in (actor, target)
    )
    if (
        actor == target
        or not all(any(x.actor == ref for x in scene.roles) for ref in (actor, target))
        or not own.alive
        or not other.alive
        or own.offstage_source
        or other.offstage_source
        or own.cell is None
        or own.cell != other.cell
        or own.inside_frame is None
        or own.frame_instance != original
    ):
        raise WorkflowError(
            "Establish actual original co-present bodies and a real lunge in this source scene"
        )
    require_free(state, actor)
    require_free(state, target)
    if target.kind == "clone_am":
        raise WorkflowError(
            "SOURCE_CLONE_BODY_REQUIRED: actual same-copy consumption needs its lifecycle adapter"
        )
    if target.kind == "pilot" and other.inside_frame is None:
        raise WorkflowError("Establish the actual target body's cockpit context")
    if state.world and target.kind in ("npc", "gorgon", "external_pilot"):
        source = next(
            (
                x
                for x in (*state.world.npcs, *state.world.gorgons, *state.world.pilots)
                if x.id == target.entity
            ),
            None,
        )
        if source is not None and not getattr(source, "revealed", False):
            raise WorkflowError(
                "Choose an actually known source target, not a hidden backend entity"
            )
    from girlframe.engine.m3_am import require_harm
    from girlframe.engine.m3_sprite import candidates

    require_harm(state, actor, target)
    if candidates(state, target, actor, bound):
        raise WorkflowError(
            "SOURCE_CONSUME_SPRITE_REQUIRED: preserve genuine interception "
            "before biting or swallowing"
        )
    if target.kind == "gorgon":
        from girlframe.engine.m3_leviathan import require_layers_clear

        assert state.world is not None
        require_layers_clear(next(x for x in state.world.gorgons if x.id == target.entity))
    vulnerable = (
        is_helpless(state, target, actor)
        or bool(other.core_exposed)
        or (own.inside_frame is True and other.inside_frame is False)
        or target.kind == "npc"
    )
    own_assets = [
        dict(id=x.id, name="Undisclosed Asset" if x.concealed else x.name)
        for x in own.assets
        if not x.damaged
    ]
    target_assets = [
        dict(id=x.id, name="Undisclosed Asset" if x.concealed else x.name)
        for x in other.assets
        if not x.damaged
    ]
    if target.kind in ("npc", "handler") and not target_assets:
        # This selector names the existing typed NPC/Handler damage consequence;
        # it is never an invented NPC Asset or a copied Pilot inventory.
        target_assets = [
            dict(id="source-body-consequence", name="Actual printed body-damage consequence")
        ]
    if not own_assets:
        raise WorkflowError("The possible actual low result needs an available owned Asset cost")
    return dict(
        vulnerable=vulnerable,
        killable=vulnerable,
        own_assets=own_assets,
        target_assets=target_assets,
        can_swallow=True,
        can_escape=not vulnerable,
        actor_vessel=own.vessel_id,
        target_vessel=other.vessel_id,
        actor_position=own.position_sha256,
        target_position=other.position_sha256,
    )


def damage(
    game: GameService,
    c: Connection,
    state: GameState,
    subject: ActorRef,
    asset: str,
    event: str,
    action: str,
) -> tuple[GameState, tuple[str, ...]]:
    from girlframe.services.m3_battle import damage_actor

    actual = game.action(c, action)
    consume = actual["data"].get("consume")
    author = (
        ActorRef.model_validate(consume["actor"])
        if consume
        else ActorRef(
            kind="pilot",
            entity=str(actual["actor_id"]),
            incarnation=state.sheets[str(actual["actor_id"])].character_id,
        )
    )
    own_cost = subject == author
    opposing = (
        ActorRef.model_validate(consume["target"]) if consume and consume.get("target") else None
    )
    source_actor = None if own_cost else author
    return damage_actor(
        game,
        c,
        state,
        target=subject,
        asset_id=None if asset == "source-body-consequence" else asset,
        source_action=action,
        source_work=None,
        event=event,
        actor=source_actor,
        opponent=opposing if own_cost else author,
        chooser_controller=int(author.entity),
        occurrence="consume_cost" if own_cost else "consume_bite",
        physical_blow=not own_cost,
        allow_sprite=not own_cost,
    )


def kill(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    target: ActorRef,
    event: str,
    action: str,
) -> tuple[GameState, tuple[str, ...]]:
    consumed = prove_kill(game, c, state, target, action, event)
    if consumed.actor != actor:
        raise WorkflowError("Preserve the actual original source eater")
    changed = GameState.model_validate_json(state.model_dump_json())
    if target.kind == "pilot":
        from girlframe.services.m3_careers import end_in_transaction

        changed = end_in_transaction(
            c,
            game,
            changed,
            target,
            reason="death",
            source_event=event,
            account="Actual entire consumption by the proved Eat source",
            archive_id=rules.identity("death", action, target.token),
        )
    elif target.kind == "handler" or same_handler_body(changed, target):
        from girlframe.services.m3_handler_consequences import force_end_handler

        changed = force_end_handler(
            game,
            c,
            changed,
            target,
            source_action=action,
            source_choice=consumed.choice,
            clause="consume_eat.kill",
            event=event,
            account="Actual entire consumption by the proved Eat source",
        )
    elif target.kind == "npc":
        actual = resolve(changed, target, profiles(c, game.store.campaign_id))
        if actual.rules == "director":
            from girlframe.engine.m3_battle_director import die
            from girlframe.services.m3_battle_director import bind_legacy_context_bodies

            changed = die(
                bind_legacy_context_bodies(game, c, changed),
                target,
                event,
                "Actual entire consumption by Eat",
            )
        else:
            assert changed.world is not None
            changed.world = changed.world.model_copy(
                update={
                    "npcs": tuple(
                        x.model_copy(update={"alive": False}) if x.id == target.entity else x
                        for x in changed.world.npcs
                    )
                }
            )
    elif target.kind == "gorgon":
        assert changed.world is not None
        changed.world = changed.world.model_copy(
            update={
                "gorgons": tuple(
                    x.model_copy(update={"alive": False}) if x.id == target.entity else x
                    for x in changed.world.gorgons
                )
            }
        )
    elif target.kind == "external_pilot":
        harpy = next((x for x in changed.harpy_states if x.id == target.entity), None)
        if harpy:
            changed.harpy_states = [
                x.model_copy(update={"alive": False, "condition_event": event})
                if x.id == target.entity
                else x
                for x in changed.harpy_states
            ]
        else:
            assert changed.world is not None
            changed.world = changed.world.model_copy(
                update={
                    "pilots": tuple(
                        x.model_copy(update={"alive": False}) if x.id == target.entity else x
                        for x in changed.world.pilots
                    )
                }
            )
    else:
        raise WorkflowError("SOURCE_BODY_DEATH_REQUIRED: use this actual body's genuine ending")
    changed = end_actor_casts(
        interrupt_journeys(changed, target, event, "Actual entire consumption"), target, event
    )
    from girlframe.engine.m3_leviathan_obsession import release_dead_sources

    changed = release_dead_sources(changed, event)
    changed.facts.append(
        dict(kind="consume_death_stage", action=action, actor=target.model_dump_json(), event=event)
    )
    return changed, ()


def _position(
    state: GameState,
    target: ActorRef,
    actor: ActorRef,
    event: str,
    cell: tuple[int, int],
    *,
    captured: bool,
    origin: str | None = None,
) -> GameState:
    if target.kind == "pilot":
        current = next(x for x in state.placements if x.actor == target)
        prior = Placement.model_validate_json(origin) if origin else current
        updates: dict[str, Any] = dict(
            girl_cell=cell,
            custody=actor if captured else prior.custody,
            source_event=event,
            account="Actual CONSUME internal custody" if captured else "Actual escape from CONSUME",
        )
        if current.mode != "outside_frame":
            updates["frame_cell"] = cell
        state.placements = [
            x.model_copy(update=updates) if x.actor == target else x for x in state.placements
        ]
    elif target.kind == "npc":
        assert state.world is not None
        state.world = state.world.model_copy(
            update={
                "npcs": tuple(
                    x.model_copy(
                        update={
                            "cell": cell,
                            "captive_of": actor.model_dump_json() if captured else None,
                            "custody_event": event,
                        }
                    )
                    if x.id == target.entity
                    else x
                    for x in state.world.npcs
                )
            }
        )
    elif target.kind == "gorgon":
        assert state.world is not None
        state.world = state.world.model_copy(
            update={
                "gorgons": tuple(
                    x.model_copy(update={"cell": cell, "position_event": event})
                    if x.id == target.entity
                    else x
                    for x in state.world.gorgons
                )
            }
        )
    elif target.kind == "external_pilot":
        harpy = next((x for x in state.harpy_states if x.id == target.entity), None)
        if harpy:
            updates = dict(
                cell=cell,
                custody="captured" if captured else "free",
                custodian=actor if captured else None,
                custody_event=event if captured else None,
                physical_source_event=event,
            )
            if harpy.linked:
                updates["frame_cell"] = cell
            state.harpy_states = [
                x.model_copy(update=updates) if x.id == target.entity else x
                for x in state.harpy_states
            ]
        else:
            assert state.world is not None
            state.world = state.world.model_copy(
                update={
                    "pilots": tuple(
                        x.model_copy(
                            update={
                                "cell": cell,
                                "custody": "captured" if captured else "free",
                                "custodian": int(actor.entity) if captured else None,
                                "custody_event": event if captured else None,
                            }
                        )
                        if x.id == target.entity
                        else x
                        for x in state.world.pilots
                    )
                }
            )
    elif target.kind == "handler":
        state.facts.append(
            dict(
                kind="consume_handler_position",
                actor=target.model_dump_json(),
                cell=json.dumps(cell),
                event=event,
                custody=actor.model_dump_json() if captured else "",
            )
        )
    return state


def swallow(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    target: ActorRef,
    event: str,
    action: str,
) -> tuple[GameState, str, tuple[str, ...]]:
    source = prove_session(game, c, state, action)
    context(game, c, state, actor, target, source.cast)
    if (
        source.play != "consume_eat"
        or source.actor != actor
        or source.target != target
        or not 8 <= source.total <= 10
    ):
        raise WorkflowError(
            "Only the actual original mid Eat source swallows this real person alive"
        )
    container_cell = frame_position(state, actor, source.frame)
    if container_cell is None:
        raise WorkflowError("Prove the original physical CONSUME Frame's actual position")
    old = next((x.model_dump_json() for x in state.placements if x.actor == target), None)
    identity = rules.identity("custody", action, target.token)
    captured = rules.InternalCustody(
        id=identity,
        session=action,
        actor=actor,
        target=target,
        frame=source.frame,
        event=event,
        original_position=old,
        cell=container_cell,
    )
    changed = _position(
        GameState.model_validate_json(state.model_dump_json()),
        target,
        actor,
        event,
        container_cell,
        captured=True,
    )
    rules.put(changed, captured)
    return changed, identity, ()


def escape(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    target: ActorRef,
    event: str,
    action: str,
    *,
    custody: str | None = None,
) -> tuple[GameState, tuple[str, ...]]:
    source = prove_session(game, c, state, action)
    if source.target != target or source.actor != actor:
        raise WorkflowError("Escape belongs to the actual original Eat participants")
    if custody is None and (source.total >= 8 or not source.vulnerable):
        return state, ()
    changed = GameState.model_validate_json(state.model_dump_json())
    if custody is not None:
        held = custody_of(changed, target)
        if held is None or held.id != custody or held.session != action or source.vulnerable:
            raise WorkflowError("Only this actual originally nonvulnerable prisoner may rip out")
        container_cell = frame_position(changed, held.actor, held.frame)
        if container_cell is None:
            raise WorkflowError(
                "Prove the original container's actual current position before escape"
            )
        changed = _position(
            changed,
            target,
            actor,
            event,
            container_cell,
            captured=False,
            origin=held.original_position,
        )
        rules.put(changed, held.model_copy(update={"escaped_event": event}))
    changed.facts.append(
        dict(
            kind="consume_escape",
            action=action,
            actor=target.model_dump_json(),
            event=event,
            custody=custody or "",
        )
    )
    return changed, ()


def mouth(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    target: ActorRef,
    event: str,
    action: str,
    *,
    held: bool,
) -> tuple[GameState, tuple[str, ...]]:
    source = prove_session(game, c, state, action)
    if source.target != target or source.actor != actor:
        raise WorkflowError("Use the actual original mouth and held body part")
    bound = profiles(c, game.store.campaign_id)
    first, second = (
        resolve(state, ref, bound, require_current_profile=False) for ref in (actor, target)
    )
    if held and (
        not first.alive
        or not second.alive
        or first.cell is None
        or first.cell != second.cell
        or source.hunger == "Ravenous"
    ):
        raise WorkflowError(
            "Actual gentle mouth contact requires the original living co-present bodies"
        )
    if not held and not any(
        x.session == action and x.actor == actor and x.target == target and not x.ended_event
        for x in rules.records(state, rules.MouthHold)
    ):
        raise WorkflowError("Recover the actual still-held original body part")
    state.facts.append(
        dict(
            kind="consume_mouth_position",
            action=action,
            actor=actor.model_dump_json(),
            target=target.model_dump_json(),
            actor_vessel=first.vessel_id or "",
            target_vessel=second.vessel_id or "",
            held=str(held),
            event=event,
        )
    )
    return state, ()


def mark_identity(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    identity: str,
    event: str,
    action: str,
) -> tuple[GameState, tuple[str, ...]]:
    actual = game.action(c, action)
    if (
        actual["actor_id"] != actor.entity
        or not actual["data"].get("receipt")
        or actual["data"].get("result", {}).get("total", 0) < 8
    ):
        raise WorkflowError("Time to Eat needs the actual original targeted eight-plus source")
    sheet = state.sheets.get(actor.entity)
    selected = next((x for x in sheet.identities if x.id == identity), None) if sheet else None
    if (
        sheet is None
        or sheet.character_id != actor.incarnation
        or selected is None
        or selected.marked
    ):
        raise WorkflowError("Mark one actual unmarked original Identity without inventing Heat")
    selected.marked = True
    sheet.revision += 1
    state.facts.append(
        dict(
            kind="consume_identity_mark",
            action=action,
            actor=actor.model_dump_json(),
            identity=identity,
            event=event,
        )
    )
    return state, ()


def _loss_ids(
    game: GameService,
    c: Connection,
    before: GameState,
    after: GameState,
    actor: ActorRef,
    reason: str,
    source: str,
) -> tuple[str, ...]:
    from girlframe.engine.m3_janus_storage import effective_assets
    from girlframe.services.m3_asset_loss import identity

    ids = []
    for family in ("girl", "frame"):
        old = [x for x in effective_assets(before, actor) if x.family == family]
        new = [x for x in effective_assets(after, actor) if x.family == family]
        if new and all(x.void for x in new) and not (old and all(x.void for x in old)):
            ids.append(identity(reason, source, actor, "void:" + family))
    return tuple(ids)


def stage_starvation_expiry(
    game: GameService,
    c: Connection,
    before: GameState,
    state: GameState,
    actor: ActorRef,
    event: str,
    action: str,
) -> tuple[str, ...]:
    temporary = rules.starving_asset(rules.frame(before, actor))
    if not any(x.id == temporary for x in before.sheets[actor.entity].assets) or any(
        x.id == temporary for x in state.sheets[actor.entity].assets
    ):
        return ()
    state.facts.append(
        dict(
            kind="consume_loss_stage",
            reason="consume_starvation_expiry",
            actor=actor.model_dump_json(),
            action=action,
            source=event,
            event=event,
        )
    )
    return _loss_ids(game, c, before, state, actor, "consume_starvation_expiry", event)


def follow_carriers(
    game: GameService, c: Connection, before: GameState, state: GameState, event: str
) -> None:
    bound = profiles(c, game.store.campaign_id)
    for held in rules.records(state, rules.InternalCustody):
        if held.escaped_event:
            continue
        container_cell = frame_position(state, held.actor, held.frame)
        if container_cell is None:
            raise WorkflowError(
                "CONSUME_CONTAINER_POSITION_REQUIRED: retain the actual swallowed body's source"
            )
        if container_cell != held.cell:
            _position(state, held.target, held.actor, event, container_cell, captured=True)
            rules.put(state, held.model_copy(update={"cell": container_cell}))
    for hold in rules.records(state, rules.MouthHold):
        if hold.ended_event:
            continue
        first, second = (
            resolve(state, ref, bound, require_alive=False, require_current_profile=False)
            for ref in (hold.actor, hold.target)
        )
        mouth_cell = frame_position(state, hold.actor, hold.frame)
        if (
            not first.alive
            or not second.alive
            or (mouth_cell is not None and second.cell is not None and mouth_cell != second.cell)
        ):
            rules.put(state, hold.model_copy(update={"ended_event": event}))


def appearance(state: GameState, actor: ActorRef) -> str | None:
    return next(
        (
            x.get("appearance")
            for x in reversed(state.facts)
            if x.get("kind") == "consume_appearance" and x.get("actor") == actor.model_dump_json()
        ),
        None,
    )


def partake(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    event: str,
    action: str,
    *,
    option: str,
    girl_asset: str,
    frame_assets: tuple[str, ...] = (),
    new_asset: SuppliedAsset | None = None,
    appearance: str = "",
    replace_frame: str | None = None,
) -> tuple[GameState, tuple[str, ...]]:
    actual = game.action(c, action)
    if (
        actual["data"].get("play") != "dive_deep"
        or not actual["data"].get("receipt")
        or actual["actor_id"] != actor.entity
    ):
        raise WorkflowError("Let Us Partake requires the actual original committed Dive Deep")
    before = GameState.model_validate_json(state.model_dump_json())
    sheet = state.sheets[actor.entity]
    selected = next((x for x in sheet.assets if x.id == girl_asset and x.family == "girl"), None)
    if (
        selected is None
        or girl_asset in blocked(state, actor)
        or girl_asset == rules.starving_asset(rules.frame(state, actor))
    ):
        raise WorkflowError("Choose an actual Girl Asset with a supported original loss source")
    owed: tuple[str, ...] = ()
    if option == "regrow":
        if (
            selected.damaged
            or len(frame_assets) > 2
            or len(set(frame_assets)) != len(frame_assets)
            or new_asset
            or appearance
            or replace_frame
        ):
            raise WorkflowError(
                "Damage one intact Girl Asset and regrow up to two actual damaged Frame Assets"
            )
        if not set(frame_assets) <= {
            x.id for x in sheet.assets if x.family == "frame" and x.damaged
        }:
            raise WorkflowError(
                "Regrow the actual damaged Frame Assets rather than inventing hardware"
            )
        state, owed = damage(game, c, state, actor, girl_asset, event, action)
        sheet = state.sheets[actor.entity]
        for asset in sheet.assets:
            if asset.id in frame_assets:
                asset.damaged = False
    elif option == "excrete":
        if (
            new_asset is None
            or new_asset.damaged
            or not new_asset.void
            or frame_assets
            or appearance
        ):
            raise WorkflowError(
                "Consume the real Girl Asset and describe one actual new Void Frame Asset"
            )
        full = sum(
            counts_toward_limit(sheet, x) for x in sheet.assets if x.family == "frame"
        ) >= frame_capacity(sheet, state)
        replacement = next(
            (x for x in sheet.assets if x.id == replace_frame and x.family == "frame"), None
        )
        if full and (
            replacement is None
            or not can_replace_at_limit(sheet, replacement)
            or replacement.id in blocked(state, actor)
        ):
            raise WorkflowError(
                "SOURCE_CAP_REPLACEMENT_REQUIRED: choose an actual replaceable Frame Asset"
            )
        if not full and replacement:
            raise WorkflowError("This real new Frame Asset does not need a replacement")
        sheet.assets = [x for x in sheet.assets if x.id not in {girl_asset, replace_frame}]
        sheet.assets.append(
            AssetState(
                id=rules.identity("excreted", action, event),
                family="frame",
                name=new_asset.name,
                description=new_asset.description,
                void=True,
            )
        )
    elif option == "appearance":
        if (
            not appearance.strip()
            or len(appearance) > 1200
            or selected.void
            or frame_assets
            or new_asset
            or replace_frame
        ):
            raise WorkflowError(
                "Author your actual emerged appearance and select an uncorrupted Girl Asset"
            )
        selected.void = True
        state.facts.append(
            dict(
                kind="consume_appearance",
                actor=actor.model_dump_json(),
                appearance=appearance.strip(),
                action=action,
                event=event,
            )
        )
    else:
        raise WorkflowError("Choose one actual printed Let Us Partake effect")
    sheet.revision += 1
    owed += _loss_ids(game, c, before, state, actor, "consume_partake", event)
    state.facts.append(
        dict(
            kind="consume_loss_stage",
            reason="consume_partake",
            actor=actor.model_dump_json(),
            action=action,
            source=event,
            event=event,
        )
    )
    return state, tuple(dict.fromkeys(owed))


def knowledge_allowed(state: GameState, target: ActorRef) -> bool:
    return not rules.forgotten(state, target)


def forget(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    target: ActorRef,
    event: str,
    action: str,
) -> GameState:
    source = prove_session(game, c, state, action)
    consumed = next(
        (
            x
            for x in rules.records(state, rules.Consumption)
            if x.session == action and x.option == "kill" and x.target == target
        ),
        None,
    )
    if source.actor != actor or consumed is None:
        raise WorkflowError("Ontological Consumption requires the actual original killing")
    original = _history(c, game, consumed.event)
    if (
        consumed not in rules.records(original, rules.Consumption)
        or resolve(
            original,
            target,
            profiles(c, game.store.campaign_id),
            require_alive=False,
            require_current_profile=False,
        ).alive
    ):
        raise WorkflowError("Commit the genuine killing before destroying its canonical memory")
    if state.world:
        state.world = state.world.model_copy(
            update={
                "npcs": tuple(
                    x.model_copy(update={"revealed": False})
                    if target.kind == "npc" and x.id == target.entity
                    else x
                    for x in state.world.npcs
                ),
                "pilots": tuple(
                    x.model_copy(update={"revealed": False})
                    if target.kind == "external_pilot" and x.id == target.entity
                    else x
                    for x in state.world.pilots
                ),
                "gorgons": tuple(
                    x.model_copy(update={"revealed": False})
                    if target.kind == "gorgon" and x.id == target.entity
                    else x
                    for x in state.world.gorgons
                ),
            }
        )
    state.facts.append(
        dict(
            kind="consume_knowledge_erased",
            target=target.model_dump_json(),
            action=action,
            event=event,
            through_revision=str(state.revision),
        )
    )
    return state


def prove_loss_source(
    game: GameService, c: Connection, after: GameState, event: str, source_id: str, actor: ActorRef
) -> dict[str, Any]:
    from girlframe.services.m3_asset_loss import snapshots

    before, original = snapshots(game, c, event)
    staged = next(
        (
            x
            for x in original.facts
            if x.get("kind") == "consume_loss_stage"
            and x.get("event") == event
            and x.get("source") == source_id
            and x.get("actor") == actor.model_dump_json()
        ),
        None,
    )
    if staged is None or staged not in after.facts:
        raise WorkflowError("Recover the actual immutable CONSUME Asset change source")
    if staged["reason"] == "consume_partake":
        real = next(
            (
                x
                for x in rules.records(original, rules.Partaking)
                if x.event == event and x.actor == actor
            ),
            None,
        )
        actual = game.action(c, staged["action"])
        if (
            real is None
            or actual["data"]["play"] != "dive_deep"
            or not actual["data"].get("receipt")
        ):
            raise WorkflowError("Recover the actual committed original Dive Partake source")
    elif staged["reason"] == "consume_starvation_expiry":
        real_eat = next(
            (
                x
                for x in rules.records(original, rules.Consumption)
                if x.event == event and x.actor == actor and x.option in ("bite", "kill")
            ),
            None,
        )
        if real_eat is None or rules.hunger(original, actor) != "Quiet":
            raise WorkflowError("Only actual Eat expires this source-owned Starving Asset")
    else:
        raise WorkflowError("Recover this actual implemented CONSUME loss source")
    own = resolve(before, actor, profiles(c, game.store.campaign_id), require_current_profile=False)
    return dict(source_action=staged["action"], piloting=own.piloting, in_battle=False)


def synchronize(game: GameService, c: Connection, event: str) -> None:
    from girlframe.services.m3_asset_loss import create_loss_work, snapshots
    from girlframe.services.m3_battle import synchronize_casts, synchronize_damage
    from girlframe.services.m3_careers import synchronize_end

    saved = _history(c, game, event)
    relevant = any(
        x.get("event") == event
        and x.get("kind") in ("consume_death_stage", "consume_loss_stage", "battle_damage_stage")
        for x in saved.facts
    )
    if not relevant:
        return
    synchronize_damage(game, c, event)
    synchronize_casts(game, c, event)
    for archive in saved.career_archives:
        if archive.source_event == event:
            synchronize_end(c, game, archive)
    for handler_archive in saved.handler_archives:
        if handler_archive.source_event == event:
            from girlframe.services.m3_handler_consequences import end_body_reviews

            end_body_reviews(game, c, handler_archive)
    if any(x.get("kind") == "consume_death_stage" and x.get("event") == event for x in saved.facts):
        from girlframe.services.m3_battle_director import create_replacements
        from girlframe.services.m3_gorgon_dormant import synchronize_endings
        from girlframe.services.m3_harpy_rest import synchronize_endings as end_harpy

        create_replacements(game, c, event)
        synchronize_endings(game, c, event, None, "consume:" + event)
        end_harpy(game, c, event)
    for stage in saved.facts:
        if stage.get("kind") != "consume_loss_stage" or stage.get("event") != event:
            continue
        before, after = snapshots(game, c, event)
        actor = ActorRef.model_validate_json(stage["actor"])
        action = game.action(c, stage["action"])
        create_loss_work(
            game,
            c,
            before,
            after,
            scope=dict(campaign_id=game.store.campaign_id, scene_id=action["scene_id"]),
            actor=actor,
            event=event,
            reason=cast(Any, stage["reason"]),
            source_id=stage["source"],
            in_battle=False,
        )
