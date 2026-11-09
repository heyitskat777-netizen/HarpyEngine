"""Finite actual learned-Play admission and one-roll consumption; source effects stay explicit."""

import hashlib
import json
from typing import Any, Literal
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import Connection

from girlframe.database import tables as t
from girlframe.engine.m2 import ChoiceAnswer, GameState, TagState
from girlframe.engine.m3_actor_bonds import current_ref
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_girl_runtime_state import GirlRuntime, has_rule
from girlframe.engine.m3_learned_play_state import LearnedPlayUse
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError

NO_ONE_BETTER = "girl.casualty.no-one-better"
BEAUTIFUL = "girl.princess.objectively-beautiful"
ITCHING = "girl.alpha.itching-for-a-fight"
ELDER = "girl.oldgen.elder-bitch"
KEEP_RIDERS = (BEAUTIFUL, ITCHING, ELDER)
SUPPORTED = {
    "girl.alpha.brutalize": ("brutalize", "ALPHA"),
    "girl.stim-blissed.dose-up": ("dose_up", "STIM-BLISSED"),
    "girl.oldgen.old-dog-new-pups": ("old_dog_new_pups", "OLDGEN"),
    "girl.newgirl.easy-target": ("easy_target", "NEWGIRL"),
    "girl.mockingbird.bad-at-being-a-person": ("mockingbird_person", "MOCKINGBIRD"),
    NO_ONE_BETTER: ("all_out_assault", "CASUALTY"),
    BEAUTIFUL: ("keep_your_head", "PRINCESS"),
    ITCHING: ("keep_your_head", "ALPHA"),
    ELDER: ("keep_your_head", "OLDGEN"),
}


def lesson_label(rule_id: str, play: str) -> str:
    if rule_id in KEEP_RIDERS:
        return {
            BEAUTIFUL: "Objectively Beautiful (Keep or own-Tag Flirt)",
            ITCHING: "Itching for a Fight (Keep: vicious enough)",
            ELDER: "Elder Bitch (Keep: additional experienced choice)",
        }[rule_id]
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


