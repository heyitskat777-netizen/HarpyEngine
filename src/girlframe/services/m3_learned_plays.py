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
from girlframe.engine.m3_learned_play_state import (
    CallLessonUse,
    DailyLessonUse,
    DefensiveRiskUse,
    HoundStatusUse,
    LearnedPlayUse,
    PsychePermit,
    RiskLessonUse,
    call_lesson_uses,
    daily_lesson_uses,
    defensive_risk_uses,
    hound_status_uses,
    learned_sex_links,
    put_defensive_risk,
    put_hound_status,
    put_risk_lesson,
    risk_lesson_uses,
    risk_ward,
)
from girlframe.services.m2_game import GameService
from girlframe.services.onboarding import WorkflowError

NO_ONE_BETTER = "girl.casualty.no-one-better"
BEAUTIFUL = "girl.princess.objectively-beautiful"
ITCHING = "girl.alpha.itching-for-a-fight"
ELDER = "girl.oldgen.elder-bitch"
HOUND = "girl.alpha.nothing-more-than-a-hound"
RISK = "girl.mockingbird.risk-factor"
CALL = "girl.mockingbird.call-of-the-void"
SHOW_DOG = "girl.princess.show-dog"
PSYCHE = "girl.stim-blissed.disposable-psyche"
DOLL = "girl.vatgrown.unassuming-doll"
SEX_LESSONS = {
    "girl.princess.sex-play": "PRINCESS",
    "girl.stim-blissed.sex-play": "STIM-BLISSED",
    "girl.alpha.sex-play": "ALPHA",
    "girl.mockingbird.sex-play": "MOCKINGBIRD",
}
DAILY: dict[
    Literal["girl.princess.show-dog", "girl.stim-blissed.disposable-psyche"], tuple[str, str]
] = {
    "girl.princess.show-dog": ("learned_show_dog", "PRINCESS"),
    "girl.stim-blissed.disposable-psyche": ("learned_psyche", "STIM-BLISSED"),
}
OFF_DUTY = ("go_off_duty", "void_observation")
CALL_OPTIONS = ("call_reclassify_assets", "call_cockpit_guest", "call_gorgon_relay")
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
    if rule_id in SEX_LESSONS:
        return SEX_LESSONS[rule_id].replace("-", " ").title() + " Sex (one voluntary source)"
    if rule_id in (SHOW_DOG, PSYCHE, DOLL):
        return {
            SHOW_DOG: "Show Dog (one actual Off-Duty source)",
            PSYCHE: "Disposable Psyche (one actual mark or Off-Duty source)",
            DOLL: "Unassuming Doll (already native; acquisition history)",
        }[rule_id]
    if rule_id == CALL:
        return "Call of the Void (one actual Dive's extra options)"
    if rule_id == RISK:
        return "Risk Factor (paid shift and its own Void ward)"
    if rule_id == HOUND:
        return "Nothing More Than a Hound (actual Dog Status +/-1)"
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


def lesson_book(rule_id: str) -> str | None:
    """The finite Status lesson has no invented underlying Play ID."""
    if rule_id in (RISK, CALL):
        return "MOCKINGBIRD"
    if rule_id in SEX_LESSONS:
        return SEX_LESSONS[rule_id]
    if rule_id in DAILY:
        return DAILY[rule_id][1]
    if rule_id == DOLL:
        return "VATGROWN"
    return "ALPHA" if rule_id == HOUND else SUPPORTED[rule_id][1] if rule_id in SUPPORTED else None


def teacher_lessons(sheet: Any) -> tuple[dict[str, str], ...]:
    result = [
        dict(id=rule, label=lesson_label(rule, play))
        for rule, (play, book) in SUPPORTED.items()
        if sheet.girl == book and has_rule(sheet, rule, book)
    ]
    if sheet.girl == "ALPHA" and has_rule(sheet, HOUND, "ALPHA"):
        result.append(dict(id=HOUND, label=lesson_label(HOUND, "")))
    if sheet.girl == "MOCKINGBIRD" and has_rule(sheet, RISK, "MOCKINGBIRD"):
        result.append(dict(id=RISK, label=lesson_label(RISK, "")))
    if sheet.girl == "MOCKINGBIRD" and has_rule(sheet, CALL, "MOCKINGBIRD"):
        result.append(dict(id=CALL, label=lesson_label(CALL, "")))
    for rule, book in ((SHOW_DOG, "PRINCESS"), (PSYCHE, "STIM-BLISSED"), (DOLL, "VATGROWN")):
        if sheet.girl == book and has_rule(sheet, rule, book):
            result.append(dict(id=rule, label=lesson_label(rule, "")))
    for rule, book in SEX_LESSONS.items():
        if sheet.girl == book and has_rule(sheet, rule, book):
            result.append(dict(id=rule, label=lesson_label(rule, "")))
    return tuple(result)


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
    book = lesson_book(rule_id)
    if book is None:
        raise WorkflowError(
            "UNSUPPORTED_LEARNED_PLAY: this real counterpart Play needs its consumer"
        )
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
    if lesson_book(rule_id) is None or actor.kind != "pilot":
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
        if rule_id in SEX_LESSONS and any(
            x.lesson == value.id and x.released_event is None for x in learned_sex_links(state)
        ):
            continue
        _prove(game, c, state, value)
        if value.claimed_action is not None:
            if rule_id in (HOUND, RISK, CALL, SHOW_DOG, PSYCHE, DOLL):
                raise WorkflowError("This lesson is spent only by its actual owned source choice")
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


def _hound_candidate(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], owner: int
) -> LearnedPlayUse | None:
    if str(owner) != str(action["actor_id"]):
        return None
    sheet = state.sheets.get(str(owner))
    if sheet is None or not sheet.character_id:
        return None
    actor = ActorRef(kind="pilot", entity=str(owner), incarnation=sheet.character_id)
    from girlframe.engine.m3_intracadre_marriage import is_dog

    runtime = sheet.girl_runtime or GirlRuntime()
    native = sheet.model_copy(
        update={"girl_runtime": runtime.model_copy(update={"learned_plays": ()})}
    )
    if (
        action["data"].get("character_ids", {}).get(str(owner)) != actor.incarnation
        or has_rule(native, HOUND, "ALPHA")
        or sheet.status_marked
        or not is_dog(state, owner)
        or any(x.actor == actor and x.clear_reason is None for x in hound_status_uses(state))
    ):
        return None
    return available(game, c, state, actor, HOUND)


