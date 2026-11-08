"""Real standalone repeated Feedback: source work, owned effects, and genuine child Plays."""

import json
from typing import TYPE_CHECKING, Any, Literal

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine import m3_ankou as rules
from girlframe.engine.m2 import AssetState, GameState, PlayInput
from girlframe.engine.m3_actor_bonds import depth, make_helpless, set_depth
from girlframe.engine.m3_actor_state import ActorRef, SceneCast
from girlframe.engine.m3_actors import fingerprint, resolve
from girlframe.engine.m3_core import install
from girlframe.services import m3_ankou_support as support
from girlframe.services.m2_state import load_state
from girlframe.services.m3_actors import profiles
from girlframe.services.m3_handler_advancements import _history
from girlframe.services.onboarding import WorkflowError
from girlframe.services.read_only_bot import GuildViewer

if TYPE_CHECKING:
    from girlframe.services.m2_game import GameService


def start(
    game: "GameService",
    c: Connection,
    state: GameState,
    actor: ActorRef,
    cast: SceneCast | None,
    source: str,
    event: str,
    *,
    count: Literal[1, 5],
    reason: Literal["relay", "obsession"],
) -> rules.FeedbackSequence:
    key = rules.identity("feedback", source, event)
    if any(x.id == key for x in rules.records(state, rules.FeedbackSequence)):
        raise WorkflowError("Preserve this exact original Feedback consequence")
    value = rules.FeedbackSequence(
        id=key, actor=actor, cast=cast, source=source, event=event, count=count, reason=reason
    )
    rules.put(state, value)
    return value


def prove(
    game: "GameService", c: Connection, state: GameState, identity: str
) -> rules.FeedbackSequence:
    value = rules.get(state, rules.FeedbackSequence, identity)
    born = rules.get(_history(c, game, value.event), rules.FeedbackSequence, identity)
    if any(
        getattr(value, k) != getattr(born, k)
        for k in ("id", "actor", "cast", "source", "event", "count", "reason")
    ):
        raise WorkflowError("Preserve the original actual Feedback cause/count/person")
    if value.reason == "relay":
        from girlframe.services.m3_ankou import prove_relay

        relay = prove_relay(game, c, state, value.source)
        if (
            relay.actor != value.actor
            or relay.consequence != "feedback"
            or relay.consequence_event != value.event
            or value.count != 1
        ):
            raise WorkflowError(
                "Only the actual Handler-selected Relay consequence causes this Feedback"
            )
    else:
        original = rules.get(_history(c, game, value.event), rules.Obsession, value.source)
        if (
            original.actor != value.actor
            or original.sequence != value.id
            or original.ended_event != value.event
            or value.count != 5
        ):
            raise WorkflowError("Preserve the actual Obsession death/whole-OffDuty source")
    return value


def prove_step(
    game: "GameService", c: Connection, state: GameState, identity: str
) -> rules.FeedbackStep:
    value = rules.get(state, rules.FeedbackStep, identity)
    sequence = prove(game, c, state, value.sequence)
    birth = rules.get(_history(c, game, value.event), rules.FeedbackStep, identity)
    if (
        value.actor != sequence.actor
        or value.id not in sequence.steps
        or sequence.venue is None
        or value.cast != sequence.venue
        or any(
            getattr(value, k) != getattr(birth, k)
            for k in ("id", "sequence", "actor", "cast", "event", "ordinal")
        )
    ):
        raise WorkflowError("Retain this actual activated standalone Feedback step and venue")
    if value.choice_event:
        selected = rules.get(_history(c, game, value.choice_event), rules.FeedbackStep, value.id)
        if any(
            getattr(selected, k) != getattr(value, k)
            for k in ("choice", "target", "target_controller", "account", "asset", "choice_event")
        ):
            raise WorkflowError("Retain the actual original Feedback owner selection")
    return value


def _new_step(state: GameState, sequence: rules.FeedbackSequence, event: str) -> rules.FeedbackStep:
    if sequence.venue is None or len(sequence.steps) >= sequence.count:
        raise WorkflowError("Activate a genuine venue for the outstanding Feedback first")
    value = rules.FeedbackStep(
        id=rules.identity("step", sequence.id, str(len(sequence.steps))),
        sequence=sequence.id,
        actor=sequence.actor,
        cast=sequence.venue,
        event=event,
        ordinal=len(sequence.steps) + 1,
    )
    rules.put(state, value)
    rules.put(state, sequence.model_copy(update={"steps": (*sequence.steps, value.id)}))
    return value


