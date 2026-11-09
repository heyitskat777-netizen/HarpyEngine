"""Finite actual learned-Play admission and one-roll consumption; source effects stay explicit."""

import hashlib
import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import GameState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_girl_runtime_state import GirlRuntime, has_rule
from girlframe.engine.m3_learned_play_state import LearnedPlayUse
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError

NO_ONE_BETTER = "girl.casualty.no-one-better"
SUPPORTED = {
    "girl.alpha.brutalize": ("brutalize", "ALPHA"),
    "girl.stim-blissed.dose-up": ("dose_up", "STIM-BLISSED"),
    "girl.oldgen.old-dog-new-pups": ("old_dog_new_pups", "OLDGEN"),
    "girl.newgirl.easy-target": ("easy_target", "NEWGIRL"),
    "girl.mockingbird.bad-at-being-a-person": ("mockingbird_person", "MOCKINGBIRD"),
    NO_ONE_BETTER: ("all_out_assault", "CASUALTY"),
}


def lesson_label(rule_id: str, play: str) -> str:
    return (
        "No One Better (high Assault extra maneuver)"
        if rule_id == NO_ONE_BETTER
        else play.replace("_", " ").title()
    )


class NoOneBetterResolution(Model):
    action: str
    lesson: str
    actor: ActorRef
    begin_event: str
    roll_event: str
    receipt_sha256: str
    modifiers_sha256: str
    total: int
    triggered: bool
    event: str


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def permanent_no_one_better(state: GameState, actor: ActorRef) -> bool:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if sheet is None or sheet.character_id != actor.incarnation:
        return False
    runtime = sheet.girl_runtime or GirlRuntime()
    return has_rule(
        sheet.model_copy(update={"girl_runtime": runtime.model_copy(update={"learned_plays": ()})}),
        NO_ONE_BETTER,
        "CASUALTY",
    )


def _replace(state: GameState, value: LearnedPlayUse) -> None:
    sheet = state.sheets[value.actor.entity]
    runtime = sheet.girl_runtime or GirlRuntime()
    sheet.girl_runtime = runtime.model_copy(
        update={
            "learned_plays": tuple(x for x in runtime.learned_plays if x.id != value.id) + (value,)
        }
    )
    sheet.revision += 1


def grant(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    teacher: ActorRef,
    session: str,
    rule_id: str,
    event: str,
) -> str:
    if rule_id not in SUPPORTED:
        raise WorkflowError(
            "UNSUPPORTED_LEARNED_PLAY: this real counterpart Play needs its consumer"
        )
    _, book = SUPPORTED[rule_id]
    if (
        actor.kind != "pilot"
        or teacher.kind != "pilot"
        or actor == teacher
        or not session
        or not event
        or actor != current_ref(state, int(actor.entity))
        or teacher != current_ref(state, int(teacher.entity))
        or not has_rule(state.sheets[teacher.entity], rule_id, book)
    ):
        raise WorkflowError("Preserve the actual original learner, teacher and chosen source Play")
    value = LearnedPlayUse(
        id=str(uuid4()), actor=actor, teacher=teacher, session=session, rule_id=rule_id, event=event
    )
    _replace(state, value)
    return value.id


def _prove(
    game: GameService,
    c: Connection,
    state: GameState,
    value: LearnedPlayUse,
) -> None:
    from girlframe.services.m3_vatgrown_plays import prove_learned_play

    source = prove_learned_play(game, c, state, value.id)
    if any(
        getattr(source, name) != getattr(value, name)
        for name in ("id", "actor", "teacher", "session", "rule_id", "event")
    ):
        raise WorkflowError("Recover the genuine original one-use learning source")


def available(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    rule_id: str,
    action_id: str | None = None,
) -> LearnedPlayUse | None:
    """Positive canonical lesson, never another person's book or reservation."""
    if rule_id not in SUPPORTED or actor.kind != "pilot":
        return None
    sheet = state.sheets.get(actor.entity)
    if sheet is None or sheet.character_id != actor.incarnation:
        return None
    runtime = sheet.girl_runtime
    for value in runtime.learned_plays if runtime else ():
        if (
            value.actor != actor
            or value.rule_id != rule_id
            or value.rolled_event is not None
            or value.claimed_action not in (None, action_id)
        ):
            continue
        _prove(game, c, state, value)
        if value.claimed_action is not None:
            from girlframe.services.m3_handler_advancements import _history

            action = game.action(c, value.claimed_action)
            meta = action["data"].get(
                "learned_no_one_better" if rule_id == NO_ONE_BETTER else "learned_play", {}
            )
            born = _history(c, game, meta.get("event", ""))
            saved = born.sheets.get(actor.entity)
            original = saved.girl_runtime if saved else None
            if (
                str(action["actor_id"]) != actor.entity
                or action["data"]["prepared"]["play"] != SUPPORTED[rule_id][0]
                or meta.get("id") != value.id
                or meta.get("rule_id") != rule_id
                or original is None
                or value not in original.learned_plays
            ):
                raise WorkflowError("Recover this original lesson's own canonical reservation")
        return value
    return None


