"""Finite actual body and resource ports for the Red Queen's source-owned workflows."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection

from girlframe.engine import m3_red_queen as rules
from girlframe.engine import m3_red_queen_effects as effects
from girlframe.engine.m2 import GameState, PlayInput
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import resolve
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_red_queen_accusation import accusation_targets as accusation_targets
from girlframe.services.m3_red_queen_accusation import accusation_viewers as accusation_viewers
from girlframe.services.m3_red_queen_accusation import director_options as director_options
from girlframe.services.m3_red_queen_accusation import endorse_accusation as endorse_accusation
from girlframe.services.m3_red_queen_accusation import punishment as punishment
from girlframe.services.m3_red_queen_accusation import validate_accusation as validate_accusation
from girlframe.services.m3_red_queen_memory import association_source as association_source
from girlframe.services.m3_red_queen_memory import extract_memories as extract_memories
from girlframe.services.m3_red_queen_transfer import transfer_source as transfer_source
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def context(
    game: "GameService",
    c: Connection,
    state: GameState,
    actor: ActorRef,
    cast: SceneCast,
    play: str,
    target: ActorRef | None,
    context_id: str | None = None,
) -> dict[str, Any]:
    bound = profiles(c, game.store.campaign_id)
    own = resolve(state, actor, bound, require_current_profile=False)
    original = rules.frame(state, actor)
    if own.offstage_source or not any(
        role.actor == actor and role.controller == own.controller for role in cast.roles
    ):
        raise WorkflowError("Use the actual original Red Queen actor and source scene")
    other = resolve(state, target, bound, require_current_profile=False) if target else None
    proof = None
    if play == "red_queen_consult":
        if (
            context_id is not None
            or not own.inside_frame
            or own.occupied_frame_instance != original
        ):
            raise WorkflowError("Consult the Court inside this actual original Frame's cockpit")
    elif play in ("red_queen_panopticon", "red_queen_memory"):
        from girlframe.services.m3_red_queen import prove_context

        if context_id is None or target is None or other is None:
            raise WorkflowError(
                "Establish the actual observation or restrained brain-access source"
            )
        proof = prove_context(game, c, state, context_id)
        expected = "distant" if play == "red_queen_panopticon" else "brain"
        if (
            proof.kind != expected
            or proof.actor != actor
            or proof.target != target
            or proof.cast.id != cast.id
            or proof.actor_vessel != own.vessel_id
            or proof.target_vessel != other.vessel_id
            or proof.actor_position != own.position_sha256
            or proof.target_position != other.position_sha256
        ):
            raise WorkflowError(
                "Refresh the actual original body and source conditions before rolling"
            )
        if expected == "brain" and (own.cell is None or own.cell != other.cell):
            raise WorkflowError("Actual restrained brain access needs physical co-presence")
    else:
        raise WorkflowError("Use an actual implemented Red Queen Play")
    return dict(
        actor=actor.model_dump(mode="json"),
        frame=original,
        vessel=own.vessel_id,
        position=own.position_sha256,
        target=target.model_dump(mode="json") if target else None,
        target_vessel=other.vessel_id if other else None,
        target_position=other.position_sha256 if other else None,
        context=proof.id if proof else None,
        source_event=proof.event if proof else None,
    )


def _copy(state: GameState, changed: GameState) -> None:
    for key in GameState.model_fields:
        setattr(state, key, getattr(changed, key))


def tag_effect(
    game: "GameService",
    c: Connection,
    state: GameState,
    giver: ActorRef,
    target: ActorRef,
    label: str,
    source_id: str,
    event: str,
) -> None:
    from girlframe.engine.m3_mockingbird import give_tag

    identity = rules.identity("tag", source_id, giver.token, target.token, event)
    people = tuple(
        sorted(
            {
                resolve(
                    state, ref, profiles(c, game.store.campaign_id), require_current_profile=False
                ).controller
                for ref in (giver, target)
            }
        )
    )
    _copy(
        state,
        give_tag(
            state,
            profiles(c, game.store.campaign_id),
            target,
            giver,
            label,
            identity,
            event,
            people,
        ),
    )
    effects.put(
        state,
        effects.TagGift(
            id=identity, giver=giver, target=target, label=label, source=source_id, event=event
        ),
    )


def mark_effect(
    game: "GameService", c: Connection, state: GameState, mark: rules.Mark, event: str
) -> tuple[str, ...]:

    if mark.target.kind not in ("pilot", "npc", "gorgon", "handler"):
        raise WorkflowError("SOURCE_COURT_BODY_PORT_REQUIRED: preserve this actual subject's rules")
    if mark.target.kind in ("npc", "gorgon", "handler"):
        am = rules.get(state, rules.CourtAM, mark.am)
        tag_effect(game, c, state, mark.actor, mark.target, am.role, mark.id, event)
        return ()
    if mark.kind not in ("flirt", "assault") or mark.counterpart is None:
        raise WorkflowError("Apply only the actual printed source-owned Court effect")
    if not any(x.actor == mark.counterpart for x in mark.cast.roles):
        raise WorkflowError("Use an actually present counterpart for the required legal Play")
    if mark.kind == "flirt":
        if mark.counterpart.kind == "npc":
            from girlframe.services.m3_battle import _visible
            from girlframe.services.m3_npc_flirt import _npc

            _npc(state, mark.counterpart)
            if not _visible(state, mark.counterpart, int(mark.target.entity)):
                raise WorkflowError("Use a counterpart visible to the actual commanded Girl")
        elif mark.counterpart.kind != "pilot":
            raise WorkflowError("SOURCE_PORT_REQUIRED: preserve this actual counterpart's rules")
    actual = resolve(
        state, mark.target, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    work = rules.identity("command-work", mark.id)
    effects.put(
        state,
        effects.Command(
            id=rules.identity("command", mark.id),
            mark=mark.id,
            actor=mark.target,
            target=mark.counterpart,
            play="flirt" if mark.kind == "flirt" else "all_out_assault",
            controller=actual.controller,
            cast=mark.cast,
            event=event,
            work=work,
        ),
    )
    return (work,)


def _command(
    game: "GameService", c: Connection, state: GameState, mark_id: str
) -> tuple[rules.Mark, effects.Command]:
    from girlframe.services.m3_handler_advancements import _history
    from girlframe.services.m3_red_queen import prove_mark

    mark = prove_mark(game, c, state, mark_id)
    value = next((x for x in effects.records(state, effects.Command) if x.mark == mark_id), None)
    if value is None:
        raise WorkflowError("Recover the actual original Court command")
    original = next(
        (
            x
            for x in effects.records(_history(c, game, value.event), effects.Command)
            if x.id == value.id
        ),
        None,
    )
    if (
        original is None
        or original.model_dump(exclude={"action", "bound_event", "completed_event"})
        != value.model_dump(exclude={"action", "bound_event", "completed_event"})
        or value.actor != mark.target
        or value.target != mark.counterpart
        or value.work not in mark.work
    ):
        raise WorkflowError("Preserve the actual original command, target and required performance")
    return mark, value


def prepare_child(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    from girlframe.engine.m3_actors import fingerprint
    from girlframe.engine.m3_handler_consequences import active_handler
    from girlframe.services.m3_enforcement_initiative import _cast
    from girlframe.services.p1_source_pause import require_ready

    if prepared.source_work is None or not any(
        x.mark == prepared.source_work for x in effects.records(state, effects.Command)
    ):
        return None
    mark, value = _command(game, c, state, prepared.source_work)
    source_cast = _cast(game, c, state, channel)
    target = prepared.target_actor
    if target is None and prepared.target is not None and value.target.kind == "pilot":
        if str(prepared.target) == value.target.entity:
            target = value.target
    actor = resolve(
        state, value.actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    if (
        mark.completed_event
        or value.action
        or value.completed_event
        or prepared.play != value.play
        or prepared.parent is not None
        or target != value.target
        or viewer.user_id != value.controller
        or actor.controller != value.controller
        or fingerprint(source_cast) != fingerprint(value.cast)
    ):
        raise WorkflowError(
            "Perform this original bearer's exact commanded Play against its actual target"
        )
    require_ready(game, c, state, mark.id)
    handler = active_handler(state)
    if handler is None or state.handler is None:
        raise WorkflowError("Recover the actual source Handler")
    return dict(
        id=mark.id,
        child=value.id,
        work=value.work,
        actor=value.actor.model_dump(mode="json"),
        target=value.target.model_dump(mode="json"),
        play=value.play,
        parent=None,
        cast=value.cast.model_dump(mode="json"),
        cast_sha256=fingerprint(value.cast),
        table=sorted({x.controller for x in value.cast.roles} | {state.handler}),
        handler=handler.model_dump(mode="json"),
        handler_controller=state.handler,
    )


def bind_child(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:

    meta = action["data"]["red_queen_child"]
    mark, child = _command(game, c, state, meta["id"])
    if child.action or child.actor.entity != action["actor_id"]:
        raise WorkflowError("Bind only the actual original bearer's genuine performance")
    effects.put(state, child.model_copy(update=dict(action=action["id"], bound_event=event)))
    rules.put(state, mark.model_copy(update=dict(child=action["id"])))


def pre_roll_child(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    action: dict[str, Any],
) -> None:
    from girlframe.engine.m3_actors import fingerprint
    from girlframe.services.m3_enforcement_initiative import _cast
    from girlframe.services.m3_handler_advancements import _history

    mark, child = _command(game, c, state, action["data"]["red_queen_child"]["id"])
    original = next(
        (
            x
            for x in effects.records(_history(c, game, child.bound_event or ""), effects.Command)
            if x.id == child.id
        ),
        None,
    )
    if (
        child.action != action["id"]
        or original != child
        or child.completed_event
        or mark.completed_event
        or viewer.user_id != child.controller
        or fingerprint(_cast(game, c, state, int(action["channel_id"]))) != fingerprint(child.cast)
    ):
        raise WorkflowError("Resume the actual bound command before consuming dice or resources")


def complete_child(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    import json
    from uuid import uuid4

    import sqlalchemy as sa

    from girlframe.database import tables as t
    from girlframe.services.m3_collateral import append, latest
    from girlframe.services.m3_dose_up import _roll_source

    mark, child = _command(game, c, state, action["data"]["red_queen_child"]["id"])
    if child.completed_event:
        return
    if (
        child.action != action["id"]
        or action["state"] != "complete"
        or action["actor_id"] != child.actor.entity
        or game.pending(c, action["id"])
        or action["data"]["play"] != child.play
    ):
        raise WorkflowError("Finish the genuine commanded Play and its real consequences first")
    _roll_source(game, c, action)
    row = latest(game, c, child.work)
    if row["state"] != "resolved":
        append(
            c,
            row,
            event,
            json.loads(row["body_json"]) | dict(child_action=action["id"], child_event=event),
            "resolved",
        )
    final = str(uuid4())
    effects.put(state, child.model_copy(update=dict(completed_event=final)))
    rules.put(state, mark.model_copy(update=dict(completed_event=final)))
    human = c.scalar(
        sa.select(t.events.c.actor_id).where(
            t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == event
        )
    )
    if human is None:
        raise WorkflowError("Preserve the actual human performance event")
    game.event(
        c,
        int(human),
        str(uuid4()),
        "m3.red_queen_command_completed",
        state,
        event_id=final,
        source_event=event,
        source=mark.id,
        child_action=action["id"],
    )


def release_child(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], event: str
) -> bool:
    import sqlalchemy as sa

    from girlframe.database import tables as t

    meta = action["data"].get("red_queen_child")
    if not meta:
        return False
    if action["data"].get("receipt") or c.scalar(
        sa.select(t.m2["m2_receipts"].c.id).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == action["id"],
        )
    ):
        raise WorkflowError(
            "Preserve every known command roll; cancel only an unrolled reservation"
        )
    mark, child = _command(game, c, state, meta["id"])
    if child.action != action["id"] or child.completed_event:
        raise WorkflowError("Release the actual unrolled original command reservation")
    effects.put(state, child.model_copy(update=dict(action=None, bound_event=None)))
    rules.put(state, mark.model_copy(update=dict(child=None)))
    return True


def command_view(game: "GameService", viewer: GuildViewer, identity: str) -> dict[str, Any]:
    """Reconstruct the original bearer's private, durable command controls."""
    from girlframe.services.m2_state import load_state
    from girlframe.services.m3_red_queen import authorize

    with game.store.engine.connect() as c:
        authorize(game, c, viewer)
        state = load_state(c, game.store.campaign_id)
        mark, child = _command(game, c, state, identity)
        if viewer.user_id != child.controller:
            raise WorkflowError("Only the actual bearer can perform this commanded Play")
        actor = resolve(
            state, child.actor, profiles(c, game.store.campaign_id), require_current_profile=False
        )
        if actor.controller != viewer.user_id:
            raise WorkflowError("Recover the actual original bearer and controller")
        return dict(
            complete=bool(mark.completed_event or child.completed_event),
            action=child.action,
            play=child.play,
            parent=dict(
                kind="red_queen_child",
                parent=None,
                channel=child.cast.channel,
                actor=child.actor.model_dump(mode="json"),
                body=dict(
                    source_work=mark.id,
                    actor=child.actor.model_dump(mode="json"),
                    attacker=child.target.model_dump(mode="json"),
                    target=child.target.model_dump(mode="json"),
                    play=child.play,
                ),
            ),
        )