def activate(
    game: "GameService",
    viewer: GuildViewer,
    key: str,
    sequence_id: str,
    channel: int,
    revision: int,
    account: str,
) -> dict[str, Any]:
    from girlframe.services.m3_ankou import AnkouService
    from girlframe.services.m3_dose_up import _cast

    def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
        sequence = prove(game, c, state, sequence_id)
        if (
            viewer.user_id != int(sequence.actor.entity)
            or sequence.venue
            or sequence.completed_event
            or sequence.terminal_event
        ):
            raise WorkflowError(
                "Activate your actual pending Feedback in a genuinely joined free scene"
            )
        cast = _cast(game, c, state, channel)
        support.cast_actor(game, c, state, cast, sequence.actor)
        lock = game.lock(c, channel)
        if lock and lock["state"] != "released":
            raise WorkflowError(
                "Finish the actual existing Play before activating standalone Feedback"
            )
        support.text(account)
        sequence = sequence.model_copy(update={"venue": cast, "activated_event": event})
        rules.put(state, sequence)
        step = _new_step(state, sequence, event)
        return dict(id=step.id, sequence=sequence.id)

    return AnkouService(game)._write(
        viewer,
        key,
        revision,
        "m3.ankou_feedback_activated",
        dict(sequence=sequence_id, channel=channel, account=account),
        operation,
    )


def _ready(
    game: "GameService", c: Connection, state: GameState, value: rules.FeedbackStep, event: str
) -> None:
    sequence = rules.get(state, rules.FeedbackSequence, value.sequence)
    rules.put(state, value.model_copy(update={"phase": "complete", "completed_event": event}))
    if value.ordinal == sequence.count:
        rules.put(state, sequence.model_copy(update={"completed_event": event}))
    else:
        _new_step(state, sequence, event)