def hound_status_available(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any], owner: int
) -> bool:
    value = _hound_candidate(game, c, state, action, owner)
    if value is None:
        return False
    _keep_raw_roll(game, c, action)
    return True


def use_hound_status(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    owner: int,
    answer: ChoiceAnswer,
    event: str,
    *,
    choice: str,
) -> bool:
    if answer.fields.get("status", "0") == "0":
        return False
    value = _hound_candidate(game, c, state, action, owner)
    if value is None:
        return False
    requests = t.m2["m2_choices"]
    row = (
        c.execute(
            sa.select(requests).where(
                requests.c.campaign_id == game.store.campaign_id,
                requests.c.id == choice,
            )
        )
        .mappings()
        .first()
    )
    if (
        answer.fields.get("status") not in ("-1", "1")
        or set(answer.fields) - {"status", "marker"}
        or row is None
        or row["action_id"] != action["id"]
        or row["kind"] != "tag_window"
        or row["actor_id"] != str(owner)
        or row["state"] != "answered"
        or action["data"].get("response_event") != event
        or action["data"].get("choices", {}).get("tag_window:" + str(owner))
        != answer.model_dump(mode="json")
        or action["data"].get("learned_hound_status")
    ):
        raise WorkflowError("Use the actual original Dog's owned Status response, once")
    direction: Literal[-1, 1] = -1 if answer.fields["status"] == "-1" else 1
    value_id = "learned-hound:" + value.id
    if any(x.id == value_id for x in hound_status_uses(state)):
        raise WorkflowError("This original lesson already has its actual Hound mark")
    use = HoundStatusUse(
        id=value_id,
        lesson=value.id,
        actor=value.actor,
        action=action["id"],
        roll_event=_keep_raw_roll(game, c, action),
        choice=choice,
        event=event,
        direction=direction,
        receipt_sha256=_keep_receipt(game, c, action),
        rank_order=state.order,
    )
    sheet = state.sheets[value.actor.entity]
    sheet.status_marked = True
    sheet.revision += 1
    action["data"]["modifiers"].append(dict(source="alpha_status", amount=direction))
    _replace(
        state, value.model_copy(update={"claimed_action": action["id"], "rolled_event": event})
    )
    put_hound_status(state, use)
    action["data"]["learned_hound_status"] = dict(
        id=use.id,
        lesson=value.id,
        event=event,
        roll_event=use.roll_event,
        choice=choice,
        amount=direction,
    )
    return True


def prove_hound_status(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> int | None:
    meta = action["data"].get("learned_hound_status")
    if meta is None:
        return None
    use = next((x for x in hound_status_uses(state) if x.id == meta.get("id")), None)
    if use is None:
        raise WorkflowError("Recover the actual source-owned learned Hound mark")
    row = (
        c.execute(
            sa.select(t.m2["m2_choices"]).where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.id == use.choice,
            )
        )
        .mappings()
        .first()
    )
    response = (
        c.execute(
            sa.select(t.m2["m2_responses"]).where(
                t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_responses"].c.choice_id == use.choice,
            )
        )
        .mappings()
        .first()
    )
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == use.event,
            )
        )
        .mappings()
        .first()
    )
    if event is None or response is None:
        raise WorkflowError("Save the actual original Status response before canonical readback")
    from girlframe.engine.m3_intracadre_marriage import is_dog
    from girlframe.services.m3_handler_advancements import _history

    born = _history(c, game, use.event)
    original_sheet = born.sheets.get(use.actor.entity)
    learned = original_sheet.girl_runtime if original_sheet else None
    value = (
        next((x for x in learned.learned_plays if x.id == use.lesson), None) if learned else None
    )
    if (
        use.action != action["id"]
        or use.actor.entity != str(action["actor_id"])
        or action["data"].get("character_ids", {}).get(use.actor.entity) != use.actor.incarnation
        or use.id != "learned-hound:" + use.lesson
        or value is None
        or value.actor != use.actor
        or value.rule_id != HOUND
        or value.claimed_action != action["id"]
        or value.rolled_event != use.event
        or use.roll_event != _keep_raw_roll(game, c, action)
        or use.receipt_sha256 != _keep_receipt(game, c, action)
        or meta
        != dict(
            id=use.id,
            lesson=use.lesson,
            event=use.event,
            roll_event=use.roll_event,
            choice=use.choice,
            amount=use.direction,
        )
        or row is None
        or row["action_id"] != action["id"]
        or row["kind"] != "tag_window"
        or row["actor_id"] != use.actor.entity
        or row["state"] != "answered"
        or [x for x in action["data"]["modifiers"] if x.get("source") == "alpha_status"]
        != [dict(source="alpha_status", amount=use.direction)]
    ):
        raise WorkflowError("Prove this exact original Hound lesson, Status choice and modifier")
    _prove(game, c, born, value)
    original = next((x for x in hound_status_uses(born) if x.id == use.id), None)
    before_raw = c.scalar(
        sa.select(t.m2["m2_state_history"].c.body_json).where(
            t.m2["m2_state_history"].c.campaign_id == game.store.campaign_id,
            t.m2["m2_state_history"].c.revision == born.revision - 1,
        )
    )
    before = GameState.model_validate_json(before_raw) if before_raw else None
    answer = ChoiceAnswer.model_validate_json(response["answer_json"])
    author = int(use.actor.entity)
    if action["data"].get("princess_child"):
        from girlframe.services.m3_princess_sex import prove_response_author

        actual_author = prove_response_author(game, c, born, action, dict(row), use.event)
        if actual_author is None:
            raise WorkflowError("Prove the actual directed Status response author")
        author = actual_author
    if (
        original is None
        or original.clear_reason is not None
        or original.cleared_event is not None
        or original != use.model_copy(update=dict(clear_reason=None, cleared_event=None))
        or before is None
        or use.actor.entity not in before.sheets
        or before.sheets[use.actor.entity].character_id != use.actor.incarnation
        or before.sheets[use.actor.entity].status_marked
        or not is_dog(before, int(use.actor.entity))
        or before.order != use.rank_order
        or not born.sheets[use.actor.entity].status_marked
        or event["kind"] not in ("m2.choice_resolved", "m3.choice_resolved")
        or event["actor_id"] != str(author)
        or response["actor_id"] != str(author)
        or response["event_id"] != use.event
        or json.loads(event["payload_json"]).get("action_id") != action["id"]
        or json.loads(event["payload_json"]).get("choice_id") != use.choice
        or answer.fields.get("status") != str(use.direction)
    ):
        raise WorkflowError(
            "Recover the actual unmarked Dog source and canonical human Status choice"
        )
    if use.clear_reason is not None:
        if use.cleared_event is None:
            raise WorkflowError("Save the actual typed Status clear before canonical readback")
        cleared = _history(c, game, use.cleared_event)
        if use not in hound_status_uses(cleared):
            raise WorkflowError("Preserve the real actual mark-clearing source")
    elif use.cleared_event is not None:
        raise WorkflowError("A cleared Hound mark needs its actual clearing cause")
    return use.direction


