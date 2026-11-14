"""Native DoctorDoctor support, actual medical resources and source-bound care."""

from typing import Literal

from pydantic import Field

from girlframe.engine.m2 import GameState, PilotSheet
from girlframe.engine.m3_actor_bonds import change, clear_helpless, is_helpless
from girlframe.engine.m3_actor_state import ActorRef, Model
from girlframe.engine.m3_privileges import suspended
from girlframe.engine.m3_reactions import DoctorTrigger, mark_obsolescence
from girlframe.engine.m3_requisition_state import FrameRuleReceipt

BOOK = "DOCTORDOCTOR MK. II"
PREFIX = "frame.doctordoctor."
NANO = PREFIX + "nanobot-injection"
TRACK = PREFIX + "planned-obsolescence"
WINGS = PREFIX + "borrowed-wings"
RAGGED = PREFIX + "running-ragged"
NURSE = PREFIX + "the-cute-nurse"
SUPPORT = PREFIX + "here-for-support"
ANGEL = PREFIX + "metal-angel"
ADRENAL = PREFIX + "adrenal-injectors"
REQUISITIONS = (WINGS, RAGGED, NURSE, SUPPORT, ANGEL, ADRENAL)
TITLES = dict(
    zip(
        REQUISITIONS,
        (
            "Borrowed Wings",
            "Running Ragged",
            "The Cute Nurse",
            "Here for Support",
            "Metal Angel",
            "Adrenal Injectors",
        ),
        strict=True,
    )
)


def sheet(state: GameState, actor: ActorRef, *, source_frame: str | None = None) -> PilotSheet:
    value = state.sheets.get(actor.entity) if actor.kind == "pilot" else None
    if value is None or value.character_id != actor.incarnation:
        raise ValueError("Use the actual original native DoctorDoctor Pilot")
    frame = value.frame_runtime.id if value.frame_runtime else "initial:" + str(actor.incarnation)
    if value.frame != BOOK or (value.frame_scrapped and source_frame != frame):
        raise ValueError("Use the actual current unscrapped native DoctorDoctor Frame")
    return value


def frame_id(state: GameState, actor: ActorRef) -> str:
    value = sheet(state, actor)
    return value.frame_runtime.id if value.frame_runtime else "initial:" + str(actor.incarnation)


def held(state: GameState, actor: ActorRef, rule: str) -> FrameRuleReceipt | None:
    try:
        frame = frame_id(state, actor)
    except ValueError:
        return None
    return next(
        (
            x
            for x in state.requisitions
            if isinstance(x, FrameRuleReceipt)
            and x.actor == actor
            and x.frame_instance == frame
            and x.rule_id == rule
            and x.donor_frame == BOOK
            and not suspended(state, x.id)
        ),
        None,
    )


class Benefit(Model):
    choices: tuple[Literal["repair", "remove", "identity"], ...] = ()
    assets: tuple[str, ...] = ()
    identity: str | None = None
    effect: str | None = None


class Care(Model):
    id: str
    doctor: ActorRef
    frame: str
    patient: ActorRef
    source_event: str
    account: str = Field(min_length=1, max_length=1200)
    patient_controller: int
    judge: int
    angel: bool = False
    phase: Literal["proposal", "active", "recovery", "complete", "ended"] = "proposal"
    care_event: str | None = None
    period: str | None = None
    confirmations: tuple[int, ...] = ()
    completion_event: str | None = None


class Loan(Model):
    id: str
    doctor: ActorRef
    frame: str
    donor: ActorRef
    donor_frame: str
    asset: str
    source_asset_json: str
    source_event: str
    account: str
    phase: Literal["borrowed", "returned"] = "borrowed"
    return_event: str | None = None


class Protection(Model):
    id: str
    doctor: ActorRef
    frame: str
    protector: ActorRef
    controller: int
    source_action: str
    source_event: str
    phase: Literal["protecting", "refused", "ended"]
    bond_event: str | None = None
    end_event: str | None = None


class Procedure(Model):
    id: str
    kind: Literal["wings", "ragged"]
    doctor: ActorRef
    frame: str
    counterpart: ActorRef
    controller: int
    source_event: str
    account: str
    channel: int
    heat: int = 0
    asset: str | None = None
    replace: str | None = Field(default=None, exclude_if=lambda value: value is None)
    phase: Literal["proposal", "complete"] = "proposal"
    completion_event: str | None = None


def values[T: Model](state: GameState, kind: str, model: type[T]) -> tuple[T, ...]:
    return tuple(model.model_validate_json(x["body"]) for x in state.facts if x.get("kind") == kind)