def synchronize(game: "GameService", c: Connection, event: str) -> None:
    issue_pending_orders(game, c, event)
    import sqlalchemy as sa

    from girlframe.database import tables as t
    from girlframe.services.m3_handler_advancements import _history
    from girlframe.services.m3_work import related

    saved = _history(c, game, event)
    if any(
        case.source_kind == "red_queen" and case.source_event == event
        for case in saved.role_punishments
    ):
        from girlframe.services.m3_role_punishments import synchronize as sync_discipline

        sync_discipline(game, c, None, event)
    table = t.m3["m3_required_work"]
    for child in effects.records(saved, effects.Command):
        if child.event != event or c.scalar(
            sa.select(table.c.id)
            .where(table.c.campaign_id == game.store.campaign_id, table.c.id == child.work)
            .limit(1)
        ):
            continue
        _command(game, c, saved, child.mark)
        related(
            c,
            game.store,
            dict(campaign_id=game.store.campaign_id, scene_id=child.cast.id),
            child.work,
            child.controller,
            child.controller,
            "red_queen_command",
            dict(
                owner=child.actor.model_dump(mode="json"),
                character=child.actor.incarnation,
                source_action=None,
                source_work=child.mark,
                child=child.id,
                play=child.play,
                target=child.target.model_dump(mode="json"),
                reason="red_queen_command",
                source_pdf=88,
                immediate=True,
            ),
            event,
        )