def risk_lesson_available(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> LearnedPlayUse | None:
    from girlframe.services.m3_mockingbird import actor

    ref = actor(action)
    if ref is None or ref.kind != "pilot":
        return None
    sheet = state.sheets.get(ref.entity)
    if sheet is None or sheet.character_id != ref.incarnation:
        return None
    runtime = sheet.girl_runtime or GirlRuntime()
    native = sheet.model_copy(
        update={"girl_runtime": runtime.model_copy(update={"learned_plays": ()})}
    )
    if has_rule(native, RISK, "MOCKINGBIRD") or ref.entity != str(action["actor_id"]):
        return None
    bound = action["data"].get("risk_factor", {}).get("learned_source")
    for value in runtime.learned_plays:
        if (
            value.rule_id != RISK
            or value.actor != ref
            or value.rolled_event is not None
            or value.claimed_action is not None
            or (bound is not None and value.id != bound)
        ):
            continue
        _prove(game, c, state, value)
        _keep_raw_roll(game, c, action)
        return value
    return None


def validate_pending_risk_lesson(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    answer: ChoiceAnswer,
    event: str,
) -> RiskLessonUse:
    meta = action["data"]["risk_factor"]
    value = risk_lesson_available(game, c, state, action)
    actual_request = (
        c.execute(
            sa.select(t.m2["m2_choices"]).where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.id == request["id"],
            )
        )
        .mappings()
        .first()
    )
    if (
        value is None
        or value.id != meta.get("learned_source")
        or meta.get("state") != "pending"
        or request["kind"] != "mockingbird_risk"
        or request["action_id"] != action["id"]
        or request["actor_id"] != value.actor.entity
        or request["state"] != "pending"
        or actual_request is None
        or actual_request["state"] != "answered"
        or actual_request["revision"] != request["revision"] + 1
        or any(actual_request[key] != request[key] for key in ("action_id", "actor_id", "kind"))
        or answer.number not in (8, 9, 10)
        or action["data"].get("response_event") != event
        or action["data"].get("choices", {}).get("mockingbird_risk:" + value.actor.entity)
        != answer.model_dump(mode="json")
    ):
        raise WorkflowError("Pay only this actual original lesson's owned Risk choice")
    from girlframe.engine.m3_actors import resolve
    from girlframe.services.m3_actors import profiles

    original = resolve(state, value.actor, profiles(c, game.store.campaign_id))
    use = RiskLessonUse(
        id="learned-risk:" + value.id,
        lesson=value.id,
        actor=value.actor,
        action=action["id"],
        offer_event=meta["learned_offer_event"],
        roll_event=_keep_raw_roll(game, c, action),
        receipt_sha256=_keep_receipt(game, c, action),
        choice=request["id"],
        event=event,
        frame=original.frame_instance,
        before=meta["before"],
        after=answer.number,
        asset=answer.fields.get("asset", ""),
    )
    if any(x.id == use.id for x in risk_lesson_uses(state)):
        raise WorkflowError("This actual source lesson already has its single paid Risk use")
    _replace(
        state, value.model_copy(update={"claimed_action": action["id"], "rolled_event": event})
    )
    put_risk_lesson(state, use)
    return use


def finalize_risk_lesson(state: GameState, use: RiskLessonUse, payment: Any) -> RiskLessonUse:
    if (
        payment.learned_source != use.id
        or payment.action != use.action
        or payment.actor != use.actor
        or payment.event != use.event
        or payment.total_before != use.before
        or payment.total_after != use.after
    ):
        raise WorkflowError("Bind the actual paid Void alteration to its original lesson")
    final = use.model_copy(update=dict(asset=payment.asset, family=payment.family))
    put_risk_lesson(state, final)
    return final


def bind_risk_ward_work(state: GameState, use_id: str, work: str) -> None:
    use = next((x for x in risk_lesson_uses(state) if x.id == use_id), None)
    if use is None or not use.asset or use.family is None or not work or work in use.work:
        raise WorkflowError("Bind only this actual paid use's new real Void consequence")
    put_risk_lesson(state, use.model_copy(update=dict(work=use.work + (work,))))