def choose(
    game: "GameService",
    viewer: GuildViewer,
    key: str,
    identity: str,
    revision: int,
    choice: Literal["bond", "purpose", "tear", "die"],
    target: ActorRef | None,
    account: str,
    *,
    asset: str | None = None,
    replace: str | None = None,
    name: str | None = None,
    in_battle: bool | None = None,
    opponent: ActorRef | None = None,
    no_opponent: bool = False,
) -> dict[str, Any]:
    from girlframe.services.m3_ankou import AnkouService

    def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
        from girlframe.services.p1_source_pause import require_ready

        value = prove_step(game, c, state, identity)
        if viewer.user_id != int(value.actor.entity) or value.phase != "choice":
            raise WorkflowError(
                "Only the original actual owner chooses this sequential Feedback effect"
            )
        require_ready(game, c, state, value.sequence)
        support.text(account)
        if choice != "die":
            if target is None or target == value.actor:
                raise WorkflowError("Select the actual other person in this activated source scene")
            support.cast_actor(game, c, state, value.cast, target)
        controller = (
            resolve(state, target, profiles(c, game.store.campaign_id)).controller
            if target
            else None
        )
        value = value.model_copy(
            update={
                "choice": choice,
                "target": target,
                "target_controller": controller,
                "account": account,
                "choice_event": event,
                "asset": asset,
                "opponent": opponent,
                "no_opponent": no_opponent,
            }
        )
        if choice == "die":
            from girlframe.services.m3_careers import end_in_transaction

            support.copy(
                state,
                end_in_transaction(
                    c,
                    game,
                    state,
                    value.actor,
                    reason="death",
                    source_event=event,
                    account=account,
                    archive_id="ankou-sequence-death:" + value.id,
                ),
            )
            archive = next(
                (
                    x
                    for x in state.career_archives
                    if x.actor == value.actor and x.source_event == event
                ),
                None,
            )
            if archive:
                rules.put(
                    state, value.model_copy(update={"phase": "ended", "completed_event": event})
                )
                sequence = rules.get(state, rules.FeedbackSequence, value.sequence)
                rules.put(state, sequence.model_copy(update={"terminal_event": event}))
            else:
                _ready(game, c, state, value, event)
        elif choice == "bond":
            assert target is not None
            if depth(state, value.actor, target) < 1 or not name:
                raise WorkflowError(
                    "Cut off a real actual Bond and name its rewritten psychological Girl Asset"
                )
            from girlframe.engine.m3_intracadre_marriage import marriage_for

            if marriage_for(state, value.actor):
                raise WorkflowError(
                    "SOURCE_MARRIAGE_BOND_REQUIRED: preserve actual marriage consequences"
                )
            result = install(
                state.sheets[value.actor.entity],
                AssetState(
                    id=rules.identity("bond-asset", value.id),
                    family="girl",
                    name=support.text(name),
                    description=account,
                ),
                replace=replace,
                state=state,
            )
            state.sheets[value.actor.entity] = result.sheet
            support.copy(state, set_depth(state, value.actor, target, 0, event))
            _ready(game, c, state, value, event)
        elif choice == "purpose":
            rules.put(state, value.model_copy(update={"phase": "purpose"}))
        else:
            if target is None or target.kind != "pilot":
                raise WorkflowError(
                    "SOURCE_REPRISAL_REQUIRED: use a genuine native recipient adapter"
                )
            from girlframe.engine.m3_budget_removal import blocked

            sheet = state.sheets[value.actor.entity]
            actual = next((x for x in sheet.assets if x.id == asset), None)
            view = resolve(state, value.actor, profiles(c, game.store.campaign_id))
            if actual is None or actual.id in blocked(state, value.actor) or actual.void:
                raise WorkflowError("Choose an actual removable owned uncorrupted Asset")
            if actual.family == "frame" and (
                view.frame_instance != rules.frame(state, value.actor)
                or view.frame_cell is None
                or view.cell != view.frame_cell
            ):
                raise WorkflowError(
                    "Be physically present at the actual original Frame before tearing its Asset"
                )
            if (
                actual.family == "girl"
                and not view.inside_frame
                and not any(
                    x.family == "girl" and x.id != actual.id and not x.damaged for x in sheet.assets
                )
            ):
                if opponent is None and not no_opponent:
                    raise WorkflowError(
                        "Identify the actual opponent, or confirm none, before last Girl-Asset loss"
                    )
                if opponent is not None:
                    if no_opponent or opponent == value.actor:
                        raise WorkflowError(
                            "Use the actual opposing person without an invented foe"
                        )
                    support.cast_actor(game, c, state, value.cast, opponent)
                    support.copy(state, make_helpless(state, value.actor, opponent, event))
                    sheet = state.sheets[value.actor.entity]
            sheet.assets = [x for x in sheet.assets if x.id != asset]
            sheet.revision += 1
            support.gain_heat(state, value.actor, 5, event, "Ankou Feedback tear")
            # The actual source-time battlefield fact stays with the real removal, not an m2 row.
            state.facts.append(
                dict(
                    kind="ankou_feedback_loss_context",
                    id=value.id,
                    event=event,
                    in_battle=json.dumps(in_battle),
                )
            )
            rules.put(state, value.model_copy(update={"phase": "child"}))
        return dict(id=value.id)

    return AnkouService(game)._write(
        viewer,
        key,
        revision,
        "m3.ankou_feedback_chosen",
        dict(
            id=identity,
            choice=choice,
            target=target.model_dump(mode="json") if target else None,
            account=account,
            asset=asset,
            replace=replace,
            name=name,
            in_battle=in_battle,
            opponent=opponent.model_dump(mode="json") if opponent else None,
            no_opponent=no_opponent,
        ),
        operation,
    )