def issue_pending_orders(game: "GameService", c: Connection, event: str) -> None:
    """Materialize only canonical Court instructions as ordinary Receive Orders."""
    import json
    from uuid import uuid4

    from girlframe.database import tables as t
    from girlframe.services.m2_state import load_state
    from girlframe.services.m3_red_queen import bind_order, order_authority

    state = load_state(c, game.store.campaign_id)
    pending: list[tuple[int, int, str, str | None, int]] = [
        (
            x.author,
            int(x.actor.entity),
            x.instruction,
            x.session,
            rules.get(state, rules.Session, x.session).cast.channel,
        )
        for x in rules.records(state, rules.Advice)
        if x.session and x.actor.kind == "pilot" and x.answered_event == event and not x.order
    ]
    pending += [
        (int(x.actor.entity), int(x.target.entity), x.instruction, None, x.cast.channel)
        for x in rules.records(state, rules.Mark)
        if x.kind == "order"
        and x.actor.kind == "pilot"
        and x.target.kind == "pilot"
        and x.event == event
        and not x.order
    ]
    for issuer, target, instruction, parent_id, channel in pending:
        authority = order_authority(game, c, state, issuer, target, instruction)
        if authority is None:
            raise WorkflowError("Recover the actual canonical Court Order authority")
        scene = game.scene(c, channel)
        if target not in scene["participants"]:
            raise WorkflowError("Receive this actual Order in the original joined source scene")
        lock = game.lock(c, channel)
        identity, order, final = str(uuid4()), str(uuid4()), str(uuid4())
        if parent_id:
            action = game.action(c, parent_id)
            if (
                action["actor_id"] != str(target)
                or not lock
                or lock["state"] != "held"
                or lock["action_id"] != parent_id
            ):
                raise WorkflowError("Preserve the actual held original Consult action")
            previous = action["data"].get("order_id")
            if previous:
                # Low Consult creates several independent Orders on one held Play.
                # Advance only after the original owner has followed the prior one;
                # never overwrite a pending response or an unresolved refusal child.
                prior = next(
                    (
                        x
                        for x in rules.records(state, rules.Advice)
                        if x.session == parent_id
                        and x.order == previous
                        and x.actor == rules.get(state, rules.Session, parent_id).actor
                        and x.author == issuer
                    ),
                    None,
                )
                table = t.m2["m2_orders"]
                row = (
                    c.execute(
                        table.select().where(
                            table.c.campaign_id == game.store.campaign_id,
                            table.c.id == previous,
                            table.c.issuer_id == str(issuer),
                            table.c.target_id == str(target),
                            table.c.channel_id == str(channel),
                            table.c.state == "followed",
                        )
                    )
                    .mappings()
                    .first()
                )
                body = json.loads(row["body_json"]) if row is not None else {}
                if (
                    prior is None
                    or not prior.answered_event
                    or body.get("text") != prior.instruction
                    or body.get("red_queen")
                    != dict(
                        kind="advice",
                        id=prior.id,
                        target=prior.actor.model_dump(mode="json"),
                        court=prior.court,
                    )
                    or game.pending(c, parent_id)
                ):
                    raise WorkflowError("Resolve the actual preceding Court Order first")
        else:
            if lock and lock["state"] != "released":
                raise WorkflowError("Resolve the current scene action before this actual Order")
            data = dict(
                play="receive_orders",
                character_ids={
                    str(uid): game.character_binding(c, state, uid, require_current_profile=False)
                    for uid in scene["participants"]
                    if str(uid) in state.sheets
                },
                order_id=order,
                order_text=instruction,
                participants=scene["participants"],
                handler=state.handler,
                depth=0,
                receipt=None,
                modifiers=[],
                result={},
                choices={},
            )
            c.execute(
                t.m2["m2_actions"]
                .insert()
                .values(
                    campaign_id=game.store.campaign_id,
                    id=identity,
                    actor_id=str(target),
                    channel_id=str(channel),
                    scene_id=scene["id"],
                    parent_id=None,
                    revision=1,
                    state="acquiring",
                    body_json=json.dumps(data),
                )
            )
            values = dict(
                action_id=identity,
                state="acquiring",
                body_json="{}",
                lease_until=0,
                claim_token=None,
            )
            table = t.m2["m2_locks"]
            if lock:
                c.execute(
                    table.update()
                    .where(
                        table.c.campaign_id == game.store.campaign_id,
                        table.c.channel_id == str(channel),
                    )
                    .values(**values)
                )
            else:
                c.execute(
                    table.insert().values(
                        campaign_id=game.store.campaign_id, channel_id=str(channel), **values
                    )
                )
            action = game.action(c, identity)
        c.execute(
            t.m2["m2_orders"]
            .insert()
            .values(
                campaign_id=game.store.campaign_id,
                id=order,
                issuer_id=str(issuer),
                target_id=str(target),
                channel_id=str(channel),
                state="awaiting_response",
                body_json=json.dumps(dict(text=instruction, red_queen=authority)),
            )
        )
        bind_order(game, c, state, authority, order, final)
        action["data"].update(order_id=order, order_text=instruction)
        if parent_id:
            game.request(c, action, target, "order_response", dict(order_id=order))
            game.save_action(c, action, state="awaiting_choices")
        game.event(
            c,
            issuer,
            str(uuid4()),
            "m2.order_issued",
            state,
            event_id=final,
            action_id=action["id"],
            order_id=order,
            red_queen=authority,
            source_event=event,
        )