def prove_risk_lesson(
    game: GameService, c: Connection, state: GameState, action: dict[str, Any]
) -> RiskLessonUse | None:
    meta = action["data"].get("risk_factor", {})
    if meta.get("learned_source") is None or meta.get("state") != "paid":
        return None
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_mockingbird import RiskPayment
    from girlframe.services.m3_actor_history import snapshot_profiles
    from girlframe.services.m3_handler_advancements import _history

    payment = RiskPayment.model_validate_json(json.dumps(meta["payment"]))
    use = next((x for x in risk_lesson_uses(state) if x.id == payment.learned_source), None)
    if use is None:
        raise WorkflowError("Recover this genuine paid Risk lesson")
    born = _history(c, game, use.event)
    offer = _history(c, game, use.offer_event)
    original = resolve(
        offer,
        use.actor,
        snapshot_profiles(c, game.store.campaign_id, offer),
        require_current_profile=False,
    )
    sheet = born.sheets.get(use.actor.entity)
    runtime = sheet.girl_runtime if sheet else None
    value = (
        next((x for x in runtime.learned_plays if x.id == use.lesson), None) if runtime else None
    )
    prior_sheet = offer.sheets.get(use.actor.entity)
    prior_runtime = prior_sheet.girl_runtime if prior_sheet else None
    prior = (
        next((x for x in prior_runtime.learned_plays if x.id == use.lesson), None)
        if prior_runtime
        else None
    )
    request = (
        c.execute(
            sa.select(t.m2["m2_choices"]).where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.id == use.choice,
            )
        )
        .mappings()
        .first()
    )
    response = (
        c.execute(
            sa.select(t.m2["m2_responses"]).where(
                t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_responses"].c.choice_id == use.choice,
            )
        )
        .mappings()
        .first()
    )
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == use.event,
            )
        )
        .mappings()
        .first()
    )
    source_work = tuple(x["id"] for x in meta["followups"])
    if (
        use not in risk_lesson_uses(born)
        or value is None
        or prior is None
        or use.id != "learned-risk:" + use.lesson
        or use.lesson != meta["learned_source"]
        or value.actor != use.actor
        or value.rule_id != RISK
        or prior != value.model_copy(update=dict(claimed_action=None, rolled_event=None))
        or value.claimed_action != action["id"]
        or value.rolled_event != use.event
        or use.actor.entity != str(action["actor_id"])
        or use.action != action["id"]
        or use.frame != original.frame_instance
        or use.offer_event != meta.get("learned_offer_event")
        or use.roll_event != _keep_raw_roll(game, c, action)
        or use.receipt_sha256 != _keep_receipt(game, c, action)
        or use.work != source_work
        or use.choice != meta.get("choice")
        or payment.actor != use.actor
        or payment.action != use.action
        or payment.event != use.event
        or payment.asset != use.asset
        or payment.family != use.family
        or payment.total_before != use.before
        or payment.total_after != use.after
        or request is None
        or response is None
        or event is None
        or request["action_id"] != use.action
        or request["actor_id"] != use.actor.entity
        or request["kind"] != "mockingbird_risk"
        or response["event_id"] != use.event
        or event["kind"] not in ("m2.choice_resolved", "m3.choice_resolved")
        or json.loads(event["payload_json"]).get("action_id") != use.action
        or json.loads(event["payload_json"]).get("choice_id") != use.choice
    ):
        raise WorkflowError("Preserve this exact original lesson, paid Void and held source work")
    _prove(game, c, offer, prior)
    answer = ChoiceAnswer.model_validate_json(response["answer_json"])
    author = int(use.actor.entity)
    if action["data"].get("princess_child"):
        from girlframe.services.m3_princess_sex import prove_response_author

        directed_author = prove_response_author(game, c, born, action, dict(request), use.event)
        if directed_author is None:
            raise WorkflowError("Prove the actual original paid Risk response author")
        author = directed_author
    if (
        response["actor_id"] != str(author)
        or event["actor_id"] != str(author)
        or answer.number != use.after
        or answer.text != payment.account
        or dict(
            kind="mockingbird_risk_paid",
            action=use.action,
            event=use.event,
            actor=use.actor.model_dump_json(),
            body=payment.model_dump_json(),
        )
        not in born.facts
        or [x for x in action["data"]["modifiers"] if x.get("source") == RISK]
        != [dict(source=RISK, amount=use.after - use.before, actor=int(use.actor.entity))]
    ):
        raise WorkflowError("Prove the real original human's paid Risk shift and modifier")
    return use


def prove_risk_ward(
    game: GameService, c: Connection, state: GameState, threshold: Any
) -> RiskLessonUse | DefensiveRiskUse | None:
    defensive = [x for x in defensive_risk_uses(state) if x.threshold == threshold.id]
    if defensive:
        if len(defensive) != 1:
            raise WorkflowError("Preserve this source's single actual defensive use")
        return prove_defensive_risk(game, c, state, threshold, defensive[0])
    candidates = [
        x
        for x in risk_lesson_uses(state)
        if (
            x.actor == threshold.actor
            and x.event == threshold.source_event
            and x.action == threshold.source_action
            and x.frame == threshold.frame_instance
            and threshold.source_works
            and set(threshold.source_works) <= set(x.work)
        )
    ]
    if not candidates:
        return None
    if len(candidates) != 1:
        raise WorkflowError("Preserve one actual paid lesson for this exact Void cause")
    use = prove_risk_lesson(game, c, state, game.action(c, candidates[0].action))
    if use != candidates[0] or any(
        risk_ward(state, threshold.actor, threshold.source_event, threshold.source_action, work)
        != use
        for work in threshold.source_works
    ):
        raise WorkflowError("Prove this threshold's actual paid source ward")
    return use


def _defensive_source_rows(
    game: GameService,
    c: Connection,
    value: Any,
    *,
    pending: bool = False,
) -> tuple[dict[str, Any], ...]:
    from girlframe.services.m3_void import source

    if not value.source_works:
        raise WorkflowError("Use a genuine original Void consequence")
    rows = []
    for identity in value.source_works:
        current, body, actor = source(game, c, identity)
        table = t.m3["m3_required_work"]
        first = (
            c.execute(
                sa.select(table).where(
                    table.c.campaign_id == game.store.campaign_id,
                    table.c.id == identity,
                    table.c.revision == 1,
                )
            )
            .mappings()
            .one()
        )
        latest = json.loads(current["body_json"])
        if (
            actor != value.actor
            or body.get("threshold", value.id) != value.id
            or (pending and current["state"] != "pending")
            or (
                pending
                and any(
                    latest.get(key)
                    for key in (
                        "damage_asset",
                        "approach",
                        "rebirth_choice",
                        "guardian",
                    )
                )
            )
        ):
            raise WorkflowError("Keep this exact unadvanced original Void source and owner")
        rows.append(dict(first))
    if not any(
        x["event_id"] == value.source_event
        and json.loads(x["body_json"]).get("source_action") == value.source_action
        for x in rows
    ):
        raise WorkflowError("Preserve the original threshold's actual canonical cause")
    return tuple(rows)


def defensive_risk_lessons(
    game: GameService,
    c: Connection,
    state: GameState,
    threshold: Any,
) -> tuple[dict[str, str], ...]:
    from girlframe.engine.m3_actors import resolve
    from girlframe.engine.m3_void import defensive_risk_fresh
    from girlframe.services.m3_actors import profiles
    from girlframe.services.m3_mockingbird import released

    if (
        not released(game)
        or not defensive_risk_fresh(threshold)
        or any(x.threshold == threshold.id for x in defensive_risk_uses(state))
        or prove_risk_ward(game, c, state, threshold) is not None
    ):
        return ()
    actor = threshold.actor
    sheet = state.sheets.get(actor.entity)
    if (
        sheet is None
        or sheet.character_id != actor.incarnation
        or has_rule(sheet, RISK, "MOCKINGBIRD")
    ):
        return ()
    actual = resolve(state, actor, profiles(c, game.store.campaign_id))
    if actual.frame_instance != threshold.frame_instance:
        return ()
    _defensive_source_rows(game, c, threshold, pending=True)
    result = []
    for value in sheet.girl_runtime.learned_plays if sheet.girl_runtime else ():
        if (
            value.actor == actor
            and value.rule_id == RISK
            and value.claimed_action is None
            and value.rolled_event is None
        ):
            _prove(game, c, state, value)
            result.append(
                dict(id=value.id, label="Use one Risk Factor lesson for this Void source")
            )
    return tuple(result)