def claim(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    event: str,
) -> bool:
    play = action["data"]["play"]
    rule = next(
        (rule for rule, (name, _) in SUPPORTED.items() if name == play and rule != NO_ONE_BETTER),
        None,
    )
    if rule is None:
        return False
    actor = current_ref(state, int(action["actor_id"]))
    sheet = state.sheets[actor.entity]
    runtime = sheet.girl_runtime or GirlRuntime()
    # An actual native/permanent ability does not spend an unrelated temporary lesson.
    permanent = sheet.model_copy(
        update={"girl_runtime": runtime.model_copy(update={"learned_plays": ()})}
    )
    if has_rule(permanent, rule, SUPPORTED[rule][1]):
        return False
    candidates = [
        x
        for x in runtime.learned_plays
        if x.rule_id == rule
        and x.actor == actor
        and x.rolled_event is None
        and x.claimed_action in (None, action["id"])
    ]
    if not candidates:
        raise WorkflowError("This one-use Play is already spent or reserved by its actual source")
    value = candidates[0]
    _prove(game, c, state, value)
    claimed = value.model_copy(update={"claimed_action": action["id"]})
    _replace(state, claimed)
    action["data"]["learned_play"] = dict(id=value.id, event=event, rule_id=rule)
    return True


def consume(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    event: str,
) -> None:
    meta = action["data"].get("learned_play")
    if meta is None:
        return
    actor = current_ref(state, int(action["actor_id"]))
    runtime = state.sheets[actor.entity].girl_runtime
    value = (
        next((x for x in runtime.learned_plays if x.id == meta["id"]), None) if runtime else None
    )
    if value is None or value.claimed_action != action["id"]:
        raise WorkflowError("Recover the actual original reserved learned Play")
    _prove(game, c, state, value)
    if value.rolled_event is not None:
        if value.rolled_event != event:
            raise WorkflowError("Reuse the known receipt; never consume a second learned Play")
        return
    if not action["data"].get("receipt"):
        raise WorkflowError("Consume this lesson only with its actual committed roll")
    _replace(state, value.model_copy(update={"rolled_event": event}))


def release_unrolled(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    """Cancel only the original unrolled reservation after canonical recovery validation."""
    meta = action["data"].get("learned_play")
    if meta is None:
        return False
    if action["data"].get("receipt"):
        raise WorkflowError("A committed learned Play cannot be refunded.")
    actor = current_ref(state, int(action["actor_id"]))
    runtime = state.sheets[actor.entity].girl_runtime
    value = (
        next((x for x in runtime.learned_plays if x.id == meta["id"]), None) if runtime else None
    )
    if (
        value is None
        or value.actor != actor
        or value.claimed_action != action["id"]
        or value.rolled_event is not None
    ):
        raise WorkflowError("Recover this original unrolled learning reservation.")
    _prove(game, c, state, value)
    _replace(state, value.model_copy(update={"claimed_action": None}))
    return True


def reserve_triggered(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> bool:
    """Reserve the one finite rider; ordinary Assault needs no lesson entitlement."""
    if action["data"]["play"] != "all_out_assault" or not action["data"].get("battle"):
        return False
    actor = ActorRef.model_validate(action["data"]["battle"]["actor"])
    if actor.kind != "pilot" or permanent_no_one_better(state, actor):
        return False
    value = available(game, c, state, actor, NO_ONE_BETTER, action["id"])
    if value is None:
        return False
    if actor != current_ref(state, int(action["actor_id"])) or not event:
        raise WorkflowError("Reserve only the actual original learner's declared Assault")
    if action["data"].get("learned_no_one_better"):
        raise WorkflowError("Reuse this Assault's original one-use rider reservation")
    from girlframe.engine.m3_battle import resource_sha
    from girlframe.services.m3_actors import profiles

    bound = profiles(c, game.store.campaign_id)
    before = resource_sha(state, actor, bound)
    _replace(state, value.model_copy(update={"claimed_action": action["id"]}))
    action["data"]["learned_no_one_better"] = dict(
        id=value.id,
        rule_id=NO_ONE_BETTER,
        event=event,
        resource_before=before,
        resource_after=resource_sha(state, actor, bound),
    )
    return True


def _triggered_reservation(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> LearnedPlayUse:
    from girlframe.services.m3_handler_advancements import _history

    meta = action["data"]["learned_no_one_better"]
    actor = ActorRef.model_validate(action["data"]["battle"]["actor"])
    born = _history(c, game, meta["event"])
    sheet = state.sheets.get(actor.entity)
    original = born.sheets.get(actor.entity)
    current = sheet.girl_runtime if sheet else None
    runtime = original.girl_runtime if original else None
    value = (
        next((x for x in current.learned_plays if x.id == meta["id"]), None) if current else None
    )
    reservation = (
        next((x for x in runtime.learned_plays if x.id == meta["id"]), None) if runtime else None
    )
    confirmed = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == meta["event"],
            )
        )
        .mappings()
        .first()
    )
    if (
        value is None
        or reservation is None
        or confirmed is None
        or confirmed["kind"] != "m3.play_confirmed"
        or json.loads(confirmed["payload_json"]).get("action_id") != action["id"]
        or action["data"]["play"] != "all_out_assault"
        or action["data"]["prepared"]["play"] != "all_out_assault"
        or meta.get("rule_id") != NO_ONE_BETTER
        or actor.kind != "pilot"
        or actor.entity != str(action["actor_id"])
        or value.actor != actor
        or value.rule_id != NO_ONE_BETTER
        or reservation
        != value.model_copy(update={"claimed_action": action["id"], "rolled_event": None})
    ):
        raise WorkflowError("Recover this exact original lesson's canonical Assault reservation")
    _prove(game, c, born, reservation)
    _prove(game, c, state, value)
    return value