def stage_tag_births(
    game: "GameService", c: Connection, before: GameState, after: GameState, event: str
) -> None:
    from girlframe.engine.m3_handler_consequences import active_handler
    from girlframe.engine.m3_mockingbird import actor_tags

    people = [
        ActorRef(kind="pilot", entity=str(x.owner), incarnation=x.character_id)
        for x in after.sheets.values()
        if x.character_id
    ]
    if after.world is not None:
        people += [ActorRef(kind="npc", entity=x.id) for x in after.world.npcs]
        people += [ActorRef(kind="gorgon", entity=x.id) for x in after.world.gorgons]
        people += [ActorRef(kind="external_pilot", entity=x.id) for x in after.world.pilots]
    people += [ActorRef(kind="external_pilot", entity=x.id) for x in after.harpy_states]
    handler = active_handler(after)
    if handler is not None:
        people.append(handler)
    existing = {(x.target, x.id) for x in effects.records(after, effects.TagGift)}
    for receiver in dict.fromkeys(people):
        try:
            old_ids = {x.id for x in actor_tags(before, receiver)}
            tags = actor_tags(after, receiver)
        except (ValueError, KeyError):
            continue
        for tag in tags:
            if tag.id in old_ids or (receiver, tag.id) in existing:
                continue
            giver = getattr(tag, "giver_actor", None) or getattr(tag, "giver_ref", None)
            if giver is None:
                raw = getattr(tag, "giver", None)
                if isinstance(raw, ActorRef):
                    giver = raw
                elif isinstance(raw, int) and (
                    incarnation := getattr(tag, "giver_character", None)
                ):
                    giver = ActorRef(kind="pilot", entity=str(raw), incarnation=incarnation)
            if not isinstance(giver, ActorRef) or giver.kind != "pilot":
                continue
            try:
                if not rules.held(after, giver, rules.JUDGEMENT):
                    continue
            except ValueError:
                continue
            effects.put(
                after,
                effects.TagGift(
                    id=tag.id,
                    giver=giver,
                    target=receiver,
                    label=tag.label,
                    source=event,
                    event=event,
                ),
            )