def activate_defensive_risk(
    game: GameService,
    c: Connection,
    state: GameState,
    threshold: Any,
    lesson: str,
    event: str,
    account: str,
) -> DefensiveRiskUse:
    if lesson not in {x["id"] for x in defensive_risk_lessons(game, c, state, threshold)}:
        raise WorkflowError("Choose your actual unused lesson for this untouched Void source")
    sheet = state.sheets[threshold.actor.entity]
    value = (
        next((x for x in sheet.girl_runtime.learned_plays if x.id == lesson), None)
        if sheet.girl_runtime
        else None
    )
    if value is None:
        raise WorkflowError("Recover the exact actual unspent defensive lesson")
    use = DefensiveRiskUse(
        id="learned-risk-defense:" + lesson,
        lesson=lesson,
        actor=threshold.actor,
        frame=threshold.frame_instance,
        threshold=threshold.id,
        cause_event=threshold.source_event,
        cause_action=threshold.source_action,
        cause_works=threshold.source_works,
        source_rows_sha256=_digest(_defensive_source_rows(game, c, threshold, pending=True)),
        before_revision=state.revision,
        before_threshold_sha256=_digest(threshold.model_dump(mode="json")),
        event=event,
        account=account,
    )
    _replace(state, value.model_copy(update=dict(rolled_event=event)))
    put_defensive_risk(state, use)
    return use


def prove_defensive_risk(
    game: GameService,
    c: Connection,
    state: GameState,
    threshold: Any,
    use: DefensiveRiskUse,
) -> DefensiveRiskUse:
    from girlframe.engine import m3_void as void
    from girlframe.services.m3_actor_history import snapshot_profiles
    from girlframe.services.m3_handler_advancements import _history

    born = _history(c, game, use.event)
    history = t.m2["m2_state_history"]
    prior_raw = c.scalar(
        sa.select(history.c.body_json).where(
            history.c.campaign_id == game.store.campaign_id,
            history.c.revision == use.before_revision,
        )
    )
    if prior_raw is None:
        raise WorkflowError("Recover the actual pre-activation Void source history")
    before = GameState.model_validate_json(prior_raw)
    prior_sheet, born_sheet = before.sheets.get(use.actor.entity), born.sheets.get(use.actor.entity)
    prior = (
        next((x for x in prior_sheet.girl_runtime.learned_plays if x.id == use.lesson), None)
        if prior_sheet and prior_sheet.girl_runtime
        else None
    )
    spent = (
        next((x for x in born_sheet.girl_runtime.learned_plays if x.id == use.lesson), None)
        if born_sheet and born_sheet.girl_runtime
        else None
    )
    event = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == use.event,
            )
        )
        .mappings()
        .first()
    )
    payload = json.loads(event["payload_json"]) if event else {}
    original = next((x for x in before.void_thresholds if x.id == use.threshold), None)
    sources = _defensive_source_rows(game, c, threshold)
    bindings = snapshot_profiles(c, game.store.campaign_id, before)
    for row in sources:
        if original is None or row["id"] not in original.source_works:
            body = json.loads(row["body_json"])
            before, original = void.start_threshold(
                before,
                bindings,
                use.actor,
                body["details"]["family"],
                row["event_id"],
                row["id"],
                source_action=body.get("source_action"),
            )
    birth_threshold = next((x for x in born.void_thresholds if x.id == use.threshold), None)
    if (
        use not in defensive_risk_uses(born)
        or use.id != "learned-risk-defense:" + use.lesson
        or threshold.actor != use.actor
        or threshold.frame_instance != use.frame
        or threshold.source_event != use.cause_event
        or threshold.source_action != use.cause_action
        or threshold.source_works != use.cause_works
        or use.source_rows_sha256 != _digest(sources)
        or original is None
        or not void.defensive_risk_fresh(original)
        or _digest(original.model_dump(mode="json")) != use.before_threshold_sha256
        or prior is None
        or spent is None
        or prior.rule_id != RISK
        or prior.actor != use.actor
        or prior.claimed_action is not None
        or prior.rolled_event is not None
        or spent != prior.model_copy(update=dict(rolled_event=use.event))
        or event is None
        or event["actor_id"] != use.actor.entity
        or event["kind"] != "m3.void_response"
        or payload.get("operation") != "use_risk_lesson"
        or payload.get("threshold") != use.threshold
        or payload.get("defensive_risk_use") != use.id
        or payload.get("lesson") != use.lesson
        or payload.get("work_id") not in use.cause_works
        or birth_threshold is None
        or birth_threshold.response_event != use.event
    ):
        raise WorkflowError(
            "Prove the real original owner's single defensive activation and untouched cause"
        )
    _prove(game, c, before, prior)
    staged = before.model_copy(deep=True)
    put_defensive_risk(staged, use)
    expected = void.apply_defensive_risk(
        staged,
        bindings,
        use.threshold,
        use,
        use.event,
    )
    if void.threshold(expected, use.threshold) != birth_threshold:
        raise WorkflowError("Keep the actual defensive classification and original physical source")
    return use


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


def prepare_call_lessons(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    play: str,
) -> tuple[dict[str, str], ...]:
    if actor.kind != "pilot" or play != "dive_deep":
        return ()
    sheet = state.sheets.get(actor.entity)
    if sheet is None or sheet.character_id != actor.incarnation:
        return ()
    runtime = sheet.girl_runtime or GirlRuntime()
    native = sheet.model_copy(
        update={"girl_runtime": runtime.model_copy(update={"learned_plays": ()})}
    )
    if has_rule(native, CALL, "MOCKINGBIRD"):
        return ()
    result = []
    for value in runtime.learned_plays:
        if (
            value.rule_id == CALL
            and value.actor == actor
            and value.rolled_event is None
            and value.claimed_action is None
        ):
            _prove(game, c, state, value)
            result.append(dict(id=value.id, rule_id=CALL, label=lesson_label(CALL, play)))
    return tuple(result)


def reserve_call_lesson(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    event: str,
) -> bool:
    identity = action["data"]["prepared"].get("learned_call")
    if identity is None:
        return False
    actor = current_ref(state, int(action["actor_id"]))
    if (
        identity
        not in {
            x["id"] for x in prepare_call_lessons(game, c, state, actor, action["data"]["play"])
        }
        or action["data"].get("learned_call")
        or not event
    ):
        raise WorkflowError("Select one actual unused Call lesson for your genuine Dive")
    runtime = state.sheets[actor.entity].girl_runtime
    assert runtime is not None
    value = next(x for x in runtime.learned_plays if x.id == identity)
    _replace(state, value.model_copy(update=dict(claimed_action=action["id"])))
    action["data"]["learned_call"] = dict(id=identity, event=event)
    return True