class KeepRiderUse(Model):
    action: str
    lesson: str
    rule_id: str
    actor: ActorRef
    begin_event: str
    roll_event: str
    receipt_sha256: str
    kind: Literal["keep", "beautiful_tag", "unused_flirt"]
    event: str
    tag: str | None = None
    winning_choice: str | None = None
    closure_choice: str | None = None
    amount: int | None = None


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
            key = (
                "learned_no_one_better"
                if rule_id == NO_ONE_BETTER
                else "learned_keep_rider"
                if rule_id in KEEP_RIDERS
                else "learned_play"
            )
            meta = action["data"].get(key, {})
            born = _history(c, game, meta.get("event", ""))
            saved = born.sheets.get(actor.entity)
            original = saved.girl_runtime if saved else None
            if (
                str(action["actor_id"]) != actor.entity
                or action["data"]["prepared"]["play"]
                not in (
                    ("keep_your_head", "flirt")
                    if rule_id == BEAUTIFUL
                    else (SUPPORTED[rule_id][0],)
                )
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
        (
            rule
            for rule, (name, _) in SUPPORTED.items()
            if name == play and rule not in (NO_ONE_BETTER, *KEEP_RIDERS)
        ),
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


def _permanent_keep_rider(state: GameState, actor: ActorRef, rule: str) -> bool:
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if sheet is None or sheet.character_id != actor.incarnation:
        return False
    runtime = sheet.girl_runtime or GirlRuntime()
    return has_rule(
        sheet.model_copy(update={"girl_runtime": runtime.model_copy(update={"learned_plays": ()})}),
        rule,
        SUPPORTED[rule][1],
    )


def prepare_keep_riders(
    game: GameService, c: Connection, state: GameState, actor: ActorRef, play: str
) -> tuple[dict[str, str], ...]:
    if actor.kind != "pilot" or play not in ("keep_your_head", "flirt"):
        return ()
    sheet = state.sheets.get(actor.entity)
    if sheet is None or sheet.character_id != actor.incarnation:
        return ()
    result = []
    for value in sheet.girl_runtime.learned_plays if sheet.girl_runtime else ():
        if (
            value.actor != actor
            or value.rule_id not in KEEP_RIDERS
            or value.rolled_event is not None
            or value.claimed_action is not None
            or (play == "flirt" and value.rule_id != BEAUTIFUL)
            or _permanent_keep_rider(state, actor, value.rule_id)
        ):
            continue
        _prove(game, c, state, value)
        result.append(
            dict(
                id=value.id,
                rule_id=value.rule_id,
                label=lesson_label(value.rule_id, play) + " — " + value.id[:8],
            )
        )
    return tuple(result)


def reserve_keep_rider(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> bool:
    identity = action["data"]["prepared"].get("learned_keep_rider")
    if identity is None:
        return False
    actor = current_ref(state, int(action["actor_id"]))
    chosen = next(
        (
            x
            for x in prepare_keep_riders(game, c, state, actor, action["data"]["play"])
            if x["id"] == identity
        ),
        None,
    )
    if chosen is None or action["data"].get("learned_keep_rider") or not event:
        raise WorkflowError("Select exactly one actual available lesson for this owned Play")
    sheet = state.sheets[actor.entity]
    assert sheet.girl_runtime is not None
    value = next(x for x in sheet.girl_runtime.learned_plays if x.id == identity)
    _replace(state, value.model_copy(update={"claimed_action": action["id"]}))
    action["data"]["learned_keep_rider"] = dict(
        id=identity,
        rule_id=value.rule_id,
        event=event,
        play=action["data"]["play"],
    )
    return True


def _keep_reservation(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> LearnedPlayUse:
    from girlframe.services.m3_handler_advancements import _history

    meta = action["data"]["learned_keep_rider"]
    born = _history(c, game, meta["event"])
    actor = current_ref(born, int(action["actor_id"]))
    sheet = state.sheets.get(actor.entity)
    initial = born.sheets[actor.entity].girl_runtime
    runtime = sheet.girl_runtime if sheet and sheet.character_id == actor.incarnation else None
    value = (
        next((x for x in runtime.learned_plays if x.id == meta["id"]), None) if runtime else None
    )
    original = (
        next((x for x in initial.learned_plays if x.id == meta["id"]), None) if initial else None
    )
    event = (
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
        or original is None
        or event is None
        or value.actor != actor
        or actor.kind != "pilot"
        or value.rule_id not in KEEP_RIDERS
        or value.rule_id != meta.get("rule_id")
        or action["data"]["prepared"].get("learned_keep_rider") != value.id
        or meta.get("play") != action["data"]["play"]
        or action["data"]["play"]
        not in (("keep_your_head", "flirt") if value.rule_id == BEAUTIFUL else ("keep_your_head",))
        or event["kind"] not in ("m2.play_confirmed", "m3.play_confirmed")
        or json.loads(event["payload_json"]).get("action_id") != action["id"]
        or original
        != value.model_copy(update={"claimed_action": action["id"], "rolled_event": None})
    ):
        raise WorkflowError("Recover this original actor's exact selected lesson reservation")
    _prove(game, c, born, original)
    _prove(game, c, state, value)
    return value


def pre_roll_keep_rider(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> None:
    if not action["data"].get("learned_keep_rider"):
        return
    value = _keep_reservation(game, c, state, action)
    if (
        value.actor != current_ref(state, int(action["actor_id"]))
        or value.claimed_action != action["id"]
        or value.rolled_event is not None
        or action["data"].get("receipt")
        or action["data"]["learned_keep_rider"].get("resolved_event")
    ):
        raise WorkflowError("Use only the original selected unrolled lesson before spending")


def release_keep_rider_unrolled(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> bool:
    if not action["data"].get("learned_keep_rider"):
        return False
    pre_roll_keep_rider(game, c, state, action)
    value = _keep_reservation(game, c, state, action)
    _replace(state, value.model_copy(update={"claimed_action": None}))
    return True


def _keep_receipt(game: GameService, c: Connection, action: dict[str, Any]) -> str:
    raw = c.scalar(
        sa.select(t.m2["m2_receipts"].c.body_json).where(
            t.m2["m2_receipts"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_receipts"].c.action_id == action["id"],
        )
    )
    if raw is None or json.loads(raw) != action["data"].get("receipt"):
        raise WorkflowError("Preserve the real selected lesson's actual roll receipt")
    return _digest(action["data"]["receipt"])


def _keep_raw_roll(game: GameService, c: Connection, action: dict[str, Any]) -> str:
    _keep_receipt(game, c, action)
    author = int(action["actor_id"])
    if action["data"].get("princess_child"):
        from girlframe.services.m2_state import load_state
        from girlframe.services.m3_princess_sex import child_author

        actual_author = child_author(game, c, load_state(c, game.store.campaign_id), action)
        if actual_author is None:
            raise WorkflowError("Prove the actual directed Play's original human author")
        author = actual_author
    event = c.scalar(
        sa.select(t.events.c.id).where(
            t.events.c.campaign_id == game.store.campaign_id,
            t.events.c.kind.in_(("m2.rolled", "m3.rolled")),
            t.events.c.actor_id == str(author),
            sa.func.json_extract(t.events.c.payload_json, "$.action_id") == action["id"],
            sa.func.json_extract(t.events.c.payload_json, "$.receipt_id")
            == action["data"]["receipt"]["id"],
        )
    )
    if event is None:
        raise WorkflowError("Recover this selected lesson's canonical original roll")
    return str(event)


def _keep_use(state: GameState, action: str) -> KeepRiderUse | None:
    rows = [
        x
        for x in state.facts
        if x.get("kind") == "learned_keep_rider_use" and x.get("id") == action
    ]
    if len(rows) > 1:
        raise WorkflowError("One selected lesson has one actual source use per Play")
    return KeepRiderUse.model_validate_json(rows[0]["body"]) if rows else None


def _record_keep_use(
    state: GameState, action: dict[str, Any], value: LearnedPlayUse, record: KeepRiderUse
) -> None:
    if (
        _keep_use(state, action["id"]) is not None
        or value.claimed_action != action["id"]
        or value.rolled_event is not None
    ):
        raise WorkflowError("Preserve the original actual lesson use; never spend twice")
    used = record.kind != "unused_flirt"
    _replace(
        state,
        value.model_copy(
            update=({"rolled_event": record.event} if used else {"claimed_action": None})
        ),
    )
    meta = action["data"]["learned_keep_rider"]
    meta.update(resolved_event=record.event, roll_event=record.roll_event, used=used)
    if record.tag is not None:
        meta.update(tag=record.tag, choice=record.winning_choice, amount=record.amount)
    state.facts.append(
        dict(kind="learned_keep_rider_use", id=action["id"], body=record.model_dump_json())
    )


def consume_keep_rider(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], roll_event: str
) -> None:
    meta = action["data"].get("learned_keep_rider")
    if meta is None or action["data"]["play"] != "keep_your_head":
        return
    value = _keep_reservation(game, c, state, action)
    if value.claimed_action != action["id"] or value.rolled_event is not None or not roll_event:
        raise WorkflowError("Spend only this actual selected Keep lesson's committed receipt")
    _record_keep_use(
        state,
        action,
        value,
        KeepRiderUse(
            action=action["id"],
            lesson=value.id,
            rule_id=value.rule_id,
            actor=value.actor,
            begin_event=meta["event"],
            roll_event=roll_event,
            receipt_sha256=_keep_receipt(game, c, action),
            kind="keep",
            event=roll_event,
        ),
    )


def active_keep_rider_rule(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> str | None:
    meta = action["data"].get("learned_keep_rider")
    if meta is None:
        return None
    if meta.get("resolved_event"):
        return keep_rider_rule(game, c, state, action) if meta["play"] == "keep_your_head" else None
    value = _keep_reservation(game, c, state, action)
    if (
        value.claimed_action != action["id"]
        or value.rolled_event is not None
        or value.actor != current_ref(state, int(action["actor_id"]))
        or action["data"]["play"] != "flirt"
        or value.rule_id != BEAUTIFUL
    ):
        raise WorkflowError("Prove this actual original learner's reserved Beautiful Flirt")
    _keep_raw_roll(game, c, action)
    return value.rule_id


def apply_beautiful_mark(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    tag: TagState,
    event: str,
    *,
    choice: str,
) -> None:
    if active_keep_rider_rule(game, c, state, action) != BEAUTIFUL:
        raise WorkflowError("Only the selected actual Beautiful lesson grants this self-mark")
    value = _keep_reservation(game, c, state, action)
    marker = action["data"].get("tag_marker_applied", {})
    owned = next((x for x in state.sheets[value.actor.entity].tags if x.id == tag.id), None)
    modifiers = [
        x
        for x in action["data"]["modifiers"]
        if x.get("source") == "girl_tag"
        and x.get("tag") == tag.id
        and x.get("actor") == int(value.actor.entity)
    ]
    closing = (
        c.execute(
            sa.select(t.m2["m2_choices"]).where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.id == choice,
            )
        )
        .mappings()
        .first()
    )
    if (
        owned != tag
        or not tag.marked
        or tag.scene_used != action["scene_id"]
        or marker.get("actor") != value.actor.model_dump(mode="json")
        or marker.get("controller") != int(value.actor.entity)
        or marker.get("tag") != tag.id
        or len(modifiers) != 1
        or marker.get("amount") != modifiers[0]["amount"]
        or closing is None
        or closing["action_id"] != action["id"]
        or closing["state"] != "answered"
        or closing["kind"] not in ("tag_window", "tag_marker_agreement")
        or action["data"].get("response_event") != event
    ):
        raise WorkflowError("Spend Beautiful only on the actual winning owned Tag adjustment")
    owner = str(value.actor.entity)
    proposed = action["data"].get("choices", {}).get("tag_window:" + owner)
    answer = ChoiceAnswer.model_validate_json(json.dumps(proposed)) if proposed else None
    if answer is None or answer.denied != (tag.id,) or answer.number not in (-1, 1):
        raise WorkflowError("Preserve the actual learner's own Tag proposal")
    winning: str | None
    if closing["kind"] == "tag_window" and closing["actor_id"] == owner:
        winning = choice
    else:
        choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
        rows = c.execute(
            sa.select(choices.c.id, responses.c.answer_json)
            .join(
                responses,
                sa.and_(
                    responses.c.campaign_id == choices.c.campaign_id,
                    responses.c.choice_id == choices.c.id,
                ),
            )
            .join(t.events, t.events.c.id == responses.c.event_id)
            .where(
                choices.c.campaign_id == game.store.campaign_id,
                choices.c.action_id == action["id"],
                choices.c.actor_id == owner,
                choices.c.kind == "tag_window",
            )
            .order_by(t.events.c.seq.desc())
        ).all()
        winning = next(
            (x.id for x in rows if ChoiceAnswer.model_validate_json(x.answer_json) == answer), None
        )
        if winning is None:
            raise WorkflowError("Recover the original human's actual winning Tag response")
    _record_keep_use(
        state,
        action,
        value,
        KeepRiderUse(
            action=action["id"],
            lesson=value.id,
            rule_id=BEAUTIFUL,
            actor=value.actor,
            begin_event=action["data"]["learned_keep_rider"]["event"],
            roll_event=_keep_raw_roll(game, c, action),
            receipt_sha256=_keep_receipt(game, c, action),
            kind="beautiful_tag",
            event=event,
            tag=tag.id,
            winning_choice=winning,
            closure_choice=choice,
            amount=int(marker["amount"]),
        ),
    )


def finish_beautiful_flirt(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], event: str
) -> None:
    meta = action["data"].get("learned_keep_rider")
    if meta is None or meta["play"] != "flirt" or meta.get("resolved_event"):
        return
    if game.pending(c, action["id"]):
        return
    value = _keep_reservation(game, c, state, action)
    if value.rule_id != BEAUTIFUL or not event:
        raise WorkflowError("Release only this actual unused Beautiful Flirt reservation")
    _record_keep_use(
        state,
        action,
        value,
        KeepRiderUse(
            action=action["id"],
            lesson=value.id,
            rule_id=BEAUTIFUL,
            actor=value.actor,
            begin_event=meta["event"],
            roll_event=_keep_raw_roll(game, c, action),
            receipt_sha256=_keep_receipt(game, c, action),
            kind="unused_flirt",
            event=event,
        ),
    )


def keep_rider_rule(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> str | None:
    meta = action["data"].get("learned_keep_rider")
    if meta is None:
        return None
    from girlframe.services.m3_handler_advancements import _history

    saved = _keep_use(state, action["id"])
    if saved is None or saved.event != meta.get("resolved_event"):
        raise WorkflowError("Recover the real selected lesson's source use")
    born = _history(c, game, saved.event)
    value = _keep_reservation(game, c, born, action)
    actual = _keep_reservation(game, c, state, action)
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
    used = saved.kind != "unused_flirt"
    if (
        _keep_use(born, action["id"]) != saved
        or event is None
        or json.loads(event["payload_json"]).get("action_id") != action["id"]
        or saved.lesson != value.id
        or saved.rule_id != value.rule_id
        or saved.actor != value.actor
        or saved.begin_event != meta["event"]
        or saved.roll_event != _keep_raw_roll(game, c, action)
        or saved.receipt_sha256 != _keep_receipt(game, c, action)
        or meta.get("roll_event") != saved.roll_event
        or meta.get("used") != used
        or (used and (value.claimed_action != action["id"] or value.rolled_event != saved.event))
        or (not used and (value.claimed_action is not None or value.rolled_event is not None))
    ):
        raise WorkflowError("Preserve the actual original lesson, source receipt and use event")
    if saved.kind == "keep":
        if action["data"]["play"] != "keep_your_head" or saved.event != saved.roll_event:
            raise WorkflowError("Use the exact selected lesson's actual Keep roll")
    else:
        if (
            action["data"]["play"] != "flirt"
            or value.rule_id != BEAUTIFUL
            or event["kind"] not in ("m2.choice_resolved", "m3.choice_resolved")
        ):
            raise WorkflowError("Use the actual selected Beautiful Flirt source")
    if saved.kind == "beautiful_tag":
        choices, responses = t.m2["m2_choices"], t.m2["m2_responses"]
        winner = (
            c.execute(
                sa.select(
                    choices,
                    responses.c.answer_json,
                    responses.c.actor_id.label("response_actor"),
                    responses.c.event_id.label("response_event"),
                )
                .join(
                    responses,
                    sa.and_(
                        responses.c.choice_id == choices.c.id,
                        responses.c.campaign_id == choices.c.campaign_id,
                    ),
                )
                .where(
                    choices.c.campaign_id == game.store.campaign_id,
                    choices.c.id == saved.winning_choice,
                )
            )
            .mappings()
            .first()
        )
        closure = (
            c.execute(
                sa.select(responses).where(
                    responses.c.campaign_id == game.store.campaign_id,
                    responses.c.choice_id == saved.closure_choice,
                )
            )
            .mappings()
            .first()
        )
        tag = next((x for x in born.sheets[value.actor.entity].tags if x.id == saved.tag), None)
        proposal = ChoiceAnswer.model_validate_json(winner["answer_json"]) if winner else None
        if (
            winner is None
            or winner["action_id"] != action["id"]
            or winner["kind"] != "tag_window"
            or winner["actor_id"] != value.actor.entity
            or proposal is None
            or proposal.denied != (saved.tag,)
            or closure is None
            or closure["event_id"] != saved.event
            or closure["actor_id"] != event["actor_id"]
            or json.loads(event["payload_json"]).get("choice_id") != saved.closure_choice
            or tag is None
            or not tag.marked
            or tag.scene_used != action["scene_id"]
            or meta.get("tag") != saved.tag
            or meta.get("choice") != saved.winning_choice
            or meta.get("amount") != saved.amount
            or not any(
                x.get("source") == "girl_tag"
                and x.get("tag") == saved.tag
                and x.get("actor") == int(value.actor.entity)
                and x.get("amount") == saved.amount
                for x in action["data"]["modifiers"]
            )
        ):
            raise WorkflowError(
                "Prove the real winning own-Tag response and actual applied modifier"
            )
        author = int(value.actor.entity)
        if action["data"].get("princess_child"):
            from girlframe.services.m3_princess_sex import prove_response_author

            directed_author = prove_response_author(
                game, c, born, action, dict(winner), winner["response_event"]
            )
            if directed_author is None:
                raise WorkflowError("Prove the actual Princess-authored original Tag response")
            author = directed_author
        winner_event = (
            c.execute(
                sa.select(t.events).where(
                    t.events.c.campaign_id == game.store.campaign_id,
                    t.events.c.id == winner["response_event"],
                )
            )
            .mappings()
            .first()
        )
        if (
            winner["response_actor"] != str(author)
            or winner_event is None
            or winner_event["actor_id"] != str(author)
            or winner_event["kind"] not in ("m2.choice_resolved", "m3.choice_resolved")
            or json.loads(winner_event["payload_json"]).get("action_id") != action["id"]
        ):
            raise WorkflowError("Preserve the original real human's winning Tag response")
    if not used:
        return None
    if actual.claimed_action != action["id"] or actual.rolled_event != saved.event:
        raise WorkflowError("Preserve the selected spent lesson for its own held outcome")
    return value.rule_id


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