def answer_purpose(
    game: "GameService",
    viewer: GuildViewer,
    key: str,
    identity: str,
    revision: int,
    given: bool,
    account: str,
    *,
    replace: str | None = None,
) -> dict[str, Any]:
    from girlframe.services.m3_ankou import AnkouService

    def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
        value = prove_step(game, c, state, identity)
        if value.phase != "purpose" or viewer.user_id != value.target_controller:
            raise WorkflowError("Only the actual begged original person authors this real response")
        support.text(account)
        if given:
            # Actual owner, rather than counterpart, later chooses a cap-required replacement.
            rules.put(
                state,
                value.model_copy(
                    update={"phase": "identity", "purpose": account, "purpose_event": event}
                ),
            )
        else:
            assert value.target is not None
            support.copy(state, make_helpless(state, value.actor, value.target, event))
            _ready(
                game,
                c,
                state,
                value.model_copy(update={"purpose": account, "purpose_event": event}),
                event,
            )
        return dict(id=value.id)

    return AnkouService(game)._write(
        viewer,
        key,
        revision,
        "m3.ankou_feedback_purpose",
        dict(id=identity, given=given, account=account, replace=replace),
        operation,
    )


def write_purpose(
    game: "GameService",
    viewer: GuildViewer,
    key: str,
    identity: str,
    revision: int,
    replace: str | None = None,
) -> dict[str, Any]:
    from girlframe.services.m3_ankou import AnkouService

    def operation(c: Connection, state: GameState, event: str) -> dict[str, Any]:
        value = prove_step(game, c, state, identity)
        if (
            value.phase != "identity"
            or viewer.user_id != int(value.actor.entity)
            or not value.purpose
        ):
            raise WorkflowError(
                "The original owner places the actual purpose their counterpart gave"
            )
        support.write_identity(
            state, value.actor, rules.identity("purpose", value.id), value.purpose, replace
        )
        _ready(game, c, state, value, event)
        return dict(id=value.id)

    return AnkouService(game)._write(
        viewer,
        key,
        revision,
        "m3.ankou_feedback_identity",
        dict(id=identity, replace=replace),
        operation,
    )


def prepare_child(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    prepared: PlayInput,
    channel: int,
) -> dict[str, Any] | None:
    source = prepared.source_work
    if source is None:
        return None
    value = next((x for x in rules.records(state, rules.FeedbackStep) if x.id == source), None)
    task = next(
        (
            x
            for x in rules.records(state, rules.Task)
            if x.id == source and x.kind in ("perform", "interrupt")
        ),
        None,
    )
    if value is None and task is None:
        return None
    from girlframe.services.m3_ankou import prove_task

    target: ActorRef | None
    allowed: tuple[str, ...]
    if value:
        value = prove_step(game, c, state, value.id)
        if value.phase != "child" or value.child or not value.target:
            raise WorkflowError("Resume this actual outstanding Feedback child")
        actor, cast, target = value.actor, value.cast, value.target
        allowed = ("flirt",)
    else:
        assert task is not None
        task = prove_task(game, c, state, task.id)
        if task.child or task.completed_event:
            raise WorkflowError("Resume this genuine owned source performance")
        actor, cast, target = task.actor, task.cast, task.target
        allowed = task.options
    support.cast_actor(game, c, state, cast, actor)
    parent = task.source_action if task and task.kind == "interrupt" else None
    if (
        viewer.user_id != int(actor.entity)
        or actor.kind != "pilot"
        or prepared.play not in allowed
        or prepared.parent != parent
        or channel != cast.channel
    ):
        raise WorkflowError(
            "Make the real selected ordinary Play with its original actor and source"
        )
    if value:
        assert target is not None
    if value and (
        prepared.target_actor not in (None, target)
        or target is None
        or prepared.target not in (None, int(target.entity))
        or prepared.identity
        or prepared.disposable_heat
        or prepared.gain
        or prepared.heat != state.sheets[actor.entity].heat
    ):
        raise WorkflowError(
            "Make the real reprisal Flirt against the selected person, spending all actual Heat"
        )
    from girlframe.services.p1_source_pause import require_ready

    if task and task.kind == "interrupt":
        incoming = game.action(c, parent or "")
        pending = game.pending(c, incoming["id"])
        if not task.request or not any(
            x["id"] == task.request and x["kind"] == "ankou_interrupt_child" for x in pending
        ):
            raise WorkflowError(
                "Retain the genuine original incoming interruption row and held Play"
            )
    else:
        require_ready(game, c, state, value.sequence if value else source)
    from girlframe.engine.m3_handler_consequences import active_handler

    handler = active_handler(state)
    if handler is None:
        raise WorkflowError("Recover the actual source Handler appointment")
    handler_controller = resolve(state, handler, profiles(c, game.store.campaign_id)).controller
    return dict(
        id=source,
        actor=actor.model_dump(mode="json"),
        target=target.model_dump(mode="json") if target else None,
        cast=cast.model_dump(mode="json"),
        cast_sha256=fingerprint(cast),
        table=sorted(
            {
                *(x.controller for x in cast.roles),
                handler_controller,
                *((cast.facilitator,) if cast.facilitator else ()),
            }
        ),
        handler=handler.model_dump(mode="json"),
        handler_controller=handler_controller,
        parent=parent,
        choice=task.request if task and task.kind == "interrupt" else None,
        play=prepared.play,
        source_work=source,
        phase="prepared",
    )