def _call_reservation(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
) -> LearnedPlayUse:
    from girlframe.services.m3_handler_advancements import _history

    meta = action["data"]["learned_call"]
    born = _history(c, game, meta["event"])
    actor = current_ref(born, int(action["actor_id"]))
    initial = born.sheets[actor.entity].girl_runtime
    sheet = state.sheets.get(actor.entity)
    runtime = sheet.girl_runtime if sheet and sheet.character_id == actor.incarnation else None
    original = (
        next((x for x in initial.learned_plays if x.id == meta["id"]), None) if initial else None
    )
    value = (
        next((x for x in runtime.learned_plays if x.id == meta["id"]), None) if runtime else None
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
        or value.rule_id != CALL
        or action["data"]["play"] != "dive_deep"
        or action["data"]["prepared"].get("learned_call") != value.id
        or action["data"].get("dive", {}).get("actor") != actor.model_dump(mode="json")
        or event["kind"] not in ("m2.play_confirmed", "m3.play_confirmed")
        or json.loads(event["payload_json"]).get("action_id") != action["id"]
        or original != value.model_copy(update=dict(claimed_action=action["id"], rolled_event=None))
    ):
        raise WorkflowError("Prove this original learner's exact authorized Call reservation")
    _prove(game, c, born, original)
    _prove(game, c, state, value)
    return value


def pre_roll_call_lesson(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
) -> None:
    if not action["data"].get("learned_call"):
        return
    value = _call_reservation(game, c, state, action)
    if (
        value.actor != current_ref(state, int(action["actor_id"]))
        or value.claimed_action != action["id"]
        or value.rolled_event is not None
        or action["data"].get("receipt")
        or action["data"]["learned_call"].get("resolved_event")
    ):
        raise WorkflowError("Use your original unrolled Call lesson reservation")


def release_call_unrolled(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
) -> bool:
    if not action["data"].get("learned_call"):
        return False
    pre_roll_call_lesson(game, c, state, action)
    value = _call_reservation(game, c, state, action)
    _replace(state, value.model_copy(update=dict(claimed_action=None)))
    return True


def _call_use(state: GameState, action: dict[str, Any]) -> CallLessonUse | None:
    values = [x for x in call_lesson_uses(state) if x.action == action["id"]]
    if len(values) > 1:
        raise WorkflowError("A genuine Dive has one actual selected Call source use")
    return values[0] if values else None


def prove_call_lesson(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
) -> CallLessonUse | None:
    meta = action["data"].get("learned_call")
    if meta is None:
        return None
    value = _call_reservation(game, c, state, action)
    use = _call_use(state, action)
    if use is None:
        if (
            value.claimed_action != action["id"]
            or value.rolled_event is not None
            or meta.get("resolved_event")
        ):
            raise WorkflowError("Preserve the real unused Call reservation")
        _keep_raw_roll(game, c, action)
        return None
    from girlframe.services.m3_handler_advancements import _history

    born = _history(c, game, use.event)
    resolved_value = _call_reservation(game, c, born, action)
    audit = (
        c.execute(
            sa.select(t.events).where(
                t.events.c.campaign_id == game.store.campaign_id,
                t.events.c.id == use.event,
            )
        )
        .mappings()
        .first()
    )
    payload = json.loads(audit["payload_json"]) if audit else {}
    if (
        _call_use(born, action) != use
        or use.lesson != value.id
        or use.actor != value.actor
        or use.begin_event != meta["event"]
        or use.event != meta.get("resolved_event")
        or use.used != meta.get("used")
        or use.roll_event != _keep_raw_roll(game, c, action)
        or use.receipt_sha256 != _keep_receipt(game, c, action)
        or resolved_value.claimed_action != (action["id"] if use.used else None)
        or resolved_value.rolled_event != (use.event if use.used else None)
        or audit is None
        or audit["kind"]
        not in (
            "m2.choice_resolved",
            "m3.choice_resolved",
            "m3.dive_void_completed",
        )
        or payload.get("action_id") != action["id"]
    ):
        raise WorkflowError("Preserve the actual selected Call source and canonical receipt")
    if use.used:
        from girlframe.services.m3_dive import _groups, _handler_controller

        choice = (
            c.execute(
                sa.select(t.m2["m2_choices"]).where(
                    t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_choices"].c.id == use.choice,
                )
            )
            .mappings()
            .first()
        )
        response = (
            c.execute(
                sa.select(t.m2["m2_responses"]).where(
                    t.m2["m2_responses"].c.campaign_id == game.store.campaign_id,
                    t.m2["m2_responses"].c.choice_id == use.choice,
                )
            )
            .mappings()
            .first()
        )
        selected = action["data"]["dive"]["steps"][use.step] if use.step is not None else {}
        group = _groups(action)[use.step] if use.step is not None else None
        chooser = (
            int(action["actor_id"])
            if group is not None and group.owner == "actor"
            else _handler_controller(action["data"]["dive"])
        )
        if (
            choice is None
            or response is None
            or use.option not in CALL_OPTIONS
            or choice["kind"] != "dive_select"
            or choice["action_id"] != action["id"]
            or json.loads(choice["body_json"]).get("step") != use.step
            or payload.get("choice_id") != use.choice
            or response["event_id"] != use.event
            or response["actor_id"] != choice["actor_id"]
            or audit["actor_id"] != choice["actor_id"]
            or ChoiceAnswer.model_validate_json(response["answer_json"]).options != (use.option,)
            or selected.get("option") != use.option
            or selected.get("source_choice") != use.choice
            or selected.get("chooser") != int(choice["actor_id"])
            or int(choice["actor_id"]) != chooser
            or any(x["option"] in CALL_OPTIONS for x in action["data"]["dive"]["steps"][: use.step])
        ):
            raise WorkflowError("Prove the actual printed chooser's first real Call option")
    elif (
        use.choice is not None
        or use.option is not None
        or use.step is not None
        or any(x["option"] in CALL_OPTIONS for x in action["data"]["dive"]["steps"])
    ):
        raise WorkflowError("An unused Call lesson has no performed extra option")
    return use


def call_lesson_entitled(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
) -> bool:
    if not action["data"].get("learned_call"):
        return False
    value = _call_reservation(game, c, state, action)
    use = prove_call_lesson(game, c, state, action)
    return bool(use.used if use is not None else value.claimed_action == action["id"])