def pre_roll_triggered(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    if not action["data"].get("learned_no_one_better"):
        return
    value = _triggered_reservation(game, c, state, action)
    if (
        value.actor != current_ref(state, int(action["actor_id"]))
        or value.claimed_action != action["id"]
        or value.rolled_event is not None
        or action["data"]["learned_no_one_better"].get("resolved_event")
        or action["data"].get("receipt")
    ):
        raise WorkflowError("Use only this original unrolled learner reservation before costs")


def triggered_resource_sha(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    actor: ActorRef,
    original: str,
) -> str:
    """Only the exact canonical reservation may change its own pre-roll resource hash."""
    meta = action["data"].get("learned_no_one_better")
    if meta is None or actor.model_dump(mode="json") != action["data"]["battle"]["actor"]:
        return original
    from girlframe.engine.m3_battle import resource_sha
    from girlframe.services.m3_actor_history import snapshot_profiles
    from girlframe.services.m3_handler_advancements import _history

    _triggered_reservation(game, c, state, action)
    born = _history(c, game, meta["event"])
    actual = resource_sha(born, actor, snapshot_profiles(c, game.store.campaign_id, born))
    if meta.get("resource_before") != original or meta.get("resource_after") != actual:
        raise WorkflowError(
            "Preserve the original declaration and exact reservation resource change"
        )
    return str(actual)


def release_triggered_unrolled(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    if not action["data"].get("learned_no_one_better"):
        return False
    pre_roll_triggered(game, c, state, action)
    value = _triggered_reservation(game, c, state, action)
    _replace(state, value.model_copy(update={"claimed_action": None}))
    return True


def _resolution(state: GameState, action: str) -> NoOneBetterResolution | None:
    rows = [
        x
        for x in state.facts
        if x.get("kind") == "learned_no_one_better_resolution" and x.get("id") == action
    ]
    if not rows:
        return None
    if len(rows) != 1:
        raise WorkflowError("Preserve one actual final rider result per original Assault")
    return NoOneBetterResolution.model_validate_json(rows[0]["body"])


def resolve_no_one_better(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> bool:
    """Stage only after all actual modifiers; canonical proof is required on later use."""
    meta = action["data"].get("learned_no_one_better")
    if meta is None:
        return False
    if meta.get("resolved_event"):
        if meta.get("triggered"):
            return consumed_no_one_better(game, c, state, action)
        _prove_resolution(game, c, state, action)
        return False
    value = _triggered_reservation(game, c, state, action)
    if value.claimed_action != action["id"] or value.rolled_event is not None or not event:
        raise WorkflowError("Resolve only this exact held one-use Assault rider")
    if game.pending(c, action["id"]):
        raise WorkflowError("Finish actual Tag choices before resolving the high Assault trigger")
    from girlframe.services.m3_dose_up import _roll_source

    rolled, total = _roll_source(game, c, action)
    resolution = NoOneBetterResolution(
        action=action["id"],
        lesson=value.id,
        actor=value.actor,
        begin_event=meta["event"],
        roll_event=rolled,
        receipt_sha256=_digest(action["data"]["receipt"]),
        modifiers_sha256=_digest(action["data"]["modifiers"]),
        total=total,
        triggered=total >= 11,
        event=event,
    )
    if _resolution(state, action["id"]) is not None:
        raise WorkflowError("This actual Assault rider already has its original resolution")
    _replace(
        state,
        value.model_copy(
            update=({"rolled_event": event} if resolution.triggered else {"claimed_action": None})
        ),
    )
    meta.update(
        resolved_event=event,
        roll_event=rolled,
        final_total=total,
        triggered=resolution.triggered,
    )
    state.facts.append(
        dict(
            kind="learned_no_one_better_resolution",
            id=action["id"],
            body=resolution.model_dump_json(),
        )
    )
    return resolution.triggered


def _prove_resolution(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> NoOneBetterResolution:
    from girlframe.services.m3_dose_up import _roll_source
    from girlframe.services.m3_handler_advancements import _history

    meta = action["data"]["learned_no_one_better"]
    saved = _resolution(state, action["id"])
    if saved is None or saved.event != meta.get("resolved_event"):
        raise WorkflowError("Recover the actual final No One Better trigger decision")
    born = _history(c, game, saved.event)
    rolled, total = _roll_source(game, c, action)
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == saved.event,
            )
        )
        .mappings()
        .first()
    )
    if (
        _resolution(born, action["id"]) != saved
        or event is None
        or event["kind"] not in ("m2.choice_resolved", "m3.choice_resolved")
        or json.loads(event["payload_json"]).get("action_id") != action["id"]
        or saved.lesson != meta["id"]
        or saved.begin_event != meta["event"]
        or saved.roll_event != rolled
        or saved.total != total
        or saved.receipt_sha256 != _digest(action["data"]["receipt"])
        or saved.modifiers_sha256 != _digest(action["data"]["modifiers"])
        or saved.triggered != (total >= 11)
        or saved.triggered != meta.get("triggered")
        or meta.get("roll_event") != rolled
        or meta.get("final_total") != total
    ):
        raise WorkflowError("Preserve the actual canonical Assault receipt and final trigger")
    at_resolution = _triggered_reservation(game, c, born, action)
    if saved.triggered:
        if (
            at_resolution.claimed_action != action["id"]
            or at_resolution.rolled_event != saved.event
        ):
            raise WorkflowError("Only this exact high Assault consumed this source lesson")
    elif at_resolution.claimed_action is not None or at_resolution.rolled_event is not None:
        raise WorkflowError("A lower actual Assault releases only its own unused reservation")
    return saved


def consumed_no_one_better(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    if not action["data"].get("learned_no_one_better"):
        return False
    saved = _prove_resolution(game, c, state, action)
    if not saved.triggered:
        return False
    current = _triggered_reservation(game, c, state, action)
    if current.claimed_action != action["id"] or current.rolled_event != saved.event:
        raise WorkflowError("Preserve the actual spent lesson for this held high Assault")
    return True


def prove_consumed(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    rule_id: str,
    roll_event: str,
) -> bool:
    """Prove this exact spent lesson; never restore its admission for another roll."""
    meta = action["data"].get("learned_play")
    if meta is None:
        return False
    from girlframe.services.m3_handler_advancements import _history

    rolled = _history(c, game, roll_event)
    claimed = _history(c, game, meta["event"])
    actor = current_ref(rolled, int(action["actor_id"]))

    def saved(source: GameState) -> LearnedPlayUse | None:
        sheet = source.sheets.get(actor.entity)
        runtime = sheet.girl_runtime if sheet else None
        return (
            next((x for x in runtime.learned_plays if x.id == meta["id"]), None)
            if runtime
            else None
        )

    value, birth, reservation = saved(state), saved(rolled), saved(claimed)
    receipt = (
        c.execute(
            sa.select(t.m2["m2_receipts"]).where(
                t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_receipts"].c.action_id == action["id"],
            )
        )
        .mappings()
        .first()
    )
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id, t.events.c.id == roll_event
            )
        )
        .mappings()
        .first()
    )
    if (
        rule_id not in SUPPORTED
        or meta.get("rule_id") != rule_id
        or action["data"]["prepared"]["play"] != SUPPORTED[rule_id][0]
        or value is None
        or birth is None
        or reservation is None
        or value != birth
        or value.actor != actor
        or value.rule_id != rule_id
        or value.claimed_action != action["id"]
        or value.rolled_event != roll_event
        or reservation != value.model_copy(update={"rolled_event": None})
        or receipt is None
        or json.loads(receipt["body_json"]) != action["data"].get("receipt")
        or event is None
        or event["kind"] not in ("m2.rolled", "m3.rolled")
        or event["actor_id"] != str(action["actor_id"])
        or json.loads(event["payload_json"]).get("action_id") != action["id"]
        or json.loads(event["payload_json"]).get("receipt_id") != receipt["id"]
    ):
        raise WorkflowError(
            "Recover this original lesson's actual reservation and consumed receipt"
        )
    _prove(game, c, rolled, value)
    return True