def put(state: GameState, kind: str, value: Care | Loan | Protection | Procedure) -> None:
    identity = str(value.id)
    entry = dict(kind=kind, id=identity, body=value.model_dump_json())
    if any(x.get("kind") == kind and x.get("id") == identity for x in state.facts):
        state.facts = [
            entry if x.get("kind") == kind and x.get("id") == identity else x for x in state.facts
        ]
    else:
        state.facts.append(entry)


def mark(
    state: GameState, actor: ActorRef, trigger: DoctorTrigger, event: str, *, cause: str = ""
) -> bool:
    if any(
        x.get("kind") == "doctor_track_mark"
        and x.get("event") == event
        and x.get("actor") == actor.model_dump_json()
        and x.get("cause", "") == cause
        for x in state.facts
    ):
        raise ValueError("This actual Doctor trigger already marked its box")
    value = sheet(state, actor)
    result = mark_obsolescence(value, trigger)
    state.sheets[actor.entity] = result.sheet
    state.facts.append(
        dict(
            kind="doctor_track_mark",
            actor=actor.model_dump_json(),
            event=event,
            trigger=trigger,
            marked=str(result.sheet.obsolescence_marked),
            cause=cause,
        )
    )
    return result.replacement_required


def repair(state: GameState, target: ActorRef, assets: tuple[str, ...], count: int) -> None:
    value = state.sheets.get(target.entity) if target.kind == "pilot" else None
    if value is None or value.character_id != target.incarnation:
        raise ValueError("Use the actual original patient's sheet, never a controller proxy")
    damaged = {
        x.id for x in value.assets if x.damaged and (x.family == "girl" or not value.frame_scrapped)
    }
    if (
        len(assets) != min(count, len(damaged))
        or len(set(assets)) != len(assets)
        or not set(assets) <= damaged
    ):
        raise ValueError("Choose the actual number of existing damaged Assets to repair")
    for asset in value.assets:
        if asset.id in assets:
            asset.damaged = False
    value.revision += 1


def unmark(state: GameState, target: ActorRef, identity: str | None) -> None:
    value = state.sheets[target.entity]
    candidates = [x for x in value.identities if x.marked and x.id not in value.sedation_locked]
    if identity is None:
        return
    actual = next((x for x in candidates if x.id == identity), None)
    if actual is None:
        raise ValueError("Choose one actual marked Identity outside active source locks")
    actual.marked = False
    value.revision += 1


def nurse(state: GameState, actor: ActorRef, patient: ActorRef, event: str) -> GameState:
    if held(state, actor, NURSE) is None:
        return state
    if any(x.get("kind") == "doctor_nurse_bond" and x.get("care") == event for x in state.facts):
        return state
    state = change(state, actor, patient, 1, event)
    state.facts.append(
        dict(
            kind="doctor_nurse_bond",
            care=event,
            doctor=actor.model_dump_json(),
            patient=patient.model_dump_json(),
        )
    )
    return state


def adrenal(state: GameState, actor: ActorRef, event: str) -> GameState:
    if held(state, actor, ADRENAL) is None or not is_helpless(state, actor):
        raise ValueError("Use your actual Adrenal Injectors while actually Helpless")
    mark(state, actor, "adrenal", event)
    return clear_helpless(state, actor, event)


def saving_care(state: GameState, patient: ActorRef) -> Care | None:
    for care in values(state, "doctor_care", Care):
        if care.patient != patient or not care.angel or care.phase not in ("active", "recovery"):
            continue
        try:
            if frame_id(state, care.doctor) == care.frame and held(state, care.doctor, ANGEL):
                return care
        except ValueError:
            pass
    return None


def prevent_death(original: GameState, patient: ActorRef, event: str) -> tuple[GameState, bool]:
    """Called before any archive, cast removal or other death-specific fallout."""
    care = saving_care(original, patient)
    injectors = held(original, patient, ADRENAL)
    if care is None and injectors is None:
        return original, False
    state = GameState.model_validate_json(original.model_dump_json())
    if care is None:
        mark(state, patient, "adrenal", event)
    state.facts.append(
        dict(
            kind="doctor_prevented_death",
            patient=patient.model_dump_json(),
            care=care.id if care else "",
            event=event,
            source="metal_angel" if care else "adrenal",
        )
    )
    return state, True


def require_harm_allowed(
    state: GameState, patient: ActorRef, opponent: ActorRef | None
) -> Protection | None:
    for protection in values(state, "doctor_protection", Protection):
        if protection.doctor != patient or protection.phase != "protecting":
            continue
        try:
            if frame_id(state, patient) != protection.frame:
                continue
        except ValueError:
            continue
        if opponent != protection.protector:
            raise ValueError(
                "The actual protector must stop protecting before someone else can hurt Doctor"
            )
        return protection
    return None