def consume_call_selection(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    request: dict[str, Any],
    option: str,
    event: str,
) -> None:
    if not action["data"].get("learned_call") or option not in CALL_OPTIONS:
        return
    value = _call_reservation(game, c, state, action)
    previous = _call_use(state, action)
    if previous is not None:
        if not previous.used or prove_call_lesson(game, c, state, action) != previous:
            raise WorkflowError("Keep this Dive's true held Call entitlement")
        return
    step = json.loads(request["body_json"])["step"]
    selected = action["data"]["dive"]["steps"][step]
    row = (
        c.execute(
            sa.select(t.m2["m2_choices"]).where(
                t.m2["m2_choices"].c.campaign_id == game.store.campaign_id,
                t.m2["m2_choices"].c.id == request["id"],
            )
        )
        .mappings()
        .first()
    )
    if (
        value.claimed_action != action["id"]
        or value.rolled_event is not None
        or request["kind"] != "dive_select"
        or row is None
        or row["state"] != "answered"
        or row["revision"] != request["revision"] + 1
        or row["action_id"] != action["id"]
        or row["actor_id"] != request["actor_id"]
        or selected["option"] != option
        or selected["source_choice"] != request["id"]
        or action["data"].get("response_event") != event
    ):
        raise WorkflowError(
            "Consume only the actual authorized source's first selected Call option"
        )
    use = CallLessonUse(
        action=action["id"],
        lesson=value.id,
        actor=value.actor,
        begin_event=action["data"]["learned_call"]["event"],
        roll_event=_keep_raw_roll(game, c, action),
        receipt_sha256=_keep_receipt(game, c, action),
        event=event,
        used=True,
        choice=request["id"],
        option=option,
        step=step,
    )
    _replace(state, value.model_copy(update=dict(rolled_event=event)))
    state.facts.append(dict(kind="learned_call_use", id=action["id"], body=use.model_dump_json()))
    action["data"]["learned_call"].update(resolved_event=event, used=True)


def finish_call_unused(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    event: str,
) -> None:
    if not action["data"].get("learned_call") or _call_use(state, action) is not None:
        return
    value = _call_reservation(game, c, state, action)
    if (
        value.claimed_action != action["id"]
        or value.rolled_event is not None
        or any(x["option"] in CALL_OPTIONS for x in action["data"]["dive"]["steps"])
    ):
        raise WorkflowError("Release only this completed Dive's genuinely unused Call lesson")
    use = CallLessonUse(
        action=action["id"],
        lesson=value.id,
        actor=value.actor,
        begin_event=action["data"]["learned_call"]["event"],
        roll_event=_keep_raw_roll(game, c, action),
        receipt_sha256=_keep_receipt(game, c, action),
        event=event,
        used=False,
    )
    _replace(state, value.model_copy(update=dict(claimed_action=None)))
    state.facts.append(dict(kind="learned_call_use", id=action["id"], body=use.model_dump_json()))
    action["data"]["learned_call"].update(resolved_event=event, used=False)


def prepare_daily_lessons(
    game: GameService,
    c: Connection,
    state: GameState,
    actor: ActorRef,
    play: str,
) -> dict[str, tuple[dict[str, str], ...]]:
    from girlframe.services.m3_access import load_registry

    result: dict[str, tuple[dict[str, str], ...]] = dict(show_dog=(), psyche=())
    sheet = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if sheet is None or sheet.character_id != actor.incarnation:
        return result
    runtime = sheet.girl_runtime or GirlRuntime()
    native = sheet.model_copy(
        update={"girl_runtime": runtime.model_copy(update={"learned_plays": ()})}
    )
    for rule, (key, book) in DAILY.items():
        try:
            load_registry().require_available(rule)
        except ValueError:
            continue
        if (rule == SHOW_DOG and play != "go_off_duty") or has_rule(native, rule, book):
            continue
        candidates = []
        for value in runtime.learned_plays:
            if (
                value.rule_id == rule
                and value.actor == actor
                and value.claimed_action is None
                and value.rolled_event is None
            ):
                _prove(game, c, state, value)
                candidates.append(dict(id=value.id, rule_id=rule, label=lesson_label(rule, play)))
        result["show_dog" if key == "learned_show_dog" else "psyche"] = tuple(candidates)
    return result


def _daily_mode(
    prepared: dict[str, Any], rule: str
) -> Literal["mark", "off_duty", "mark_off_duty"]:
    off_duty = prepared["play"] in OFF_DUTY
    marking = bool(prepared.get("disposable_heat") and prepared.get("identity"))
    if rule == SHOW_DOG and prepared["play"] == "go_off_duty":
        return "off_duty"
    if rule == PSYCHE:
        if off_duty and marking:
            return "mark_off_duty"
        if off_duty:
            return "off_duty"
        if marking:
            return "mark"
    raise WorkflowError("This actual source must trigger the selected lesson's printed effect")


def reserve_daily_lessons(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    event: str,
) -> bool:
    prepared = action["data"]["prepared"]
    actor = current_ref(state, int(action["actor_id"]))
    choices = prepare_daily_lessons(game, c, state, actor, prepared["play"])
    changed = False
    for rule, (key, _) in DAILY.items():
        identity = prepared.get(key)
        if identity is None:
            continue
        candidates = choices["show_dog" if rule == SHOW_DOG else "psyche"]
        if identity not in {x["id"] for x in candidates} or action["data"].get(key) or not event:
            raise WorkflowError(
                "Explicitly select your actual unused lesson for this original source"
            )
        mode = _daily_mode(prepared, rule)
        runtime = state.sheets[actor.entity].girl_runtime
        assert runtime is not None
        value = next(x for x in runtime.learned_plays if x.id == identity)
        _replace(state, value.model_copy(update=dict(claimed_action=action["id"])))
        action["data"][key] = dict(id=identity, event=event, mode=mode)
        changed = True
    return changed