def judgement_source(
    game: "GameService", c: Connection, state: GameState, source: rules.Context, tag_id: str
) -> str:
    import sqlalchemy as sa

    from girlframe.database import tables as t
    from girlframe.engine.m3_mockingbird import actor_tags
    from girlframe.services.m3_handler_advancements import _history
    from girlframe.services.m3_red_queen import prove_context, require_rule

    actual = prove_context(game, c, state, source.id)
    if actual.kind != "watching":
        raise WorkflowError("Use the actual original Handler's watching source")
    require_rule(game, c, state, actual.actor, rules.JUDGEMENT)
    gift = next(
        (
            x
            for x in effects.records(state, effects.TagGift)
            if x.id == tag_id and x.giver == actual.actor and x.target == actual.target
        ),
        None,
    )
    if gift is None:
        raise WorkflowError("Recover the actual new Tag given by this original Red Queen")
    birth = _history(c, game, gift.event)
    recorded = next(
        (
            x
            for x in effects.records(birth, effects.TagGift)
            if x.id == gift.id and x.target == gift.target
        ),
        None,
    )
    tag = next((x for x in actor_tags(birth, gift.target) if x.id == tag_id), None)
    events = t.events
    context_seq = c.scalar(
        sa.select(events.c.seq).where(
            events.c.campaign_id == game.store.campaign_id, events.c.id == actual.event
        )
    )
    tag_seq = c.scalar(
        sa.select(events.c.seq).where(
            events.c.campaign_id == game.store.campaign_id, events.c.id == gift.event
        )
    )
    if (
        recorded != gift
        or tag is None
        or tag.label != gift.label
        or context_seq is None
        or tag_seq is None
        or context_seq > tag_seq
    ):
        raise WorkflowError("The actual Handler must already be watching at this genuine Tag birth")
    return gift.event