def bind_child(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    meta = action["data"].get("ankou_effect_child")
    if not meta:
        return
    source = meta["id"]
    value = next((x for x in rules.records(state, rules.FeedbackStep) if x.id == source), None)
    if value:
        rules.put(state, value.model_copy(update={"child": action["id"], "child_event": event}))
    else:
        task = rules.get(state, rules.Task, source)
        rules.put(state, task.model_copy(update={"child": action["id"]}))


def pre_roll_child(
    game: "GameService",
    c: Connection,
    viewer: GuildViewer,
    state: GameState,
    action: dict[str, Any],
) -> None:
    meta = action["data"]["ankou_effect_child"]
    value = next((x for x in rules.records(state, rules.FeedbackStep) if x.id == meta["id"]), None)
    if value:
        prove_step(game, c, state, value.id)
        if value.child != action["id"] or value.phase != "child":
            raise WorkflowError("Use the actual already bound Feedback child")
        actor, cast = value.actor, value.cast
    else:
        from girlframe.services.m3_ankou import prove_task

        task = prove_task(game, c, state, meta["id"])
        if task.child != action["id"] or task.completed_event:
            raise WorkflowError("Use this actual bound nominated performance")
        actor, cast = task.actor, task.cast
    if support.actual_action_actor(action) != actor or viewer.user_id != int(actor.entity):
        raise WorkflowError("Never substitute another same-account source actor")
    support.cast_actor(game, c, state, cast, actor)
    from girlframe.services.m3_dose_up import _cast

    if fingerprint(_cast(game, c, state, cast.channel)) != meta["cast_sha256"]:
        raise WorkflowError("Refresh the actual changed child source scene")


def complete_child(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    meta = action["data"].get("ankou_effect_child")
    if not meta:
        return
    if (
        action["state"] != "complete"
        or not action["data"].get("receipt")
        or game.pending(c, action["id"])
    ):
        return
    from uuid import uuid4

    completion_event = str(uuid4())
    value = next((x for x in rules.records(state, rules.FeedbackStep) if x.id == meta["id"]), None)
    if value:
        value = prove_step(game, c, state, value.id)
        if value.completed_event:
            return
        if value.child != action["id"]:
            raise WorkflowError("Preserve the actual original reprisal child")
        from girlframe.services.m3_collateral import latest

        if any(latest(game, c, x)["state"] != "resolved" for x in value.work):
            return
        _ready(game, c, state, value, completion_event)
    else:
        from girlframe.services.m3_ankou import prove_task

        task = prove_task(game, c, state, meta["id"])
        if task.completed_event:
            return
        if task.child != action["id"]:
            raise WorkflowError("Preserve the actual nominated performance child")
        rules.put(state, task.model_copy(update={"completed_event": completion_event}))
        if task.kind == "interrupt":
            incoming = game.action(c, task.source_action or "")
            for row in game.pending(c, incoming["id"]):
                if row["id"] == task.request and row["kind"] == "ankou_interrupt_child":
                    c.execute(
                        t.m2["m2_choices"]
                        .update()
                        .where(
                            t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                            t.m2["m2_choices"].c.id == row["id"],
                        )
                        .values(
                            state="answered",
                            revision=row["revision"] + 1,
                            body_json=json.dumps(
                                dict(
                                    task=task.id,
                                    child=action["id"],
                                    completed_event=completion_event,
                                )
                            ),
                        )
                    )

    if not value and task.kind == "interrupt":
        incoming = game.action(c, task.source_action or "")
        if not game.pending(c, incoming["id"]):
            if incoming["data"].get("receipt"):
                from girlframe.services.m2_choices import ChoiceEngine

                incoming["data"]["ankou_interruption_completion"] = dict(
                    task=task.id,
                    child=action["id"],
                    prior_response_event=incoming["data"].get("response_event"),
                    event=completion_event,
                )
                incoming["data"]["response_event"] = completion_event
                ChoiceEngine(game).results(c, state, incoming)
                game.save_action(c, incoming)
            else:
                game.save_action(c, incoming, state="ready_to_roll")
    game.event(
        c,
        int(action["actor_id"]),
        completion_event,
        "m3.ankou_child_completed",
        state,
        event_id=completion_event,
        source=meta["id"],
        child=action["id"],
        child_source_event=event,
    )


def prove_loss_source(
    game: "GameService",
    c: Connection,
    after: GameState,
    event: str,
    source_id: str,
    actor: ActorRef,
) -> dict[str, Any]:
    from girlframe.services.m3_asset_loss import snapshots

    before, saved = snapshots(game, c, event)
    value = prove_step(game, c, saved, source_id)
    if (
        value.actor != actor
        or value.choice != "tear"
        or value.choice_event != event
        or not value.asset
    ):
        raise WorkflowError("Use the actual canonical original Feedback tear and chosen Asset")
    old = before.sheets.get(actor.entity)
    new = saved.sheets.get(actor.entity)
    if (
        old is None
        or new is None
        or old.character_id != actor.incarnation
        or new.character_id != actor.incarnation
        or not any(x.id == value.asset for x in old.assets)
        or any(x.id == value.asset for x in new.assets)
        or [x for x in old.assets if x.id != value.asset] != new.assets
    ):
        raise WorkflowError("Prove exactly one actual source-owned Asset removal")
    from girlframe.engine.m3_leviathan_obsession import allowed_gain

    if new.heat != old.heat + allowed_gain(before, actor, 5, "Ankou Feedback tear", event):
        raise WorkflowError("Preserve the actual fiveHeat gain from this exact original cost")
    fact = next(
        (
            x
            for x in saved.facts
            if x.get("kind") == "ankou_feedback_loss_context"
            and x.get("id") == source_id
            and x.get("event") == event
        ),
        None,
    )
    if fact is None:
        raise WorkflowError("Preserve the actual source-time battlefield context")
    actual = resolve(
        before, actor, profiles(c, game.store.campaign_id), require_current_profile=False
    )
    return dict(
        piloting=actual.piloting, in_battle=json.loads(fact["in_battle"]), source_action=None
    )


def materialize(game: "GameService", c: Connection, event: str) -> None:
    state = load_state(c, game.store.campaign_id)
    from girlframe.services.m3_collateral import latest
    from girlframe.services.m3_work import related

    work = t.m3["m3_required_work"]
    for task in rules.records(state, rules.Task):
        if (
            task.kind != "interrupt"
            or task.request
            or task.completed_event
            or not task.source_action
        ):
            continue
        current = rules.get(load_state(c, game.store.campaign_id), rules.Task, task.id)
        if current.request or current.completed_event:
            continue
        incoming = game.action(c, task.source_action)
        request = game.request(c, incoming, task.controller, "ankou_interrupt", dict(task=task.id))
        from uuid import uuid4

        bound_event = str(uuid4())
        state = load_state(c, game.store.campaign_id)
        rules.put(state, current.model_copy(update={"request": request}))
        game.event(
            c,
            task.controller,
            bound_event,
            "m3.ankou_interrupt_bound",
            state,
            event_id=bound_event,
            source=task.id,
            incoming=incoming["id"],
        )
    state = load_state(c, game.store.campaign_id)
    for sequence in rules.records(state, rules.FeedbackSequence):
        if not c.scalar(
            sa.select(work.c.id).where(
                work.c.campaign_id == game.store.campaign_id, work.c.id == sequence.id
            )
        ):
            related(
                c,
                game.store,
                dict(campaign_id=game.store.campaign_id, campaign_context=True),
                sequence.id,
                int(sequence.actor.entity),
                int(sequence.actor.entity),
                "ankou_feedback_sequence",
                dict(
                    source=sequence.id,
                    actor=sequence.actor.model_dump(mode="json"),
                    immediate=True,
                    source_action=None,
                ),
                sequence.event,
            )
        if sequence.completed_event or sequence.terminal_event:
            row = latest(game, c, sequence.id)
            if row["state"] != "resolved":
                from girlframe.services.m3_collateral import append

                append(
                    c,
                    row,
                    sequence.completed_event or sequence.terminal_event or event,
                    json.loads(row["body_json"])
                    | dict(
                        completed_event=sequence.completed_event,
                        terminal_event=sequence.terminal_event,
                    ),
                    "resolved",
                )
    for step in rules.records(state, rules.FeedbackStep):
        if step.choice != "tear" or not step.choice_event or step.work:
            continue
        from girlframe.services.m3_asset_loss import create_loss_work, snapshots

        before, after = snapshots(game, c, step.choice_event)
        context = prove_loss_source(game, c, after, step.choice_event, step.id, step.actor)
        ids = create_loss_work(
            game,
            c,
            before,
            after,
            scope=dict(campaign_id=game.store.campaign_id, scene_id=step.cast.id),
            actor=step.actor,
            event=step.choice_event,
            reason="ankou_feedback_sequence",
            source_id=step.id,
            in_battle=context["in_battle"],
        )
        if ids:
            # Save genuine newly materialized children as a distinct canonical transition.
            from uuid import uuid4

            update = str(uuid4())
            rules.put(state, step.model_copy(update={"work": tuple(ids)}))
            game.event(
                c,
                int(step.actor.entity),
                update,
                "m3.ankou_feedback_loss_work",
                state,
                event_id=update,
                source=step.id,
            )


def projection(
    game: "GameService", c: Connection, state: GameState, value: Any, viewer: GuildViewer
) -> dict[str, Any]:
    if isinstance(value, rules.FeedbackSequence):
        prove(game, c, state, value.id)
        return dict(
            can_activate=value.venue is None
            and not value.completed_event
            and not value.terminal_event,
            step=value.steps[-1] if value.steps else None,
        )
    value = prove_step(game, c, state, value.id)
    from girlframe.services.p1_source_pause import projection as pause

    bound = profiles(c, game.store.campaign_id)
    return dict(
        pause=pause(game, c, value.sequence),
        can_choose=value.phase == "choice" and viewer.user_id == int(value.actor.entity),
        can_answer=value.phase == "purpose" and viewer.user_id == value.target_controller,
        can_write=value.phase == "identity" and viewer.user_id == int(value.actor.entity),
        targets=[
            dict(
                id=x.actor.token,
                ref=x.actor.model_dump(mode="json"),
                label=resolve(state, x.actor, bound).label,
            )
            for x in value.cast.roles
            if x.actor != value.actor
        ],
        counter=dict(
            kind="ankou_effect_child",
            parent=None,
            channel=value.cast.channel,
            body=dict(
                source_work=value.id,
                target=value.target.model_dump(mode="json") if value.target else None,
                allowed=("flirt",),
            ),
        )
        if value.phase == "child" and value.child is None
        else None,
        child=value.child,
        can_resume=bool(value.child),
        assets=[dict(id=x.id, label=x.name) for x in state.sheets[value.actor.entity].assets],
        identities=[
            dict(id=x.id, label=x.name) for x in state.sheets[value.actor.entity].identities
        ],
    )


def release_child(
    game: "GameService", c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    meta = action["data"].get("ankou_effect_child")
    if not meta:
        return
    if action["data"].get("receipt"):
        raise WorkflowError("Keep the genuine known result; this actual child cannot be unrolled")
    value = next((x for x in rules.records(state, rules.FeedbackStep) if x.id == meta["id"]), None)
    if value:
        value = prove_step(game, c, state, value.id)
        if value.child != action["id"] or value.phase != "child":
            raise WorkflowError("Release only this actual unrolled bound reprisal")
        rules.put(state, value.model_copy(update={"child": None, "child_event": None}))
    else:
        from girlframe.services.m3_ankou import prove_task

        task = prove_task(game, c, state, meta["id"])
        if task.child != action["id"] or task.completed_event:
            raise WorkflowError("Release only this actual source's unfinished unrolled performance")
        rules.put(state, task.model_copy(update={"child": None}))