def _daily_reservation(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    rule: str,
) -> LearnedPlayUse:
    from girlframe.services.m3_handler_advancements import _history

    if rule not in DAILY:
        raise WorkflowError("Use one of the two actual supported daily lesson sources")
    key, _ = DAILY[rule]
    meta = action["data"][key]
    born = _history(c, game, meta["event"])
    actor = current_ref(born, int(action["actor_id"]))
    initial = born.sheets[actor.entity].girl_runtime
    sheet = state.sheets.get(actor.entity)
    runtime = sheet.girl_runtime if sheet and sheet.character_id == actor.incarnation else None
    original = (
        next((x for x in initial.learned_plays if x.id == meta["id"]), None) if initial else None
    )
    value = (
        next((x for x in runtime.learned_plays if x.id == meta["id"]), None) if runtime else None
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
        or value.rule_id != rule
        or action["data"]["prepared"].get(key) != value.id
        or meta.get("mode") != _daily_mode(action["data"]["prepared"], rule)
        or event["kind"] not in ("m2.play_confirmed", "m3.play_confirmed")
        or json.loads(event["payload_json"]).get("action_id") != action["id"]
        or original != value.model_copy(update=dict(claimed_action=action["id"], rolled_event=None))
    ):
        raise WorkflowError("Recover the original actor's exact source-specific lesson reservation")
    _prove(game, c, born, original)
    _prove(game, c, state, value)
    return value


def pre_roll_daily_lessons(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
) -> None:
    for rule, (key, _) in DAILY.items():
        if action["data"].get(key) is None:
            continue
        value = _daily_reservation(game, c, state, action, rule)
        if (
            value.actor != current_ref(state, int(action["actor_id"]))
            or value.claimed_action != action["id"]
            or value.rolled_event is not None
            or action["data"].get("receipt")
            or action["data"][key].get("resolved_event")
        ):
            raise WorkflowError("Use only this current original source's unrolled lesson")


def release_daily_unrolled(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
) -> bool:
    if not any(action["data"].get(key) for key, _ in DAILY.values()):
        return False
    pre_roll_daily_lessons(game, c, state, action)
    for rule, (key, _) in DAILY.items():
        if action["data"].get(key):
            value = _daily_reservation(game, c, state, action, rule)
            _replace(state, value.model_copy(update=dict(claimed_action=None)))
    return True


def consume_daily_lessons(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    roll_event: str,
) -> None:
    for rule, (key, _) in DAILY.items():
        if not action["data"].get(key):
            continue
        value = _daily_reservation(game, c, state, action, rule)
        if (
            value.claimed_action != action["id"]
            or value.rolled_event is not None
            or any(x.action == action["id"] and x.rule_id == rule for x in daily_lesson_uses(state))
        ):
            raise WorkflowError(
                "Consume each actual source lesson once at its real committed receipt"
            )
        meta = action["data"][key]
        use = DailyLessonUse(
            action=action["id"],
            lesson=value.id,
            rule_id=rule,
            actor=value.actor,
            mode=meta["mode"],
            begin_event=meta["event"],
            event=roll_event,
            receipt_sha256=_keep_receipt(game, c, action),
        )
        _replace(state, value.model_copy(update=dict(rolled_event=roll_event)))
        state.facts.append(
            dict(kind="learned_daily_use", id=action["id"] + ":" + rule, body=use.model_dump_json())
        )
        meta["resolved_event"] = roll_event


def prove_daily_lesson(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
    rule: str,
) -> DailyLessonUse | None:
    if rule not in DAILY:
        raise WorkflowError("Use one of the two actual supported daily lesson sources")
    key, _ = DAILY[rule]
    if not action["data"].get(key):
        return None
    values = [x for x in daily_lesson_uses(state) if x.action == action["id"] and x.rule_id == rule]
    if len(values) != 1:
        raise WorkflowError("Recover the genuine committed source lesson and receipt")
    use = values[0]
    from girlframe.services.m3_handler_advancements import _history

    born = _history(c, game, use.event)
    value = _daily_reservation(game, c, born, action, rule)
    meta = action["data"][key]
    if (
        use not in daily_lesson_uses(born)
        or use.actor != value.actor
        or use.lesson != value.id
        or use.mode != meta["mode"]
        or use.begin_event != meta["event"]
        or use.event != meta.get("resolved_event")
        or use.event != _keep_raw_roll(game, c, action)
        or use.receipt_sha256 != _keep_receipt(game, c, action)
        or value.claimed_action != action["id"]
        or value.rolled_event != use.event
    ):
        raise WorkflowError("Prove this exact original source, lesson and canonical receipt")
    if use.mode in ("mark", "mark_off_duty"):
        from girlframe.engine.m3_disposable_psyche import disposals

        disposal = next(
            (x for x in disposals(born) if x.id == action["id"] and x.actor == use.actor), None
        )
        if disposal is None or disposal.receipt != action["data"]["receipt"]["id"]:
            raise WorkflowError("Preserve the actual owned Identity disposal and Heat cost")
        if disposal.event != use.event:
            from girlframe.services.m3_disposable_psyche import prove_feedback_disposal

            if disposal.commit_event is None or disposal.roll_event != use.event:
                raise WorkflowError("Preserve the genuine pre-RNG disposal and later actual roll")
            prove_feedback_disposal(game, c, born, disposal, action)
    return use


def prepare_psyche_permit(
    game: GameService,
    c: Connection,
    state: GameState,
    owner: int,
    prepared: Any,
) -> PsychePermit | None:
    identity = prepared.learned_psyche
    if identity is None:
        return None
    actor = current_ref(state, owner)
    sheet = state.sheets[actor.entity]
    value = (
        next((x for x in sheet.girl_runtime.learned_plays if x.id == identity), None)
        if sheet.girl_runtime
        else None
    )
    if (
        value is None
        or value.rule_id != PSYCHE
        or value.actor != actor
        or value.rolled_event is not None
    ):
        raise WorkflowError("Use your actual unspent original Psyche lesson for this mark")
    _prove(game, c, state, value)
    mode = _daily_mode(prepared.model_dump(mode="json"), PSYCHE)
    if mode == "off_duty":
        raise WorkflowError(
            "A real mark/removal requires its explicit disposal amount and Identity"
        )
    if value.claimed_action is not None:
        action = game.action(c, value.claimed_action)
        if action["data"]["prepared"] != prepared.model_dump(mode="json"):
            raise WorkflowError("Keep the exact original claimed source for this Identity mark")
        _daily_reservation(game, c, state, action, PSYCHE)
    return PsychePermit(lesson=value, mode=mode)


def off_duty_psyche_permit(
    game: GameService,
    c: Connection,
    state: GameState,
    action: dict[str, Any],
) -> PsychePermit | None:
    use = prove_daily_lesson(game, c, state, action, PSYCHE)
    if use is None:
        return None
    if use.mode not in ("off_duty", "mark_off_duty"):
        return None
    value = _daily_reservation(game, c, state, action, PSYCHE)
    return PsychePermit(lesson=value, mode=use.mode)
